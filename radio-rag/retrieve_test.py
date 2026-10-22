#!/usr/bin/env python3
"""retrieve_test.py — GENUINE in-memory retrieval test over the full radio dump.

Embeds a list of real Persian questions with the SAME model the vectors were
built with (Qwen3-Embedding-0.6B / 1024 via LiteLLM on 52:4000), then ranks all
checkpointed vectors by cosine similarity. Proves: (a) the stored vectors are
searchable, (b) retrieval returns the right program + air-date citation, (c)
session-scoped doc_ids resolve back to a real session. Read-only, no ES.

Usage:
    LITELLM_KEY=... python3 retrieve_test.py /tmp/radio_pilot/full_dump \
        --queries "q1|q2|q3" [--k 5]
"""
import argparse, json, math, os, sys, time
import urllib.request

LITELLM = os.environ.get("LITELLM_URL", "http://172.20.1.52:4000/v1")
MODEL = os.environ.get("EMBED_MODEL", "Qwen3-Embedding-0.6B")

DEFAULT_QUERIES = [
    "ولایت فقیه و مبانی آن در اندیشه اسلامی چیست",
    "نقش خانواده و تربیت فرزند در اسلام",
    "حکم وضو و شرایط صحیح نماز",
    "مفهوم عدل و نقش آن در فقه اسلامی",
    "تفسیر آیه و روش فهم قرآن",
]


def embed(texts):
    key = os.environ.get("LITELLM_KEY", "")
    body = json.dumps({"model": MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(LITELLM + "/embeddings", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    return [d["embedding"] for d in data["data"]]


def load_vectors(path):
    """-> (chunk_id -> (doc_id, session_id, chunk_type, vec))"""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out[d["chunk_id"]] = (d["doc_id"], d.get("session_id"),
                                  d.get("chunk_type"), d["vector"])
    return out


def load_chunks_meta(path):
    """chunk_id -> {program_name, air_persian, air_gregorian, air_time, citation}"""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out[d["chunk_id"]] = {
                "program_name": d.get("program_name"),
                "program_radio": d.get("program_radio"),
                "air_persian": d.get("air_persian"),
                "air_gregorian": d.get("air_gregorian"),
                "air_time": d.get("air_time"),
                "citation": d.get("citation"),
                "text": d.get("text", "")[:160],
                "chunk_type": d.get("chunk_type"),
                "start_hms": d.get("start_hms"),
                "end_hms": d.get("end_hms"),
            }
    return out


def cosine(a, b):
    # both L2-normalized, so dot product == cosine
    s = 0.0
    for x, y in zip(a, b):
        s += x * y
    return s


def topk(qvec, vecs, k):
    scored = []
    for cid, (doc_id, sid, ctype, v) in vecs.items():
        scored.append((cosine(qvec, v), cid, doc_id, sid, ctype))
    scored.sort(key=lambda t: -t[0])
    return scored[:k]


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("dump_dir")
    ap.add_argument("--queries", default="|".join(DEFAULT_QUERIES))
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    vpath = os.path.join(args.dump_dir, "vectors_v2.jsonl")
    dpath = os.path.join(args.dump_dir, "dump_v2.jsonl")
    print(f"loading vectors from {vpath} ...", file=sys.stderr)
    t0 = time.time()
    vecs = load_vectors(vpath)
    print(f"  {len(vecs)} vectors loaded in {time.time()-t0:.1f}s", file=sys.stderr)
    meta = load_chunks_meta(dpath)
    print(f"  {len(meta)} chunk metas loaded", file=sys.stderr)

    qs = [q.strip() for q in args.queries.split("|") if q.strip()]
    qvecs = embed(qs)
    assert all(len(v) == 1024 for v in qvecs), "unexpected dim"

    report = {"model": MODEL, "dim": 1024, "n_vectors": len(vecs), "results": []}
    for q, qv in zip(qs, qvecs):
        hits = topk(qv, vecs, args.k)
        hits_out = []
        for score, cid, doc_id, sid, ctype in hits:
            m = meta.get(cid, {})
            hits_out.append({
                "score": round(score, 4),
                "doc_id": doc_id,
                "session_id": sid,
                "chunk_type": ctype,
                "citation": m.get("citation"),
                "program": m.get("program_name"),
                "air_fa": m.get("air_persian"),
                "air_gr": m.get("air_gregorian"),
                "time": f"{m.get('start_hms')} - {m.get('end_hms')}",
                "text": m.get("text"),
            })
        report["results"].append({"query": q, "top": hits_out})

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
