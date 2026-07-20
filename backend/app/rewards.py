"""Reward math. Pure functions only — no I/O, no ORM. This module is the
project's fingerprint; keep it yours.

Model recap (see README / DECISIONS.md):
- Each habit has a weight in [WEIGHT_FLOOR, 1.0] driven by maturity.
- Pool shares = weight / sum(weights), expressed in permille (integer 1/1000ths).
- A check-off unlocks share/7 of the pool for that day.
- A full-week streak (7 check-offs, or 6 + one skip token) earns a bonus.
- Weights taper only when a habit is BOTH old enough and consistently done —
  reinforcement-schedule thinning.

Implemented: weights -> shares, unlock accumulation.
Your TDD backlog (tests exist in tests/test_rewards.py, currently skipped):
  - habit_weight(): the maturity curve
  - week_streak_result(): streak + skip-token logic
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

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

    Spec (implement me — tests in test_rewards.py encode this):
    - weeks_active < FULL_WEIGHT_WEEKS  -> 1.0 regardless of completion.
    - Taper only while trailing_completion >= INGRAINED_THRESHOLD; a habit that
      slips below the threshold holds its current position, it does not taper
      further (but also does not bounce back up — monotonic non-increasing is
      fine for v1; simplest correct approach: taper progress is
      min(weeks_active - FULL_WEIGHT_WEEKS, TAPER_WEEKS) counted only when
      completion qualifies — pass qualifying_weeks in v2 if you want that
      precision; for v1 the tests treat weeks_active as qualifying weeks).
    - Linear glide: 1.0 down to WEIGHT_FLOOR across TAPER_WEEKS.
    - Never below WEIGHT_FLOOR.
    """
    raise NotImplementedError("your TDD backlog — see tests/test_rewards.py")


@dataclass(frozen=True)
class StreakResult:
    streak_intact: bool
    skips_used: int
    bonus_permille: int


def week_streak_result(checkoff_days: set[date], week_days: list[date]) -> StreakResult:
    """Streak + skip-token logic for one habit over one week.

    Spec (implement me):
    - 7/7 days checked -> intact, 0 skips, STREAK_BONUS_PERMILLE.
    - 6/7 -> intact via one skip token, bonus still awarded (slack by design:
      avoids the what-the-hell effect).
    - <= 5/7 -> streak broken, no bonus, skips_used reports tokens spent (max
      SKIP_TOKENS_PER_WEEK).
    - Days in the future (relative to max(week_days) actually elapsed) must not
      count against the streak — a Wednesday check of a Mon-start week has only
      3 judgeable days. Signature may need the 'today' date; adjust it and the
      tests when you implement.
    """
    raise NotImplementedError("your TDD backlog — see tests/test_rewards.py")
