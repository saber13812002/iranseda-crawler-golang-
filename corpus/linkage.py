"""Source-linkage URL builders + HTTP validation for the 4 IranSeda link types.

Stage 2 (mission 2026-11-05). Implements the normative contract in
``docs/corpus/CORPUS_LINKAGE_SPEC.md`` §6, updated with the Stage 2
read-only probe findings (all closed, see reports/corpus/CORPUS_LINKAGE_STAGE2.md):

* OQ-1 (``d=`` parameter): the live site's archive convention is
  **gregorian, month-first, UNPADDED** (``M/D/YYYY``, e.g. ``11/5/2026``).
  Evidence: ``d=14/8/1405`` (day-first/jalali) returns the ASP.NET error
  ``Conversion failed when converting date and/or time from character
  string.``; ``d=5/11/2026`` renders a 7-day window 5/8..5/14/2026 (May,
  i.e. month-first). This supersedes the §6.2 "day-first, zero-padded"
  assumption; the spec already anticipated the switch ("if the probe
  shows ..., the contract value switches").
* OQ-2: episode page = ``epgarchivePart``; ``<title>`` =
  ``آرشیو رادیو - برنامه {program_name} -``; the ``e`` id occurs in
  ``<meta androidAddress="...&e={e}">`` and in the body.
* OQ-3: program intro page = ``radio_programs.url`` verbatim (live 200).
* OQ-7: HEAD is supported (Content-Length == GET body); GET stays the
  validation default (title extraction needs the body).
* OQ-8: the site wall clock is Asia/Tehran local.
* OQ-11: 100% of session links are ``ch=`` + ``e=`` (no ``m=``).

Constraints:
  * Python stdlib only (same as the rest of the corpus package).
  * Read-only: validation performs GET requests only; never mutates state.
  * Offline-testable: :func:`validate_link` accepts an injectable
    ``fetch`` callable, so the unit tests run with zero network access.
"""

import datetime as _dt
import html as _html
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from corpus import jalali

__all__ = [
    "TIMEZONE", "JALALI_MONTH_NAMES",
    "JALALI_YEAR_MIN", "JALALI_YEAR_MAX", "GREGORIAN_YEAR_MIN", "GREGORIAN_YEAR_MAX",
    "LINK_EPISODE", "LINK_DAY_ARCHIVE", "LINK_TIME_SLOT", "LINK_PROGRAM", "LINK_TYPES",
    "STATUS_VALID", "STATUS_INVALID", "STATUS_UNVERIFIED",
    "REASONS",
    "DATE_STATUS_CONFIRMED", "DATE_STATUS_UNVERIFIED", "DATE_STATUS_IMPOSSIBLE", "DATE_STATUS_NONE",
    "DATE_REASONS",
    "MAX_REDIRECTS", "USER_AGENT",
    "FetchError", "FetchTimeout", "RedirectOut",
    "build_episode_url", "build_day_archive_url", "build_time_slot_url",
    "build_program_page_url", "link_type_of", "site_date_from_gregorian",
    "classify_date", "normalize_text", "extract_title", "default_fetch",
    "validate_link",
]

# ---------------------------------------------------------------------------
# Constants (spec §4.2 / §4.3 / §6)
# ---------------------------------------------------------------------------

TIMEZONE = "Asia/Tehran"  # B19 — constant, never derived

# §4.2 plausibility windows.
JALALI_YEAR_MIN, JALALI_YEAR_MAX = 1390, 1407
GREGORIAN_YEAR_MIN, GREGORIAN_YEAR_MAX = 1990, 2037

JALALI_MONTH_NAMES = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)

# Link types (§9.2 naming for the first four; "program_page" keeps the
# spec §6.4 section name).
LINK_EPISODE = "episode"
LINK_DAY_ARCHIVE = "day_archive"
LINK_TIME_SLOT = "time_slot"
LINK_PROGRAM = "program_page"
LINK_TYPES = (LINK_EPISODE, LINK_DAY_ARCHIVE, LINK_TIME_SLOT, LINK_PROGRAM)

# §6.5 result statuses.
STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
STATUS_UNVERIFIED = "unverified"

# §6.5 reason enum (verbatim).
REASONS = (
    "http_error", "not_found", "title_mismatch", "id_mismatch",
    "date_mismatch", "time_mismatch", "program_mismatch",
    "timeout", "blocked", "redirect_out",
)

# §4.2 date-validity statuses (K20 values).
DATE_STATUS_CONFIRMED = "confirmed"
DATE_STATUS_UNVERIFIED = "unverified"
DATE_STATUS_IMPOSSIBLE = "impossible"
DATE_STATUS_NONE = "none"

# §4.2 impossible reasons (verbatim) + free-form reasons for "none".
DATE_REASON_IMPLAUSIBLE_YEAR = "implausible_year"
DATE_REASON_MONTH_GT_12 = "month_gt_12"
DATE_REASON_DAY_GT_31 = "day_gt_31"
DATE_REASON_MISMATCH = "gregorian_jalali_mismatch"
DATE_REASONS = (
    DATE_REASON_IMPLAUSIBLE_YEAR, DATE_REASON_MONTH_GT_12,
    DATE_REASON_DAY_GT_31, DATE_REASON_MISMATCH,
)

# URL templates (§6.1/§6.2/§6.3). ``site_base`` is config-driven
# (corpus.config.Config.site_base / corpus.SITE_BASE).
TEMPLATE_EPISODE = "epgarchivePart/?VALID=TRUE&ch={ch}&e={e}"
TEMPLATE_DAY_ARCHIVE = "timeArchive/?VALID=TRUE&ch={ch}&d={d}"
TEMPLATE_TIME_SLOT = "timeArchivePart/?VALID=TRUE&ch={ch}&ti={ti}&d={d}"
PROGRAM_PATH_DEFAULT = "/Program/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MAX_REDIRECTS = 3
BODY_CAP = 300_000  # bytes; all observed pages are < 70 KB
BLOCKED_STATUSES = (401, 403, 407, 429)

# Persian (U+06F0-06F9) and Arabic-Indic (U+0660-0669) digits -> ASCII.
_FA_DIGIT_TRANS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)


class FetchError(Exception):
    """Network-level failure (not an HTTP response)."""


class FetchTimeout(FetchError):
    """Request exceeded the timeout budget."""


class RedirectOut(FetchError):
    """A redirect left the radio.iranseda.ir host (§6.5.2)."""


# ---------------------------------------------------------------------------
# Text normalization (§6.5.4)
# ---------------------------------------------------------------------------

def normalize_text(s):
    """NFC + strip diacritics/zero-width + casefold + Persian/Arabic-Indic
    digit folding + single-space whitespace. Returns "" for None."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", str(s))
    out = []
    for ch in s:
        # Mn/Me = combining marks (Arabic diacritics, etc.); Cf = format
        # chars (U+200B/200C/200D, U+FEFF, tatweel U+0640).
        if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        out.append(ch)
    s = "".join(out).casefold()
    s = s.translate(_FA_DIGIT_TRANS)
    return re.sub(r"\s+", " ", s).strip()


def extract_title(html_body):
    """First ``<title>`` of an HTML document, NFC-normalized; None if absent."""
    if not html_body:
        return None
    m = re.search(r"<title[^>]*>(.*?)</title>", html_body, re.I | re.S)
    if not m:
        return None
    t = _html.unescape(m.group(1))
    t = unicodedata.normalize("NFC", t).strip()
    return t or None


def _contains(haystack, needle):
    """Normalization-aware substring test (§6.5.4)."""
    n = normalize_text(needle)
    if not n:
        return False
    return n in normalize_text(haystack)


def _compact(s, limit=180):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= limit else s[:limit] + "…"


def _utcnow_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _host_of(site_base):
    return urllib.parse.urlparse(site_base or "https://radio.iranseda.ir/").netloc.lower()


# ---------------------------------------------------------------------------
# URL builders (§6.1–§6.4)
# ---------------------------------------------------------------------------

def _join_base(site_base, suffix):
    base = (site_base or "https://radio.iranseda.ir/").rstrip("/")
    return base + ("/" + suffix if not suffix.startswith("/") else suffix)


def site_date_from_gregorian(gregorian_date):
    """'YYYY-MM-DD' -> the site's ``d`` value.

    OQ-1: gregorian, **month-first**, **unpadded** (``M/D/YYYY``).
    The §6.2 "day-first zero-padded" wording is superseded by the live
    probe evidence (see module docstring).
    """
    y, m, d = (int(x) for x in str(gregorian_date).split("-"))
    return "%d/%d/%d" % (m, d, y)


def hhmm(t):
    """'HH:MM:SS' (or 'HH:MM') -> 'HH:MM' (B16 truncated to the minute)."""
    m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", str(t).strip())
    if not m:
        raise ValueError("not an HH:MM(:SS) time: %r" % (t,))
    return "%s:%s" % (m.group(1), m.group(2))


def build_episode_url(ch, e, site_base=None):
    """§6.1 — normalized episode URL (param order VALID, ch, e)."""
    ch = str(ch).strip()
    e = str(e).strip()
    if not ch or not e:
        raise ValueError("ch and e are required")
    return _join_base(site_base, TEMPLATE_EPISODE.format(ch=ch, e=e))


def build_day_archive_url(ch, gregorian_date, site_base=None):
    """§6.2 — day archive URL. ``gregorian_date`` = 'YYYY-MM-DD'
    (the session's B12; for canonical filenames it is derived from the
    jalali stem via corpus.jalali)."""
    ch = str(ch).strip()
    if not ch:
        raise ValueError("ch is required")
    d = site_date_from_gregorian(gregorian_date)
    return _join_base(site_base, TEMPLATE_DAY_ARCHIVE.format(ch=ch, d=d))


def build_time_slot_url(ch, start_time, gregorian_date, site_base=None):
    """§6.3 — time-slot archive URL. ``start_time`` = B16 'HH:MM'/'HH:MM:SS'."""
    ch = str(ch).strip()
    if not ch:
        raise ValueError("ch is required")
    ti = hhmm(start_time)
    h, mi = int(ti.split(":")[0]), int(ti.split(":")[1])
    if h > 23 or mi > 59:
        raise ValueError("start_time out of range: %r" % (start_time,))
    d = site_date_from_gregorian(gregorian_date)
    return _join_base(site_base, TEMPLATE_TIME_SLOT.format(ch=ch, ti=ti, d=d))


def build_program_page_url(program, site_base=None):
    """§6.4 — program intro page: the stored URL **verbatim** plus a
    separately normalized form (re-order/standardize only; values are
    never re-derived; no title-based construction, R5).

    ``program``: dict with at least ``url`` (A7). Returns
    ``{"raw": ..., "normalized": ...}``; both None when ``url`` is empty
    (the link is null by policy).
    """
    raw = (program or {}).get("url")
    if not raw or not str(raw).strip():
        return {"raw": None, "normalized": None}
    raw = str(raw).strip()
    host = _host_of(site_base)
    p = urllib.parse.urlparse(raw)
    pairs = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    d = {}
    for k, v in pairs:
        d.setdefault(k, v)
    norm_pairs = []
    seen = set()
    for k in ("VALID", "ch", "m"):  # canonical order
        if k in d:
            norm_pairs.append((k, d[k]))
            seen.add(k)
    for k, v in pairs:  # extras preserved, original order
        if k not in seen:
            norm_pairs.append((k, v))
            seen.add(k)
    path = p.path or PROGRAM_PATH_DEFAULT
    if not path.endswith("/"):
        path += "/"
    norm = "https://%s%s?%s" % (host, path, urllib.parse.urlencode(norm_pairs))
    return {"raw": raw, "normalized": norm}


def link_type_of(url):
    """Infer the link type from the URL path (None when unknown)."""
    path = urllib.parse.urlparse(url).path
    if "epgarchivePart" in path:
        return LINK_EPISODE
    if "timeArchivePart" in path:
        return LINK_TIME_SLOT
    if "timeArchive" in path:
        return LINK_DAY_ARCHIVE
    if "Program" in path:
        return LINK_PROGRAM
    return None


# ---------------------------------------------------------------------------
# Date classification (§4.2)
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")


def classify_date(session, verified=False):
    """§4.2 date-validity classifier (K20 value).

    ``session``: dict, may carry any of
      * ``filename`` — canonical audio stem (B11 source of truth),
      * ``broadcast_jalali`` — explicit 'YYYY-MM-DD',
      * ``broadcast_gregorian`` — explicit 'YYYY-MM-DD' (cross-checked).

    Returns::

        {
          "status": "confirmed" | "unverified" | "impossible" | "none",
          "timezone": "Asia/Tehran",
          "reasons": [...],          # §4.2 enum when impossible
          "jalali":    {"date", "time", "source"} | None,
          "gregorian": {"date", "time", "source"} | None,
          "raw": {filename, broadcast_jalali, broadcast_gregorian},
        }

    Raw inputs are always preserved (mission: raw preserved).
    ``verified=True`` marks a date that an archive page matched
    (Stage 2 live validation flips unverified -> confirmed).
    """
    s = session or {}
    raw = {
        "filename": s.get("filename"),
        "broadcast_jalali": s.get("broadcast_jalali"),
        "broadcast_gregorian": s.get("broadcast_gregorian"),
    }
    out = {
        "status": DATE_STATUS_NONE,
        "timezone": TIMEZONE,
        "reasons": [],
        "jalali": None,
        "gregorian": None,
        "raw": raw,
    }

    # 1) Resolve the jalali date: filename stem first, then explicit.
    jdate = jtime = None
    src = None
    if s.get("filename"):
        parsed = jalali.parse_broadcast(jalali.stem_of(s["filename"]))
        if parsed:
            jdate = parsed["jalali"]["date"]
            jtime = parsed["jalali"]["time"]
            src = "filename"
    if jdate is None and s.get("broadcast_jalali"):
        m = _DATE_RE.match(str(s["broadcast_jalali"]).strip())
        if m:
            jdate = "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
            jtime = s.get("broadcast_time")
            src = "explicit"
    if jdate is None and s.get("broadcast_gregorian"):
        try:
            gy, gm, gd = (int(x) for x in str(s["broadcast_gregorian"]).split("-"))
            jy, jm, jd = jalali.gregorian_to_jalali(gy, gm, gd)
            jdate = "%04d-%02d-%02d" % (jy, jm, jd)
            src = "derived_from_gregorian"
        except (ValueError, TypeError):
            out["reasons"].append("malformed_date_source")
            return out
    if jdate is None:
        out["reasons"].append("no_date_source")
        return out

    # 2) Structural + plausibility checks.
    reasons = set()
    jy, jm, jd = (int(x) for x in jdate.split("-"))
    if not 1 <= jm <= 12:
        reasons.add(DATE_REASON_MONTH_GT_12)
    elif not 1 <= jd <= 31:
        reasons.add(DATE_REASON_DAY_GT_31)
    else:
        try:
            jalali.validate(jy, jm, jd)  # month-aware day range (30 Esfand leap)
        except (ValueError, TypeError):
            reasons.add(DATE_REASON_DAY_GT_31)
    gdate = None
    if not reasons:
        if not JALALI_YEAR_MIN <= jy <= JALALI_YEAR_MAX:
            reasons.add(DATE_REASON_IMPLAUSIBLE_YEAR)
        else:
            gy, gm, gd = jalali.jalali_to_gregorian(jy, jm, jd)
            gdate = "%04d-%02d-%02d" % (gy, gm, gd)
            if not GREGORIAN_YEAR_MIN <= gy <= GREGORIAN_YEAR_MAX:
                reasons.add(DATE_REASON_IMPLAUSIBLE_YEAR)
    # 3) Cross-check an explicitly supplied gregorian date.
    if not reasons and s.get("broadcast_gregorian") and gdate:
        g = str(s["broadcast_gregorian"]).strip()
        if g != gdate:
            try:
                ry, rm, rd = (int(x) for x in g.split("-"))
                if "%04d-%02d-%02d" % jalali.gregorian_to_jalali(ry, rm, rd) != jdate:
                    reasons.add(DATE_REASON_MISMATCH)
            except (ValueError, TypeError):
                reasons.add(DATE_REASON_MISMATCH)

    out["jalali"] = {"date": jdate, "time": jtime, "source": src}
    if gdate is not None:
        out["gregorian"] = {
            "date": gdate,
            "time": jtime,
            "source": "derived_from_jalali" if src in ("filename", "explicit") else "explicit",
        }
    if reasons:
        out["status"] = DATE_STATUS_IMPOSSIBLE
        out["reasons"] = sorted(reasons)
    else:
        out["status"] = DATE_STATUS_CONFIRMED if verified else DATE_STATUS_UNVERIFIED
    return out


# ---------------------------------------------------------------------------
# HTTP fetch (default, injectable)
# ---------------------------------------------------------------------------

def default_fetch(url, timeout=15.0, host=None):
    """GET with a browser-like UA; follows at most MAX_REDIRECTS redirects,
    all of which must stay on ``host`` (else RedirectOut).

    Returns ``{"status", "body", "final_url"}``. HTTP error responses
    (404/403/...) are returned with their status, not raised.
    Raises FetchTimeout / FetchError on network failure.
    """
    host = host or _host_of(url)
    visited = []

    class _RedirectLog(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            visited.append(newurl)
            if len(visited) > MAX_REDIRECTS:
                raise FetchError("too many redirects (> %d)" % MAX_REDIRECTS)
            nh = urllib.parse.urlparse(newurl).netloc.lower()
            if nh != host:
                raise RedirectOut(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(_RedirectLog())
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    })
    t0 = time.time()
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read(BODY_CAP)
            return {
                "status": resp.status,
                "body": body.decode("utf-8", "replace"),
                "final_url": resp.url,
                "elapsed": time.time() - t0,
                "redirects": list(visited),
            }
    except RedirectOut:
        raise
    except FetchError:
        raise
    except urllib.error.HTTPError as e:  # 4xx/5xx are responses, not failures
        try:
            body = e.read(BODY_CAP)
        except Exception:
            body = b""
        return {
            "status": e.code,
            "body": body.decode("utf-8", "replace"),
            "final_url": e.url,
            "elapsed": time.time() - t0,
            "redirects": list(visited),
        }
    except (socket.timeout, TimeoutError):
        raise FetchTimeout("timeout after %.1fs on %s" % (timeout, url))
    except urllib.error.URLError as e:
        raise FetchError("url error: %s" % (e.reason,))
    except Exception as e:  # defensive: any other transport failure
        raise FetchError("%s: %s" % (type(e).__name__, e))


# ---------------------------------------------------------------------------
# Per-type content checks (§6.7 matrix)
# ---------------------------------------------------------------------------

def _parse_site_date(s):
    """Site 'd' value (M/D/YYYY, month-first, unpadded) -> (y, m, d) or None."""
    if not s:
        return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(s).strip())
    if not m:
        return None
    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return (y, mo, d)


def _id_in_body(needle, body):
    needle = str(needle).strip()
    if not needle:
        return 0
    return len(re.findall(r"(?<!\d)%s(?!\d)" % re.escape(needle), body))


def _check_episode(q, session, program, body, title):
    warnings, evidence = [], {}
    e = str(q.get("e", "")).strip()
    n = _id_in_body(e, body)
    evidence["e_id"] = e
    evidence["e_id_occurrences"] = n
    if n:
        first = re.search(r"(?<!\d)%s(?!\d)" % re.escape(e), body)
        a = max(0, first.start() - 60)
        b = min(len(body), first.end() + 60)
        evidence["e_id_context"] = _compact(body[a:b])
    if not e or n == 0:
        return STATUS_INVALID, "id_mismatch", warnings, evidence
    pname = (session or {}).get("program_name")
    if pname:
        ok = _contains(title, pname)
        evidence["title_has_program_name"] = ok
        if not ok:
            return STATUS_INVALID, "title_mismatch", warnings, evidence
    m = (program or {}).get("m")
    if m:
        ok = _id_in_body(m, body) > 0
        evidence["m_in_body"] = ok
        if not ok:
            warnings.append("m_id_not_in_body")
    return STATUS_VALID, None, warnings, evidence


def _check_day_archive(q, session, program, body, title):
    """Strict: the page shows a 7-day ``d=`` window centered on the target
    date (median == target). Probed: timeArchive renders exactly that
    window for any valid d= (e.g. d=11/5/2026 -> 11/1..11/7/2026)."""
    warnings, evidence = [], {}
    d = q.get("d")
    target = _parse_site_date(d)
    evidence["d_target"] = ("%04d-%02d-%02d" % target) if target else d
    if target is None:
        evidence["note"] = "unparseable d= parameter"
        return STATUS_INVALID, "date_mismatch", warnings, evidence
    seen = set()
    for mo, dd, yy in re.findall(r"[?&]d=(\d{1,2})/(\d{1,2})/(\d{4})", body):
        seen.add(_dt.date(int(yy), int(mo), int(dd)))
    t = _dt.date(*target)
    prev = nxt = 0
    for k in range(1, 8):
        if (t - _dt.timedelta(days=k)) in seen:
            prev += 1
        else:
            break
    for k in range(1, 8):
        if (t + _dt.timedelta(days=k)) in seen:
            nxt += 1
        else:
            break
    evidence["d_window_prev_days"] = prev
    evidence["d_window_next_days"] = nxt
    evidence["d_window_days_observed"] = len(seen)
    if not (prev >= 3 and nxt >= 3):
        return STATUS_INVALID, "date_mismatch", warnings, evidence
    # Soft (logged): program identity. The day-archive <title> is
    # channel-level ("رادیو معارف - آرشیو زمانی"), so per the documented
    # §6.7 deviation the soft check runs against the body.
    pname = (session or {}).get("program_name")
    if pname and not _contains(body, pname):
        warnings.append("program_name_not_on_page")
    m = (program or {}).get("m")
    if m and _id_in_body(m, body) == 0:
        warnings.append("m_id_not_in_body")
    return STATUS_VALID, None, warnings, evidence


def _check_time_slot(q, session, program, body, title):
    """Strict: <title> contains 'ساعت HH:MM' (time) and the jalali date
    'D MonthName YYYY' derived from d= (date). Probed title format:
    'آرشیو رادیو - پنجشنبه 14 آبان 1405 - ساعت 12:30'."""
    warnings, evidence = [], {}
    ti = str(q.get("ti", "")).strip()
    if not ti:
        bt = (session or {}).get("broadcast_time") or (session or {}).get("start_time")
        if bt:
            ti = hhmm(bt)
    evidence["ti"] = ti
    d = q.get("d")
    target = _parse_site_date(d)
    evidence["d_target"] = ("%04d-%02d-%02d" % target) if target else d
    if ti:
        if title is None or not _contains(title, "ساعت " + ti):
            return STATUS_INVALID, "time_mismatch", warnings, evidence
        evidence["title_has_time"] = True
    if target is None:
        return STATUS_INVALID, "date_mismatch", warnings, evidence
    jy, jm, jd = jalali.gregorian_to_jalali(*target)
    jstr = "%d %s %d" % (jd, JALALI_MONTH_NAMES[jm - 1], jy)
    evidence["expected_title_date"] = jstr
    if title is None or not _contains(title, jstr):
        return STATUS_INVALID, "date_mismatch", warnings, evidence
    evidence["title_has_date"] = True
    # Soft (logged), body-level (title is date/channel-level).
    pname = (session or {}).get("program_name")
    if pname and not _contains(body, pname):
        warnings.append("program_name_not_on_page")
    m = (program or {}).get("m")
    if m and _id_in_body(m, body) == 0:
        warnings.append("m_id_not_in_body")
    return STATUS_VALID, None, warnings, evidence


def _check_program(q, session, program, body, title):
    warnings, evidence = [], {}
    prog = program or {}
    pname = prog.get("name") or (session or {}).get("program_name")
    evidence["program_name"] = pname
    if pname:
        ok = title is not None and _contains(title, pname)
        evidence["title_has_program_name"] = ok
        if not ok:
            return STATUS_INVALID, "title_mismatch", warnings, evidence
    else:
        warnings.append("program_name_missing")
    m = str(q.get("m") or prog.get("m") or "").strip()
    evidence["m_id"] = m or None
    if m:
        n = _id_in_body(m, body)
        evidence["m_id_occurrences"] = n
        if n == 0:
            return STATUS_INVALID, "program_mismatch", warnings, evidence
    return STATUS_VALID, None, warnings, evidence


_CHECKS = {
    LINK_EPISODE: _check_episode,
    LINK_DAY_ARCHIVE: _check_day_archive,
    LINK_TIME_SLOT: _check_time_slot,
    LINK_PROGRAM: _check_program,
}


# ---------------------------------------------------------------------------
# validate_link (§6.5 protocol)
# ---------------------------------------------------------------------------

def _result(url, link_type, status, reason, http_status=None, title=None,
            warnings=None, evidence=None, note=None, final_url=None,
            elapsed_ms=None, last_verified_at=None):
    r = {
        "url": url,
        "link_type": link_type,
        "status": status,
        "reason": reason,
        "http_status": http_status,
        "final_url": final_url,
        "title": title,
        "warnings": warnings or [],
        "evidence": evidence or {},
        "last_verified_at": last_verified_at or _utcnow_iso(),
    }
    if note:
        r["evidence"]["note"] = note
    if elapsed_ms is not None:
        r["evidence"]["elapsed_ms"] = int(elapsed_ms * 1000)
    return r


def validate_link(url, session=None, program=None, link_type=None,
                  fetch=None, timeout=15.0, site_base=None):
    """Validate one generated link against the live site (§6.5 + §6.7).

    ``fetch``: injectable ``fetch(url, timeout=..., host=...) ->
    {"status", "body", "final_url"}`` (default: :func:`default_fetch`).
    Tests inject a fake; production uses the real one.

    Returns the §6.5 result record:
    ``status`` ∈ valid|invalid|unverified + ``reason`` (enum, None when
    valid) + evidence (observed title, id occurrences, window, ...) +
    ``last_verified_at``.

    Status discipline (Stage 2, documented in the report):
      404 -> invalid:not_found
      401/403/407/429 -> unverified:blocked
      timeout -> unverified:timeout
      other network error -> unverified:http_error
      other non-200 -> invalid:http_error
      redirect off-host -> invalid:redirect_out
      content mismatch -> invalid:<type-specific reason>
    """
    lt = link_type or link_type_of(url)
    if lt not in LINK_TYPES:
        raise ValueError("unsupported link type for url %r" % (url,))
    t0 = time.time()
    host = _host_of(site_base)
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query,
                                    keep_blank_values=True))

    # Cross-check URL vs session/program *before* spending a request.
    if lt == LINK_EPISODE and session and session.get("e"):
        if str(q.get("e", "")).strip() != str(session["e"]).strip():
            return _result(url, lt, STATUS_INVALID, "id_mismatch",
                           note="url/session e mismatch",
                           evidence={"url_e": q.get("e"), "session_e": str(session["e"])})
    if lt == LINK_PROGRAM and program and program.get("m"):
        if str(q.get("m", "")).strip() != str(program["m"]).strip():
            return _result(url, lt, STATUS_INVALID, "program_mismatch",
                           note="url/program m mismatch",
                           evidence={"url_m": q.get("m"), "program_m": str(program["m"])})

    fetcher = fetch or default_fetch
    try:
        resp = fetcher(url, timeout=timeout, host=host)
    except FetchTimeout as e:
        return _result(url, lt, STATUS_UNVERIFIED, "timeout", note=str(e))
    except RedirectOut as e:
        return _result(url, lt, STATUS_INVALID, "redirect_out",
                       evidence={"redirect_to": str(e)})
    except FetchError as e:
        return _result(url, lt, STATUS_UNVERIFIED, "http_error", note=str(e))
    except Exception as e:  # defensive net
        return _result(url, lt, STATUS_UNVERIFIED, "http_error",
                       note="%s: %s" % (type(e).__name__, e))

    http_status = int(resp.get("status") or 0)
    body = resp.get("body") or ""
    title = extract_title(body)
    base = {
        "http_status": http_status,
        "final_url": resp.get("final_url"),
        "title": title,
        "last_verified_at": _utcnow_iso(),
        "elapsed_ms": resp.get("elapsed"),
    }
    if http_status == 404:
        return _result(url, lt, STATUS_INVALID, "not_found", **base)
    if http_status in BLOCKED_STATUSES:
        return _result(url, lt, STATUS_UNVERIFIED, "blocked", **base)
    if http_status != 200:
        return _result(url, lt, STATUS_INVALID, "http_error", **base)

    status, reason, warnings, evidence = _CHECKS[lt](q, session, program, body, title)
    r = _result(url, lt, status, reason, warnings=warnings, evidence=evidence, **base)
    if resp.get("redirects"):
        r["evidence"]["redirects"] = list(resp["redirects"])
    return r
