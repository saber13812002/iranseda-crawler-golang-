#!/usr/bin/env python3
"""Definitive unambiguous retrieval test: name the program + topic,
expect that program + a real time range as the top hit."""
import json, time, math, urllib.request, sys, os

LITELLM_URL = "http://172.20.1.52:4000/v1"
KEY = os.environ["LITELLM_KEY"]
MODEL = "Qwen3-Embedding-0.6B"


def embed(texts):
    req = urllib.request.Request(
        LITELLM_URL + "/embeddings",
        data=json.dumps({"model": MODEL, "input": texts}).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
    dd = sorted(d["data"], key=lambda x: x["index"])
    return [x["embedding"] for x in dd]


def norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


chunks = [json.loads(l) for l in open("/tmp/radio_pilot/state/dump_v1.jsonl", encoding="utf-8")]
t0 = time.time()
cv = [norm(v) for v in embed([c["text"] for c in chunks])]
te = time.time() - t0
print(f"indexed {len(chunks)} chunks in {te:.1f}s", file=sys.stderr)

Q = "در برنامه پرسمان خانواده چه توصیه‌ای برای تقویت مهارت‌های ارتباطی با اعضای خانواده داده شد؟"
qv = norm(embed([Q])[0])
scored = sorted(((sum(x * y for x, y in zip(qv, c)), i) for i, c in enumerate(cv)),
                reverse=True)[:3]
print(f"\nQ: {Q}\n")
for s, i in scored:
    c = chunks[i]
    print(f"[{s:.4f}] {c['chunk_type']:<14} {c['citation']}")
    print(f"    excerpt: {c['text'][:150]}")
