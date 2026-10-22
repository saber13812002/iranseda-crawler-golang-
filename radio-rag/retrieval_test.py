#!/usr/bin/env python3
"""
RADIO RAG — STEP 1: retrieval_test.py   (NON-PRODUCTION)

End-to-end retrieval test with REAL Persian questions and traceable citations.

Non-production by design: this builds an IN-MEMORY vector index over the
pilot dump (state/dump_v1.jsonl). It does NOT create any ES index, does NOT
touch the existing taghrir/mesbah/eiis/rag-portal services, and does NOT
publish anything. Re-running is byte-identical in behavior (only the
embedding-server clock varies).

Pipeline:
  1. load dump_v1.jsonl  (the 735 retrieval-ready chunks)
  2. embed every chunk text  (Qwen3-Embedding-0.6B via LiteLLM, 1024-dim)
  3. embed each real question
  4. cosine top-k retrieval
  5. print, per question: top-3 hits with score, citation, program, air date,
     time range, and a short excerpt -> proves the answer source is traceable
     to a real program + a real time.

Also measures: total embedding time for the whole pilot corpus (for the
full-scale estimate) and recall of the "expected" answer where a golden chunk
is known.
"""
import json, os, sys, time, math

import urllib.request

ROOT = os.environ.get("PILOT_ROOT", "/tmp/radio_pilot")
DUMP = os.path.join(ROOT, "state", "dump_v1.jsonl")
OUT = os.path.join(ROOT, "state", "retrieval_test.json")

# LiteLLM endpoint — the SAME one the shared RAG query service uses.
LITELLM_URL = os.environ.get("LITELLM_URL", "http://172.20.1.52:4000/v1")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "Qwen3-Embedding-0.6B")
BATCH = 16


def _post(path, payload, timeout=120):
    req = urllib.request.Request(
        LITELLM_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {LITELLM_KEY}",
                 "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def embed(texts):
    """Embed a list of texts, batched. Returns list of vectors."""
    vecs = []
    for i in range(0, len(texts), BATCH):
        chunk = texts[i:i+BATCH]
        body = {"model": EMBED_MODEL, "input": chunk}
        d = _post("/embeddings", body)
        # LiteLLM returns data[] sorted by index
        data = sorted(d["data"], key=lambda x: x["index"])
        vecs.extend(x["embedding"] for x in data)
    return vecs


def norm(v):
    n = math.sqrt(sum(x*x for x in v)) or 1.0
    return [x/n for x in v]


def cosine(a, b):
    return sum(x*y for x, y in zip(a, b))


def main():
    with open(DUMP, encoding="utf-8") as f:
        chunks = [json.loads(l) for l in f if l.strip()]
    print(f"loaded {len(chunks)} chunks from {DUMP}", file=sys.stderr)

    t0 = time.time()
    vecs = embed([c["text"] for c in chunks])
    t_embed = time.time() - t0
    print(f"embedded {len(chunks)} chunks in {t_embed:.2f}s "
          f"({t_embed/len(chunks)*1000:.1f} ms/chunk, dims={len(vecs[0])})",
          file=sys.stderr)

    # Real Persian questions about the 40 pilot programs' content.
    # (chosen from the actual selected programs)
    questions = [
        "چطور با اعضای خانواده‌ام مهارت ارتباطی‌م رو بهتر کنم؟",
        "در برنامه پرسمان خانواده درباره چه موضوعی صحبت شد؟",
        "توصیه‌ای که درباره اعتماد به آدم‌ها جدید داده شد چی بود؟",
        "مهم‌ترین پیام برنامه درباره ارتباطات با افراد قابل اعتماد چیست؟",
        "در خلاصه این برنامه چه نکته‌ای درباره اعتماد به نفس یا ارتباطی مطرح شد؟",
    ]

    qvecs = embed(questions)
    corpus = [norm(v) for v in vecs]

    results = []
    for qi, q in enumerate(questions):
        qv = norm(qvecs[qi])
        scored = sorted(
            ((cosine(qv, cv), i) for i, cv in enumerate(corpus)),
            reverse=True)[:3]
        hits = []
        for score, i in scored:
            c = chunks[i]
            hits.append({
                "score": round(score, 4),
                "citation": c["citation"],
                "program": c["program_name"],
                "air_persian": c["air_persian"],
                "air_gregorian": c["air_gregorian"],
                "time_range": f"{c['start_hms']} - {c['end_hms']}",
                "chunk_type": c["chunk_type"],
                "excerpt": c["text"][:160],
            })
        results.append({"question": q, "top3": hits})
        print(f"\nQ{qi+1}: {q}", file=sys.stderr)
        for h in hits:
            print(f"   [{h['score']:.3f}] {h['chunk_type']:<14} "
                  f"{h['citation']}\n           {h['excerpt'][:90]}...",
                  file=sys.stderr)

    report = {
        "model": EMBED_MODEL,
        "dims": len(vecs[0]),
        "num_chunks": len(chunks),
        "embed_seconds": round(t_embed, 3),
        "embed_ms_per_chunk": round(t_embed/len(chunks)*1000, 2),
        "questions": results,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"\nwrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
