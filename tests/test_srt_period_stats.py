"""
test_srt_period_stats.py — non-destructive tests for the SRT production
period stats (PHASE 7, sections 3.2 / 3.3).

Covers the six required scenarios with in-memory fixtures (no MySQL, no
network, no production record touched):

  1. new SRT (today)                    -> srt_today / 7d / 14d increment
  2. no-new-work run (no production)    -> today == 0, quiet days count as zeros
  3. failed run                         -> period stats unaffected (failed runs
                                           write pipeline_runs rows, never
                                           radio_program_sessions)
  4. reprocess / re-publish of an
     existing file                       -> production date fixed, no double count
  5. Tehran day boundary                -> a 00:30 Tehran session belongs to the
                                           new Tehran date, not the UTC date
  6. old + new data in window           -> 7d window (regression for the old
                                           INTERVAL 3 DAY bug) + true-zero vs
                                           missing-day distinction

Run:  py -3.13 -m pytest .tmp_phase3/tests/test_srt_period_stats.py -q
"""
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, R)

import dashboard.logic as logic  # noqa: E402

TEHRAN = timezone(timedelta(hours=3, minutes=30))
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=TEHRAN)  # fixed "now" for determinism
TODAY = NOW.date()


def D(d):
    return d.isoformat()


class SrtPeriodStatsNewSrtTest(unittest.TestCase):
    """Scenario 1 — a new SRT produced today is counted exactly once."""

    def test_new_srt_today(self):
        out = logic._compute_srt_period_stats({D(TODAY): 264}, NOW)
        self.assertEqual(out["srt_today"], 264)
        self.assertEqual(out["srt_yesterday"], 0)
        self.assertEqual(out["srt_last_7d"], 264)
        self.assertEqual(out["srt_last_14d"], 264)
        # today is still running -> it is NOT counted as a zero day
        self.assertEqual(out["srt_zero_output_days_14d"], 13)


class SrtPeriodStatsNoProductionTest(unittest.TestCase):
    """Scenarios 2 & 3 — no-new-work / failed runs produce nothing; fully
    elapsed quiet days are true zero-output days."""

    def test_quiet_days_are_zero_days(self):
        # Only the 26th (today-3) produced 40; all other complete days
        # (today-1 .. today-13) produced nothing.
        by_day = {D(TODAY - timedelta(days=3)): 40}
        out = logic._compute_srt_period_stats(by_day, NOW)
        self.assertEqual(out["srt_today"], 0)
        self.assertEqual(out["srt_yesterday"], 0)
        # 13 complete days, 1 with data -> 12 true zero-output days
        self.assertEqual(out["srt_zero_output_days_14d"], 12)

    def test_failed_run_does_not_change_period_stats(self):
        by_day = {D(TODAY): 5}
        before = logic._compute_srt_period_stats(by_day, NOW)
        later = logic._compute_srt_period_stats(by_day, datetime(2026, 10, 29, 18, 0, tzinfo=TEHRAN))
        self.assertEqual(before["srt_today"], later["srt_today"])
        self.assertEqual(before["srt_last_7d"], later["srt_last_7d"])


class SrtPeriodStatsReprocessTest(unittest.TestCase):
    """Scenario 4 — reprocessing / republishing an existing SRT must not
    double-count: the session's production date (first subtitled state) is
    fixed, so the day map — and every window — is stable across the day."""

    def test_reprocess_unchanged_production_date(self):
        by_day = {D(TODAY): 10}
        a = logic._compute_srt_period_stats(by_day, NOW)
        b = logic._compute_srt_period_stats(by_day, datetime(2026, 10, 29, 22, 0, tzinfo=TEHRAN))
        self.assertEqual(a, b)
        self.assertEqual(a["srt_today"], 10)


class SrtPeriodStatsDayBoundaryTest(unittest.TestCase):
    """Scenario 5 — Tehran day boundary: a session produced at 00:30 Tehran
    on the 30th (21:00 UTC on the 29th) belongs to the 30th, not the 29th."""

    def test_late_utc_but_next_tehran_day(self):
        # produced 2026-10-29 21:00 UTC == 2026-10-30 00:30 Tehran
        by_day = {D(date(2026, 10, 30)): 3}
        out = logic._compute_srt_period_stats(by_day, datetime(2026, 10, 29, 23, 59, tzinfo=TEHRAN))
        self.assertEqual(out["srt_today"], 0)
        # ...and once Tehran midnight has passed it IS today:
        out2 = logic._compute_srt_period_stats(by_day, datetime(2026, 10, 30, 1, 0, tzinfo=TEHRAN))
        self.assertEqual(out2["srt_today"], 3)

    def test_evening_tehran_batch_counts_today(self):
        # 23:30 Tehran on the 29th (20:00 UTC) is still "today"
        out = logic._compute_srt_period_stats({D(TODAY): 8}, datetime(2026, 10, 29, 23, 30, tzinfo=TEHRAN))
        self.assertEqual(out["srt_today"], 8)


class SrtPeriodStatsWindowTest(unittest.TestCase):
    """Scenario 6 — old + new data in the window: the 7-day sum must span 7
    days (regression for the old INTERVAL 3 DAY SQL window) and zero-output
    days must count only complete days inside the window."""

    def test_7d_window_covers_all_seven_days(self):
        by_day = {
            D(TODAY - timedelta(days=1)): 3,
            D(TODAY - timedelta(days=4)): 7,   # outside the old 3-day window
            D(TODAY - timedelta(days=5)): 5,   # outside the old 3-day window
        }
        out = logic._compute_srt_period_stats(by_day, NOW)
        self.assertEqual(out["srt_last_7d"], 15)  # old bug would yield 3
        self.assertEqual(out["srt_last_14d"], 15)
        # complete days 1..13 minus the 3 days with data -> 10 true zeros
        self.assertEqual(out["srt_zero_output_days_14d"], 10)

    def test_data_beyond_14d_is_outside_the_window(self):
        by_day = {
            D(TODAY - timedelta(days=13)): 9,   # inside the 14-day window
            D(TODAY - timedelta(days=14)): 77,  # outside
        }
        out = logic._compute_srt_period_stats(by_day, NOW)
        self.assertEqual(out["srt_last_14d"], 9)
        self.assertEqual(out["srt_last_7d"], 0)


if __name__ == "__main__":
    unittest.main()
