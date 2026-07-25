"""Tests for the pure reward math.

Passing tests cover the implemented functions. Skipped tests are the spec for
what YOU implement next — delete the skip marks and make them green.
"""
import datetime as dt

import pytest

from app.rewards import (
    INGRAINED_THRESHOLD,
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
    with pytest.raises(ValueError, match="must sum to a positive value"):
        pool_shares({1: 0.0})


# ---------- unlocked_cents (implemented) ----------

def test_perfect_week_unlocks_whole_pool_with_bonuses():
    shares = pool_shares({1: 1.0, 2: 1.0, 3: 1.0})
    cents = unlocked_cents(
        10_000,
        shares,
        {1: 7, 2: 7, 3: 7},
        dict.fromkeys(shares, STREAK_BONUS_PERMILLE),
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


# ---------- habit_weight ----------

def test_new_habit_has_full_weight_even_when_nailed():
    assert habit_weight(weeks_active=2, trailing_completion=1.0) == 1.0


def test_old_nailed_habit_reaches_floor():
    assert habit_weight(weeks_active=20, trailing_completion=0.95) == WEIGHT_FLOOR


def test_struggling_habit_does_not_taper():
    # below the ingrained threshold -> no taper, regardless of age
    assert habit_weight(weeks_active=20, trailing_completion=0.5) == 1.0


def test_taper_is_monotonic_and_bounded():
    prev = 1.0
    for weeks in range(0, 30):
        w = habit_weight(weeks_active=weeks, trailing_completion=0.9)
        assert WEIGHT_FLOOR <= w <= 1.0
        assert w <= prev
        prev = w


def test_glide_is_linear_at_midpoint():
    # 4 of 8 taper weeks elapsed -> exactly halfway from 1.0 to the floor
    assert habit_weight(weeks_active=8, trailing_completion=0.9) == 0.625


def test_exactly_threshold_completion_tapers():
    # >= is inclusive: a habit at exactly the ingrained threshold tapers
    assert habit_weight(
        weeks_active=20, trailing_completion=INGRAINED_THRESHOLD
    ) == WEIGHT_FLOOR


# ---------- week_streak_result ----------

WEEK = [dt.date(2026, 7, 20) + dt.timedelta(days=i) for i in range(7)]  # Mon-Sun


def test_perfect_week_earns_bonus_without_skips():
    r = week_streak_result(set(WEEK), WEEK)
    assert r == StreakResult(streak_intact=True, skips_used=0,
                             bonus_permille=STREAK_BONUS_PERMILLE)


def test_one_miss_spends_skip_token_and_keeps_bonus():
    r = week_streak_result(set(WEEK[:3] + WEEK[4:]), WEEK)
    assert r.streak_intact
    assert r.skips_used == 1
    assert r.bonus_permille == STREAK_BONUS_PERMILLE


def test_two_misses_break_the_streak():
    r = week_streak_result(set(WEEK[2:]), WEEK)
    assert not r.streak_intact
    assert r.bonus_permille == 0
    assert r.skips_used == 1  # the one token is spent even though it wasn't enough


def test_future_days_do_not_count_as_misses():
    # Wednesday of a Mon-start week: 3 judgeable days, all checked
    r = week_streak_result(set(WEEK[:3]), WEEK, today=WEEK[2])
    assert r == StreakResult(streak_intact=True, skips_used=0, bonus_permille=0)


def test_midweek_miss_spends_token_but_no_bonus_yet():
    # checked Mon + Wed, missed Tue, judged on Wed -> alive via token, no bonus
    r = week_streak_result({WEEK[0], WEEK[2]}, WEEK, today=WEEK[2])
    assert r == StreakResult(streak_intact=True, skips_used=1, bonus_permille=0)


def test_midweek_two_misses_break_the_streak():
    # only Wed checked by Wed -> Mon and Tue are both misses
    r = week_streak_result({WEEK[2]}, WEEK, today=WEEK[2])
    assert not r.streak_intact
    assert r.bonus_permille == 0


def test_today_on_last_day_completes_the_week():
    # today == Sunday judges all 7 days: bonus is awarded, same as today=None
    r = week_streak_result(set(WEEK), WEEK, today=WEEK[6])
    assert r.bonus_permille == STREAK_BONUS_PERMILLE


def test_today_before_week_start_judges_nothing():
    # rollover edge: a not-yet-started week has no judgeable days and no bonus
    r = week_streak_result(set(), WEEK, today=WEEK[0] - dt.timedelta(days=1))
    assert r == StreakResult(streak_intact=True, skips_used=0, bonus_permille=0)
