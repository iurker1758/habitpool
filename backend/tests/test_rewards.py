"""Tests for the pure reward math.

Passing tests cover the implemented functions. Skipped tests are the spec for
what YOU implement next — delete the skip marks and make them green.
"""
import datetime as dt

import pytest

from app.rewards import (
    STREAK_BONUS_PERMILLE,
    WEIGHT_FLOOR,
    StreakResult,
    habit_weight,
    pool_shares,
    unlocked_cents,
    week_streak_result,
)

# ---------- pool_shares (implemented) ----------

def test_equal_weights_split_evenly_and_sum_to_1000():
    shares = pool_shares({1: 1.0, 2: 1.0, 3: 1.0})
    assert sum(shares.values()) == 1000
    assert sorted(shares.values()) == [333, 333, 334]


def test_tapered_habit_gets_smaller_share():
    shares = pool_shares({1: 1.0, 2: WEIGHT_FLOOR})
    assert shares[1] > shares[2]
    assert sum(shares.values()) == 1000


def test_single_habit_takes_whole_pool():
    assert pool_shares({7: 0.6}) == {7: 1000}


def test_zero_total_weight_rejected():
    with pytest.raises(ValueError):
        pool_shares({1: 0.0})


# ---------- unlocked_cents (implemented) ----------

def test_perfect_week_unlocks_whole_pool_with_bonuses():
    shares = pool_shares({1: 1.0, 2: 1.0, 3: 1.0})
    cents = unlocked_cents(
        10_000,
        shares,
        {1: 7, 2: 7, 3: 7},
        {h: STREAK_BONUS_PERMILLE for h in shares},
    )
    assert cents == 10_000  # capped at pool


def test_half_effort_unlocks_roughly_half():
    shares = pool_shares({1: 1.0, 2: 1.0})
    cents = unlocked_cents(10_000, shares, {1: 4, 2: 3})
    assert 4_500 <= cents <= 5_500


def test_no_checkoffs_unlocks_nothing():
    shares = pool_shares({1: 1.0})
    assert unlocked_cents(10_000, shares, {}) == 0


def test_more_than_seven_days_is_clamped():
    shares = pool_shares({1: 1.0})
    assert unlocked_cents(7_000, shares, {1: 99}) == 7_000


# ---------- habit_weight (YOUR TDD BACKLOG) ----------

pytestmark_weight = pytest.mark.skip(reason="TODO(you): implement habit_weight")


@pytest.mark.skip(reason="TODO(you): implement habit_weight")
def test_new_habit_has_full_weight_even_when_nailed():
    assert habit_weight(weeks_active=2, trailing_completion=1.0) == 1.0


@pytest.mark.skip(reason="TODO(you): implement habit_weight")
def test_old_nailed_habit_reaches_floor():
    assert habit_weight(weeks_active=20, trailing_completion=0.95) == WEIGHT_FLOOR


@pytest.mark.skip(reason="TODO(you): implement habit_weight")
def test_struggling_habit_does_not_taper():
    # below the ingrained threshold -> no taper, regardless of age
    assert habit_weight(weeks_active=20, trailing_completion=0.5) == 1.0


@pytest.mark.skip(reason="TODO(you): implement habit_weight")
def test_taper_is_monotonic_and_bounded():
    prev = 1.0
    for weeks in range(0, 30):
        w = habit_weight(weeks_active=weeks, trailing_completion=0.9)
        assert WEIGHT_FLOOR <= w <= 1.0
        assert w <= prev
        prev = w


# ---------- week_streak_result (YOUR TDD BACKLOG) ----------

WEEK = [dt.date(2026, 7, 20) + dt.timedelta(days=i) for i in range(7)]  # Mon-Sun


@pytest.mark.skip(reason="TODO(you): implement week_streak_result")
def test_perfect_week_earns_bonus_without_skips():
    r = week_streak_result(set(WEEK), WEEK)
    assert r == StreakResult(streak_intact=True, skips_used=0,
                             bonus_permille=STREAK_BONUS_PERMILLE)


@pytest.mark.skip(reason="TODO(you): implement week_streak_result")
def test_one_miss_spends_skip_token_and_keeps_bonus():
    r = week_streak_result(set(WEEK[:3] + WEEK[4:]), WEEK)
    assert r.streak_intact and r.skips_used == 1
    assert r.bonus_permille == STREAK_BONUS_PERMILLE


@pytest.mark.skip(reason="TODO(you): implement week_streak_result")
def test_two_misses_break_the_streak():
    r = week_streak_result(set(WEEK[2:]), WEEK)
    assert not r.streak_intact
    assert r.bonus_permille == 0
