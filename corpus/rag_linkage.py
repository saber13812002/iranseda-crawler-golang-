"""RAG linkage dataset + asset manifest (Stage 4, Task A.5).

Builds the RAG-ready citation dataset described by the spec:

* ``rag_linkage.jsonl`` — one line per ``radio_program_sessions.id``
  carrying the K1-K22 chunk metadata contract (spec §7.1) resolved
  offline, read-only and deterministic (R8).  The join is
  corpus ``record_id`` <-> RAG ``doc_id`` via ``session_id`` (spec
  §8.3): ``Chunk.session_id`` -> DB ``sessions.id`` -> ``(ch, e)`` =
  ``session_uid`` = corpus ``record_id``.  ``doc_id`` is read from the
  live Neo4j ``radio`` database (read-only HTTP transaction API; the
  53 venv has no neo4j driver) and, when Neo4j is unreachable, derived
  from the same ``<stem>__s{session_id}`` rule the RAG pipeline uses
  (``mapped_from: "db_derived"``) — the export never hard-fails on
  Neo4j unavailability.
* ``asset_manifest.jsonl`` — one line per ASSET (the Stage 3 registry
  flattened), C1..C14 + evidence fields, written to ``out_dir``.

Null discipline (R5): a key is OMITTED when null — absence = null,
never fabricated ("" / "null" / template URLs are never emitted).
Quarantine discipline (R4/§10.1): quarantined sessions are flagged
``quarantined: true`` and carry NO public archive/asset URLs (they
stay citable-by-id only).

Read-only guarantees: MySQL SELECTs only (corpus.database), ONE
``git ls-tree -r`` per run (no per-asset git calls), Neo4j
MATCH/RETURN only.  No writes to DB, Neo4j, SRT/TXT or services.

Usage:

    python -m corpus.cli rag-linkage
        # defaults: Neo4j read attempted, 30MB sha cap
    python -m corpus.rag_linkage [--no-neo4j] [--sha-cap BYTES] [--no-sha]
        # standalone flags (--sha-cap 0 == --no-sha: presence-only)

Local (no network) tests live in tests/corpus/test_rag_linkage.py.
"""

import base64
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime

from . import assets as _assets
from . import config as _config
from . import extractor as _extractor
from . import scan_assets as _scan

ASSET_MANIFEST_NAME = "asset_manifest.jsonl"
RAG_LINKAGE_NAME = "rag_linkage.jsonl"
VALIDATION_CACHE_NAME = "linkage_validation_cache.jsonl"

# K4 asset_type -> K14-K19 contract key (spec §7.1)
K_ASSET_KEYS = {
    "raw_srt": "raw_srt_url",
    "corrected_srt": "corrected_srt_url",
    "full_txt": "full_text_url",
    "corrected_txt": "corrected_text_url",
    "summary_fa": "summary_url",
    "summary_en": "summary_en_url",
    "audio": "audio_url",
}

_NEOMATCH = (
    "MATCH (n:Chunk) WHERE n.doc_id IS NOT NULL AND n.session_id IS NOT "
    "NULL RETURN DISTINCT n.doc_id AS doc_id, n.session_id AS session_id"
)

# fail-closed: these tokens mean a write/admin effect ANYWHERE in the
# statement (a read head does not make "MATCH (n) DELETE n" read-only)
_CYPHER_WRITE_TOKENS = frozenset({
    "CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE", "DROP",
    "LOAD", "CONSTRAINT", "GRANT", "REVOKE",
    "REMOVALABEL", "REMOVALABELS", "REMOVEPROPERTY", "REMOVEINDEX",
    "REMOVECONSTRAINT",
})

# internal / bulky asset-entry keys that never leave the manifest
# (size_bytes IS a C8 contract field and stays in the manifest)
_ASSET_SKIP_KEYS = frozenset(
    {"_raw_url", "_blob_url", "fingerprint"})


# ---------------------------------------------------------------------------
# small helpers

def _utcnow():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(data)
    os.replace(tmp, path)


def _utc_dt(v):
    """datetime/date/str -> 'YYYY-MM-DD HH:MM:SS' (or None)."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, str):
        return v[:19].replace("T", " ")
    return None


# ---------------------------------------------------------------------------
# doc_id — the RAG document key (spec §2.4, §8.3)

def derive_doc_id(session):
    """doc_id = ``<stem>__s{session_id}`` — the EXACT rule the RAG
    pipeline (radio-rag/extract.py) uses.  None when the session has no
    parseable filename stem (absence, never fabricated)."""
    filename = (session.get("filename") or "").strip()
    if not filename:
        return None
    stem = filename.split(".", 1)[0].strip()
    if not stem:
        return None
    return "%s__s%d" % (stem, int(session.get("id") or 0))


# ---------------------------------------------------------------------------
# Neo4j read-only access (HTTP transaction API — the 53 venv has no
# neo4j driver; MATCH/RETURN only, never a write verb)

def _docker_env(name, key):
    """Read ONE env value from a docker container (in-process, on 53).
    Never prints the value."""
    try:
        p = subprocess.run(
            ["docker", "inspect", "--format",
             "{{range .Config.Env}}{{println .}}{{end}}", name],
            capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            return None
        for line in (p.stdout or "").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip() or None
        return None
    except (OSError, subprocess.SubprocessError):
        return None


def _neo4j_creds():
    """(host, port, user, password, source) or None.

    Password resolution order: env NEO4J_PASSWORD / NEO4J_PASS, then the
    ``radio_api`` container env (in-process; never printed)."""
    host = os.environ.get("NEO4J_HOST", "127.0.0.1")
    port = int(os.environ.get("NEO4J_HTTP_PORT", "7474"))
    user = os.environ.get("NEO4J_USER", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD") or os.environ.get("NEO4J_PASS")
    src = "env"
    if not pwd:
        pwd = _docker_env("radio_api", "NEO4J_PASSWORD")
        src = "docker:radio_api"
        if not pwd:
            auth = _docker_env("neo4j_db", "NEO4J_AUTH")
            if auth:
                # NEO4J_AUTH is "user:password" — keep the password half
                pwd = auth.partition(":")[2] or None
                src = "docker:neo4j_db(NEO4J_AUTH)"
    if not pwd:
        return None
    return host, port, user, pwd, src


def neo4j_query(creds, database="radio", statement=_NEOMATCH, timeout=60):
    """One READ-ONLY transaction (MATCH/RETURN/SHOW only).

    Returns the list of result-row dicts.  Raises on any failure — the
    caller decides the fallback (db_derived doc_id, never abort)."""
    stmt = (statement or "").lstrip()
    head = stmt.split(None, 1)[0].upper() if stmt else ""
    if head not in ("MATCH", "RETURN", "SHOW", "CALL", "EXPLAIN"):
        raise ValueError("read-only statement required, got %r" % head)
    bad = set(re.findall(r"[A-Za-z_]+", stmt.upper())) & _CYPHER_WRITE_TOKENS
    if bad:
        raise ValueError(
            "read-only statement required, found write token(s) %s"
            % sorted(bad))
    host, port, user, pwd, _src = creds
    auth = base64.b64encode(
        ("%s:%s" % (user, pwd)).encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        "http://%s:%d/db/%s/tx/commit" % (host, port, database),
        data=json.dumps(
            {"statements": [{"statement": stmt}]}).encode("utf-8"),
        headers={"Authorization": "Basic " + auth,
                 "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8") or "{}")
    errors = payload.get("errors") or []
    if errors:
        raise RuntimeError(
            "neo4j query failed: %s" % json.dumps(errors, ensure_ascii=False))
    results = payload.get("results") or []
    if not results:
        return []
    # tx/commit payloads carry "columns" (neo4j 5.x); older
    # tooling used "fields" - accept both.
    fields = (results[0].get("columns")
              or results[0].get("fields") or [])
    out = []
    for row in results[0].get("data") or []:
        out.append(dict(zip(fields, row.get("row") or [])))
    return out


def fetch_neo4j_docs(log=print, timeout=60):
    """Live Neo4j ``radio`` doc inventory:
    ``{"source": "neo4j", "docs": {sid:int -> doc_id}, "n_docs": int}``
    or ``{"source": "unavailable", "docs": {}, "n_docs": 0,
    "warning": str}`` — unavailability NEVER aborts the build."""
    try:
        creds = _neo4j_creds()
    except Exception as exc:  # noqa: BLE001 - in-process probe
        return {"source": "unavailable", "docs": {}, "n_docs": 0,
                "warning": "credential probe failed: %s" % exc}
    if creds is None:
        return {"source": "unavailable", "docs": {}, "n_docs": 0,
                "warning": "neo4j credentials not found "
                           "(env NEO4J_PASSWORD or radio_api container)"}
    try:
        rows = neo4j_query(creds, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - never fail the export
        log("rag-linkage: Neo4j unavailable (%s) — "
            "falling back to db_derived doc_id" % exc)
        return {"source": "unavailable", "docs": {}, "n_docs": 0,
                "warning": "neo4j query failed: %s" % exc}
    docs = {}
    for r in rows:
        sid = r.get("session_id")
        doc = r.get("doc_id")
        if sid is None or doc is None:
            continue
        try:
            docs[int(sid)] = str(doc)
        except (TypeError, ValueError):
            continue
    log("rag-linkage: Neo4j radio -> %d distinct doc_id "
        "(%d rows)" % (len(docs), len(rows)))
    return {"source": "neo4j", "docs": docs, "n_docs": len(docs)}


# ---------------------------------------------------------------------------
# corpus record inputs

def _read_corpus_records(cfg):
    """Live corpus.jsonl (or shards) -> {session_id: record}."""
    out_dir = cfg.out_dir
    paths = []
    sp = os.path.join(out_dir, "corpus.jsonl")
    if os.path.exists(sp):
        paths.append(sp)
    elif os.path.isdir(out_dir):
        for n in sorted(os.listdir(out_dir)):
            if n.startswith("corpus-") and n.endswith(".jsonl"):
                paths.append(os.path.join(out_dir, n))
    by_sid = {}
    total = 0
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                total += 1
                sid = (rec.get("database_refs") or {}).get("session_id")
                if sid is not None:
                    by_sid[int(sid)] = rec
    return by_sid, total


def quarantine_ids(out_dir):
    """record_id set from <out_dir>/quarantine.jsonl (spec §10.1)."""
    qids = set()
    p = os.path.join(out_dir, "quarantine.jsonl")
    if not os.path.exists(p):
        return qids
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            rid = (obj.get("record") or {}).get("record_id") or \
                obj.get("quarantine", {}).get("record_id")
            if rid:
                qids.add(rid)
    return qids


def _load_validation_cache(out_dir):
    """linkage_validation_cache.jsonl (spec §6.6) -> {url: entry}.

    Accepts a JSONL object stream OR one JSON object.  Missing file ->
    {} (links stay 'eligible'/unverified; the cache is pure input)."""
    p = os.path.join(out_dir, VALIDATION_CACHE_NAME)
    cache = {}
    if not os.path.exists(p):
        return cache
    with open(p, encoding="utf-8") as f:
        content = f.read()
    try:
        obj = json.loads(content)
        if isinstance(obj, dict):
            for url, entry in obj.items():
                if isinstance(entry, dict):
                    cache[url] = entry
        return cache
    except ValueError:
        pass
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            for url, entry in obj.items():
                if isinstance(entry, dict):
                    cache[url] = entry
    return cache


# ---------------------------------------------------------------------------
# K1-K22 row builder (pure — unit-testable with fakes)

def _rec_archive_urls(rec, cache):
    """{K-key: url} from a corpus record's linkage.links.

    Status discipline (§7.2.4): a URL is served IFF the link is
    ``eligible`` (unvalidated) or ``valid`` (cache hit).  ``excluded``
    (quarantine) and ``not_eligible`` never yield a URL.  The cache
    file is the §6.6 source of ``valid``; its absence keeps links
    unverified — never a reason to fabricate."""
    out = {}
    lg = rec.get("linkage")
    if not isinstance(lg, dict):
        return out
    for lk in lg.get("links") or []:
        t = lk.get("type")
        url = lk.get("url")
        status = lk.get("status")
        if not url or status not in ("eligible", "valid"):
            continue
        entry = (cache or {}).get(url) or {}
        if entry.get("status") == "invalid":
            continue
        if t == _linkage_link_episode():
            out["archive_episode_url"] = url
        elif t == _linkage_link_day():
            out["archive_day_url"] = url
        elif t == _linkage_link_slot():
            out["archive_time_slot_url"] = url
        elif t == _linkage_link_program():
            out["program_page_url"] = url
    return out


def _linkage_link_episode():
    from .linkage import LINK_EPISODE
    return LINK_EPISODE


def _linkage_link_day():
    from .linkage import LINK_DAY_ARCHIVE
    return LINK_DAY_ARCHIVE


def _linkage_link_slot():
    from .linkage import LINK_TIME_SLOT
    return LINK_TIME_SLOT


def _linkage_link_program():
    from .linkage import LINK_PROGRAM
    return LINK_PROGRAM


def build_rag_row(session, corpus_rec, quarantined, doc_id,
                  mapped_from, cache=None, validated_at=None,
                  linkage_version="1.1"):
    """One rag_linkage.jsonl line (K1-K22, null keys omitted)."""
    sid = int(session["id"])
    row = {}

    # K1 / K2
    row["record_id"] = (corpus_rec.get("record_id")
                        if corpus_rec else None) or \
        _session_record_id(session)
    row["session_id"] = sid

    # K3 / K4
    if corpus_rec is not None:
        row["session_uid"] = corpus_rec.get("session_uid") or \
            row["record_id"]
    else:
        row["session_uid"] = _session_record_id(session)
    pid = session.get("program_id")
    if pid is not None:
        row["program_id"] = int(pid)

    # K5 / K6
    if corpus_rec is not None:
        prog = corpus_rec.get("program")
        if isinstance(prog, dict) and prog.get("name"):
            row["program_title"] = prog["name"]
        pu = corpus_rec.get("program_uid")
        if pu:
            row["program_uid"] = pu

    # K8 broadcast dates (from the record's broadcast block, as-is)
    if corpus_rec is not None:
        br = corpus_rec.get("broadcast")
        if isinstance(br, dict):
            j = br.get("jalali")
            if isinstance(j, dict) and j.get("date"):
                row["broadcast_date_persian"] = j["date"]
            g = br.get("gregorian")
            if isinstance(g, dict) and g.get("date"):
                row["broadcast_date_gregorian"] = g["date"]
            bt = (j or {}).get("time") or (g or {}).get("time")
            if bt:
                row["broadcast_time"] = bt

    # K10
    row["timezone"] = "Asia/Tehran"

    # K7 + K11-K13 (archive links; status discipline above)
    urls = _rec_archive_urls(corpus_rec, cache) if corpus_rec else {}
    if quarantined:
        urls = {}
    for k in ("program_page_url", "archive_episode_url",
              "archive_day_url", "archive_time_slot_url"):
        if urls.get(k):
            row[k] = urls[k]

    # K14-K19 (published asset URLs only — see manifest builder)
    if corpus_rec is not None and not quarantined:
        for k, v in (corpus_rec.get("_rag_asset_urls") or {}).items():
            if v:
                row[k] = v

    # K20
    if corpus_rec is not None:
        lg = corpus_rec.get("linkage")
        if isinstance(lg, dict):
            row["air_date_status"] = lg.get("air_date_status") or "none"
        else:
            row["air_date_status"] = "none"
    else:
        row["air_date_status"] = "none"

    # K21
    row["quarantined"] = bool(quarantined)

    # K22
    row["linkage_version"] = linkage_version
    if validated_at:
        row["linkage_validated_at"] = validated_at

    # identity evidence (additive; the join's own audit trail)
    if corpus_rec is not None and corpus_rec.get("session_uid_status"):
        row["session_uid_status"] = corpus_rec["session_uid_status"]
    if corpus_rec is not None and corpus_rec.get("program_uid_status"):
        row["program_uid_status"] = corpus_rec["program_uid_status"]
    if doc_id:
        row["doc_id"] = doc_id
        row["doc_id_mapped_from"] = mapped_from
    else:
        row["doc_id_missing"] = True

    return row


def _session_record_id(session):
    from .database import Database
    pid = session.get("program_id")
    link = session.get("link") or ""
    ch = Database.parse_ch(link)
    e = Database.parse_e(link)
    if ch is not None and e is not None:
        return "iranseda:ch%d:e%s" % (ch, e)
    return "iranseda:db%s:s%d" % (
        pid if pid is not None else "x", int(session.get("id") or 0))


# ---------------------------------------------------------------------------
# asset manifest (Stage 3 registry, flattened)

def _clean_asset_entry(entry):
    out = {}
    for k, v in entry.items():
        if k in _ASSET_SKIP_KEYS:
            continue
        if k == "produced_at":
            out[k] = _utc_dt(v)
        else:
            out[k] = v
    return out


def build_asset_rows(registry):
    """registry rows (corpus.assets.build_registry) -> one dict PER
    ASSET for asset_manifest.jsonl (deterministic order: registry order
    = session id order; assets already sorted by (type, filename))."""
    rows = []
    for s in registry:
        for a in s.get("assets") or []:
            row = {
                "session_id": s.get("session_id"),
                "program_id": s.get("program_id"),
                "session_uid": s.get("session_uid"),
                "quarantined": bool(s.get("quarantined")),
            }
            row.update(_clean_asset_entry(a))
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# main build

def main(cfg, log=print, neo4j=True, sha_cap=None, no_sha=False,
         validated_at=None):
    """Build rag_linkage.jsonl + asset_manifest.jsonl in cfg.out_dir.

    Returns the summary dict (the CLI prints it as JSON).
    """
    t0 = time.time()
    generated_at = _utcnow()

    by_sid, corpus_total = _read_corpus_records(cfg)
    qids = quarantine_ids(cfg.out_dir)
    cache = _load_validation_cache(cfg.out_dir)
    log("rag-linkage: corpus records=%d, quarantine ids=%d, "
        "validation cache urls=%d"
        % (corpus_total, len(qids), len(cache)))

    # --- DB (read-only): every session row --------------------------------
    from . import database as _database
    db = _database.Database(cfg)
    db.connect()
    try:
        sessions = list(db.fetch_sessions()[1])
        llm_rows = list(db.fetch_llm_outputs()[1])
        counts = db.table_counts()
    finally:
        db.close()
    log("rag-linkage: db sessions=%d, llm rows=%d"
        % (len(sessions), len(llm_rows)))

    # --- Neo4j (read-only) doc inventory -----------------------------------
    if neo4j:
        neo = fetch_neo4j_docs(log=log)
    else:
        log("rag-linkage: --no-neo4j — using db_derived doc_id")
        neo = {"source": "unavailable", "docs": {}, "n_docs": 0,
               "warning": "skipped (--no-neo4j)"}
    if neo.get("warning"):
        log("rag-linkage: neo4j note: %s" % neo["warning"])

    # --- asset branch (R7: live GITHUB_BRANCH, never hardcoded) ------------
    git_paths = None
    gh = _scan.load_github(cfg.root, cfg.root)
    branch = gh.get("branch")
    if branch:
        rc, out, err = _scan.git_out(cfg.root,
                                     ["ls-tree", "-r", "--name-only",
                                      branch])
        if rc == 0:
            git_paths = set(l for l in out.splitlines() if l.strip())
            log("rag-linkage: git ls-tree %s -> %d paths"
                % (branch, len(git_paths)))
        else:
            log("rag-linkage: git ls-tree failed (rc=%d) — "
                "git-tree tier stays null" % rc)
    else:
        log("rag-linkage: GITHUB_BRANCH not set — "
            "git-tree tier stays null")

    # --- disk tier (C9) -----------------------------------------------------
    # Asset relpaths are ROOT-relative ("downloads/..."), so check_disk
    # takes cfg.root as base (same convention as scan_assets.py).
    # cap semantics (assets.check_disk): None -> full sha256; 0 ->
    # presence-only (all C7 null); >0 -> sha only for files <= cap.
    cap = 0 if no_sha else (
        sha_cap if sha_cap is not None else _assets.DEFAULT_SHA_CAP)
    registry = _assets.build_registry(
        sessions, llm_rows, gh, quarantine_ids=qids)
    _assets.check_disk(registry, cfg.root, sha_cap_bytes=cap)
    # per-session registry index for the published-asset URL pass (K14-K19)
    registry_by_sid = {row["session_id"]: row for row in registry}
    if git_paths is not None:
        _mark_git_tree(registry, git_paths)
    log("rag-linkage: registry sessions=%d, assets=%d"
        % (len(registry), sum(s["asset_count"] for s in registry)))

    # --- per-session assembly ----------------------------------------------
    validated_at = validated_at or generated_at
    rows = []
    doc_from = {"neo4j": 0, "db_derived": 0, "missing": 0}
    air_status_counts = {}
    n_quar = 0
    for s in sessions:
        sid = int(s["id"])
        rec = by_sid.get(sid)
        uid = _assets.session_uid(s)
        quar = uid in qids
        if quar:
            n_quar += 1
        # doc_id: Neo4j read only; fallback derivation (never abort)
        doc = neo["docs"].get(sid)
        mapped = "neo4j"
        if doc is None:
            doc = derive_doc_id(s)
            mapped = "db_derived" if doc else None
        if doc is None:
            doc_from["missing"] += 1
        else:
            doc_from[mapped if mapped == "neo4j" else "db_derived"] += 1
        # published asset URLs (K14-K19) — R5: published state only
        urls = {}
        for a in (registry_by_sid.get(sid) or {}).get("assets", ()):
            key = K_ASSET_KEYS.get(a["asset_type"])
            if key and a.get("published") == _assets.PUBLISHED \
                    and a.get("raw_url"):
                urls[key] = a["raw_url"]
        if rec is not None:
            rec = dict(rec)
            rec["_rag_asset_urls"] = urls
        row = build_rag_row(s, rec, quar, doc,
                            mapped or "missing",
                            cache=cache, validated_at=validated_at)
        rows.append(row)
        st = row.get("air_date_status") or "none"
        air_status_counts[st] = air_status_counts.get(st, 0) + 1

    rows.sort(key=lambda r: r["session_id"])
    rag_lines = [json.dumps(r, ensure_ascii=False) + "\n" for r in rows]
    map_id = hashlib.sha256("".join(rag_lines).encode("utf-8")).hexdigest()

    # --- write outputs ------------------------------------------------------
    os.makedirs(cfg.out_dir, exist_ok=True)
    rag_path = os.path.join(cfg.out_dir, RAG_LINKAGE_NAME)
    _atomic_write(rag_path, "".join(rag_lines))

    asset_rows = build_asset_rows(registry)
    asset_path = os.path.join(cfg.out_dir, ASSET_MANIFEST_NAME)
    _atomic_write(asset_path,
                  "".join(json.dumps(r, ensure_ascii=False) + "\n"
                          for r in asset_rows))

    summary = {
        "module": "corpus.rag_linkage",
        "generated_at": generated_at,
        "duration_s": round(time.time() - t0, 1),
        "map_id": map_id,
        "linkage_version": "1.1",
        "sessions_total": len(sessions),
        "rag_rows": len(rows),
        "rag_quarantined": n_quar,
        "corpus_records_read": corpus_total,
        "db_sessions": counts.get("radio_program_sessions"),
        "doc_id": {"source": neo["source"],
                   "neo4j_distinct": neo.get("n_docs", 0),
                   "from_neo4j": doc_from["neo4j"],
                   "from_db_derived": doc_from["db_derived"],
                   "missing": doc_from["missing"],
                   "warning": neo.get("warning")},
        "air_date_status_counts": dict(sorted(air_status_counts.items())),
        "git_branch": branch,
        "git_tree_paths": (len(git_paths) if git_paths is not None
                           else None),
        "sha_cap": cap,
        "asset_manifest_rows": len(asset_rows),
        "asset_published": sum(
            1 for r in asset_rows
            if r.get("published") == _assets.PUBLISHED),
        "asset_excluded": sum(
            1 for r in asset_rows
            if r.get("published") == _assets.EXCLUDED),
        "outputs": {"rag_linkage": rag_path,
                    "asset_manifest": asset_path},
    }
    return summary


def _mark_git_tree(registry, git_paths):
    """Set C10 from the single ls-tree set (fast tier; C12 stays null
    — per-asset git-log is the Stage 3 deep-verification mode, not the
    corpus pass)."""
    n = 0
    for s in registry:
        for a in s["assets"]:
            a["exists_in_git_tree"] = (a["relpath"] in git_paths)
            if a["exists_in_git_tree"]:
                n += 1
            _assets._recompute_published(a)
    return n


# ---------------------------------------------------------------------------
# __main__ convenience (equivalent to corpus.cli rag-linkage)

def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-neo4j", action="store_true",
                    help="skip the Neo4j read; derive doc_id from DB")
    ap.add_argument("--sha-cap", type=int, default=None,
                    metavar="BYTES",
                    help="sha256 cap for the disk tier (default: 30MB, "
                         "the Stage 3 cap; 0 = presence-only, no sha)")
    ap.add_argument("--no-sha", action="store_true",
                    help="presence-only disk scan (C7 stays null)")
    args = ap.parse_args(argv)
    cfg = _config.Config.from_env()
    summary = main(cfg, neo4j=not args.no_neo4j, sha_cap=args.sha_cap,
                   no_sha=args.no_sha)
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
