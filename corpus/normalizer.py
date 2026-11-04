"""Text normalization (Persian-safe).

Rules (data model §6):
  * NFC-normalize all text fields.
  * Collapse whitespace: tabs/newlines/control chars -> single spaces,
    squeeze repeats, strip ends (legacy program names have embedded
    tabs/newlines).
  * Preserve zero-width non-joiner U+200C (part of Persian orthography).
  * The raw DB value is always kept in a *_raw field by the mapper.
"""

import unicodedata

_CTRL = [c for c in map(chr, range(0x20)) if c not in "\t\n\r"]


def nfc(text):
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    return unicodedata.normalize("NFC", text)


def collapse_ws(text):
    """Collapse all whitespace runs (incl. tabs/newlines) to single spaces."""
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    out = []
    prev_space = False
    for ch in text:
        if ch == " " or ch == "\t" or ch == "\n" or ch == "\r" or ch == "\f" or ch == "\v":
            if not prev_space:
                out.append(" ")
            prev_space = True
        else:
            out.append(ch)
            prev_space = False
    return "".join(out).strip()


def normalize_text(text):
    """NFC + whitespace collapse. The canonical corpus text transform."""
    if text is None:
        return None
    t = collapse_ws(nfc(text))
    return t if t else ("" if text not in (None, "") else None)


def is_blank(text):
    return text is None or str(text).strip() == ""


def has_control_chars(text):
    """True when the (raw) text contains control chars — used to flag
    malformed free-text fields (e.g. time_description)."""
    if not text:
        return False
    return any(ch in _CTRL or ord(ch) < 32 for ch in str(text))


def normalize_for_db(text):
    """For values that go back to a DB context (none today; helper kept
    for the future). Same as normalize_text but keeps single empty string
    as empty string rather than None."""
    if text is None:
        return None
    t = collapse_ws(nfc(text))
    return t
