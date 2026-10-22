#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_radio_neo4j.py — import the FULL radio dump+vectors (76,543 chunks,
1024-dim) into a NEW Neo4j database `radio` on server 53, via the graph-rag
`langgraph_app` container (which has the neo4j driver + bolt reachability + creds).

CONTRACT (Phase 3, option: Neo4j independent DB — no shared service touched):
  * NO re-embedding. Each Chunk node uses the pre-computed 1024-dim vector from
    vectors_v2.jsonl directly.
  * New database `radio` (dash/digits only — Neo4j db names can't have '_').
    Existing DBs (mesbah, taghrir, falsafe-siasi-*) are NEVER touched.
  * session_id is preserved on every node; doc_id keeps the session-scoped form
    (<stem>__s<session_id>) so two airings with identical text stay distinct.
  * Citation metadata (program, air date FA/GR, time range) is carried per chunk.
  * Vector index: 1024-dim, COSINE, quantization on — identical config to the
    proven `mesbah`/`falsafe-siasi-1000-embed-06b` indices.

Usage (inside langgraph_app):
    python import_radio_neo4j.py --vectors /tmp/vectors.jsonl --dump /tmp/dump.jsonl \
        --collection radio [--reset] [--limit N]
"""
import argparse, json, os, sys, time

from neo4j import GraphDatabase

# citation + identity metadata carried from the dump (all present per chunk)
META = ["program_name", "program_radio", "air_persian", "air_gregorian",
        "air_time", "air_source", "start_hms", "end_hms", "citation",
        "chunk_type", "language", "channel"]

DIM = 1024


def _wait_online(drv, db, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with drv.session() as s:
            row = s.run("SHOW DATABASES YIELD name, currentStatus WHERE name=$n", n=db).single()
            st = row["currentStatus"] if row else "?"
        if st in ("online", "standby"):
            print("  db %s -> %s" % (db, st))
            return
        time.sleep(3)
    raise SystemExit("database %s not online in %ds" % (db, timeout))


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--vectors", required=True, help="vectors_v2.jsonl (readable in container)")
    ap.add_argument("--dump", required=True, help="dump_v2.jsonl (citation meta, readable in container)")
    ap.add_argument("--collection", required=True, help="target Neo4j database name (no '_')")
    ap.add_argument("--reset", action="store_true", help="clear the target DB first (ONLY that DB)")
    ap.add_argument("--batch", type=int, default=250)
    ap.add_argument("--limit", type=int, default=0, help="import only first N (smoke test)")
    args = ap.parse_args()

    db = args.collection
    assert "_" not in db, "Neo4j database names cannot contain '_'; use dash/digits only"

    # load vectors: chunk_id -> vector (list of floats)
    print("loading vectors ...")
    t0 = time.time()
    vec_by_chunk = {}
    with open(args.vectors, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            vec_by_chunk[d["chunk_id"]] = d["vector"]
    nvec = len(vec_by_chunk)
    print("  %d vectors in %.1fs" % (nvec, time.time() - t0))

    # load dump meta keyed by chunk_id, attach vectors, keep order
    print("loading dump meta + attaching vectors ...")
    records = []
    with open(args.dump, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            cid = d["chunk_id"]
            v = vec_by_chunk.get(cid)
            if v is None:
                continue  # dump chunk without a vector (shouldn't happen)
            rec = dict(d)
            rec["embedding"] = v
            rec["doc_id"] = d.get("doc_id")
            rec["session_id"] = d.get("session_id")
            records.append(rec)
    if args.limit:
        records = records[:args.limit]
    if not records:
        raise SystemExit("no records to import")
    total = len(records)
    dim = len(records[0]["embedding"])
    assert dim == DIM, "unexpected dim %d (expected %d)" % (dim, DIM)
    print("importing %d chunks (dim=%d) into db %s" % (total, dim, db))

    drv = GraphDatabase.driver(os.environ["NEO4J_URI"],
                               auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]))
    try:
        # 1) ensure the (new) database exists
        with drv.session() as s:
            s.run("CREATE DATABASE `%s` IF NOT EXISTS" % db)
        print("ensuring database %s online ..." % db)
        _wait_online(drv, db)

        # 2) optional reset of ONLY the target db
        with drv.session(database=db) as s:
            if args.reset:
                before = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
                s.run("MATCH (n) DETACH DELETE n")
                print("  reset target db (removed %d pre-existing nodes)" % before)

        # 3) create Chunk nodes with DUMP's vectors (no re-embed) + citation meta
        set_clause = ", ".join("c.%s=row.%s" % (k, k) for k in META)
        q = ("UNWIND $rows AS row "
             "CREATE (c:Chunk) "
             "SET c.chunk_text=row.chunk_text, c.chunk_id=row.chunk_id, "
             "c.doc_id=row.doc_id, c.session_id=row.session_id, "
             "c.embedding=row.embedding, c._row=row._row, " + set_clause)
        t0 = time.time()
        with drv.session(database=db) as s:
            for st in range(0, total, args.batch):
                rows = []
                for i, r in enumerate(records[st:st + args.batch]):
                    row = {
                        "chunk_text": r.get("text"), "chunk_id": r.get("chunk_id"),
                        "doc_id": r.get("doc_id"), "session_id": r.get("session_id"),
                        "embedding": r["embedding"], "_row": st + i,
                    }
                    for k in META:
                        row[k] = r.get(k)
                    rows.append(row)
                s.run(q, rows=rows)
                done = min(st + args.batch, total)
                if done % 2000 < args.batch:
                    print("  %d/%d nodes (%.0fs)" % (done, total, time.time() - t0))
        print("chunks created in %.0fs" % (time.time() - t0))

        # 4) drop temp row id
        with drv.session(database=db) as s:
            s.run("MATCH (c:Chunk) REMOVE c._row")

        # 5) vector index (explicit 1024-dim COSINE config matching mesbah)
        with drv.session(database=db) as s:
            s.run(
                "CREATE VECTOR INDEX `vector_index_chunk` IF NOT EXISTS "
                "FOR (n:Chunk) ON (n.embedding) OPTIONS {indexConfig: {"
                "`vector.dimensions`: 1024, `vector.hnsw.ef_construction`: 100, "
                "`vector.hnsw.m`: 16, `vector.quantization.enabled`: true, "
                "`vector.similarity_function`: 'COSINE'}}")
        print("waiting for vector_index_chunk ONLINE ...")
        deadline = time.time() + 300
        while time.time() < deadline:
            with drv.session(database=db) as s:
                row = s.run(
                    "SHOW VECTOR INDEXES YIELD name, state, populationPercent "
                    "WHERE name='vector_index_chunk'").single()
            if row and str(row["state"]).upper() == "ONLINE":
                print("  vector_index_chunk ONLINE  populationPercent=%s" % row["populationPercent"])
                break
            time.sleep(3)
        else:
            print("  WARNING: vector_index_chunk not ONLINE in time; check manually")

        # 6) summary counts
        with drv.session(database=db) as s:
            cnt = s.run("MATCH (n:Chunk) RETURN count(n) AS c").single()["c"]
            ndoc = s.run("MATCH (n:Chunk) RETURN count(DISTINCT n.doc_id) AS c").single()["c"]
            nsess = s.run("MATCH (n:Chunk) RETURN count(DISTINCT n.session_id) AS c").single()["c"]
            nullv = s.run("MATCH (n:Chunk) WHERE n.embedding IS NULL RETURN count(n) AS c").single()["c"]
        print("DONE: chunks=%d distinct_doc_id=%d distinct_session_id=%d null_embedding=%d"
              % (cnt, ndoc, nsess, nullv))
    finally:
        drv.close()


if __name__ == "__main__":
    main()
