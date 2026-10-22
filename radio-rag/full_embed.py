#!/usr/bin/env python3
"""RADIO RAG — FULL EMBED: embed the whole session-keyed dump.

Reads full_dump/dump_v2.jsonl, embeds every chunk's `text` with the SAME
model the RAG query service uses (Qwen3-Embedding-0.6B / 1024 via LiteLLM on
52:4000), and writes a CHECKPOINTED vector file so the run is resumable:

  full_dump/vectors_v2.jsonl   one line per chunk: {chunk_id, doc_id, session_id,
                                chunk_type, dim, vector:[...]}
  full_dump/embed_manifest.json counts, dims, elapsed, bytes, sha256, params

Resumability: before embedding, load any existing vectors_v2.jsonl and skip
chunk_ids already present. If the process dies, re-running continues from where
it left off. Parallelism: N worker threads hit LiteLLM concurrently (it batches
server-side); the default N=8 cut the pilot's ~50ms/chunk single-stream to
~7ms/chunk wall-clock.

Read-only on the corpus. No secrets (LiteLLM key from env LITELLM_KEY).
"""
import json, os, sys, time, math, hashlib
import urllib.request
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

LITELLM_URL = os.environ.get("LITELLM_URL", "http://172.20.1.52:4000/v1")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "Qwen3-Embedding-0.6B")
BATCH = 32          # texts per LiteLLM call
WORKERS = int(os.environ.get("EMBED_WORKERS", "8"))  # parallel HTTP streams
RETRY = 4
SLEEP_BASE = 1.5


def embed_batch(texts):
    last = None
    for attempt in range(RETRY):
        try:
            body = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
            req = urllib.request.Request(
                LITELLM_URL + "/embeddings", data=body,
                headers={"Authorization": f"Bearer {LITELLM_KEY}",
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read().decode())
            data = sorted(d["data"], key=lambda x: x["index"])
            return [x["embedding"] for x in data]
        except Exception as e:  # noqa
            last = e
            time.sleep(SLEEP_BASE * (2 ** attempt))
    raise RuntimeError(f"embed failed after {RETRY} tries: {last}")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "full_dump"
    dump = os.path.join(root, "dump_v2.jsonl")
    vout = os.path.join(root, "vectors_v2.jsonl")
    mout = os.path.join(root, "embed_manifest.json")

    if not LITELLM_KEY:
        raise SystemExit("LITELLM_KEY not set")

    # load dump (keep chunk_id + text)
    items = []
    with open(dump, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            items.append((c["chunk_id"], c["doc_id"], c["session_id"],
                          c["chunk_type"], c["text"]))
    total = len(items)
    print(f"loaded {total} chunks from {dump}", file=sys.stderr)

    # load existing checkpoint
    done = set()
    if os.path.exists(vout):
        with open(vout, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["chunk_id"])
                except Exception:
                    pass
    print(f"checkpoint: {len(done)} already embedded, {total - len(done)} to go",
          file=sys.stderr)

    todo = [it for it in items if it[0] not in done]
    t0 = time.time()
    n_done, bytes_written, dims = 0, 0, 0
    lock = threading.Lock()

    # process in batches; each worker takes one batch
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    fout = open(vout, "a", encoding="utf-8")

    def work(batch):
        vecs = embed_batch([b[4] for b in batch])
        rows = []
        for (cid, did, sid, ctype, _t), v in zip(batch, vecs):
            rows.append(json.dumps({
                "chunk_id": cid, "doc_id": did, "session_id": sid,
                "chunk_type": ctype, "dim": len(v), "vector": v,
            }, ensure_ascii=False))
        return rows

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(work, b) for b in batches]
        for fut in as_completed(futs):
            rows = fut.result()
            with lock:
                for r in rows:
                    fout.write(r + "\n")
                    n_done += 1
                    bytes_written += len(r.encode())
                fout.flush()
                if n_done % 2000 == 0 or n_done == len(todo):
                    el = time.time() - t0
                    print(f"  {n_done}/{len(todo)} embedded | {el:.0f}s | "
                          f"{n_done/max(el,0.1):.1f} chunks/s", file=sys.stderr)
    fout.close()

    el = time.time() - t0
    # verify final file
    nfile, sz = 0, 0
    with open(vout, "rb") as f:
        for _ in f:
            nfile += 1
        sz = os.path.getsize(vout)
    # sample dims
    with open(vout, encoding="utf-8") as f:
        dims = len(json.loads(f.readline())["vector"])
    with open(vout, "rb") as f:
        h = hashlib.sha256()
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    manifest = {
        "dump_version": "2.0", "model": EMBED_MODEL, "dims": dims,
        "chunks_total": total, "chunks_embedded": nfile,
        "resume_skipped": len(done),
        "elapsed_seconds": round(el, 1),
        "rate_chunks_per_sec": round(n_done / max(el, 0.1), 1),
        "vectors_file": "vectors_v2.jsonl",
        "vectors_bytes": sz,
        "vectors_sha256": h.hexdigest(),
        "params": {"batch": BATCH, "workers": WORKERS,
                   "litellm": LITELLM_URL, "model": EMBED_MODEL},
    }
    with open(mout, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
