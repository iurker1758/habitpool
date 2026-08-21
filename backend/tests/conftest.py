"""Shared fixtures. The API tests run against in-memory SQLite so CI needs no
Postgres service.
"""
import os

# app.database builds the engine at import time from settings, and settings
# reads the environment ahead of backend/.env — so this must run before any
# `app` import, and it guarantees the suite never touches a developer's .env
# database. `sqlite+aiosqlite://` (memory) gets a StaticPool, so every session
# shares the one connection that holds the create_all'd schema.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Base, engine
from app.main import app

# The check-off upsert is written with the Postgres insert construct and
# `on_conflict_do_nothing(constraint="uq_checkoff_habit_day")`. Compiled for
# SQLite the constraint name is dropped, leaving a bare `ON CONFLICT DO
# NOTHING` — equivalent here because that is the table's only unique
# constraint, so the idempotency tests exercise the real upsert path.


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
