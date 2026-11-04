"""SRT parsing: both live timestamp formats + edge cases."""

from corpus import srt as S

ORIGINAL = """1
00:00:00,000 --> 00:00:03,500
سلام و درود

2
00:00:03,500 --> 00:00:07,250
به برنامهٔ امروز خوش آمدید
"""

CORRECTED = """1
0:00:00 --> 0:00:30
سلام و درود

2
0:00:30 --> 0:01:00
به برنامهٔ امروز خوش آمدید
"""


def test_original_format_parses():
    cues, err = S.parse_srt(ORIGINAL)
    assert err is None
    assert len(cues) == 2
    assert cues[0]["start"] == 0.0
    assert abs(cues[0]["end"] - 3.5) < 1e-9
    assert cues[1]["start"] == 3.5
    assert "سلام" in cues[0]["text"]


def test_corrected_format_no_ms_parses():
    cues, err = S.parse_srt(CORRECTED)
    assert err is None
    assert len(cues) == 2
    assert cues[0]["start"] == 0.0
    assert cues[0]["end"] == 30.0
    assert cues[1]["end"] == 60.0


def test_stats():
    seg, dur = S.srt_stats(ORIGINAL)
    assert seg == 2
    assert abs(dur - 7.25) < 1e-9
    seg2, dur2 = S.srt_stats(CORRECTED)
    assert seg2 == 2
    assert dur2 == 60.0


def test_garbage_rejected():
    cues, err = S.parse_srt("this is not an srt file\njust text")
    assert cues == [] and err is not None
    seg, dur = S.srt_stats("")
    assert seg is None and dur is None
    seg, dur = S.srt_stats(None)
    assert seg is None and dur is None


def test_ts_variants():
    assert S.ts_to_seconds("00:00:03,500") == 3.5
    assert S.ts_to_seconds("1:02:03") == 3723.0
    assert S.ts_to_seconds("00:00:03.5") == 3.5
    assert S.ts_to_seconds("bad") is None
    assert S.ts_to_seconds("00:99:00") is None
    assert S.ts_to_seconds("00:00:61") is None


def test_srt_to_text():
    txt = S.srt_to_text(ORIGINAL)
    assert txt is not None
    assert "سلام و درود" in txt
    assert len(txt.splitlines()) == 2


def test_bom_and_crlf():
    blob = "\ufeff1\r\n00:00:00,000 --> 00:00:01,000\r\nhi\r\n"
    cues, err = S.parse_srt(blob)
    assert err is None and len(cues) == 1 and cues[0]["text"] == "hi"


def test_looks_like_srt():
    assert S.looks_like_srt(ORIGINAL)
    assert not S.looks_like_srt("no cues here")
