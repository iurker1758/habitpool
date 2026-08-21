"""Shared fixtures. The API tests run against in-memory SQLite so CI needs no
Postgres service.
"""
import os

# app.database builds the engine and app.auth decides whether Access is on at
# import time, both from settings, and settings reads the environment ahead of
# backend/.env — so this must run before any `app` import. It guarantees the
# suite never touches a developer's .env database and never 401s because the
# shell carries the deployment's Access config (test_auth turns Access on per
# test via monkeypatch). `sqlite+aiosqlite://` (memory) gets a StaticPool, so
# every session shares the one connection that holds the create_all'd schema.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["ACCESS_TEAM_DOMAIN"] = ""
os.environ["ACCESS_AUD"] = ""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Base, engine
from app.main import app

# The check-off upsert is written with the Postgres insert construct and
# `on_conflict_do_nothing(constraint="uq_checkoff_habit_day")`. Compiled for
# SQLite the constraint name is dropped, leaving a bare `ON CONFLICT DO
# NOTHING`. That matches the same conflicts here: the insert never supplies
# `id`, so (habit_id, day) is the only constraint it can hit. The tests
# therefore cover the do-nothing semantics; whether the constraint name
# resolves is checked only at Postgres runtime.


@pytest.fixture
async def db() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
