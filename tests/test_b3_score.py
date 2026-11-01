"""
B3 — pure-function tests for the LLM content scoring helpers
(dashboard/logic.py). No DB, no network, no LLM: the deterministic parts
(Jalali->Gregorian date math, strict-JSON extraction, dimension clamping,
server-side total, confidence band) are tested here. The live collector +
LLM run + SQL layer are validated against the real site during the B3
checkpoint.

Ground-truth date anchors (verified against the live site's own weekday
labels — e.g. 'چهارشنبه 29 مهر 1405' is Wednesday 2026-10-21, and the
newest live card '10 آبان 1405' == today 2026-11-01):
    1 Farvardin 1403 == 2024-03-20  (1403 is a 366-day Jalali year)
    1 Farvardin 1405 == 2026-03-21
    29 Mehr 1405      == 2026-10-21

Run (server 53, dashboard venv):
    cd <repo> && dashboard/venv/bin/python tests/test_b3_score.py
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
import logic  # noqa: E402


# -- Jalali year / leap --------------------------------------------------------

class TestIsLeap:
    def test_1403_leap(self):
        assert logic._b3_is_leap(1403) is True

    def test_1405_not_leap(self):
        assert logic._b3_is_leap(1405) is False

    def test_1406_not_leap(self):
        assert logic._b3_is_leap(1406) is False

    def test_1408_leap(self):
        assert logic._b3_is_leap(1408) is True

    def test_1404_not_leap(self):
        assert logic._b3_is_leap(1404) is False


# -- Jalali -> Gregorian --------------------------------------------------------

class TestJalaliToDate:
    def test_anchor_day(self):
        assert logic._b3_jalali_to_date(1403, 1, 1) == date(2024, 3, 20)

    def test_last_day_of_leap_1403(self):
        assert logic._b3_jalali_to_date(1403, 12, 30) == date(2025, 3, 20)

    def test_live_label_29_mehr_1405(self):
        # 'چهارشنبه 29 مهر 1405' on the site == Wednesday 2026-10-21
        assert logic._b3_jalali_to_date(1405, 7, 29) == date(2026, 10, 21)

    def test_month_boundary_mehr_to_aban(self):
        assert logic._b3_jalali_to_date(1405, 7, 30) == date(2026, 10, 22)
        assert logic._b3_jalali_to_date(1405, 8, 1) == date(2026, 10, 23)

    def test_nowruz_1405(self):
        assert logic._b3_jalali_to_date(1405, 1, 1) == date(2026, 3, 21)

    def test_mid_year(self):
        # 1 Tir 1405 == 2026-06-22, so 12 Tir 1405 == 2026-07-03
        assert logic._b3_jalali_to_date(1405, 4, 12) == date(2026, 7, 3)

    def test_before_anchor(self):
        # 29 Esfand 1402 == the day before Nowruz 1403 (2024-03-19)
        assert logic._b3_jalali_to_date(1402, 12, 29) == date(2024, 3, 19)

    def test_invalid_month(self):
        assert logic._b3_jalali_to_date(1405, 13, 1) is None

    def test_invalid_day_for_month(self):
        assert logic._b3_jalali_to_date(1405, 7, 31) is None  # Mehr = 30 days

    def test_invalid_esfand_non_leap(self):
        assert logic._b3_jalali_to_date(1405, 12, 30) is None

    def test_garbage(self):
        assert logic._b3_jalali_to_date("x", 1, 1) is None
        assert logic._b3_jalali_to_date(1405, "meh", 1) is None


# -- card label parsing ---------------------------------------------------------

class TestParseCardDate:
    def test_ascii_digits(self):
        assert logic._b3_parse_card_date("29 مهر 1405") == date(2026, 10, 21)

    def test_padded_day(self):
        assert logic._b3_parse_card_date("01 آبان 1405") == date(2026, 10, 23)

    def test_farsi_digits(self):
        assert logic._b3_parse_card_date("29 مهر ۱۴۰۵") == date(2026, 10, 21)

    def test_arabic_digits(self):
        assert logic._b3_parse_card_date("٢٩ مهر ١٤٠٥") == date(2026, 10, 21)

    def test_missing_year(self):
        assert logic._b3_parse_card_date("29 مهر") is None

    def test_unknown_month(self):
        assert logic._b3_parse_card_date("29 ماهفوق 1405") is None

    def test_empty_and_none(self):
        assert logic._b3_parse_card_date("") is None
        assert logic._b3_parse_card_date(None) is None

    def test_garbage(self):
        assert logic._b3_parse_card_date("hello world") is None
        assert logic._b3_parse_card_date("31 مهر 1405") is None


# -- strict-JSON extraction -----------------------------------------------------

class TestExtractJson:
    def test_clean(self):
        data, err = logic._b3_extract_json('{"a": 1}')
        assert err is None and data == {"a": 1}

    def test_markdown_fence(self):
        data, err = logic._b3_extract_json('```json\n{"a": {"b": 2}}\n```')
        assert err is None and data == {"a": {"b": 2}}

    def test_prose_around(self):
        data, err = logic._b3_extract_json(
            'Sure! Here you go: {"a": 1} — hope that helps.')
        assert err is None and data == {"a": 1}

    def test_braces_inside_string(self):
        data, err = logic._b3_extract_json('{"s": "a {b} c", "n": 2}')
        assert err is None and data == {"s": "a {b} c", "n": 2}

    def test_escaped_quotes(self):
        data, err = logic._b3_extract_json('{"s": "he said \\"hi\\" ok"}')
        assert err is None and data == {"s": 'he said "hi" ok'}

    def test_first_object_wins(self):
        data, err = logic._b3_extract_json('{"a": 1} garbage {"b": 2}')
        assert err is None and data == {"a": 1}

    def test_no_object(self):
        data, err = logic._b3_extract_json("no json here")
        assert data is None and err == "no JSON object found"

    def test_array_is_rejected(self):
        data, err = logic._b3_extract_json("[1, 2, 3]")
        assert data is None and err == "no JSON object found"

    def test_unbalanced(self):
        data, err = logic._b3_extract_json('{"a": 1')
        assert data is None and err == "unbalanced JSON"

    def test_invalid_json(self):
        data, err = logic._b3_extract_json('{"a": }')
        assert data is None and err.startswith("invalid JSON")

    def test_empty(self):
        data, err = logic._b3_extract_json("")
        assert data is None and err == "empty response"


# -- clamping / total / confidence ---------------------------------------------

ALL_DIMS = {"continuity": 25, "audio_quality": 20, "content_value": 20,
            "weekly_count": 15, "asr_duration": 10, "not_repeat": 10}


class TestClampDims:
    def test_in_range_unchanged(self):
        out = logic._b3_clamp_dims(dict(ALL_DIMS))
        assert out == {k: float(v) for k, v in ALL_DIMS.items()}

    def test_keys_exact_and_ordered(self):
        out = logic._b3_clamp_dims({})
        assert list(out.keys()) == [k for k, _ in logic._B3_DIMS]

    def test_clamped_to_max(self):
        out = logic._b3_clamp_dims({"continuity": 99, "not_repeat": 100})
        assert out["continuity"] == 25.0
        assert out["not_repeat"] == 10.0

    def test_negative_zeroed(self):
        out = logic._b3_clamp_dims({"continuity": -5})
        assert out["continuity"] == 0.0

    def test_non_numeric_zeroed(self):
        out = logic._b3_clamp_dims({"audio_quality": "abc", "content_value": None})
        assert out["audio_quality"] == 0.0
        assert out["content_value"] == 0.0

    def test_missing_zeroed(self):
        out = logic._b3_clamp_dims({})
        assert all(v == 0.0 for v in out.values())

    def test_rounds_one_decimal(self):
        out = logic._b3_clamp_dims({"weekly_count": 1.2345})
        assert out["weekly_count"] == 1.2

    def test_unknown_keys_ignored(self):
        out = logic._b3_clamp_dims({"continuity": 5, "invented": 99})
        assert "invented" not in out


class TestTotal:
    def test_perfect(self):
        assert logic._b3_total(logic._b3_clamp_dims(dict(ALL_DIMS))) == 100.0

    def test_partial(self):
        out = logic._b3_clamp_dims({"continuity": 1.1, "not_repeat": 2.2})
        assert logic._b3_total(out) == 3.3

    def test_zero(self):
        assert logic._b3_total(logic._b3_clamp_dims({})) == 0.0

    def test_never_over_100(self):
        assert logic._b3_total(logic._b3_clamp_dims(dict(ALL_DIMS))) <= 100.0


class TestConfidence:
    def test_high(self):
        assert logic._b3_confidence(80.0) == "high"
        assert logic._b3_confidence(95.3) == "high"

    def test_medium(self):
        assert logic._b3_confidence(79.9) == "medium"
        assert logic._b3_confidence(60.0) == "medium"

    def test_low(self):
        assert logic._b3_confidence(59.9) == "low"
        assert logic._b3_confidence(0.0) == "low"

    def test_none(self):
        assert logic._b3_confidence(None) is None


# -- schema invariants ----------------------------------------------------------

def test_dim_weights_sum_to_100():
    assert sum(mx for _k, mx in logic._B3_DIMS) == 100


# ---------------------------------------------------------------------------
# Self-runner: the dashboard venv on server 53 has no pytest, so this file is
# also runnable directly:  python tests/test_b3_score.py
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
