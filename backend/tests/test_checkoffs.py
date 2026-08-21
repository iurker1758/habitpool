"""The headline guarantee: a check-off is one row per (habit, local day) no
matter how many times the client sends it — double taps and offline retries
must never double-count.
"""
import datetime as dt
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Checkoff

pytestmark = pytest.mark.usefixtures("db")


async def _count_rows() -> int:
    async with SessionLocal() as session:
        n = await session.scalar(select(func.count()).select_from(Checkoff))
    assert n is not None
    return n


async def _habit(client: AsyncClient) -> int:
    r = await client.post("/api/habits", json={"name": "Stretch"})
    assert r.status_code == 201
    return r.json()["id"]


async def _summary(client: AsyncClient) -> dict[str, Any]:
    r = await client.get("/api/week/current")
    assert r.status_code == 200
    return r.json()


async def test_double_post_is_idempotent(client: AsyncClient):
    hid = await _habit(client)
    # Nonzero pool so unlocked_cents moves on the first check-off and the
    # "unchanged on the second" assertion is not trivially 0 == 0.
    await client.put("/api/week/current/pool", json={"pool_cents": 7000})
    today = (await _summary(client))["today"]

    first = await client.post("/api/checkoffs", json={"habit_id": hid, "day": today})
    assert first.status_code == 201
    after_first = await _summary(client)
    assert after_first["unlocked_cents"] > 0

    second = await client.post("/api/checkoffs", json={"habit_id": hid, "day": today})
    assert second.status_code == 201
    assert second.json() == first.json()

    after_second = await _summary(client)
    assert await _count_rows() == 1
    assert after_second["unlocked_cents"] == after_first["unlocked_cents"]
    assert after_second["checkoff_days"] == {str(hid): [today]}


async def test_delete_then_repost(client: AsyncClient):
    hid = await _habit(client)
    today = (await _summary(client))["today"]
    body = {"habit_id": hid, "day": today}

    assert (await client.post("/api/checkoffs", json=body)).status_code == 201
    assert (await client.request("DELETE", "/api/checkoffs", json=body)).status_code == 204
    assert await _count_rows() == 0

    assert (await client.post("/api/checkoffs", json=body)).status_code == 201
    assert await _count_rows() == 1


async def test_delete_missing_is_noop(client: AsyncClient):
    hid = await _habit(client)
    r = await client.request("DELETE", "/api/checkoffs", json={"habit_id": hid})
    assert r.status_code == 204
    assert await _count_rows() == 0


async def test_future_day_rejected(client: AsyncClient):
    hid = await _habit(client)
    today = dt.date.fromisoformat((await _summary(client))["today"])
    tomorrow = (today + dt.timedelta(days=1)).isoformat()

    r = await client.post("/api/checkoffs", json={"habit_id": hid, "day": tomorrow})
    assert r.status_code == 400
    assert await _count_rows() == 0


async def test_default_day_is_local_today(client: AsyncClient):
    hid = await _habit(client)
    today = (await _summary(client))["today"]

    r = await client.post("/api/checkoffs", json={"habit_id": hid})
    assert r.status_code == 201
    assert r.json() == {"habit_id": hid, "day": today}
