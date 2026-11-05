"""Session asset registry + 5-way asset verification (Stage 3, Task B).

Implements the CORPUS LINKAGE SPEC section 5 asset model (C1..C14):

* one registry entry per (session, asset_type, filename);
* the branch for C4/C5/C6 is always taken from production config/env at
  run time (R7) - a missing branch ABORTS, it is never hardcoded;
* "stored path first, pattern second" (section 5.2): audio from
  sessions.filename, raw_srt from sessions.srt_filename (OQ-10: top-level
  downloads/{srt_filename}), LLM artifacts from llm_output.file_relpath
  (verbatim); the only pattern-only asset is summary_en, and only for
  canonical stems;
* C5/C6 are exposed only when C11 == "published" (R5: no synthetic URLs);
* C14 (processing_version) = llm_output.model for LLM artifacts, null
  everywhere else (never guessed).

Five-way verification per asset:
  1. on disk (C9 + C7 sha256 + C8 size + C13 mtime)
  2. in the asset branch's git tree (C10 + C12 publishing commit)
  3. in the operational branch's git tree (OQ-6 parity evidence)
  4. HTTP status of the GitHub raw URL (bounded, resumable, <=2 concurrent)
  5. SHA-256 local == downloaded

Open questions encoded here (full evidence in
reports/corpus/CORPUS_LINKAGE_STAGE3.md):
  OQ-4  the asset repo is the GitHub remote saber13812000/iranseda-crawler-
        golang- - there is NO GitLab namespace; the raw URL template is the
        production one (root config.py:103):
        https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}
  OQ-5  canonical stem family = radio-{slug}-{JY}-{JM}-{JD}-{HH}-{MM}
        (5 numeric tokens, 2-digit Jalali year FIRST; seconds implicitly
        00) - the production corpus/jalali.py _STEM_RE is authoritative.
        Legacy variants (underscore N_N_N-N_N, " - Copy", "(N)") are
        reported as stem_family="unparsed"; no date is emitted from an
        unrecognized family (R5).
  OQ-6  the asset branch (GITHUB_BRANCH, config .env) and the operational
        branch (the checked-out branch that refresh_site.sh pushes to) are
        BOTH checked; the trees are allowed to diverge and the divergence
        is reported, not papered over.

Design: pure, read-only, stdlib-only (no pymysql, no jdatetime). All data
enters as plain dicts; the CLI (corpus/scan_assets.py) is the only thing
that touches the DB or the network. git and fetch callables are injectable
so the unit tests run fully offline.
"""

import hashlib
import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import quote

from corpus import jalali

# ---------------------------------------------------------------------------
# constants

ASSET_TYPES = (
    "audio",
    "raw_srt",
    "corrected_srt",
    "full_txt",
    "corrected_txt",
    "summary_fa",
    "summary_en",
    "other_llm",
)

PUBLISHED = "published"
NOT_PUBLISHED = "not_published"
MISSING = "missing"
EXCLUDED = "excluded"

# llm_output.job_type -> asset_type (spec 5.2). Unknown job types pass
# through as other_llm (KNOWN_JOB_TYPES policy: pass through, never fail).
JOB_TO_ASSET = {
    "correct_subtitles": "corrected_srt",
    "correct_text": "corrected_txt",
    "summary": "summary_fa",
    "full_text": "full_txt",
    "qa": "other_llm",
}

# Canonical stem (OQ-5). The lookahead (dot or end-of-string) guards
# against false positives such as a 3-digit tail (...-300) and against
# legacy " - Copy" / "(N)" names, which must stay unparsed.
CANONICAL_PREFIX_RE = re.compile(
    r"^(radio-(?P<chan>[A-Za-z]+)-"
    r"(?P<jy>\d{2})-(?P<jm>\d{2})-(?P<jd>\d{2})-"
    r"(?P<hh>\d{2})-(?P<mi>\d{2}))"
    r"(?=\.|$)"
)

# session_uid parsing (mirrors corpus.database record_id_for; kept local so
# this module stays importable without pymysql).
RE_CH = re.compile(r"[?&]ch=(\d+)")
RE_E = re.compile(r"[?&]e=(\d+)")

DEFAULT_HTTP_TIMEOUT = 15.0
DEFAULT_MAX_REQUESTS = 300
DEFAULT_MAX_WORKERS = 2
DEFAULT_SHA_CAP = 30 * 1024 * 1024  # downloaded bodies above this: full sha skipped
FP_CHUNK = 1024 * 1024  # head/tail fingerprint window (1MB each)
USER_AGENT = "iranseda-corpus-asset-verifier/1.0 (read-only, stage 3)"


# ---------------------------------------------------------------------------
# small helpers

def _utcnow():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_dt(v):
    """datetime/date/str -> 'YYYY-MM-DD HH:MM:SS' (or None)."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, str):
        return v[:19].replace("T", " ")
    return None


def _norm_relpath(p):
    p = (p or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _sha256_file(path, cap=None):
    h = hashlib.sha256()
    total = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            h.update(chunk)
            if cap is not None and total > cap:
                return None
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. stem parser (OQ-5)

def parse_asset_filename(filename):
    """Classify one asset filename (basename or relpath).

    Returns a dict:
      filename       input verbatim
      basename       basename only
      extension      lowercased final extension (no dot) or None
      raw_stem       basename minus the final extension
      stem           canonical stem or None
      stem_family    "canonical" | "unparsed" | "none"
                     - canonical: 5-token radio-{slug}-{JY}-{JM}-{JD}-{HH}-{MM}
                     - unparsed:   radio-* name that does not match the
                                   canonical grammar (legacy underscore,
                                   " - Copy", "(N)", bad digit runs)
                     - none:       not a radio-* named file at all
      asset_suffix   for canonical: text between stem and extension
                     ("correct" in stem.correct.srt; "" otherwise)
      chan           channel slug (canonical only)
      components     {jy,jm,jd,hh,mi} ints (canonical only)
      date_valid     jalali date validity (canonical only)
      time_valid     hh<=23 and mi<=59 (canonical only)
      broadcast      jalali.parse_broadcast(stem) result or None
    """
    name = str(filename or "").strip()
    base = os.path.basename(name)
    if "." in base:
        raw_stem, _, ext = base.rpartition(".")
        ext = ext.lower() or None
    else:
        raw_stem, ext = base, None

    out = {
        "filename": name,
        "basename": base,
        "extension": ext,
        "raw_stem": raw_stem,
        "stem": None,
        "stem_family": "none",
        "asset_suffix": None,
        "chan": None,
        "components": None,
        "date_valid": None,
        "time_valid": None,
        "broadcast": None,
    }
    if not base.startswith("radio-"):
        return out

    m = CANONICAL_PREFIX_RE.match(raw_stem)
    if not m:
        out["stem_family"] = "unparsed"
        return out

    out["stem_family"] = "canonical"
    out["stem"] = m.group(0)
    out["chan"] = m.group("chan")
    jy = int(m.group("jy"))
    jm = int(m.group("jm"))
    jd = int(m.group("jd"))
    hh = int(m.group("hh"))
    mi = int(m.group("mi"))
    out["components"] = {"jy": jy, "jm": jm, "jd": jd, "hh": hh, "mi": mi}
    suffix = raw_stem[len(out["stem"]):]
    if suffix.startswith("."):
        suffix = suffix[1:]
    out["asset_suffix"] = suffix
    try:
        jalali.validate(1400 + jy, jm, jd)
        out["date_valid"] = True
    except ValueError:
        out["date_valid"] = False
    out["time_valid"] = hh <= 23 and mi <= 59
    out["broadcast"] = jalali.parse_broadcast(out["stem"])
    return out


# ---------------------------------------------------------------------------
# 2. session identity (mirrors corpus.database.record_id_for)

def parse_ch(link):
    m = RE_CH.search(link or "")
    return int(m.group(1)) if m else None


def parse_e(link):
    m = RE_E.search(link or "")
    return m.group(1) if m else None


def session_uid(session):
    ch = parse_ch(session.get("link"))
    e = parse_e(session.get("link"))
    if ch is not None and e is not None:
        return "iranseda:ch%d:e%s" % (ch, e)
    pid = session.get("program_id")
    pid = pid if pid is not None else "x"
    return "iranseda:db%s:s%d" % (pid, int(session.get("id") or 0))


# ---------------------------------------------------------------------------
# 3. URL builders (OQ-4: GitHub raw/blob template, branch from config - R7)

def _require_branch(branch):
    if not branch or not str(branch).strip():
        raise ValueError(
            "R7 violation: asset branch missing. The branch must come from "
            "production config/env (GITHUB_BRANCH); it is never hardcoded.")
    return str(branch).strip()


def _require_identity(user, repo):
    if not user or not repo:
        raise ValueError("github user and repo are required (R7: from config)")


def github_raw_url(user, repo, branch, relpath):
    """https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}

    (production template, root config.py:103; OQ-4: no GitLab namespace)."""
    _require_identity(user, repo)
    b = _require_branch(branch)
    return "https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        user, repo, b, quote(_norm_relpath(relpath), safe="/"))


def github_blob_url(user, repo, branch, relpath):
    _require_identity(user, repo)
    b = _require_branch(branch)
    return "https://github.com/%s/%s/blob/%s/%s" % (
        user, repo, b, quote(_norm_relpath(relpath), safe="/"))


# ---------------------------------------------------------------------------
# 4. registry builder (spec 5)

def _new_entry(asset_type, filename, relpath, github, quarantined, source):
    relpath = _norm_relpath(relpath)
    a = {
        # C1..C14
        "asset_type": asset_type,                      # C1
        "filename": os.path.basename(relpath) or filename,  # C2
        "relpath": relpath,                            # C3
        "branch": _require_branch(github.get("branch")),    # C4
        "raw_url": None,                               # C5 (published only)
        "blob_url": None,                              # C6 (published only)
        "sha256": None,                                # C7
        "size_bytes": None,                            # C8
        "exists_on_disk": None,                        # C9
        "exists_in_git_tree": None,                    # C10
        "published": None,                             # C11
        "publishing_commit_sha": None,                 # C12
        "produced_at": None,                           # C13
        "processing_version": None,                    # C14
        # extras (evidence, not part of the 14-field contract)
        "source": source,
        "quarantined": bool(quarantined),
        "operational_branch_present": None,
        "http_status": None,
        "http_reason": None,
        "sha_match": None,
        "http_verified_at": None,
        # internal (always computed; exposed as C5 only when published, R5)
        "_raw_url": github_raw_url(github["user"], github["repo"],
                                   github["branch"], relpath),
        "_blob_url": github_blob_url(github["user"], github["repo"],
                                     github["branch"], relpath),
    }
    _recompute_published(a)
    return a


def _recompute_published(a):
    """C11 from C9/C10/quarantine; expose C5/C6 only when published (R5)."""
    c9 = a.get("exists_on_disk")
    c10 = a.get("exists_in_git_tree")
    if a.get("quarantined"):
        a["published"] = EXCLUDED
    elif c9 is None or c10 is None:
        a["published"] = None  # pipeline incomplete (disk/git not checked)
    elif not c9:
        a["published"] = MISSING
    elif not c10:
        a["published"] = NOT_PUBLISHED
    else:
        a["published"] = PUBLISHED
    if a["published"] == PUBLISHED:
        a["raw_url"] = a.get("_raw_url")
        a["blob_url"] = a.get("_blob_url")
    else:
        a["raw_url"] = None
        a["blob_url"] = None


def build_registry(sessions, llm_rows, github, operational_branch=None,
                   quarantine_ids=None):
    """Build the per-session asset registry (spec 5.1).

    sessions:  list of radio_program_sessions row dicts
               (id, program_id, link, filename, srt_filename, ...)
    llm_rows:  list of llm_output row dicts
               (id, session_id, job_type, model, file_relpath, finished_at)
    github:    {"user": str, "repo": str, "branch": str} - branch REQUIRED
               (R7: abort when missing, never hardcoded)
    operational_branch: optional checked-out (operational) branch name for
               OQ-6 parity checks
    quarantine_ids: optional set of quarantined record_ids (spec 10.1)

    Returns a list of session rows:
      {session_id, program_id, session_uid, quarantined, filename,
       srt_filename, stem, stem_family, broadcast_jalali, asset_count,
       assets: [entry, ...]}
    Assets are sorted by (asset_type, filename) - deterministic (R8).
    """
    branch = _require_branch(github.get("branch"))
    _require_identity(github.get("user"), github.get("repo"))
    quarantine = set(quarantine_ids or ())
    op_branch = (operational_branch or "").strip() or None

    llm_by_sid = {}
    for r in (llm_rows or ()):
        sid = r.get("session_id")
        if sid is None:
            continue
        llm_by_sid.setdefault(int(sid), []).append(r)

    registry = []
    for s in sessions:
        sid = int(s.get("id") or 0)
        uid = session_uid(s)
        quarantined = uid in quarantine
        fname = (s.get("filename") or "").strip()
        srtf = (s.get("srt_filename") or "").strip()
        parse = parse_asset_filename(fname) if fname else None

        entries = []
        seen = {}  # (asset_type, relpath) -> entry (for dedup, latest wins)

        def add(asset_type, filename, relpath, source,
                produced_at=None, processing_version=None, sort_id=0):
            relpath = _norm_relpath(relpath)
            key = (asset_type, relpath)
            prev = seen.get(key)
            if prev is not None:
                if sort_id > prev["_sort_id"]:
                    _drop(entries, prev)
                else:
                    return
            e = _new_entry(asset_type, filename, relpath, github,
                           quarantined, source)
            e["_sort_id"] = sort_id
            if produced_at is not None:
                e["produced_at"] = produced_at
            if processing_version is not None:
                e["processing_version"] = processing_version
            entries.append(e)
            seen[key] = e

        # audio - sessions.filename (100% populated; spec 5.2)
        if fname:
            add("audio", fname, "downloads/" + os.path.basename(fname),
                "db:filename", sort_id=0)
        # raw_srt - sessions.srt_filename (OQ-10: top-level downloads/)
        if srtf:
            add("raw_srt", srtf, "downloads/" + os.path.basename(srtf),
                "db:srt_filename", sort_id=0)
        # LLM artifacts - llm_output.file_relpath verbatim (stored path wins)
        for r in sorted(llm_by_sid.get(sid, []),
                        key=lambda r: int(r.get("id") or 0)):
            rel = (r.get("file_relpath") or "").strip()
            if not rel:
                continue
            job = r.get("job_type")
            atype = JOB_TO_ASSET.get(job, "other_llm")
            add(atype, os.path.basename(_norm_relpath(rel)), rel,
                "db:llm:%s" % (job or "?"),
                produced_at=_iso_dt(r.get("finished_at")),
                processing_version=r.get("model") or None,
                sort_id=int(r.get("id") or 0))
        # summary_en - pattern-only (no stored path exists), canonical stems
        # only; a stored path would have won and suppressed it via `seen`
        if parse and parse["stem_family"] == "canonical":
            add("summary_en",
                parse["stem"] + ".summary.en.txt",
                "downloads/cleaned/%s.summary.en.txt" % parse["stem"],
                "pattern", sort_id=-1)

        # drop the internal sort key, then deterministic order (R8)
        for e in entries:
            e.pop("_sort_id", None)
        entries.sort(key=lambda a: (a["asset_type"], a["filename"], a["relpath"]))

        registry.append({
            "session_id": sid,
            "program_id": s.get("program_id"),
            "session_uid": uid,
            "quarantined": quarantined,
            "filename": fname or None,
            "srt_filename": srtf or None,
            "stem": parse["stem"] if parse else None,
            "stem_family": parse["stem_family"] if parse else "none",
            "broadcast_jalali": (parse["broadcast"]["jalali"]["date"]
                                 if parse and parse["broadcast"] else None),
            "asset_count": len(entries),
            "assets": entries,
        })
    return registry


def _drop(lst, item):
    try:
        lst.remove(item)
    except ValueError:
        pass


def iter_assets(registry):
    for s in registry:
        for a in s["assets"]:
            yield s, a


# ---------------------------------------------------------------------------
# 5. way 1: on-disk (C9/C8/C7/C13)

def _head_tail_fingerprint(path, chunk=FP_CHUNK):
    """(head_sha256, tail_sha256, size) of a local file.

    head = first `chunk` bytes; tail = last `chunk` bytes. Used by way 5
    for large assets: a bounded 2x-Range-request probe can verify remote
    identity without downloading the full body."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(chunk)
        f.seek(max(0, size - chunk))
        tail = f.read(chunk)
    return _sha256_bytes(head), _sha256_bytes(tail), size


def check_disk(registry, downloads_dir, sha_cap_bytes=None, fp_chunk=FP_CHUNK):
    """Set C9 (and C8/C7/C13-mtime fallback) from the local downloads tree.

    Local sha256 is always computed for on-disk files (sha_cap_bytes=None).
    Files larger than sha_cap_bytes also get a head/tail fingerprint
    (fingerprint={head_sha256, tail_sha256, size_bytes, chunk}) that way 5
    uses for a bounded Range-based comparison instead of a full download.
    produced_at is only set from mtime when the DB did not supply one.
    """
    on_disk = 0
    for s in registry:
        for a in s["assets"]:
            parts = a["relpath"].split("/")
            p = os.path.join(downloads_dir, *parts) if parts else ""
            if p and os.path.isfile(p):
                a["exists_on_disk"] = True
                st = os.stat(p)
                a["size_bytes"] = int(st.st_size)
                if a.get("produced_at") is None:
                    a["produced_at"] = datetime.fromtimestamp(
                        st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                a["sha256"] = _sha256_file(p, cap=sha_cap_bytes)
                if sha_cap_bytes and a["size_bytes"] > sha_cap_bytes:
                    h, t, _sz = _head_tail_fingerprint(p, fp_chunk)
                    a["fingerprint"] = {"head_sha256": h, "tail_sha256": t,
                                        "size_bytes": a["size_bytes"],
                                        "chunk": fp_chunk}
                else:
                    a["fingerprint"] = None
                on_disk += 1
            else:
                a["exists_on_disk"] = False
                a["size_bytes"] = None
                a["sha256"] = None
                a["fingerprint"] = None
            _recompute_published(a)
    return on_disk


# ---------------------------------------------------------------------------
# 6. ways 2+3: git trees (C10/C12 + operational-branch parity, OQ-6)

def _git_default(repo):
    def run(args):
        p = subprocess.run(["git", "-C", repo] + list(args),
                           capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout or "", p.stderr or ""
    return run


def check_git_tree(registry, repo, asset_ref, operational_ref=None,
                   git=None):
    """Set C10/C12 on the asset ref and operational_branch_present on the
    operational ref (OQ-6 parity).

    asset_ref / operational_ref are GIT REFS (e.g. "origin/download-db",
    "phase3-radio-rag-service"); the CLI resolves them after a read-only
    `git fetch origin` (the asset branch normally exists only as
    origin/<branch>; the operational branch is the checked-out local branch).
    git is an injectable callable (args_list) -> (rc, out, err) for offline
    tests.
    """
    git = git or _git_default(repo)
    ab = _require_branch(asset_ref)
    op = (operational_ref or "").strip() or None
    n_asset = n_op = 0
    for s in registry:
        for a in s["assets"]:
            rc, _o, _e = git(["cat-file", "-e", "%s:%s" % (ab, a["relpath"])])
            a["exists_in_git_tree"] = (rc == 0)
            if rc == 0:
                n_asset += 1
                rc2, out2, _e2 = git(["log", "-1", "--format=%H", ab,
                                      "--", a["relpath"]])
                sha = out2.strip() if rc2 == 0 else ""
                a["publishing_commit_sha"] = sha or None
            else:
                a["publishing_commit_sha"] = None
            if op:
                rc3, _o3, _e3 = git(["cat-file", "-e",
                                     "%s:%s" % (op, a["relpath"])])
                a["operational_branch_present"] = (rc3 == 0)
                if rc3 == 0:
                    n_op += 1
            else:
                a["operational_branch_present"] = None
            _recompute_published(a)
    return {"in_asset_branch": n_asset, "in_operational_branch": n_op}


# ---------------------------------------------------------------------------
# 7. ways 4+5: HTTP raw URL + sha comparison (bounded, resumable)

def default_asset_fetch(url, timeout=DEFAULT_HTTP_TIMEOUT,
                        sha_cap_bytes=DEFAULT_SHA_CAP):
    """GET the raw URL. Returns {status, body, truncated, final_url,
    elapsed, reason}. Bodies above sha_cap are read only up to the cap
    (truncated=True, body=None) - the sha is then skipped, not faked.
    Never raises; failures come back as reason strings.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            chunks = []
            total = 0
            truncated = False
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if sha_cap_bytes and total > sha_cap_bytes:
                    truncated = True
                    break
                chunks.append(chunk)
            return {
                "status": status,
                "body": None if truncated else b"".join(chunks),
                "truncated": truncated,
                "final_url": resp.geturl(),
                "elapsed": round(time.time() - t0, 3),
                "reason": None,
            }
    except urllib.error.HTTPError as e:
        try:
            b = e.read(1024)
        except Exception:
            b = b""
        return {
            "status": e.code, "body": b, "truncated": False,
            "final_url": None, "elapsed": round(time.time() - t0, 3),
            "reason": "http_%d" % e.code,
        }
    except Exception as e:
        if isinstance(e, socket.timeout) or "timed out" in str(e).lower():
            reason = "timeout"
        else:
            reason = "network_error"
        return {
            "status": None, "body": None, "truncated": False,
            "final_url": None, "elapsed": round(time.time() - t0, 3),
            "reason": "%s: %s" % (reason, type(e).__name__),
        }


def _fp_range_get(url, rng, timeout, limit):
    """One real Range GET -> (status, body, content_length).

    Reads at most `limit` bytes: if the server ignores the Range header it
    streams the full file, but we only consume the window and abort - the
    full body is never downloaded."""
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Range": rng})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(limit)
        clen = resp.headers.get("Content-Length")
        return int(resp.status), body, (int(clen) if clen else None)


def fp_range_fetch(url, fp, timeout=DEFAULT_HTTP_TIMEOUT, rng_get=None):
    """Bounded remote probe for ONE large asset: at most two Range GETs
    (head and tail windows of the local fingerprint) - never downloads the
    full body. GitHub raw (and any RFC-compliant endpoint) honours Range.

    rng_get: injectable callable(range_header) -> (status, body, clen)
    (default: a real Range GET). Used by offline tests.
    Returns {status, fp_ok, size_ok, remote_size, head_ok, tail_ok, reason}.
    fp_ok is True only when head window AND tail window AND total size all
    match the local file - that is what sets sha_match=True on the row."""
    chunk = fp.get("chunk") or FP_CHUNK
    size = fp.get("size_bytes")
    out = {"http_status": None, "fp_ok": None, "size_ok": None,
           "remote_size": None, "head_ok": None, "tail_ok": None,
           "reason": None}
    if rng_get is None:
        def rng_get(rng):
            return _fp_range_get(url, rng, timeout, chunk + 16)

    # -- head window
    try:
        st, bh, clen = rng_get("bytes=0-%d" % (chunk - 1))
    except Exception as e:
        out["reason"] = "%s: %s" % (
            "http_%s" % getattr(e, "code", "?"), type(e).__name__)
        out["http_status"] = getattr(e, "code", None)
        return out
    out["http_status"] = st
    if st == 200:
        # server ignored Range and streamed the whole file: only trust the
        # head window when exactly the window size came back
        if clen is not None and clen == chunk and len(bh) == chunk:
            out["head_ok"] = (_sha256_bytes(bh) == fp.get("head_sha256"))
            out["remote_size"] = clen
            if size is not None:
                out["size_ok"] = (clen == size)
        else:
            out["reason"] = "range_ignored_full_body"
            return out
    elif st == 206:
        out["head_ok"] = (_sha256_bytes(bh) == fp.get("head_sha256"))
        out["remote_size"] = clen
        if size is not None:
            out["size_ok"] = (clen == size)
    else:
        out["reason"] = "head_http_%s" % st
        return out

    # -- tail window
    if not size:
        out["reason"] = out.get("reason") or "no_local_size"
        out["fp_ok"] = False
        return out
    lo = max(0, size - chunk)
    try:
        st2, bt, _clen2 = rng_get("bytes=%d-" % lo)
    except Exception as e:
        out["reason"] = "%s: %s" % (
            "tail_http_%s" % getattr(e, "code", "?"), type(e).__name__)
        out["fp_ok"] = False
        return out
    if st2 == 206:
        out["tail_ok"] = (_sha256_bytes(bt) == fp.get("tail_sha256"))
    elif st2 == 200:
        # tail Range ignored: only trust it when the body is exactly the
        # expected tail window
        need = min(chunk, size)
        if len(bt) == need:
            out["tail_ok"] = (_sha256_bytes(bt) == fp.get("tail_sha256"))
        else:
            out["reason"] = "tail_range_ignored"
            out["fp_ok"] = False
            return out
    else:
        out["reason"] = "tail_http_%s" % st2
        out["fp_ok"] = False
        return out

    if out["head_ok"] is True and out["tail_ok"] is True \
            and out["size_ok"] is True:
        out["fp_ok"] = True
    else:
        out["fp_ok"] = False
    return out


def _http_one(fetch, url, a, timeout, cap):
    try:
        r = fetch(url, timeout=timeout)
    except Exception as e:
        a["http_status"] = None
        a["http_reason"] = "fetch_error: %s" % type(e).__name__
        a["sha_match"] = None
        a["http_verified_at"] = _utcnow()
        return {"http_status": None, "http_reason": a["http_reason"],
                "sha_match": None, "http_verified_at": a["http_verified_at"]}
    status = r.get("status")
    a["http_status"] = status
    a["http_verified_at"] = _utcnow()
    if status == 200:
        a["http_reason"] = None
        body = r.get("body")
        if r.get("truncated") or (isinstance(body, (bytes, bytearray))
                                  and cap and len(body) > cap):
            a["sha_match"] = "skipped_large"
        elif isinstance(body, (bytes, bytearray)) and body:
            if a.get("sha256"):
                a["sha_match"] = (_sha256_bytes(bytes(body))
                                  == a["sha256"])
            else:
                a["sha_match"] = "n/a"
        else:
            a["http_reason"] = "no_body"
            a["sha_match"] = "n/a"
    else:
        if status is not None:
            a["http_reason"] = r.get("reason") or "http_%s" % status
        else:
            a["http_reason"] = r.get("reason") or "http_error"
        a["sha_match"] = None
    return {"http_status": status, "http_reason": a["http_reason"],
            "sha_match": a["sha_match"],
            "http_verified_at": a["http_verified_at"],
            "elapsed": r.get("elapsed")}


def _load_cache(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _save_cache(cache, path):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def verify_http(registry, fetch=None, timeout=DEFAULT_HTTP_TIMEOUT,
                max_requests=DEFAULT_MAX_REQUESTS,
                max_workers=DEFAULT_MAX_WORKERS,
                sha_cap_bytes=DEFAULT_SHA_CAP, cache_path=None,
                verify_statuses=None, fp_probe=None):
    """Ways 4+5 over the registry.

    fetch: callable(url, timeout=...) -> dict (default_asset_fetch when
           None). Injectable for offline tests.
    fp_probe: callable(url, fingerprint, timeout) -> dict (fp_range_fetch
           when None) for large assets (way 5 bounded head/tail/size
           comparison instead of a full download). Injectable for offline
           tests.
    verify_statuses: subset of {published, not_published, missing,
           excluded} to probe; None = every entry that has an internal URL.
    Bounded: hard request budget (max_requests), <=2 concurrent workers,
    per-request timeout. Deduplicated: entries sharing the same raw URL
    (two sessions with the same filename) cost ONE request; the first entry
    carries the sha comparison, the rest mirror the HTTP result. Large
    assets with a local fingerprint use a 2-Range probe and report
    sha_match="fp_match"/"fp_mismatch" (never a plain true - it is a
    head+tail+size check, not a full body sha). Resumable: a prior cache
    JSON at cache_path is reused (its URLs are not re-fetched).
    Returns run stats.
    """
    if fetch is None:
        def fetch(url, timeout=timeout):
            return default_asset_fetch(url, timeout=timeout,
                                       sha_cap_bytes=sha_cap_bytes)
    if fp_probe is None:
        def fp_probe(url, fp, timeout=timeout):
            return fp_range_fetch(url, fp, timeout=timeout)
    cache = _load_cache(cache_path) if cache_path else {}
    workers = max(1, min(2, int(max_workers)))
    stats = {
        "entries_checked": 0,
        "distinct_urls": 0,
        "requests_used": 0,
        "reused_from_prior": 0,
        "skipped_budget": 0,
        "http_200": 0,
        "http_404": 0,
        "http_other": 0,
        "http_error": 0,
        "sha_match_true": 0,
        "sha_match_false": 0,
        "sha_skipped_large": 0,
        "sha_na": 0,
        "fp_probes": 0,
        "fp_match": 0,
        "fp_mismatch": 0,
        "fp_error": 0,
    }
    # dedup by URL: sessions sharing a filename produce the same raw URL -
    # fetch it once and share the result (way 4/5 is per-URL, not per-row)
    by_url = {}
    for _s, a in iter_assets(registry):
        if verify_statuses and a.get("published") not in verify_statuses:
            continue
        url = a.get("_raw_url")
        if not url:
            continue
        stats["entries_checked"] += 1
        by_url.setdefault(url, []).append(a)
    stats["distinct_urls"] = len(by_url)
    to_fetch = []
    for url, entries in by_url.items():
        c = cache.get(url)
        if c:
            for a in entries:
                a["http_status"] = c.get("http_status")
                a["http_reason"] = c.get("http_reason")
                a["sha_match"] = c.get("sha_match")
                a["http_verified_at"] = c.get("http_verified_at")
                if c.get("fingerprint"):
                    a["fingerprint_probe"] = c["fingerprint"]
            stats["reused_from_prior"] += len(entries)
        else:
            to_fetch.append((url, entries))
    budget = max(0, int(max_requests) - stats["requests_used"])
    for url, entries in to_fetch[budget:]:
        for a in entries:
            a["http_status"] = None
            a["http_reason"] = "budget_exhausted"
            a["sha_match"] = None
        stats["skipped_budget"] += len(entries)
    to_fetch = to_fetch[:budget]
    if to_fetch:
        stats["requests_used"] += len(to_fetch)

        def _mirror(entries, res):
            if len(entries) > 1:
                for a in entries[1:]:
                    a["http_status"] = res.get("http_status")
                    a["http_reason"] = res.get("http_reason")
                    a["sha_match"] = res.get("sha_match")
                    a["http_verified_at"] = res.get("http_verified_at")
                    if res.get("fingerprint"):
                        a["fingerprint_probe"] = res["fingerprint"]

        def _one(url, entries):
            # the first entry carries the comparison; entries sharing the
            # URL mirror the result
            first = entries[0]
            fp = first.get("fingerprint")
            if fp and first.get("exists_on_disk"):
                # large asset: bounded 2-Range probe (no full download)
                stats["fp_probes"] += 1
                try:
                    fr = fp_probe(url, fp, timeout=timeout)
                except Exception as e:
                    fr = {"http_status": None, "fp_ok": None, "reason":
                          "probe_error: %s" % type(e).__name__}
                first["http_status"] = fr.get("http_status")
                first["http_verified_at"] = _utcnow()
                if fr.get("fp_ok") is True:
                    first["sha_match"] = "fp_match"
                    first["http_reason"] = None
                    stats["fp_match"] += 1
                elif fr.get("fp_ok") is False:
                    first["sha_match"] = "fp_mismatch"
                    first["http_reason"] = fr.get("reason") or "fingerprint_mismatch"
                    stats["fp_mismatch"] += 1
                else:
                    first["sha_match"] = None
                    first["http_reason"] = fr.get("reason") or "fp_incomplete"
                    stats["fp_error"] += 1
                res = {
                    "http_status": first["http_status"],
                    "http_reason": first["http_reason"],
                    "sha_match": first["sha_match"],
                    "http_verified_at": first["http_verified_at"],
                    "fingerprint": fr,
                }
            else:
                res = _http_one(fetch, url, first, timeout, sha_cap_bytes)
            _mirror(entries, res)
            return url, res
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_one, url, entries): url
                    for url, entries in to_fetch}
            for fut in as_completed(futs):
                url, res = fut.result()
                st = res.get("http_status")
                if st == 200:
                    stats["http_200"] += 1
                elif st == 404:
                    stats["http_404"] += 1
                elif st is None:
                    stats["http_error"] += 1
                else:
                    stats["http_other"] += 1
                sm = res.get("sha_match")
                if sm is True:
                    stats["sha_match_true"] += 1
                elif sm is False:
                    stats["sha_match_false"] += 1
                elif sm == "skipped_large":
                    stats["sha_skipped_large"] += 1
                elif sm == "n/a":
                    stats["sha_na"] += 1
                cache[url] = {
                    "http_status": res.get("http_status"),
                    "http_reason": res.get("http_reason"),
                    "sha_match": res.get("sha_match"),
                    "http_verified_at": res.get("http_verified_at"),
                    "elapsed": res.get("elapsed"),
                }
                if res.get("fingerprint"):
                    cache[url]["fingerprint"] = res["fingerprint"]
    if cache_path and cache:
        _save_cache(cache, cache_path)
    return stats


# ---------------------------------------------------------------------------
# 8. reporting helpers

def five_way_row(session, a):
    """One row of the 5-way verification matrix (report-ready, no secrets)."""
    return {
        "session_id": session.get("session_id"),
        "session_uid": session.get("session_uid"),
        "quarantined": bool(session.get("quarantined")),
        "asset_type": a["asset_type"],
        "filename": a["filename"],
        "relpath": a["relpath"],
        "branch": a["branch"],
        "source": a["source"],
        "status": a["published"],
        "on_disk": a["exists_on_disk"],
        "in_asset_branch": a["exists_in_git_tree"],
        "in_operational_branch": a["operational_branch_present"],
        "raw_url": a["raw_url"],
        "sha256": a["sha256"],
        "size_bytes": a["size_bytes"],
        "produced_at": a["produced_at"],
        "processing_version": a["processing_version"],
        "publishing_commit_sha": a["publishing_commit_sha"],
        "http_status": a["http_status"],
        "http_reason": a["http_reason"],
        "sha_match": a["sha_match"],
        "http_verified_at": a["http_verified_at"],
        "fingerprint": a.get("fingerprint"),
        "fingerprint_probe": a.get("fingerprint_probe"),
    }


def _sha_bucket(sm):
    if sm is True:
        return "true"
    if sm is False:
        return "false"
    if sm in ("skipped_large", "n/a", "fp_match", "fp_mismatch"):
        return sm
    return "none"


def summarize(registry):
    """Aggregate counts for the report (per asset type + session coverage)."""
    per_type = {}
    total_assets = 0
    for _s, a in iter_assets(registry):
        total_assets += 1
        t = a["asset_type"]
        d = per_type.setdefault(t, {
            "total": 0,
            "status": {},
            "on_disk": 0,
            "in_asset_branch": 0,
            "in_operational_branch": 0,
            "operational_unknown": 0,
            "http_200": 0,
            "http_404": 0,
            "http_other": 0,
            "http_error": 0,
            "skipped_budget": 0,
            "sha_match": {"true": 0, "false": 0, "skipped_large": 0,
                          "n/a": 0, "fp_match": 0, "fp_mismatch": 0,
                          "none": 0},
            "source": {},
        })
        d["total"] += 1
        st = a["published"] or "pending"
        d["status"][st] = d["status"].get(st, 0) + 1
        if a["exists_on_disk"] is True:
            d["on_disk"] += 1
        if a["exists_in_git_tree"] is True:
            d["in_asset_branch"] += 1
        if a["operational_branch_present"] is True:
            d["in_operational_branch"] += 1
        elif a["operational_branch_present"] is None:
            d["operational_unknown"] += 1
        hs = a["http_status"]
        if hs == 200:
            d["http_200"] += 1
        elif hs == 404:
            d["http_404"] += 1
        elif hs is not None:
            d["http_other"] += 1
        elif a["http_reason"] == "budget_exhausted":
            d["skipped_budget"] += 1
        elif a["http_reason"] is not None:
            d["http_error"] += 1
        d["sha_match"][_sha_bucket(a["sha_match"])] += 1
        d["source"][a["source"]] = d["source"].get(a["source"], 0) + 1

    n_sessions = len(registry)
    n_q = sum(1 for s in registry if s.get("quarantined"))
    fam = {}
    stems = set()
    programs = set()
    ym = []
    for s in registry:
        f = s.get("stem_family") or "none"
        fam[f] = fam.get(f, 0) + 1
        if s.get("stem"):
            stems.add(s["stem"])
        if s.get("program_id") is not None:
            programs.add(s["program_id"])
        bj = s.get("broadcast_jalali")
        if bj:
            ym.append(bj[:7])
    return {
        "total_sessions": n_sessions,
        "quarantined_sessions": n_q,
        "total_assets": total_assets,
        "stem_family": fam,
        "distinct_stems": len(stems),
        "distinct_programs": len(programs),
        "jalali_year_month_min": min(ym) if ym else None,
        "jalali_year_month_max": max(ym) if ym else None,
        "asset_types": per_type,
    }
