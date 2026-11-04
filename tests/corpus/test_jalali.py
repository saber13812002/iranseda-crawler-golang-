"""Vendored Jalali conversion vs the jdatetime-generated verification table."""

import json
import os

from corpus import jalali

TABLE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "corpus", "verification", "jalali_table.json")


def _rows():
    with open(TABLE, encoding="utf-8") as f:
        return json.load(f)


def test_table_loads():
    rows = _rows()
    assert len(rows) >= 700, "verification table too small: %d" % len(rows)


def test_all_j2g_rows_match_jdatetime():
    bad = []
    for (jy, jm, jd, gy, gm, gd) in _rows():
        got = jalali.jalali_to_gregorian(jy, jm, jd)
        if got != (gy, gm, gd):
            bad.append(((jy, jm, jd), got, (gy, gm, gd)))
    assert not bad, "mismatches: %s" % bad[:5]


def test_round_trip_g2j():
    bad = []
    for (jy, jm, jd, gy, gm, gd) in _rows():
        got = jalali.gregorian_to_jalali(gy, gm, gd)
        if got != (jy, jm, jd):
            bad.append(((gy, gm, gd), got, (jy, jm, jd)))
    assert not bad, "round-trip mismatches: %s" % bad[:5]


def test_nowruz_anchors():
    # Nowruz anchors from the jdatetime-generated table
    expect = {
        1399: (2020, 3, 20),
        1400: (2021, 3, 21),
        1401: (2022, 3, 21),
        1402: (2023, 3, 21),
        1403: (2024, 3, 20),
        1404: (2025, 3, 21),
        1405: (2026, 3, 21),
    }
    for jy, g in expect.items():
        assert jalali.jalali_to_gregorian(jy, 1, 1) == g, (jy, g)


def test_leap_rules():
    # verified against nowruz anchors: 1399 (%33=13) and 1403 (%33=17) are
    # leap years; 1400-1402 (%33=14..16) and 1404-1405 (%33=18..19) are not.
    assert jalali.is_leap(1399)
    assert not jalali.is_leap(1400)
    assert not jalali.is_leap(1401)
    assert not jalali.is_leap(1402)
    assert jalali.is_leap(1403)
    assert not jalali.is_leap(1404)
    assert not jalali.is_leap(1405)
    assert jalali.days_in_month(1399, 12) == 30
    assert jalali.days_in_month(1403, 12) == 30
    assert jalali.days_in_month(1404, 12) == 29
    try:
        jalali.validate(1404, 12, 30)
        raise AssertionError("1404-12-30 should be invalid")
    except ValueError:
        pass
    jalali.validate(1399, 12, 30)  # valid in leap year


def test_validate_rejects_garbage():
    for args in ((1400, 0, 1), (1400, 13, 1), (1400, 1, 0), (1400, 1, 32),
                 (9378, 1, 1), ("a", 1, 1)):
        try:
            jalali.validate(*args)
            raise AssertionError("should reject %r" % (args,))
        except (ValueError, TypeError):
            pass


def test_parse_broadcast_real_stems():
    # real production stem (Jalali 1400-01-14 15:00)
    r = jalali.parse_broadcast("radio-maaref-00-01-14-15-00")
    assert r["jalali"]["date"] == "1400-01-14"
    assert r["jalali"]["time"] == "15:00:00"
    assert r["jalali"]["source"] == "filename"
    assert r["gregorian"]["source"] == "derived_from_jalali_filename"
    assert r["gregorian"]["conversion"]
    # the gregorian date must agree with the verification table
    row = [x for x in _rows() if x[:3] == [1400, 1, 14]][0]
    assert r["gregorian"]["date"] == "%04d-%02d-%02d" % tuple(row[3:6])

    r2 = jalali.parse_broadcast("radio-farhangian-03-07-15-23-30")
    assert r2["jalali"]["date"] == "1403-07-15"
    assert r2["jalali"]["time"] == "23:30:00"


def test_parse_broadcast_rejects_bad_stems():
    for stem in ("", "weird.mp3", "radio-maaref-00-13-01-00-00",
                 "radio-maaref-00-01-32-00-00", "radio-maaref-00-01-01-25-00",
                 "radio_maaref_00_01_01_00_00", "RADIO-MAAREF-00-01-01-00-00"):
        assert jalali.parse_broadcast(stem) is None, stem


def test_stem_of():
    assert jalali.stem_of("radio-a-00-01-01-00-00.mp3") == "radio-a-00-01-01-00-00"
    assert jalali.stem_of(None) == ""
    assert jalali.stem_of("") == ""
