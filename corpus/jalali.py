"""Jalali <-> Gregorian date conversion, vendored (pure stdlib).

The conversion algorithms are vendored from the `jalali_core` package
(which `jdatetime` 6.x depends on), i.e. the FarsiWeb `jalali.c` lineage:

  Copyright (C) 2001  Roozbeh Pournader <roozbeh@sharif.edu>
  Copyright (C) 2001  Mohammad Toossi <mohammad@bamdad.org>
  Copyright (C) 2003-2011 Parspooyesh Fanavar (http://parspooyesh.com/)
  jdatetime is (c) 2010-2011 Milad Rastian <eslashmili at gmail.com>.

Original license: GNU Lesser General Public License v2.1 or later.
See https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html

Why vendored: the production host's venv only ships pymysql; the corpus
package must run on stdlib + pymysql alone. Verification against the
authoritative library is embedded in the package:
  corpus/verification/jalali_table.json  (710 rows, Jalali 1399..1406,
  generated from jdatetime 6.1.1, including full round-trip checks).
tests/test_jalali.py asserts every row.

Leap rule (jdatetime `date.isleap`): a Jalali year is leap when
  year % 33 in (1, 5, 9, 13, 17, 22, 26, 30)
(30 Esfand exists in leap years).
"""

import re

CONVERSION_LIB = "corpus.jalali (vendored jalali_core / jdatetime 6.1.1 algorithm)"

G_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
J_DAYS_IN_MONTH = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

MINYEAR = 1
MAXYEAR = 9377


def is_leap(year):
    """True when the Jalali year has 30 Esfand (same rule as jdatetime)."""
    return year % 33 in (1, 5, 9, 13, 17, 22, 26, 30)


def days_in_month(year, month):
    """Days in Jalali month (1..12) of the given Jalali year."""
    if month == 12 and is_leap(year):
        return 30
    return J_DAYS_IN_MONTH[month - 1]


def validate(year, month, day):
    """Validate a Jalali date; raises ValueError on invalid input."""
    if not (isinstance(year, int) and isinstance(month, int) and isinstance(day, int)):
        raise TypeError("an integer is required")
    if year < MINYEAR or year > MAXYEAR:
        raise ValueError("year is out of range")
    if month < 1 or month > 12:
        raise ValueError("month must be in 1..12")
    if day < 1:
        raise ValueError("day is out of range for month")
    if month == 12 and day == 30 and is_leap(year):
        return  # 30 Esfand is OK in leap years
    if month == 12 and day == 30 and not is_leap(year):
        raise ValueError("day is out of range for month")
    if day > J_DAYS_IN_MONTH[month - 1]:
        raise ValueError("day is out of range for month")


def jalali_to_gregorian(year, month, day):
    """Jalali -> (gyear, gmonth, gday). Vendored from jalali_core.

    Algorithm based on FarsiWeb's jalali.c (see module docstring).
    """
    validate(year, month, day)
    jy = year - 979
    g_day_no = 365 * jy + (jy // 33) * 8 + (jy % 33 + 3) // 4 + day - 1 + 79
    for i in range(month - 1):
        g_day_no += J_DAYS_IN_MONTH[i]

    gy = 1600 + 400 * (g_day_no // 146097)  # 146097 = 365*400 + 400/4 - 400/100 + 400/400
    g_day_no %= 146097

    leap = 1
    if g_day_no >= 36525:  # 36525 = 365*100 + 100/4
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)  # 36524 = 365*100 + 100/4 - 100/100
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = 0

    gy += 4 * (g_day_no // 1461)  # 1461 = 365*4 + 4/4
    g_day_no %= 1461

    if g_day_no >= 366:
        leap = 0
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365

    i = 0
    while g_day_no >= G_DAYS_IN_MONTH[i] + (i == 1 and leap):
        g_day_no -= G_DAYS_IN_MONTH[i] + (i == 1 and leap)
        i += 1
    return (gy, i + 1, g_day_no + 1)


def gregorian_to_jalali(gyear, gmonth, gday):
    """Gregorian -> (jyear, jmonth, jday). Vendored from jalali_core."""
    gy = gyear - 1600
    gm = gmonth - 1

    j_day_no = (
        365 * gy + (gy + 3) // 4 - (gy + 99) // 100
        + (gy + 399) // 400 + gday - 1 - 79
    )
    for i in range(gm):
        j_day_no += G_DAYS_IN_MONTH[i]
    if gm > 1 and ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)):
        # leap and after Feb
        j_day_no += 1

    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        j_day_no -= 1
        jy += j_day_no // 365
        j_day_no %= 365

    i = 0
    for i in range(11):
        if not j_day_no >= J_DAYS_IN_MONTH[i]:
            i -= 1
            break
        j_day_no -= J_DAYS_IN_MONTH[i]

    return (jy, i + 2, j_day_no + 1)


# ---------------------------------------------------------------------------
# Broadcast-date parsing from canonical filenames
# ---------------------------------------------------------------------------

# radio-<chan>-JJ-MM-DD-HH-MM  (Jalali date, 2-digit year -> 14JJ).
# The live 53 production convention has exactly 5 numeric tokens (NO seconds);
# seconds are implicitly 00. Verified 2026-11-04 against 100% of DB audio
# filenames and all on-disk audio files (0 exceptions).
_STEM_RE = re.compile(
    r"^radio-(?P<chan>[A-Za-z]+)-"
    r"(?P<jy>\d{2})-(?P<jm>\d{2})-(?P<jd>\d{2})-"
    r"(?P<hh>\d{2})-(?P<mi>\d{2})$"
)


def stem_of(filename):
    """Filename -> stem without extension ('' when empty)."""
    if not filename:
        return ""
    return str(filename).split(".", 1)[0].strip()


def parse_broadcast(stem):
    """Parse a canonical filename stem into broadcast date+time.

    Returns dict with jalali/gregorian date/time and the conversion lib,
    or None when the stem does not match the pattern (caller must add a
    warning and emit broadcast=null — never guess).
    """
    m = _STEM_RE.match(stem or "")
    if not m:
        return None
    jy = 1400 + int(m.group("jy"))
    jm = int(m.group("jm"))
    jd = int(m.group("jd"))
    hh = int(m.group("hh"))
    mi = int(m.group("mi"))
    try:
        validate(jy, jm, jd)
    except ValueError:
        return None
    if hh > 23 or mi > 59:
        return None
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    time_s = "%02d:%02d:00" % (hh, mi)  # seconds implicitly 00 (5-token stems)
    return {
        "jalali": {
            "date": "%04d-%02d-%02d" % (jy, jm, jd),
            "time": time_s,
            "source": "filename",
        },
        "gregorian": {
            "date": "%04d-%02d-%02d" % (gy, gm, gd),
            "time": time_s,
            "source": "derived_from_jalali_filename",
            "conversion": CONVERSION_LIB,
        },
    }
