"""Database models.

Design notes (see DECISIONS.md):
- Money is integer cents.
- Checkoff has a unique (habit_id, day) constraint -> idempotent check-offs.
- HabitWeek freezes each habit's pool share at week rollover so unlocked
  percentages never jitter mid-week.
- All "day"/"week start" values are local dates in the configured timezone.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# All week math happens in this timezone. See DECISIONS.md #8.
APP_TIMEZONE = "America/New_York"


class HabitStatus(str, enum.Enum):
    active = "active"        # in the money system
    graduated = "graduated"  # tracked, but earns nothing (deliberate ceremony)
    archived = "archived"    # hidden entirely


class Habit(Base):
    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    # Implementation intention: "after I ___" (Gollwitzer). Shown next to the habit.
    cue: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[HabitStatus] = mapped_column(
        Enum(HabitStatus), default=HabitStatus.active
    )
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())

    checkoffs: Mapped[list["Checkoff"]] = relationship(back_populates="habit")


class Checkoff(Base):
    __tablename__ = "checkoffs"
    # The idempotency guarantee: one check-off per habit per local day.
    __table_args__ = (UniqueConstraint("habit_id", "day", name="uq_checkoff_habit_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id"))
    day: Mapped[dt.date] = mapped_column(Date)  # local date, not UTC timestamp

    habit: Mapped["Habit"] = relationship(back_populates="checkoffs")


class Week(Base):
    """One pay-tracking week. Starts Monday 00:00 local."""

    __tablename__ = "weeks"

    id: Mapped[int] = mapped_column(primary_key=True)
    start_day: Mapped[dt.date] = mapped_column(Date, unique=True)
    pool_cents: Mapped[int] = mapped_column(Integer, default=0)

    habit_weeks: Mapped[list["HabitWeek"]] = relationship(back_populates="week")


class HabitWeek(Base):
    """Frozen snapshot of a habit's share of the pool for one week.

    share_permille: this habit's slice of the pool in 1/1000ths (integers,
    same rationale as cents). Sum over active habits <= 1000.
    Computed once at week rollover from the maturity-tapered weights.
    """

    __tablename__ = "habit_weeks"
    __table_args__ = (UniqueConstraint("week_id", "habit_id", name="uq_habitweek"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("weeks.id"))
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id"))
    share_permille: Mapped[int] = mapped_column(Integer)

    week: Mapped["Week"] = relationship(back_populates="habit_weeks")
