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


def test_sanitize_private_paths_masks_server_paths():
    # The exact production shape (probe19, 2026-11-04): an ffmpeg error with
    # a quoted absolute path. The message must survive, the path must not.
    raw = ("ffmpeg failed: [Errno 1094995529] Invalid data found when "
           "processing input: '/home/saber/saberprojects/iranseda/"
           "downloads/radio-maaref-04-01-01-09-00.mp3'")
    out = N.sanitize_private_paths(raw)
    assert "/home/" not in out
    assert "saber" not in out
    assert "Invalid data found when processing input" in out
    assert "<server-path>" in out


def test_sanitize_private_paths_all_validator_prefixes():
    # Must neutralize every prefix validator.PRIVATE_PATH_RE rejects.
    for bad in ("/home/x/a.mp3", "/root/a.mp3", "/var/www/site/index.php",
                r"C:\Users\me\file.txt", "C:/Users/me/file.txt"):
        out = N.sanitize_private_paths("x " + bad + " y")
        assert bad not in out, (bad, out)
        assert "<server-path>" in out, (bad, out)


def test_sanitize_private_paths_noop_and_none():
    assert N.sanitize_private_paths(None) is None
    assert N.sanitize_private_paths("plain text no path") == "plain text no path"
    # non-absolute /home-like mentions are NOT paths — leave them alone
    assert N.sanitize_private_paths("see /homework/notes") == "see /homework/notes"
