"""Cloudflare Access identity (DECISIONS.md #10).

The security boundary is the `Cf-Access-Jwt-Assertion` JWT that Access attaches
to every request it lets through: RS256-signed by the team's keys, `aud` bound
to this application's AUD tag. The bare `Cf-Access-Authenticated-User-Email`
header is never read — it is trivially forgeable by anything that can reach
the origin without going through Access.

Auth is off only when both ACCESS_TEAM_DOMAIN and ACCESS_AUD are unset (local
dev); setting exactly one is a misconfiguration and refuses to start.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Header, HTTPException

from .config import settings

log = logging.getLogger(__name__)

CERTS_PATH = "/cdn-cgi/access/certs"
# The TTL bounds how long a rotated-out key stays trusted; the refetch floor
# bounds how often an unknown `kid` (forged or freshly rotated in) can make us
# hit the certs endpoint.
JWKS_TTL_SECONDS = 15 * 60
JWKS_MIN_REFRESH_SECONDS = 60

DEV_EMAIL = "dev@localhost"


@dataclass(frozen=True)
class AccessUser:
    email: str


# Everything a JWKS fetch can raise: transport, non-2xx, non-JSON body, body
# without "keys", unparseable key material.
FETCH_ERRORS = (httpx.HTTPError, ValueError, KeyError, jwt.PyJWTError)


class JWKSUnavailable(Exception):
    """No keys cached and the throttle forbids fetching: an outage, not a bad token."""


class JWKSCache:
    def __init__(self, certs_url: str) -> None:
        self.certs_url = certs_url
        self._keys: dict[str, jwt.PyJWK] = {}
        # Last successful fetch decides staleness; last ATTEMPT decides the
        # throttle. Throttling on success time would mean a failing endpoint is
        # retried by every request, serialized behind the lock.
        self._fetched_at: float | None = None
        self._attempted_at: float | None = None
        self._lock = asyncio.Lock()

    def _stale(self) -> bool:
        return (
            self._fetched_at is None
            or time.monotonic() - self._fetched_at > JWKS_TTL_SECONDS
        )

    def _may_refetch(self) -> bool:
        return (
            self._attempted_at is None
            or time.monotonic() - self._attempted_at > JWKS_MIN_REFRESH_SECONDS
        )

    async def _fetch(self) -> jwt.PyJWKSet:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(self.certs_url)
        resp.raise_for_status()
        return jwt.PyJWKSet.from_dict(resp.json())

    async def _refresh(self) -> None:
        # Stamped before the request so a failure (including a timeout) still
        # starts the throttle window.
        self._attempted_at = time.monotonic()
        try:
            key_set = await self._fetch()
        except FETCH_ERRORS:
            # A key that verified a minute ago still verifies; only an empty
            # cache makes this an outage rather than a blip.
            if not self._keys:
                raise
            log.warning("JWKS refresh failed; serving cached keys", exc_info=True)
            return
        self._keys = {k.key_id: k for k in key_set.keys if k.key_id is not None}
        self._fetched_at = time.monotonic()

    async def key_for(self, kid: str) -> jwt.PyJWK | None:
        key = self._keys.get(kid)
        if key is not None and not self._stale():
            return key
        async with self._lock:
            # Another waiter may have refreshed while we queued.
            key = self._keys.get(kid)
            if key is not None and not self._stale():
                return key
            if self._may_refetch():
                await self._refresh()
            elif not self._keys:
                raise JWKSUnavailable
            return self._keys.get(kid)


def _issuer(team_domain: str) -> str:
    return f"https://{team_domain}.cloudflareaccess.com"


def enabled() -> bool:
    return bool(settings.access_team_domain or settings.access_aud)


if enabled() and not (settings.access_team_domain and settings.access_aud):
    raise RuntimeError("ACCESS_TEAM_DOMAIN and ACCESS_AUD must be set together (or both unset)")
if not enabled():
    log.warning("Cloudflare Access auth disabled: every request acts as %s", DEV_EMAIL)

jwks = JWKSCache(_issuer(settings.access_team_domain) + CERTS_PATH)


async def verify_access_jwt(token: str) -> AccessUser:
    """Raise 401 unless `token` is a live Access JWT for this app."""
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "malformed access token") from exc
    if not isinstance(kid, str):
        raise HTTPException(401, "access token has no key id")
    try:
        key = await jwks.key_for(kid)
    except (*FETCH_ERRORS, JWKSUnavailable) as exc:
        raise HTTPException(503, "could not fetch access signing keys") from exc
    if key is None:
        raise HTTPException(401, "access token signed by unknown key")
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=settings.access_aud,
            issuer=_issuer(settings.access_team_domain),
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        # One message for expired / wrong audience / bad signature: the split
        # helps someone probing the AUD tag and nobody else.
        raise HTTPException(401, "invalid access token") from exc
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        if claims.get("common_name"):
            # Service tokens verify but carry no user identity.
            raise HTTPException(401, "service tokens are not accepted")
        raise HTTPException(401, "access token carries no email")
    return AccessUser(email=email.strip().lower())


async def current_user(
    cf_access_jwt_assertion: str | None = Header(default=None),
) -> AccessUser:
    if not enabled():
        return AccessUser(email=DEV_EMAIL)
    if not cf_access_jwt_assertion:
        raise HTTPException(401, "missing access token")
    return await verify_access_jwt(cf_access_jwt_assertion)
