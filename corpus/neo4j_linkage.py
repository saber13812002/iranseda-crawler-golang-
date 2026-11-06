"""In-place K1-K22 linkage metadata propagation to existing Chunk nodes
(Stage 5, Task A — spec §8.4, decision D-3).

Propagates the Stage 4 ``rag_linkage.jsonl`` linkage metadata onto the
EXISTING ``Chunk`` nodes of the Neo4j ``radio`` database, in place,
additive-only and metadata-only:

* NO re-embedding, NO re-chunking, NO index rebuild, NO doc_id churn.
* Only the 20 additive contract keys (spec §7.1) are written:
  ``record_id, session_uid, program_id, program_uid, program_page_url,
  timezone, episode_url, day_archive_url, timeslot_archive_url,
  raw_srt_url, corrected_srt_url, full_text_url, corrected_text_url,
  summary_url, summary_en_url, audio_url, air_date_status, quarantined,
  linkage_version, linkage_validated_at``.
* Existing non-null values are NEVER overwritten (first run: all 20 keys
  are absent on every node, so the first apply is purely additive; a
  re-apply is a verified no-op).
* Null discipline (R5): a null linkage value is OMITTED, never written as
  "" / "null" / a template URL.
* Quarantine discipline (R4/§10.1): quarantined rows get identity/status
  metadata (record_id, session_uid, program_id, program_uid, timezone,
  air_date_status, quarantined=true, linkage_version,
  linkage_validated_at) but NO URL properties — "citable by id only".
* The join is ``Chunk.doc_id`` == rag_linkage ``doc_id`` (spec §8.3,
  realized on doc_id since one doc_id == one session; each linkage row
  has a distinct doc_id).
* Chunks whose doc_id has no linkage row are NEVER touched (unlinked:
  no properties, never partial, never fake).

Write mechanics (spec §8.4): batched ``UNWIND ... MATCH (n:Chunk)
WHERE n.doc_id = r.doc_id AND n.chunk_id = r.chunk_id SET n += r.props``
over the Neo4j HTTP tx/commit API, batches <= 900 nodes, idempotent,
resumable via a state file, dry-run MANDATORY before apply, pre-update
snapshot (counts, doc_id set + checksum, index state, deterministic
text/embedding sample, pre-existing additive-key values) stored on 53,
rollback = SET old value (only where one pre-existed) / REMOVE of the
additive keys on the affected nodes.

Reads reuse ``corpus.rag_linkage.neo4j_query`` (read-only, fail-closed
write-token guard).  The write path is a SEPARATE function with its own
guard (UNWIND/MATCH heads only; SET/REMOVE mutations only; DELETE /
CREATE / MERGE / DROP / LOAD forbidden everywhere in this module).

Usage (on 53, from the repo worktree):

    venv/bin/python -m corpus.cli neo4j-linkage snapshot --out DIR
    venv/bin/python -m corpus.cli neo4j-linkage dry-run --snapshot DIR
    venv/bin/python -m corpus.cli neo4j-linkage apply   --snapshot DIR
    venv/bin/python -m corpus.cli neo4j-linkage post    --snapshot DIR
    venv/bin/python -m corpus.cli neo4j-linkage rollback --snapshot DIR

    (standalone: venv/bin/python -m corpus.neo4j_linkage <subcommand> …)
"""

import argparse
import base64
import hashlib
import json
import os
import re
import time
import urllib.request
from datetime import datetime

from . import rag_linkage as _rl

RAG_LINKAGE_NAME = "rag_linkage.jsonl"

# ---------------------------------------------------------------------------
# Contract: rag_linkage row key -> Chunk node property (spec §7.1)

ROW_TO_PROP = {
    "record_id": "record_id",                  # K1
    "session_uid": "session_uid",              # K3
    "program_id": "program_id",                # K4
    "program_uid": "program_uid",              # K6
    "program_page_url": "program_page_url",    # K7
    "timezone": "timezone",                    # K10
    "archive_episode_url": "episode_url",      # K11
    "archive_day_url": "day_archive_url",      # K12
    "archive_time_slot_url": "timeslot_archive_url",  # K13
    "raw_srt_url": "raw_srt_url",              # K14
    "corrected_srt_url": "corrected_srt_url",  # K15
    "full_text_url": "full_text_url",          # K16
    "corrected_text_url": "corrected_text_url",  # K17
    "summary_url": "summary_url",              # K18
    "summary_en_url": "summary_en_url",        # K18 (EN, additive)
    "audio_url": "audio_url",                  # K19
    "air_date_status": "air_date_status",      # K20
    "quarantined": "quarantined",              # K21
    "linkage_version": "linkage_version",      # K22
    "linkage_validated_at": "linkage_validated_at",  # K22
}

ADDITIVE_KEYS = tuple(sorted(set(ROW_TO_PROP.values())))

# URL-valued keys — stripped entirely for quarantined rows (§10.1)
URL_KEYS = frozenset({
    "program_page_url", "episode_url", "day_archive_url",
    "timeslot_archive_url", "raw_srt_url", "corrected_srt_url",
    "full_text_url", "corrected_text_url", "summary_url",
    "summary_en_url", "audio_url",
})

# Keys every linked chunk must carry after apply (quarantine-stripped
# set for quarantined rows; identity set for both):
IDENTITY_KEYS = frozenset({
    "record_id", "session_uid", "program_id", "program_uid", "timezone",
    "air_date_status", "quarantined", "linkage_version",
    "linkage_validated_at",
})

DEFAULT_DB = "radio"
DEFAULT_BATCH = 900          # nodes per UNWIND tx (mission cap: <= 1000)
DEFAULT_SAMPLE = 150         # bounded immutable-key sample size
STATE_NAME = "linkage_update_state.json"
SNAPSHOT_NAME = "snapshot.json"

# mission sample B (Stage 3 §4.3) — always read back after apply/post
SAMPLE_B_DOCS = (
    "radio-maaref-05-03-10-05-30__s5290",
    "radio-maaref-05-03-10-05-30__s7040",
)


# ---------------------------------------------------------------------------
# small helpers

def _utcnow():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(data)
    os.replace(tmp, path)


def _sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _q(creds, db, stmt, timeout=120):
    """One read, fail-closed: raises on server-side errors too (a query
    that SUCCEEDED server-side with 0 rows is fine; a query that FAILED
    is never silently treated as an empty result set)."""
    try:
        return _rl.neo4j_query(creds, database=db, statement=stmt,
                               timeout=timeout)
    except ValueError:
        raise
    except Exception as e:
        msg = str(e)
        if "write token(s)" in msg or "read-only statement" in msg:
            raise
        raise RuntimeError("neo4j read failed: %s" % msg)


# ---------------------------------------------------------------------------
# Neo4j write path (guarded; the ONLY way this module mutates anything)

def neo4j_write(creds, database=DEFAULT_DB, statement="", parameters=None,
                timeout=180):
    """One WRITE transaction over the HTTP tx/commit API.

    Guard (fail-closed): the statement must start with UNWIND or MATCH,
    must contain at least one mutation verb (SET or REMOVE), and may not
    contain DELETE / CREATE / MERGE / DROP / LOAD anywhere.  Returns the
    list of result-row dicts (the caller checks counts)."""
    stmt = (statement or "").strip()
    head = stmt.split(None, 1)[0].upper() if stmt else ""
    if head not in ("UNWIND", "MATCH"):
        raise ValueError(
            "write path accepts only UNWIND/MATCH statements, got %r" % head)
    up = stmt.upper()
    for tok in ("DELETE", "CREATE", "MERGE", "DROP", "LOAD"):
        if re.search(r"\b%s\b" % tok, up):
            raise ValueError("forbidden token %s in write statement" % tok)
    if "SET" not in up and "REMOVE" not in up:
        raise ValueError("write path requires SET or REMOVE (read-only "
                         "statements use corpus.rag_linkage.neo4j_query)")
    host, port, user, pwd, _src = creds
    auth = base64.b64encode(
        ("%s:%s" % (user, pwd)).encode("utf-8")).decode("ascii")
    body = {"statements": [{"statement": stmt}]}
    if parameters:
        body["statements"][0]["parameters"] = parameters
    req = urllib.request.Request(
        "http://%s:%d/db/%s/tx/commit" % (host, port, database),
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Basic " + auth,
                 "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8") or "{}")
    errors = payload.get("errors") or []
    if errors:
        raise RuntimeError("neo4j write failed: %s" % json.dumps(errors))
    out = []
    for res in payload.get("results") or []:
        fields = res.get("columns") or res.get("fields") or []
        for row in res.get("data") or []:
            out.append(dict(zip(fields, row.get("row") or [])))
    return out


# ---------------------------------------------------------------------------
# linkage map

def row_props(row):
    """Per-chunk property map for ONE rag_linkage row (spec §7.1).

    Null discipline: null/empty values are OMITTED (never written).
    Quarantine discipline: quarantined rows carry identity/status keys
    only — no URL properties (§10.1, "citable by id only")."""
    props = {}
    quar = bool(row.get("quarantined"))
    for rk, pk in ROW_TO_PROP.items():
        v = row.get(rk)
        if v is None or v == "":
            continue
        if pk in URL_KEYS and quar:
            continue
        if pk == "quarantined":
            v = bool(v)
        elif pk == "program_id":
            try:
                v = int(v)
            except (TypeError, ValueError):
                continue
        props[pk] = v
    return props


def load_linkage_map(path):
    """rag_linkage.jsonl -> ({doc_id: row}, duplicates, n_rows).

    One row per session; each doc_id is expected to be unique (Stage 4
    build guarantees it — 10,568 non-null doc_ids, all distinct).  A
    duplicate doc_id is recorded; the FIRST row wins and the conflict is
    reported (never silently merged)."""
    by_doc = {}
    dups = {}
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n += 1
            d = row.get("doc_id")
            if not d:
                continue
            if d in by_doc:
                dups.setdefault(d, []).append(row)
            else:
                by_doc[d] = row
    return by_doc, dups, n


# ---------------------------------------------------------------------------
# plan (pure)

def plan_node(want, existing):
    """Decide, per additive key, what to do on ONE node.

    returns (to_set, noop, conflicts):
      to_set    — keys whose current value is NULL (safe additive write)
      noop      — keys already equal to the planned value (idempotent)
      conflicts — keys whose current value is NON-NULL and DIFFERENT
                  (NEVER overwritten; reported)"""
    to_set, noop, conflicts = {}, [], []
    for k, v in want.items():
        cur = existing.get(k)
        if cur is None:
            to_set[k] = v
        elif cur == v:
            noop.append(k)
        else:
            conflicts.append(k)
    return to_set, noop, conflicts


def build_write_rows(plans, batch=DEFAULT_BATCH):
    """plans: list of {"doc_id","chunk_id","to_set"} (to_set may be {}).

    Returns (batches, skipped) where each batch is {"rows": [...],
    "n_nodes": int} with <= `batch` rows; rows with empty to_set are
    counted in `skipped` (idempotent no-op — never rewritten)."""
    batches = []
    skipped = 0
    cur = []
    for p in plans:
        if not p.get("to_set"):
            skipped += 1
            continue
        cur.append({"doc_id": p["doc_id"], "chunk_id": p["chunk_id"],
                    "props": p["to_set"]})
        if len(cur) >= batch:
            batches.append({"rows": cur, "n_nodes": len(cur)})
            cur = []
    if cur:
        batches.append({"rows": cur, "n_nodes": len(cur)})
    return batches, skipped


# ---------------------------------------------------------------------------
# snapshot

def _doc_set_query():
    return ("MATCH (n:Chunk) WHERE n.doc_id IS NOT NULL "
            "RETURN DISTINCT n.doc_id AS doc_id ORDER BY 1")


def _sample_query(n):
    # NOTE: no sha256() — not a Cypher function; text is returned and
    # hashed client-side (emb_size is computed from size(n.embedding),
    # which DOES exist — embeddings live in the index, not as node props).
    return (
        "MATCH (n:Chunk) WHERE n.doc_id IS NOT NULL "
        "AND n.chunk_id IS NOT NULL "
        "RETURN n.doc_id AS doc_id, n.chunk_id AS chunk_id, "
        "n.chunk_text AS text, size(n.embedding) AS emb, "
        "n.session_id AS session_id "
        "ORDER BY doc_id, chunk_id LIMIT %d" % int(n))


def _existing_keys_where():
    return " OR ".join("n.%s IS NOT NULL" % k for k in ADDITIVE_KEYS)


def _existing_map():
    return "{%s}" % ", ".join("%s: n.%s" % (k, k) for k in ADDITIVE_KEYS)


def take_snapshot(creds, db=DEFAULT_DB, out_dir=None, sample=DEFAULT_SAMPLE,
                  log=print):
    """Pre-update snapshot: counts, doc_id set + checksum, index state,
    deterministic text/embedding sample, pre-existing additive-key
    values (expected empty on a first run; captured for safe rollback).

    Returns the snapshot dict (also written to <out_dir>/snapshot.json
    + SHA256SUMS).  Read-only."""
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_dir = out_dir or "/tmp/stage5_neo4j_snapshot_%s" % ts
    os.makedirs(out_dir, exist_ok=True)

    host, port, _u, _p, src = creds

    rows = _q(creds, db, "MATCH (n:Chunk) RETURN count(n) AS c")
    n_chunks = int(rows[0]["c"]) if rows else 0
    rows = _q(creds, db, _doc_set_query())
    doc_ids = sorted(r["doc_id"] for r in rows if r.get("doc_id") is not None)
    doc_sha = _sha256_text("\n".join(doc_ids))

    # Neo4j 2025.x: the YIELD column is `indexProvider` (not `provider`).
    idx_rows = _q(
        creds, db,
        "SHOW INDEXES YIELD name, state, indexProvider, type, entityType "
        "WHERE name = 'vector_index_chunk' "
        "RETURN name, state, indexProvider, type, entityType")
    index = None
    if idx_rows:
        r = idx_rows[0]
        index = {"name": r.get("name"), "state": r.get("state"),
                 "provider": r.get("indexProvider"), "type": r.get("type"),
                 "entity_type": r.get("entityType")}

    sample_rows = _q(creds, db, _sample_query(sample))
    sample_data = [{"doc_id": r["doc_id"], "chunk_id": r["chunk_id"],
                    "text_sha256": _sha256_text(r["text"] or ""),
                    "emb_size": r["emb"],
                    "session_id": r["session_id"]} for r in sample_rows]

    pre_rows = _q(
        creds, db,
        "MATCH (n:Chunk) WHERE %s "
        "RETURN n.doc_id AS doc_id, n.chunk_id AS chunk_id, %s AS existing "
        "ORDER BY doc_id, chunk_id" % (_existing_keys_where(), _existing_map()))
    pre_state = [{"doc_id": r["doc_id"], "chunk_id": r["chunk_id"],
                  "existing": {k: v for k, v in (r["existing"] or {}).items()
                               if v is not None}}
                 for r in pre_rows]

    snap = {
        "created_at": _utcnow(),
        "host": host, "port": port, "db": db, "creds_src": src,
        "n_chunks": n_chunks,
        "n_docs": len(doc_ids),
        "doc_ids": doc_ids,
        "doc_ids_sha256": doc_sha,
        "index": index,
        "sample_n": int(sample),
        "sample": sample_data,
        "pre_state": pre_state,
    }
    sp = os.path.join(out_dir, SNAPSHOT_NAME)
    _atomic_write(sp, json.dumps(snap, ensure_ascii=False, indent=1))
    sums = "%s  %s\n" % (_sha256_file(sp), SNAPSHOT_NAME)
    _atomic_write(os.path.join(out_dir, "SHA256SUMS"), sums)
    log("snapshot written to %s (chunks=%d docs=%d pre_state=%d)"
        % (out_dir, n_chunks, len(doc_ids), len(pre_state)))
    return snap


def load_snapshot(out_dir):
    sp = os.path.join(out_dir, SNAPSHOT_NAME)
    with open(sp, encoding="utf-8") as f:
        snap = json.load(f)
    sums_p = os.path.join(out_dir, "SHA256SUMS")
    if os.path.exists(sums_p):
        expected = _sha256_file(sp)
        with open(sums_p, encoding="utf-8") as f:
            line = f.readline().strip()
        if not line.startswith(expected):
            raise RuntimeError(
                "snapshot checksum mismatch — refusing to use %s" % sp)
    return snap


# ---------------------------------------------------------------------------
# live reads used by dry-run / apply / post / rollback

def live_counts(creds, db=DEFAULT_DB):
    rows = _q(creds, db, "MATCH (n:Chunk) RETURN count(n) AS c")
    n_chunks = int(rows[0]["c"]) if rows else 0
    doc_ids = sorted(r["doc_id"] for r in _q(creds, db, _doc_set_query())
                     if r.get("doc_id") is not None)
    return n_chunks, doc_ids


def live_index(creds, db=DEFAULT_DB):
    rows = _q(
        creds, db,
        "SHOW INDEXES YIELD name, state, indexProvider, type, entityType "
        "WHERE name = 'vector_index_chunk' "
        "RETURN name, state, indexProvider, type, entityType")
    return rows[0] if rows else None


def live_sample(creds, db=DEFAULT_DB, n=DEFAULT_SAMPLE):
    rows = _q(creds, db, _sample_query(n))
    return [{"doc_id": r["doc_id"], "chunk_id": r["chunk_id"],
             "text_sha256": _sha256_text(r["text"] or ""),
             "emb_size": r["emb"],
             "session_id": r["session_id"]} for r in rows]


def fetch_node_pairs(creds, db, doc_ids, chunk_docs=2000):
    """(doc_id, chunk_id) for all nodes whose doc_id is in `doc_ids`,
    fetched in doc-chunks (parameter-free statements, one tx each)."""
    out = []
    for i in range(0, len(doc_ids), chunk_docs):
        part = doc_ids[i:i + chunk_docs]
        in_list = ", ".join(json.dumps(d) for d in part)
        rows = _q(
            creds, db,
            "MATCH (n:Chunk) WHERE n.doc_id IN [%s] "
            "RETURN n.doc_id AS doc_id, n.chunk_id AS chunk_id "
            "ORDER BY doc_id, chunk_id" % in_list, timeout=300)
        out.extend((r["doc_id"], r["chunk_id"]) for r in rows)
    return out


def fetch_existing(creds, db, doc_ids, chunk_docs=2000):
    """Per-node existing additive-key values (nodes having ANY non-null
    additive key only — expected empty before the first apply)."""
    out = {}
    for i in range(0, len(doc_ids), chunk_docs):
        part = doc_ids[i:i + chunk_docs]
        in_list = ", ".join(json.dumps(d) for d in part)
        rows = _q(
            creds, db,
            "MATCH (n:Chunk) WHERE n.doc_id IN [%s] AND (%s) "
            "RETURN n.doc_id AS doc_id, n.chunk_id AS chunk_id, %s AS existing"
            % (in_list, _existing_keys_where(), _existing_map()),
            timeout=300)
        for r in rows:
            existing = {k: v for k, v in (r["existing"] or {}).items()
                        if v is not None}
            out[(r["doc_id"], r["chunk_id"])] = existing
    return out


def doc_chunk_counts(creds, db, doc_ids, chunk_docs=2000):
    """{doc_id: n_chunks}."""
    out = {}
    for i in range(0, len(doc_ids), chunk_docs):
        part = doc_ids[i:i + chunk_docs]
        in_list = ", ".join(json.dumps(d) for d in part)
        rows = _q(
            creds, db,
            "MATCH (n:Chunk) WHERE n.doc_id IN [%s] "
            "RETURN n.doc_id AS doc_id, count(*) AS c" % in_list,
            timeout=300)
        for r in rows:
            out[r["doc_id"]] = int(r["c"])
    return out


# ---------------------------------------------------------------------------
# dry-run (read-only; mandatory before apply)

def dry_run(cfg, snapshot_dir, map_path=None, db=DEFAULT_DB, log=print):
    """Full plan, zero writes.  Emits JSON: coverage, per-batch plan
    aggregates, invariance assertions vs the snapshot, conflicts."""
    creds = _rl._neo4j_creds()
    if not creds:
        raise RuntimeError("no Neo4j credentials available")
    snap = load_snapshot(snapshot_dir)
    map_path = map_path or os.path.join(cfg.out_dir, RAG_LINKAGE_NAME)
    by_doc, dups, n_rows = load_linkage_map(map_path)

    n_chunks, doc_ids = live_counts(creds, db)
    doc_sha = _sha256_text("\n".join(doc_ids))

    live_docs = set(doc_ids)
    map_docs = set(by_doc)
    linked_docs = sorted(live_docs & map_docs)
    unlinked_docs = sorted(live_docs - map_docs)
    quar_docs = sorted(d for d in linked_docs
                       if bool(by_doc[d].get("quarantined")))

    counts = doc_chunk_counts(creds, db, linked_docs + unlinked_docs)
    linked_chunks = sum(counts.get(d, 0) for d in linked_docs)
    unlinked_chunks = sum(counts.get(d, 0) for d in unlinked_docs)

    # per-node plan (existing-value aware: first run all additive keys
    # are null; a re-run after apply must show 100% noop)
    pairs = fetch_node_pairs(creds, db, linked_docs)
    existing = fetch_existing(creds, db, linked_docs)
    to_set_n = noop_n = conflict_n = 0
    conflicts = {}
    key_fill = {}
    for (d, _c) in pairs:
        want = row_props(by_doc[d])
        to_set, noop, conf = plan_node(want, existing.get((d, _c), {}))
        to_set_n += len(to_set)
        noop_n += len(noop)
        conflict_n += len(conf)
        for k in to_set:
            key_fill[k] = key_fill.get(k, 0) + 1
        if conf:
            conflicts["%s/%s" % (d, _c)] = conf

    n_batches, _skipped = build_write_rows(
        [{"doc_id": d, "chunk_id": c,
          "to_set": plan_node(row_props(by_doc[d]),
                              existing.get((d, c), {}))[0]}
         for (d, c) in pairs])

    # invariance assertions vs the snapshot (pre-write gate)
    sample = live_sample(creds, db, snap.get("sample_n", DEFAULT_SAMPLE))
    snap_by_key = {(s["doc_id"], s["chunk_id"]): s for s in snap["sample"]}
    sample_diff = []
    for s in sample:
        ref = snap_by_key.get((s["doc_id"], s["chunk_id"]))
        if ref is None or ref["text_sha256"] != s["text_sha256"] \
                or ref["emb_size"] != s["emb_size"]:
            sample_diff.append(s["doc_id"] + "/" + str(s["chunk_id"]))
    idx = live_index(creds, db)
    assertions = {
        "chunk_count": {"before": snap["n_chunks"], "live": n_chunks,
                        "pass": n_chunks == snap["n_chunks"]},
        "doc_id_set": {"before_n": snap["n_docs"], "live_n": len(doc_ids),
                       "sha_before": snap["doc_ids_sha256"],
                       "sha_live": doc_sha,
                       "pass": doc_sha == snap["doc_ids_sha256"]
                       and len(doc_ids) == snap["n_docs"]},
        "text_embedding_sample": {
            "n": len(sample),
            "diffs": sample_diff[:20],
            "pass": not sample_diff and len(sample) == len(snap["sample"])},
        "vector_index": {
            "before": snap.get("index", {}).get("state")
            if snap.get("index") else None,
            "live": idx.get("state") if idx else None,
            "pass": bool(idx) and str(idx.get("state")).upper() == "ONLINE"},
    }
    all_pass = all(a["pass"] for a in assertions.values())

    plan = {
        "mode": "dry-run", "generated_at": _utcnow(),
        "db": db, "map": map_path, "map_rows": n_rows,
        "map_docs": len(map_docs),
        "coverage": {
            "live_docs": len(live_docs), "live_chunks": n_chunks,
            "linked_docs": len(linked_docs),
            "linked_chunks": linked_chunks,
            "unlinked_docs": len(unlinked_docs),
            "unlinked_chunks": unlinked_chunks,
            "unlinked_reason": "doc_id not present in rag_linkage.jsonl "
                               "(no properties written, never partial)",
            "quarantined_docs": len(quar_docs),
            "quarantined_chunks": sum(counts.get(d, 0) for d in quar_docs),
            "quarantined_note": "identity/status keys only, no URL props",
            "map_docs_not_in_live": len(map_docs - live_docs),
            "duplicate_doc_ids": sorted(dups),
        },
        "plan": {
            "nodes": len(pairs),
            "keys_to_set": to_set_n, "keys_noop": noop_n,
            "keys_conflict": conflict_n,
            "key_fill": key_fill,
            "n_batches": n_batches,
            "batch_size": DEFAULT_BATCH,
            "conflicts": conflicts,
        },
        "assertions": assertions,
        "assertions_pass": all_pass,
    }
    out_p = os.path.join(snapshot_dir, "dry_run_plan.json")
    _atomic_write(out_p, json.dumps(plan, ensure_ascii=False, indent=1))
    log("dry-run plan written to %s (pass=%s)" % (out_p, all_pass))
    return plan


# ---------------------------------------------------------------------------
# apply

def _load_state(state_p):
    if not os.path.exists(state_p):
        return {"batches_done": []}
    with open(state_p, encoding="utf-8") as f:
        return json.load(f)


def _save_state(state_p, state, extra=None):
    s = dict(state)
    s["updated_at"] = _utcnow()
    if extra:
        s.update(extra)
    _atomic_write(state_p, json.dumps(s, ensure_ascii=False, indent=1))


def apply(cfg, snapshot_dir, map_path=None, db=DEFAULT_DB,
          batch=DEFAULT_BATCH, state_path=None, docs=None, dry_run=False,
          log=print):
    """Apply the linkage properties in batched UNWIND txs.  Idempotent
    (pure additive SET of planned values), resumable (state file skips
    completed batches).  Aborts (non-zero return) on any count mismatch,
    index OFFLINE, or assertion failure.

    ``docs`` optionally restricts the update to a subset of doc_ids
    (rehearsals); ``dry_run`` plans everything and performs NO writes and
    NO state changes."""
    creds = _rl._neo4j_creds()
    if not creds:
        raise RuntimeError("no Neo4j credentials available")
    snap = load_snapshot(snapshot_dir)
    map_path = map_path or os.path.join(cfg.out_dir, RAG_LINKAGE_NAME)
    by_doc, dups, _n_rows = load_linkage_map(map_path)
    state_p = state_path or os.path.join(snapshot_dir, STATE_NAME)
    state = _load_state(state_p)
    map_sha = _sha256_file(map_path)
    if state.get("map_sha256") and state.get("map_sha256") != map_sha:
        raise RuntimeError(
            "state file references a different map (sha mismatch) — "
            "delete the state file to restart")

    # pre-gate: index ONLINE + chunk count stable vs snapshot
    idx = live_index(creds, db)
    if not idx or str(idx.get("state")).upper() != "ONLINE":
        raise RuntimeError("BLOCKED: vector_index_chunk is not ONLINE "
                           "(state=%s) — aborting before any write"
                           % (idx.get("state") if idx else "missing"))
    n_chunks, doc_ids = live_counts(creds, db)
    if n_chunks != snap["n_chunks"]:
        raise RuntimeError(
            "BLOCKED: chunk count changed since snapshot "
            "(%d -> %d) — aborting" % (snap["n_chunks"], n_chunks))

    linked_docs = sorted(set(doc_ids) & set(by_doc))
    if docs:
        docs_set = set(docs)
        linked_docs = [d for d in linked_docs if d in docs_set]
        log("apply scoped to %d doc_ids (rehearsal)" % len(linked_docs))
    pairs = fetch_node_pairs(creds, db, linked_docs)
    existing = fetch_existing(creds, db, linked_docs)
    plans = []
    for (d, c) in pairs:
        want = row_props(by_doc[d])
        to_set, _noop, conf = plan_node(want, existing.get((d, c), {}))
        if conf:
            log("WARNING conflict %s/%s keys=%s (skipped, never overwritten)"
                % (d, c, conf))
        plans.append({"doc_id": d, "chunk_id": c, "to_set": to_set})

    batches, skipped = build_write_rows(plans, batch=batch)
    if dry_run:
        n_keys = sum(len(p["to_set"]) for p in plans)
        log("apply DRY-RUN: docs=%d nodes=%d keys_to_set=%d "
            "(no writes, state untouched)"
            % (len(linked_docs), len(plans), n_keys))
        return {"dry_run": True, "applied_nodes": 0,
                "skipped_noop_nodes": skipped, "batches": len(batches),
                "nodes": len(plans), "keys_to_set": n_keys}
    _save_state(state_p, {}, extra={
        "map_sha256": map_sha, "snapshot": snapshot_dir, "db": db,
        "map_rows": len(by_doc), "total_batches": len(batches),
        "started_at": _utcnow(),
    })
    done_keys = set(state.get("batches_done", []))
    t0 = time.time()
    applied_nodes = 0
    for bi, b in enumerate(batches):
        bkey = "b%05d-%s" % (bi, hashlib.sha256(
            json.dumps(b["rows"], sort_keys=True).encode()).hexdigest()[:12])
        if bkey in done_keys:
            continue
        stmt = (
            "UNWIND $rows AS r "
            "MATCH (n:Chunk) WHERE n.doc_id = r.doc_id "
            "AND n.chunk_id = r.chunk_id "
            "SET n += r.props "
            "RETURN count(n) AS c")
        rows = neo4j_write(creds, db, stmt, {"rows": b["rows"]})
        got = int(rows[0]["c"]) if rows else 0
        if got != b["n_nodes"]:
            raise RuntimeError(
                "BLOCKED: batch %d matched %d nodes, expected %d — "
                "aborting (remaining batches NOT applied; state saved)"
                % (bi, got, b["n_nodes"]))
        applied_nodes += got
        state.setdefault("batches_done", []).append(bkey)
        _save_state(state_p, state, extra={
            "last_batch": bi, "applied_nodes": applied_nodes})
    _save_state(state_p, state, extra={
        "complete": True, "applied_nodes": applied_nodes,
        "skipped_noop_nodes": skipped,
        "elapsed_s": round(time.time() - t0, 2)})
    log("apply complete: nodes_written=%d noop=%d batches=%d elapsed=%.1fs"
        % (applied_nodes, skipped, len(batches), time.time() - t0))
    return {"applied_nodes": applied_nodes, "skipped_noop_nodes": skipped,
            "batches": len(batches), "state": state_p}


# ---------------------------------------------------------------------------
# post-apply assertions + read-back

def readback(creds, db, doc_id):
    """All 20 additive keys (+ doc_id/chunk_id/session_id) of the first
    chunk of `doc_id`."""
    rows = _q(
        creds, db,
        "MATCH (n:Chunk) WHERE n.doc_id = %s "
        "RETURN n.doc_id AS doc_id, n.chunk_id AS chunk_id, "
        "n.session_id AS session_id, %s AS k "
        "ORDER BY n.chunk_id LIMIT 1" % (json.dumps(doc_id), _existing_map()))
    if not rows:
        return None
    r = rows[0]
    return {"doc_id": r["doc_id"], "chunk_id": r["chunk_id"],
            "session_id": r["session_id"],
            "props": {k: v for k, v in (r["k"] or {}).items()
                      if v is not None}}


def post(cfg, snapshot_dir, map_path=None, db=DEFAULT_DB,
         sample_docs=None, log=print):
    """Post-write audit (spec §8.4): counts, doc_id set, text/embedding
    sample, index state, zero null session_uid among linked chunks,
    per-doc homogeneity, and exact read-back of sample nodes (incl.
    mission sample B) vs rag_linkage.jsonl."""
    creds = _rl._neo4j_creds()
    if not creds:
        raise RuntimeError("no Neo4j credentials available")
    snap = load_snapshot(snapshot_dir)
    map_path = map_path or os.path.join(cfg.out_dir, RAG_LINKAGE_NAME)
    by_doc, _dups, _n_rows = load_linkage_map(map_path)

    n_chunks, doc_ids = live_counts(creds, db)
    doc_sha = _sha256_text("\n".join(doc_ids))
    linked_docs = sorted(set(doc_ids) & set(by_doc))
    idx = live_index(creds, db)
    sample = live_sample(creds, db, snap.get("sample_n", DEFAULT_SAMPLE))
    snap_by_key = {(s["doc_id"], s["chunk_id"]): s for s in snap["sample"]}
    sample_diff = [s["doc_id"] + "/" + str(s["chunk_id"]) for s in sample
                   if (snap_by_key.get((s["doc_id"], s["chunk_id"])) is None
                       or snap_by_key[(s["doc_id"], s["chunk_id"])]["text_sha256"]
                       != s["text_sha256"]
                       or snap_by_key[(s["doc_id"], s["chunk_id"])]["emb_size"]
                       != s["emb_size"])]

    null_uid_n = 0
    homog_bad = 0
    for i in range(0, len(linked_docs), 2000):
        part = linked_docs[i:i + 2000]
        in_list = ", ".join(json.dumps(d) for d in part)
        rows = _q(
            creds, db,
            "MATCH (n:Chunk) WHERE n.doc_id IN [%s] AND n.session_uid IS NULL "
            "RETURN count(n) AS c" % in_list)
        null_uid_n += int(rows[0]["c"]) if rows else 0
    for i in range(0, len(linked_docs), 2000):
        part = linked_docs[i:i + 2000]
        rows = _q(
            creds, db,
            "MATCH (n:Chunk) WHERE n.doc_id IN [%s] "
            "RETURN n.doc_id AS d, count(DISTINCT n.session_uid) AS u"
            % ", ".join(json.dumps(d) for d in part))
        homog_bad += sum(1 for r in rows if int(r["u"]) != 1)

    sample_docs = list(sample_docs or [])
    for d in SAMPLE_B_DOCS:
        if d in by_doc and d not in sample_docs:
            sample_docs.append(d)
    readback_out = {}
    live_doc_set = set(doc_ids)
    for d in sample_docs[:20]:
        got = readback(creds, db, d)
        want = row_props(by_doc[d]) if d in by_doc else None
        in_live = d in live_doc_set
        if in_live:
            ok = (got is not None and want is not None
                  and all(got["props"].get(k) == v for k, v in want.items()))
        else:
            # map-only doc (not present in the live db): the CORRECT result
            # is absence — we must not have written a phantom node/props.
            ok = got is None
        readback_out[d] = {"found": got is not None, "in_live": in_live,
                           "expected": "match" if in_live else "absent",
                           "match": ok,
                           "props": got["props"] if got else None}

    assertions = {
        "chunk_count": {"before": snap["n_chunks"], "live": n_chunks,
                        "pass": n_chunks == snap["n_chunks"]},
        "doc_id_set": {"sha_before": snap["doc_ids_sha256"],
                       "sha_live": doc_sha,
                       "pass": doc_sha == snap["doc_ids_sha256"]},
        "text_embedding_sample": {"diffs": sample_diff[:20],
                                  "pass": not sample_diff
                                  and len(sample) == len(snap["sample"])},
        "vector_index": {"live": idx.get("state") if idx else None,
                         "pass": bool(idx)
                         and str(idx.get("state")).upper() == "ONLINE"},
        "linked_session_uid_null": {"n": null_uid_n,
                                    "pass": null_uid_n == 0},
        "homogeneity": {"docs_checked": len(linked_docs),
                        "bad_docs": homog_bad, "pass": homog_bad == 0},
        "readback_samples": {
            d: v["match"] for d, v in readback_out.items()},
    }
    all_pass = all(v["pass"] for k, v in assertions.items()
                   if isinstance(v, dict) and "pass" in v)
    all_pass = all_pass and all(readback_out[d]["match"]
                                for d in readback_out)
    out = {"mode": "post", "generated_at": _utcnow(), "db": db,
           "linked_docs": len(linked_docs),
           "assertions": assertions,
           "readback": readback_out, "all_pass": all_pass}
    out_p = os.path.join(snapshot_dir, "post_audit.json")
    _atomic_write(out_p, json.dumps(out, ensure_ascii=False, indent=1))
    log("post audit written to %s (pass=%s)" % (out_p, all_pass))
    return out


# ---------------------------------------------------------------------------
# rollback (SET old value where one pre-existed; REMOVE otherwise)

def rollback(cfg, snapshot_dir, db=DEFAULT_DB, state_path=None,
             map_path=None, docs=None, dry_run=False, log=print):
    """Reverse the additive write.  Safe because the snapshot captured
    every pre-existing non-null additive value (expected: none on a
    first run, so rollback = REMOVE of the keys on the affected nodes).

    ``docs`` optionally restricts the rollback to a subset of doc_ids
    (rehearsals); ``dry_run`` computes the full plan without any write;
    ``map_path`` defaults to <cfg.out_dir>/rag_linkage.jsonl when it exists."""
    creds = _rl._neo4j_creds()
    if not creds:
        raise RuntimeError("no Neo4j credentials available")
    snap = load_snapshot(snapshot_dir)
    state_p = state_path or os.path.join(snapshot_dir, STATE_NAME)
    state = _load_state(state_p)
    if not state.get("complete") and not state.get("batches_done"):
        log("WARNING: state file shows no completed apply — rolling back "
            "anyway (harmless if nothing was written)")

    # affected doc_ids = linked docs present in the snapshot
    if map_path is None:
        cfg_out = getattr(cfg, "out_dir", None)
        if (cfg_out
                and os.path.exists(os.path.join(cfg_out, RAG_LINKAGE_NAME))):
            map_path = os.path.join(cfg_out, RAG_LINKAGE_NAME)
    if map_path and os.path.exists(map_path):
        by_doc, _d, _n = load_linkage_map(map_path)
        affected = sorted(set(snap["doc_ids"]) & set(by_doc))
    else:
        affected = list(snap["doc_ids"])
    if docs:
        docs_set = set(docs)
        affected = [d for d in affected if d in docs_set]
    pre = {(p["doc_id"], p["chunk_id"]): p["existing"]
           for p in snap.get("pre_state", [])}
    pairs = fetch_node_pairs(creds, db, affected)
    keys_with_pre = sorted({k for v in pre.values() for k in v})
    if dry_run:
        n_ops = sum(len([k for k in ADDITIVE_KEYS
                         if k not in pre.get((d, c), {})])
                    for (d, c) in pairs)
        log("rollback DRY-RUN: nodes=%d node-key removals=%d "
            "(no writes)" % (len(pairs), n_ops))
        return {"dry_run": True, "nodes": len(pairs),
                "node_key_removals": n_ops,
                "restored_keys": keys_with_pre}
    n_ops = 0
    for i in range(0, len(pairs), DEFAULT_BATCH):
        part = pairs[i:i + DEFAULT_BATCH]
        rows = []
        for (d, c) in part:
            rows.append({"doc_id": d, "chunk_id": c})
        # (1) restore pre-existing values (per-node map, expected empty)
        set_rows = [{"doc_id": d, "chunk_id": c,
                     "old": pre.get((d, c), {})} for (d, c) in part]
        if any(r["old"] for r in set_rows):
            neo4j_write(
                creds, db,
                "UNWIND $rows AS r "
                "MATCH (n:Chunk) WHERE n.doc_id = r.doc_id "
                "AND n.chunk_id = r.chunk_id "
                "SET n += r.old "
                "RETURN count(n) AS c",
                {"rows": set_rows})
        # (2) REMOVE each key (per key, only for nodes without a pre-value
        #     for that key — keys with pre-values were just restored)
        for k in ADDITIVE_KEYS:
            rem = [{"doc_id": r["doc_id"], "chunk_id": r["chunk_id"]}
                   for r in set_rows if k not in r["old"]]
            if not rem:
                continue
            neo4j_write(
                creds, db,
                "UNWIND $rows AS r "
                "MATCH (n:Chunk) WHERE n.doc_id = r.doc_id "
                "AND n.chunk_id = r.chunk_id "
                "REMOVE n.%s "
                "RETURN count(n) AS c" % k,
                {"rows": rem})
            n_ops += len(rem)
    log("rollback complete: %d node-key removals over %d nodes"
        % (n_ops, len(pairs)))
    return {"nodes": len(pairs), "node_key_removals": n_ops,
            "restored_keys": keys_with_pre}


# ---------------------------------------------------------------------------
# CLI

def main(cfg, argv=None, log=print):
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("snapshot", help="pre-update snapshot (read-only)")
    sp.add_argument("--out", default=None)
    sp.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    sp.add_argument("--db", default=DEFAULT_DB)

    dp = sub.add_parser("dry-run", help="full plan, zero writes")
    dp.add_argument("--snapshot", required=True)
    dp.add_argument("--map", default=None)
    dp.add_argument("--db", default=DEFAULT_DB)

    apy = sub.add_parser("apply", help="apply the linkage (writes)")
    apy.add_argument("--snapshot", required=True)
    apy.add_argument("--map", default=None)
    apy.add_argument("--db", default=DEFAULT_DB)
    apy.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    apy.add_argument("--state", default=None)
    apy.add_argument("--docs", default="",
                     help="comma-separated doc_ids to restrict the apply "
                          "(rehearsals)")
    apy.add_argument("--dry-run", action="store_true",
                     help="plan only: zero writes, state untouched")

    pp = sub.add_parser("post", help="post-write audit + read-back")
    pp.add_argument("--snapshot", required=True)
    pp.add_argument("--map", default=None)
    pp.add_argument("--db", default=DEFAULT_DB)
    pp.add_argument("--sample-docs", default="",
                    help="comma-separated doc_ids to read back "
                         "(mission sample B is always included)")

    rp = sub.add_parser("rollback", help="remove the additive keys")
    rp.add_argument("--snapshot", required=True)
    rp.add_argument("--map", default=None)
    rp.add_argument("--db", default=DEFAULT_DB)
    rp.add_argument("--state", default=None)
    rp.add_argument("--docs", default="",
                    help="comma-separated doc_ids to restrict the rollback "
                         "(rehearsals)")
    rp.add_argument("--dry-run", action="store_true",
                    help="plan only: zero writes")

    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        take_snapshot(_rl._neo4j_creds(), db=a.db, out_dir=a.out,
                      sample=a.sample, log=log)
        return 0
    if a.cmd == "dry-run":
        plan = dry_run(cfg, a.snapshot, map_path=a.map, db=a.db, log=log)
        print(json.dumps(plan, ensure_ascii=False, indent=1))
        return 0 if plan["assertions_pass"] else 2
    if a.cmd == "apply":
        apply(cfg, a.snapshot, map_path=a.map, db=a.db, batch=a.batch,
              state_path=a.state,
              docs=[d for d in a.docs.split(",") if d.strip()] or None,
              dry_run=a.dry_run, log=log)
        return 0
    if a.cmd == "post":
        out = post(cfg, a.snapshot, map_path=a.map, db=a.db,
                   sample_docs=[d for d in a.sample_docs.split(",")
                                if d.strip()], log=log)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0 if out["all_pass"] else 2
    if a.cmd == "rollback":
        out = rollback(cfg, a.snapshot, db=a.db, state_path=a.state,
                       map_path=a.map,
                       docs=[d for d in a.docs.split(",") if d.strip()]
                       or None,
                       dry_run=a.dry_run, log=log)
        print(json.dumps(out, ensure_ascii=False))
        return 0
    return 1


def _main():
    from . import config as _config
    cfg = _config.Config.from_env()
    return main(cfg)


if __name__ == "__main__":
    import sys
    sys.exit(_main())
