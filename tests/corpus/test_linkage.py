"""Offline unit tests for corpus.linkage (Stage 2).

No network access: validate_link gets an injectable fake fetcher.
Run via:  python tests/corpus/run_all.py
"""

import re

from corpus import linkage
from corpus.linkage import (
    FetchError, FetchTimeout, RedirectOut,
    build_episode_url, build_day_archive_url, build_time_slot_url,
    build_program_page_url, link_type_of, site_date_from_gregorian,
    classify_date, normalize_text, extract_title, hhmm, validate_link,
    JALALI_MONTH_NAMES,
)

BASE = "https://radio.iranseda.ir/"
EP_URL = BASE + "epgarchivePart/?VALID=TRUE&ch=14&e=154148408"
MISSION_EP_URL = BASE + "epgarchivePart/?VALID=TRUE&ch=14&e=154148409"
DAY_URL = BASE + "timeArchive/?VALID=TRUE&ch=14&d=11/5/2026"
TS_URL = BASE + "timeArchivePart/?VALID=TRUE&ch=14&ti=12:30&d=11/5/2026"
PROG_URL = BASE + "Program/?VALID=TRUE&ch=14&m=044125"

# 2026-11-05 gregorian == 1405-08-14 jalali (Aban 14, 1405)
SESSION = {
    "id": 10884, "ch": 14, "e": "154148408",
    "filename": "radio-maaref-05-08-14-12-30.mp4",
    "program_name": "رهنمود",
}
PROGRAM = {"id": 5, "name": "رهنمود", "url": PROG_URL, "m": "043100"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class FakeFetch(object):
    """url -> response dict or Exception; records calls."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def __call__(self, url, timeout=15.0, host=None):
        self.calls.append(url)
        v = self.mapping[url]
        if isinstance(v, Exception):
            raise v
        if isinstance(v, type):
            raise v("synthetic")
        return v


def resp(status=200, title="", body="", final_url=None):
    html = ("<html><head><title>%s</title></head><body>%s</body></html>"
            % (title, body))
    return {"status": status, "body": html,
            "final_url": final_url or None, "elapsed": 0.2, "redirects": []}


def episode_body(e, extra=""):
    return ('<meta androidAddress="https://player.iranseda.ir/epg-player/?VALID=TRUE&e=%s">'
            '<a href="?ch=14&e=%s">p</a>%s') % (e, e, extra)


def day_body(days, ch=14):
    return "".join(
        '<a href="timeArchive/?VALID=TRUE&ch=%d&d=%s">x</a>' % (ch, d) for d in days
    )


DAY_WINDOW_OK = ["11/2/2026", "11/3/2026", "11/4/2026", "11/5/2026",
                 "11/6/2026", "11/7/2026", "11/8/2026"]


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def test_build_episode_url():
    assert build_episode_url(14, "154148409") == MISSION_EP_URL
    assert build_episode_url(14, SESSION["e"]) == EP_URL
    assert build_episode_url("18", 123, site_base="https://radio.iranseda.ir") == \
        BASE + "epgarchivePart/?VALID=TRUE&ch=18&e=123"
    try:
        build_episode_url(14, "")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_site_date_month_first_unpadded():
    # OQ-1: gregorian, month-first M/D/YYYY, unpadded
    assert site_date_from_gregorian("2026-11-05") == "11/5/2026"
    assert site_date_from_gregorian("2026-01-02") == "1/2/2026"
    assert site_date_from_gregorian("2026-05-11") == "5/11/2026"


def test_build_day_archive_url():
    assert build_day_archive_url(14, "2026-11-05") == DAY_URL
    assert build_day_archive_url(18, "2026-01-02") == \
        BASE + "timeArchive/?VALID=TRUE&ch=18&d=1/2/2026"


def test_build_time_slot_url():
    assert build_time_slot_url(14, "12:30:00", "2026-11-05") == TS_URL
    assert build_time_slot_url(14, "12:30", "2026-11-05") == TS_URL
    try:
        build_time_slot_url(14, "3:99", "2026-11-05")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_build_program_page_url_verbatim_and_normalized():
    out = build_program_page_url({"url": PROG_URL, "m": "044125"})
    assert out["raw"] == PROG_URL  # verbatim (A7), no re-derivation
    assert out["normalized"] == PROG_URL  # already canonical order
    # re-order/standardize only:
    out2 = build_program_page_url({"url": "https://radio.iranseda.ir/Program/?m=044125&VALID=TRUE&ch=14"})
    assert out2["normalized"] == PROG_URL
    # empty url -> null by policy
    assert build_program_page_url({"url": ""}) == {"raw": None, "normalized": None}
    assert build_program_page_url({}) == {"raw": None, "normalized": None}


def test_link_type_of():
    assert link_type_of(EP_URL) == "episode"
    assert link_type_of(DAY_URL) == "day_archive"
    assert link_type_of(TS_URL) == "time_slot"
    assert link_type_of(PROG_URL) == "program_page"
    assert link_type_of(BASE + "nope/") is None


def test_hhmm_truncation():
    assert hhmm("12:30:00") == "12:30"
    assert hhmm("0:05:30") == "0:05"
    assert hhmm("23:59") == "23:59"


# ---------------------------------------------------------------------------
# normalization + title extraction
# ---------------------------------------------------------------------------

def test_normalize_text_digits_and_diacritics():
    # Persian digits fold to ASCII
    assert normalize_text("۱۲۳") == "123"
    # Arabic-Indic digits fold too
    assert normalize_text("٠١٢") == "012"
    # zero-width non-joiner / joiner / BOM stripped
    assert normalize_text("رهن\u200cود") == "رهنود"
    assert normalize_text("رهن\u200dود") == "رهنود"
    assert normalize_text("\ufeffرهنود") == "رهنود"
    # casefold
    assert normalize_text("ABC") == "abc"
    # whitespace collapsed
    assert normalize_text("a  b\n c") == "a b c"
    # NFC determinism
    assert normalize_text("شفا") == "شفا"
    # None-safe
    assert normalize_text(None) == ""


def test_extract_title():
    assert extract_title("<html><title>  X  </title></html>") == "X"
    assert extract_title("<html><title></title></html>") is None
    assert extract_title("<html></html>") is None
    assert extract_title("") is None


# ---------------------------------------------------------------------------
# classify_date
# ---------------------------------------------------------------------------

def test_classify_date_unverified_canonical():
    cd = classify_date(SESSION)
    assert cd["status"] == "unverified"
    assert cd["timezone"] == "Asia/Tehran"
    assert cd["jalali"]["date"] == "1405-08-14"
    assert cd["jalali"]["time"] == "12:30:00"
    assert cd["gregorian"]["date"] == "2026-11-05"
    assert cd["raw"]["filename"] == "radio-maaref-05-08-14-12-30.mp4"
    # confirmed flag flips status when an archive page matched
    cd2 = classify_date(SESSION, verified=True)
    assert cd2["status"] == "confirmed"


def test_classify_date_impossible_implausible_year():
    cd = classify_date({"filename": "radio-maaref-97-12-28-20-30.mp3"})
    assert cd["status"] == "impossible"
    assert "implausible_year" in cd["reasons"]
    # raw preserved
    assert cd["raw"]["filename"] == "radio-maaref-97-12-28-20-30.mp3"
    assert cd["jalali"]["date"] == "1497-12-28"


def test_classify_date_none_no_source():
    cd = classify_date({"filename": "weird-name.mp3"})
    assert cd["status"] == "none"
    assert cd["jalali"] is None


def test_classify_date_gregorian_crosscheck_mismatch():
    # filename says 1405-08-14 (=2026-11-05) but explicit gregorian is 2027-01-01
    cd = classify_date({
        "filename": "radio-maaref-05-08-14-12-30.mp4",
        "broadcast_gregorian": "2027-01-01",
    })
    assert cd["status"] == "impossible"
    assert "gregorian_jalali_mismatch" in cd["reasons"]


# ---------------------------------------------------------------------------
# validate_link: episode
# ---------------------------------------------------------------------------

def test_validate_episode_valid():
    f = FakeFetch({EP_URL: resp(title="آرشیو رادیو - برنامه رهنمود - ",
                                body=episode_body(SESSION["e"]))})
    r = validate_link(EP_URL, session=SESSION, program=PROGRAM, fetch=f)
    assert r["status"] == "valid", r
    assert r["reason"] is None
    assert r["http_status"] == 200
    assert r["evidence"]["e_id_occurrences"] == 2
    assert r["last_verified_at"]
    assert len(f.calls) == 1


def test_validate_mission_synthetic_episode():
    # mission sample e=154148409 (absent from DB) is a live episode
    s = {"ch": 14, "e": "154148409", "filename": None, "id": None,
         "program_name": "به امید دیدار"}
    f = FakeFetch({MISSION_EP_URL: resp(
        title="آرشیو رادیو - برنامه به امید دیدار - ",
        body=episode_body("154148409"))})
    r = validate_link(MISSION_EP_URL, session=s, fetch=f)
    assert r["status"] == "valid", r


def test_validate_episode_id_mismatch():
    f = FakeFetch({EP_URL: resp(title="آرشیو رادیو - برنامه رهنمود - ",
                                body=episode_body("999999999"))})
    r = validate_link(EP_URL, session=SESSION, fetch=f)
    assert r["status"] == "invalid"
    assert r["reason"] == "id_mismatch"


def test_validate_episode_title_mismatch():
    f = FakeFetch({EP_URL: resp(title="آرشیو رادیو - برنامه برنامه دیگر - ",
                                body=episode_body(SESSION["e"]))})
    r = validate_link(EP_URL, session=SESSION, fetch=f)
    assert r["status"] == "invalid"
    assert r["reason"] == "title_mismatch"


def test_validate_episode_no_fetch_on_session_mismatch():
    f = FakeFetch({EP_URL: resp(body=episode_body(SESSION["e"]))})
    r = validate_link(EP_URL, session=dict(SESSION, e="123456789"), fetch=f)
    assert r["status"] == "invalid"
    assert r["reason"] == "id_mismatch"
    assert f.calls == []  # never hit the network


def test_validate_episode_404():
    f = FakeFetch({EP_URL: resp(status=404, body="<html>not found</html>")})
    r = validate_link(EP_URL, fetch=f)
    assert (r["status"], r["reason"]) == ("invalid", "not_found")


def test_validate_episode_blocked():
    f = FakeFetch({EP_URL: resp(status=403, body="")})
    r = validate_link(EP_URL, fetch=f)
    assert (r["status"], r["reason"]) == ("unverified", "blocked")


def test_validate_episode_other_http_error():
    f = FakeFetch({EP_URL: resp(status=500, body="")})
    r = validate_link(EP_URL, fetch=f)
    assert (r["status"], r["reason"]) == ("invalid", "http_error")


def test_validate_episode_timeout():
    f = FakeFetch({EP_URL: FetchTimeout("timed out")})
    r = validate_link(EP_URL, fetch=f)
    assert (r["status"], r["reason"]) == ("unverified", "timeout")


def test_validate_episode_network_error():
    f = FakeFetch({EP_URL: FetchError("connection refused")})
    r = validate_link(EP_URL, fetch=f)
    assert (r["status"], r["reason"]) == ("unverified", "http_error")


def test_validate_episode_redirect_out():
    f = FakeFetch({EP_URL: RedirectOut("https://evil.example/x")})
    r = validate_link(EP_URL, fetch=f)
    assert (r["status"], r["reason"]) == ("invalid", "redirect_out")
    assert r["evidence"]["redirect_to"] == "https://evil.example/x"


def test_validate_episode_unsupported_url():
    try:
        validate_link(BASE + "whatever/?x=1", fetch=FakeFetch({}))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# validate_link: day archive
# ---------------------------------------------------------------------------

def test_validate_day_archive_valid():
    f = FakeFetch({DAY_URL: resp(title="رادیو معارف - آرشیو زمانی",
                                 body=day_body(days=DAY_WINDOW_OK) + "رهنود")})
    r = validate_link(DAY_URL, session=SESSION, program=PROGRAM, fetch=f)
    assert r["status"] == "valid", r
    assert r["evidence"]["d_target"] == "2026-11-05"
    assert r["evidence"]["d_window_prev_days"] == 3
    assert r["evidence"]["d_window_next_days"] == 3


def test_validate_day_archive_date_mismatch_off_center():
    # window is entirely in the past (no days after target)
    days = ["10/30/2026", "10/31/2026", "11/1/2026", "11/2/2026",
            "11/3/2026", "11/4/2026", "11/5/2026"]  # target 11/5 is the edge
    f = FakeFetch({DAY_URL: resp(title="x", body=day_body(days=days))})
    r = validate_link(DAY_URL, fetch=f)
    assert (r["status"], r["reason"]) == ("invalid", "date_mismatch")


def test_validate_day_archive_soft_warn_program():
    f = FakeFetch({DAY_URL: resp(title="رادیو معارف - آرشیو زمانی",
                                 body=day_body(days=DAY_WINDOW_OK))})
    r = validate_link(DAY_URL, session=SESSION, program=PROGRAM, fetch=f)
    assert r["status"] == "valid"
    assert "program_name_not_on_page" in r["warnings"]
    assert "m_id_not_in_body" in r["warnings"]


# ---------------------------------------------------------------------------
# validate_link: time slot
# ---------------------------------------------------------------------------

def test_validate_time_slot_valid():
    title = "آرشیو رادیو - پنجشنبه 14 آبان 1405 - ساعت 12:30"
    f = FakeFetch({TS_URL: resp(title=title, body="رهنمود")})
    r = validate_link(TS_URL, session=SESSION, program=PROGRAM, fetch=f)
    assert r["status"] == "valid", r
    assert r["evidence"]["title_has_time"] is True
    assert r["evidence"]["title_has_date"] is True


def test_validate_time_slot_time_mismatch():
    title = "آرشیو رادیو - پنجشنبه 14 آبان 1405 - ساعت 13:30"
    f = FakeFetch({TS_URL: resp(title=title, body="")})
    r = validate_link(TS_URL, fetch=f)
    assert (r["status"], r["reason"]) == ("invalid", "time_mismatch")


def test_validate_time_slot_date_mismatch():
    title = "آرشیو رادیو - پنجشنبه 15 آبان 1405 - ساعت 12:30"
    f = FakeFetch({TS_URL: resp(title=title, body="")})
    r = validate_link(TS_URL, fetch=f)
    assert (r["status"], r["reason"]) == ("invalid", "date_mismatch")


def test_validate_time_slot_empty_page():
    # the probed failure mode: 15-byte page with no title and no e-ids
    f = FakeFetch({TS_URL: resp(title="", body="<html></html>")})
    r = validate_link(TS_URL, fetch=f)
    assert r["status"] == "invalid"
    assert r["reason"] in ("time_mismatch", "date_mismatch")


# ---------------------------------------------------------------------------
# validate_link: program page
# ---------------------------------------------------------------------------

def test_validate_program_valid():
    body = ('<img src="picturebymmc?chn=radio-maaref&s=c&m=044125">'
            '<img src="picturebymmc?chn=radio-maaref&s=c&m=044125">')
    f = FakeFetch({PROG_URL: resp(title="برنامه پیام ولایت", body=body)})
    r = validate_link(PROG_URL, program={"name": "پیام ولایت", "m": "044125"},
                      fetch=f)
    assert r["status"] == "valid", r
    assert r["evidence"]["m_id_occurrences"] == 2


def test_validate_program_title_mismatch():
    f = FakeFetch({PROG_URL: resp(title="برنامه دیگری", body="m=044125")})
    r = validate_link(PROG_URL, program={"name": "پیام ولایت", "m": "044125"},
                      fetch=f)
    assert (r["status"], r["reason"]) == ("invalid", "title_mismatch")


def test_validate_program_program_mismatch():
    f = FakeFetch({PROG_URL: resp(title="برنامه پیام ولایت", body="nothing")})
    r = validate_link(PROG_URL, program={"name": "پیام ولایت", "m": "044125"},
                      fetch=f)
    assert (r["status"], r["reason"]) == ("invalid", "program_mismatch")


def test_validate_program_m_mismatch_prefetch():
    f = FakeFetch({PROG_URL: resp(title="x", body="m=044125")})
    r = validate_link(PROG_URL, program={"name": "پیام ولایت", "m": "099999"},
                      fetch=f)
    assert (r["status"], r["reason"]) == ("invalid", "program_mismatch")
    assert f.calls == []


def test_jalali_month_names_present():
    assert len(JALALI_MONTH_NAMES) == 12
    assert JALALI_MONTH_NAMES[7] == "آبان"
