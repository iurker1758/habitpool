"""Access JWT boundary: only a live, correctly-signed, correctly-audienced token
from the configured team is an identity; everything else is 401.
"""
import asyncio
import datetime as dt
from collections.abc import AsyncIterator
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm

from app import auth
from app.config import settings
from app.main import app

TEAM = "testteam"
AUD = "aud-tag-for-habitpool"
ISS = f"https://{TEAM}.cloudflareaccess.com"

GOOD_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ROGUE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    public: dict[str, Any] = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {**public, "kid": kid}


def _token(key: rsa.RSAPrivateKey = GOOD_KEY, kid: str = "k1", **overrides: Any) -> str:
    now = dt.datetime.now(dt.UTC)
    claims: dict[str, Any] = {
        "aud": [AUD],
        "iss": ISS,
        "iat": now,
        "exp": now + dt.timedelta(minutes=5),
        "email": "jason@example.com",
        **overrides,
    }
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


class FakeJWKS(auth.JWKSCache):
    def __init__(self, keys: list[dict[str, Any]]) -> None:
        super().__init__(certs_url="https://unused.invalid")
        self._payload = keys
        self.fetches = 0
        self.delay = 0.0

    def rewind(self, seconds: float) -> None:
        assert self._fetched_at is not None
        assert self._attempted_at is not None
        self._fetched_at -= seconds
        self._attempted_at -= seconds

    async def _fetch(self) -> jwt.PyJWKSet:
        self.fetches += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return jwt.PyJWKSet.from_dict({"keys": self._payload})


@pytest.fixture
def access_on(monkeypatch: pytest.MonkeyPatch) -> FakeJWKS:
    monkeypatch.setattr(settings, "access_team_domain", TEAM)
    monkeypatch.setattr(settings, "access_aud", AUD)
    fake = FakeJWKS([_jwk(GOOD_KEY, "k1")])
    monkeypatch.setattr(auth, "jwks", fake)
    return fake


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_valid_token_yields_email(client: AsyncClient, access_on: FakeJWKS):
    r = await client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": _token()})
    assert r.status_code == 200
    assert r.json() == {"email": "jason@example.com"}


async def test_missing_header_is_401(client: AsyncClient, access_on: FakeJWKS):
    r = await client.get("/api/me")
    assert r.status_code == 401


async def test_bare_email_header_is_not_trusted(client: AsyncClient, access_on: FakeJWKS):
    r = await client.get(
        "/api/me", headers={"Cf-Access-Authenticated-User-Email": "jason@example.com"}
    )
    assert r.status_code == 401


async def test_all_routes_gated_before_db(client: AsyncClient, access_on: FakeJWKS):
    # No DB in tests: a 401 proves the auth dependency ran before get_session.
    for method, path in [("GET", "/api/habits"), ("GET", "/api/week/current")]:
        r = await client.request(method, path)
        assert r.status_code == 401, path


@pytest.mark.parametrize(
    ("label", "token"),
    [
        ("rogue key, known kid", _token(key=ROGUE_KEY)),
        ("unknown kid", _token(kid="k-other")),
        ("wrong audience", _token(aud=["some-other-app"])),
        ("wrong issuer", _token(iss="https://otherteam.cloudflareaccess.com")),
        ("expired", _token(exp=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1))),
        ("no exp", _token(exp=None)),
        ("no email", _token(email=None)),
        ("garbage", "not.a.jwt"),
    ],
    ids=lambda v: v if isinstance(v, str) and "." not in v else "",
)
async def test_bad_tokens_are_401(
    client: AsyncClient, access_on: FakeJWKS, label: str, token: str
):
    r = await client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert r.status_code == 401, label


async def test_alg_none_rejected(client: AsyncClient, access_on: FakeJWKS):
    token = jwt.encode({"aud": [AUD], "iss": ISS, "email": "x@y"}, key="", algorithm="none",
                       headers={"kid": "k1"})
    r = await client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert r.status_code == 401


async def test_unknown_kid_refetch_is_rate_limited(access_on: FakeJWKS):
    await access_on.key_for("k1")
    assert access_on.fetches == 1
    for _ in range(5):
        await access_on.key_for("forged-kid")
    assert access_on.fetches == 1


async def test_fresh_known_key_skips_the_lock(access_on: FakeJWKS):
    await access_on.key_for("k1")
    async with access_on._lock:  # pyright: ignore[reportPrivateUsage]
        assert await asyncio.wait_for(access_on.key_for("k1"), timeout=0.5) is not None


async def test_rotated_key_is_picked_up_after_min_interval(access_on: FakeJWKS):
    await access_on.key_for("k1")
    access_on._payload.append(_jwk(ROGUE_KEY, "k2"))  # pyright: ignore[reportPrivateUsage]
    access_on.rewind(auth.JWKS_MIN_REFRESH_SECONDS + 1)
    assert await access_on.key_for("k2") is not None
    assert access_on.fetches == 2


async def test_jwks_fetch_failure_is_503(
    client: AsyncClient, access_on: FakeJWKS, monkeypatch: pytest.MonkeyPatch
):
    async def boom(self: auth.JWKSCache) -> jwt.PyJWKSet:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(FakeJWKS, "_fetch", boom)
    r = await client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": _token()})
    assert r.status_code == 503


async def test_disabled_mode_acts_as_dev_user(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "access_team_domain", "")
    monkeypatch.setattr(settings, "access_aud", "")
    r = await client.get("/api/me")
    assert r.status_code == 200
    assert r.json() == {"email": auth.DEV_EMAIL}


def _real_cache(monkeypatch: pytest.MonkeyPatch, handler: Any) -> auth.JWKSCache:
    """A JWKSCache whose HTTP goes to `handler` instead of the network."""
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def patched(**kw: Any) -> httpx.AsyncClient:
        return real_client(transport=transport, **kw)

    monkeypatch.setattr(auth.httpx, "AsyncClient", patched)
    cache = auth.JWKSCache(certs_url="https://unused.invalid/certs")
    monkeypatch.setattr(auth, "jwks", cache)
    return cache


async def test_stale_cache_survives_refresh_failure(
    client: AsyncClient, access_on: FakeJWKS, monkeypatch: pytest.MonkeyPatch
):
    state = {"up": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if not state["up"]:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"keys": [_jwk(GOOD_KEY, "k1")]})

    cache = _real_cache(monkeypatch, handler)
    await cache.key_for("k1")
    cache._fetched_at = cache._attempted_at = 0.0  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(auth.time, "monotonic", lambda: float(auth.JWKS_TTL_SECONDS + 1))
    state["up"] = False
    r = await client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": _token()})
    assert r.status_code == 200


async def test_failed_refetch_is_throttled(monkeypatch: pytest.MonkeyPatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("down")

    cache = _real_cache(monkeypatch, handler)
    with pytest.raises(httpx.ConnectError):
        await cache.key_for("k1")
    for _ in range(4):
        with pytest.raises(auth.JWKSUnavailable):
            await cache.key_for("k1")
    assert calls["n"] == 1


async def test_malformed_jwks_body_with_empty_cache_is_503(
    client: AsyncClient, access_on: FakeJWKS, monkeypatch: pytest.MonkeyPatch
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    _real_cache(monkeypatch, handler)
    r = await client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": _token()})
    assert r.status_code == 503


async def test_service_token_is_rejected(client: AsyncClient, access_on: FakeJWKS):
    token = _token(email=None, common_name="some-service-token-id")
    r = await client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert r.status_code == 401
    assert "service token" in r.json()["detail"]


async def test_email_is_normalized(client: AsyncClient, access_on: FakeJWKS):
    token = _token(email="  Jason@Example.COM ")
    r = await client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert r.json() == {"email": "jason@example.com"}


async def test_first_fetch_happens_even_when_monotonic_is_small(
    access_on: FakeJWKS, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(auth.time, "monotonic", lambda: 1.0)
    assert await access_on.key_for("k1") is not None
    assert access_on.fetches == 1


@pytest.mark.parametrize(
    "exc", [ValueError("bad json"), KeyError("keys"), jwt.PyJWKError("bad key")]
)
async def test_malformed_jwks_body_is_503(
    client: AsyncClient, access_on: FakeJWKS, monkeypatch: pytest.MonkeyPatch, exc: Exception
):
    async def boom(self: auth.JWKSCache) -> jwt.PyJWKSet:
        raise exc

    monkeypatch.setattr(FakeJWKS, "_fetch", boom)
    r = await client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": _token()})
    assert r.status_code == 503


async def test_concurrent_lookups_share_one_refresh(access_on: FakeJWKS):
    access_on.delay = 0.01
    await asyncio.gather(*(access_on.key_for("k1") for _ in range(5)))
    assert access_on.fetches == 1
