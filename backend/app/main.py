"""HabitPool API. Routes kept in one module for now; split into routers when it grows.

Schema is managed by Alembic — run `alembic upgrade head` before starting.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from . import rewards
from .database import get_session
from .models import APP_TIMEZONE, Checkoff, Habit, HabitStatus, HabitWeek, Week

TZ = ZoneInfo(APP_TIMEZONE)


def local_today() -> dt.date:
    return dt.datetime.now(TZ).date()


def week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())  # Monday


app = FastAPI(title="HabitPool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- schemas ----------

class HabitIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    cue: str = Field(default="", max_length=200)


class HabitOut(HabitIn):
    id: int
    status: HabitStatus
    model_config = {"from_attributes": True}


class CheckoffIn(BaseModel):
    habit_id: int
    day: dt.date | None = None  # defaults to local today


class WeekSummary(BaseModel):
    start_day: dt.date
    pool_cents: int
    unlocked_cents: int
    shares_permille: dict[int, int]
    checkoff_days: dict[int, list[dt.date]]


class PoolIn(BaseModel):
    pool_cents: int = Field(ge=0)


# ---------- habits ----------

@app.get("/api/habits", response_model=list[HabitOut])
async def list_habits(session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(
        select(Habit).where(Habit.status != HabitStatus.archived).order_by(Habit.id)
    )
    return list(rows)


@app.post("/api/habits", response_model=HabitOut, status_code=201)
async def create_habit(body: HabitIn, session: AsyncSession = Depends(get_session)):
    habit = Habit(name=body.name, cue=body.cue)
    session.add(habit)
    await session.commit()
    await session.refresh(habit)
    return habit


# ---------- check-offs ----------

@app.post("/api/checkoffs", status_code=201)
async def check_off(body: CheckoffIn, session: AsyncSession = Depends(get_session)):
    """Idempotent: repeat calls for the same habit+day succeed without effect."""
    day = body.day or local_today()
    if day > local_today():
        raise HTTPException(400, "cannot check off the future")
    stmt = (
        pg_insert(Checkoff)
        .values(habit_id=body.habit_id, day=day)
        .on_conflict_do_nothing(constraint="uq_checkoff_habit_day")
    )
    await session.execute(stmt)
    await session.commit()
    return {"habit_id": body.habit_id, "day": day}


@app.delete("/api/checkoffs", status_code=204)
async def undo_check_off(body: CheckoffIn, session: AsyncSession = Depends(get_session)):
    day = body.day or local_today()
    row = await session.scalar(
        select(Checkoff).where(Checkoff.habit_id == body.habit_id, Checkoff.day == day)
    )
    if row:
        await session.delete(row)
        await session.commit()


# ---------- current week ----------

async def _get_or_roll_week(session: AsyncSession) -> Week:
    """Fetch this week's row, creating + freezing shares at first touch.

    v1 weight policy: all active habits weigh 1.0 until habit_weight() is
    implemented; then compute maturity-tapered weights here at rollover.
    """
    start = week_start(local_today())
    week = await session.scalar(select(Week).where(Week.start_day == start))
    if week:
        return week

    prev = await session.scalar(select(Week).order_by(Week.start_day.desc()).limit(1))
    week = Week(start_day=start, pool_cents=prev.pool_cents if prev else 0)
    session.add(week)
    await session.flush()

    habits = (await session.scalars(
        select(Habit).where(Habit.status == HabitStatus.active)
    )).all()
    if habits:
        weights = {h.id: 1.0 for h in habits}  # TODO: rewards.habit_weight(...)
        for hid, permille in rewards.pool_shares(weights).items():
            session.add(HabitWeek(week_id=week.id, habit_id=hid, share_permille=permille))
    await session.commit()
    await session.refresh(week)
    return week


@app.get("/api/week/current", response_model=WeekSummary)
async def current_week(session: AsyncSession = Depends(get_session)):
    week = await _get_or_roll_week(session)
    shares = {
        hw.habit_id: hw.share_permille
        for hw in await session.scalars(
            select(HabitWeek).where(HabitWeek.week_id == week.id)
        )
    }
    end = week.start_day + dt.timedelta(days=6)
    checkoffs = (await session.scalars(
        select(Checkoff).where(Checkoff.day >= week.start_day, Checkoff.day <= end)
    )).all()
    by_habit: dict[int, list[dt.date]] = {}
    for c in checkoffs:
        by_habit.setdefault(c.habit_id, []).append(c.day)

    counts = {hid: len(days) for hid, days in by_habit.items()}
    # TODO: streak bonuses once week_streak_result() is implemented
    unlocked = rewards.unlocked_cents(week.pool_cents, shares, counts)
    return WeekSummary(
        start_day=week.start_day,
        pool_cents=week.pool_cents,
        unlocked_cents=unlocked,
        shares_permille=shares,
        checkoff_days=by_habit,
    )


@app.put("/api/week/current/pool", response_model=WeekSummary)
async def set_pool(body: PoolIn, session: AsyncSession = Depends(get_session)):
    week = await _get_or_roll_week(session)
    week.pool_cents = body.pool_cents
    await session.commit()
    return await current_week(session)
