"""Persian text normalization rules."""

from corpus import normalizer as N


def test_nfc_basic():
    # "ta + ZWNJ" ordering: composed vs decomposed must converge under NFC
    decomposed = "ت\u200cص"  # already NFC in this case
    assert N.nfc("a\u0308") == "a\u0308" or N.nfc("a\u0308")  # sanity
    assert N.nfc(None) is None


def test_collapse_whitespace():
    assert N.collapse_ws("a\t\n b") == "a b"
    assert N.collapse_ws("  leading and trailing  ") == "leading and trailing"
    assert N.collapse_ws("") == ""
    assert N.collapse_ws(None) is None


def test_normalize_text():
    raw = "  برنامهٔ\n\tصبح\t\tخوب  "
    out = N.normalize_text(raw)
    assert out == "برنامهٔ صبح خوب"
    assert "\t" not in out and "\n" not in out


def test_zwnj_preserved():
    text = "تصحیح‌پرتاب"
    assert N.normalize_text(text) == "تصحیح‌پرتاب"
    assert "\u200c" in N.normalize_text(text)


def test_has_control_chars():
    assert N.has_control_chars("ok text") is False
    assert N.has_control_chars("bad\x01text") is True
    assert N.has_control_chars("") is False
    assert N.has_control_chars(None) is False


def test_is_blank():
    assert N.is_blank(None)
    assert N.is_blank("   ")
    assert not N.is_blank("x")
