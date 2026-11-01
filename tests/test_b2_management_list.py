"""
B2 — pure-function tests for the per-program management list helpers
(dashboard/logic.py). No DB, no network: only the deterministic helpers are
tested here; the SQL layer is validated live against the 32 real programs
during the B2 checkpoint (D5-style SQL validation).

Run (server 53, dashboard venv):
    cd <repo> && dashboard/venv/bin/python -m pytest tests/test_b2_management_list.py -q
"""
import os
import sys
from datetime import time as dtime
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
import logic  # noqa: E402

TZ = "Asia/Tehran"


# -- _b2_parse_start -----------------------------------------------------------

class TestParseStart:
    def test_hms_string(self):
        assert logic._b2_parse_start("16:00:00") == "16:00"

    def test_hm_string(self):
        assert logic._b2_parse_start("06:00") == "06:00"

    def test_time_object(self):
        assert logic._b2_parse_start(dtime(17, 40, 0)) == "17:40"

    def test_datetime_object(self):
        assert logic._b2_parse_start(datetime(2026, 11, 1, 14, 5)) == "14:05"

    def test_none_returns_default(self):
        assert logic._b2_parse_start(None) is None
        assert logic._b2_parse_start(None, default="00:00") == "00:00"

    def test_garbage_returns_default(self):
        assert logic._b2_parse_start("not a time") is None
        assert logic._b2_parse_start("25:99:xx", default="08:00") == "08:00"


# -- _b2_minutes ---------------------------------------------------------------

class TestMinutes:
    def test_strings(self):
        assert logic._b2_minutes("00:00:00") == 0
        assert logic._b2_minutes("06:00") == 360
        assert logic._b2_minutes("23:59:59") == 1439

    def test_objects(self):
        assert logic._b2_minutes(dtime(14, 50)) == 14 * 60 + 50
        assert logic._b2_minutes(datetime(2026, 1, 1, 0, 30)) == 30

    def test_invalid(self):
        assert logic._b2_minutes(None) is None
        assert logic._b2_minutes("??") is None
        assert logic._b2_minutes("abc") is None


# -- _b2_extract_m_from_url ----------------------------------------------------

class TestExtractM:
    def test_six_digit(self):
        assert logic._b2_extract_m_from_url(
            "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044002") == "044002"

    def test_eight_digit(self):
        assert logic._b2_extract_m_from_url(
            "https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=00044002") == "00044002"

    def test_no_m(self):
        assert logic._b2_extract_m_from_url("https://radio.iranseda.ir/") is None
        assert logic._b2_extract_m_from_url(None) is None


# -- _b2_broadcast_days --------------------------------------------------------

def _d(dow, tmin):
    return {"day_of_week": dow, "time_min": tmin}


class TestBroadcastDays:
    def test_weekdays_and_matches(self):
        # declared start 16:00 = 960 min; rows within 15 min match
        dates = [
            _d(5, 960), _d(5, 965),   # Fri, both match (16:00, 16:05)
            _d(2, 961),                # Tue, match
            _d(4, 720),                # Thu, does not match (12:00)
        ]
        r = logic._b2_broadcast_days(dates, "16:00:00")
        assert r["days"] == [2, 4, 5]
        assert r["time_match"] == 3

    def test_boundary_15_minutes(self):
        assert logic._b2_broadcast_days([_d(1, 945)], "16:00")["time_match"] == 1
        assert logic._b2_broadcast_days([_d(1, 944)], "16:00")["time_match"] == 0
        assert logic._b2_broadcast_days([_d(1, 976)], "16:00")["time_match"] == 0
        assert logic._b2_broadcast_days([_d(1, 975)], "16:00")["time_match"] == 1

    def test_no_declared_start_counts_rows_only(self):
        r = logic._b2_broadcast_days([_d(1, 100), _d(3, 200)], None)
        assert r["days"] == [1, 3]
        assert r["time_match"] == 0

    def test_empty_window_returns_empty(self):
        assert logic._b2_broadcast_days([], "16:00") == {"days": [], "time_match": 0}

    def test_missing_time_min_ignored_in_matches(self):
        r = logic._b2_broadcast_days([_d(1, None), _d(2, 960)], "16:00")
        assert r["days"] == [1, 2]
        assert r["time_match"] == 1


# -- _b2_schedule_status -------------------------------------------------------

class TestScheduleStatus:
    def test_stable(self):
        dates = [_d(2, 960), _d(4, 963), _d(5, 958)]
        assert logic._b2_schedule_status(dates, "16:00") == "stable"

    def test_irregular(self):
        dates = [_d(2, 960), _d(4, 1200)]
        assert logic._b2_schedule_status(dates, "16:00") == "irregular"

    def test_no_declared_start(self):
        assert logic._b2_schedule_status([_d(1, 100)], None) == "no_declared_start"

    def test_no_data(self):
        assert logic._b2_schedule_status([], "16:00") == "no_data"

    def test_irregular_when_row_lacks_time(self):
        # a row without a parseable start time never matches -> irregular
        assert logic._b2_schedule_status([_d(1, None), _d(2, 960)], "16:00") == "irregular"


# -- SQL constant checks (the query string must be the canonical form) --------

def test_tz_helper_unchanged():
    assert logic._TZ_OFF == "+03:30"
    assert logic._tzcol("x") == "CONVERT_TZ(x, '+00:00', '+03:30')"


# ---------------------------------------------------------------------------
# Self-runner: the dashboard venv on server 53 has no pytest, so this file is
# also runnable directly:  python tests/test_b2_management_list.py
# ---------------------------------------------------------------------------

def main():
    import traceback
    failures = 0
    count = 0
    for name, cls in sorted(globals().items()):
        if not (name.startswith("Test") and isinstance(cls, type)):
            continue
        for tname in sorted(dir(cls)):
            if not tname.startswith("test_"):
                continue
            count += 1
            inst = cls()
            fn = getattr(inst, tname)
            try:
                fn()
            except Exception:  # noqa: BLE001
                failures += 1
                print("FAIL %s.%s" % (name, tname))
                traceback.print_exc()
    print("%d tests, %d failures" % (count, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
