"""Reward math. Pure functions only — no I/O, no ORM. This module is the
project's fingerprint; keep it yours.

Model recap (see README / DECISIONS.md):
- Each habit has a weight in [WEIGHT_FLOOR, 1.0] driven by maturity.
- Pool shares = weight / sum(weights), expressed in permille (integer 1/1000ths).
- A check-off unlocks share/7 of the pool for that day.
- A full-week streak (7 check-offs, or 6 + one skip token) earns a bonus.
- Weights taper only when a habit is BOTH old enough and consistently done —
  reinforcement-schedule thinning.

Implemented: weights -> shares, unlock accumulation, habit_weight(),
week_streak_result(). (The TDD backlog is complete.)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

WEIGHT_FLOOR = 0.25       # ingrained habits never taper below this (keep the tick alive)
FULL_WEIGHT_WEEKS = 4     # no taper before this age
TAPER_WEEKS = 8           # weeks of high completion to glide from 1.0 down to the floor
INGRAINED_THRESHOLD = 0.8 # trailing completion rate that counts as "being nailed"
STREAK_BONUS_PERMILLE = 50  # per-habit bonus for a (skip-forgiven) perfect week
SKIP_TOKENS_PER_WEEK = 1


def pool_shares(weights: dict[int, float]) -> dict[int, int]:
    """Normalize habit weights into permille shares of the pool.

    Integer permille (like cents) so sums are exact. Remainder from rounding is
    given to the highest-weight habit so shares total exactly 1000.
    """
    if not weights:
        return {}
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    raw = {hid: int(w / total * 1000) for hid, w in weights.items()}
    remainder = 1000 - sum(raw.values())
    top = max(weights, key=lambda hid: weights[hid])
    raw[top] += remainder
    return raw


def unlocked_cents(
    pool_cents: int,
    shares_permille: dict[int, int],
    checkoff_counts: dict[int, int],
    streak_bonuses_permille: dict[int, int] | None = None,
) -> int:
    """Total unlocked cents for a week.

    Each check-off of habit h unlocks share_h/7 of the pool. Bonuses add flat
    permille. Capped at the pool.
    """
    bonuses = streak_bonuses_permille or {}
    permille_earned = 0.0
    for hid, share in shares_permille.items():
        days = min(checkoff_counts.get(hid, 0), 7)
        permille_earned += share * days / 7
        permille_earned += bonuses.get(hid, 0)
    cents = int(pool_cents * permille_earned / 1000)
    return min(cents, pool_cents)


def habit_weight(weeks_active: int, trailing_completion: float) -> float:
    """Maturity-tapered weight in [WEIGHT_FLOOR, 1.0].

    - weeks_active < FULL_WEIGHT_WEEKS  -> 1.0 regardless of completion.
    - Taper only while trailing_completion >= INGRAINED_THRESHOLD
      (reinforcement-schedule thinning applies to habits being nailed, not
      habits being rebuilt). NOTE: below the threshold the weight rebounds to
      1.0 — v1 does not hold the tapered position, so the curve is monotonic
      only at sustained-high completion. v1 also treats weeks_active as
      qualifying weeks; a qualifying_weeks parameter is the v2 refinement if
      held-position precision is ever wanted. See DECISIONS.md #14.
    - Linear glide from 1.0 down to WEIGHT_FLOOR across TAPER_WEEKS.
    """
    if weeks_active < FULL_WEIGHT_WEEKS or trailing_completion < INGRAINED_THRESHOLD:
        return 1.0
    taper_progress = min(weeks_active - FULL_WEIGHT_WEEKS, TAPER_WEEKS)
    return 1.0 - (1.0 - WEIGHT_FLOOR) * taper_progress / TAPER_WEEKS


@dataclass(frozen=True)
class StreakResult:
    streak_intact: bool
    skips_used: int
    bonus_permille: int


def week_streak_result(
    checkoff_days: set[date], week_days: list[date], *, today: date | None
) -> StreakResult:
    """Streak + skip-token logic for one habit over one week.

    - week_days is the list of days the habit was EXPECTED: callers pass only
      days the habit was active (a habit created Thursday gets Thu-Sun, not
      the full week), and an empty list earns nothing.
    - today is required (keyword-only, so a mid-week caller can't silently
      fall into whole-week judging) and must be a local APP_TIMEZONE date —
      no clock read here, this module stays pure. today=None means the week
      has fully elapsed (historical weeks). See DECISIONS.md #15.
    - A day is judgeable once it has fully elapsed (day < today), or if it is
      today and already checked off — a done day can't become undone, so
      counting it early can only ever help. An unfinished today is never a
      miss; future days never count against the streak.
    - Misses among judgeable days spend skip tokens (slack by design: avoids
      the what-the-hell effect); the streak is intact while misses <=
      SKIP_TOKENS_PER_WEEK. skips_used reports tokens spent, capped at
      SKIP_TOKENS_PER_WEEK even when the streak is already broken.
    - The bonus is awarded only once every expected day is judgeable and the
      streak held — never from incomplete data.
    """
    if isinstance(today, datetime):
        raise TypeError("today must be a local date, not a datetime")
    if not week_days:
        return StreakResult(streak_intact=True, skips_used=0, bonus_permille=0)
    judgeable = [
        d for d in week_days
        if today is None or d < today or (d == today and d in checkoff_days)
    ]
    misses = sum(1 for d in judgeable if d not in checkoff_days)
    intact = misses <= SKIP_TOKENS_PER_WEEK
    week_complete = len(judgeable) == len(week_days)
    return StreakResult(
        streak_intact=intact,
        skips_used=min(misses, SKIP_TOKENS_PER_WEEK),
        bonus_permille=STREAK_BONUS_PERMILLE if intact and week_complete else 0,
    )
