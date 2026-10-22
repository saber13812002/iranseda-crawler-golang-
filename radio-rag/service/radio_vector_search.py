#!/usr/bin/env python3
"""radio_vector_search.py — vector-search the `radio` Neo4j DB with real Persian
queries (embedded via LiteLLM 0.6B/1024) to validate the index end-to-end.
Run inside langgraph_app (has neo4j driver + bolt + creds)."""
import json, os, sys, urllib.request

LITELLM = os.environ.get("LITELLM_URL", "http://172.20.1.52:4000/v1")
MODEL = "Qwen3-Embedding-0.6B"
KEY = os.environ.get("LITELLM_KEY", "")

QUERIES = [
    "حکم وضو و شرایط صحیح نماز",
    "مبانی ولایت فقیه در اندیشه اسلامی",
    "نقش خانواده و تربیت فرزند",
    "تفسیر آیه و روش فهم قرآن",
]


def embed(texts):
    body = json.dumps({"model": MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(LITELLM + "/embeddings", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=120) as r:
        return [d["embedding"] for d in json.loads(r.read().decode())["data"]]


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(os.environ["NEO4J_URI"],
                               auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]))
    qvecs = embed(QUERIES)
    with drv.session(database="radio") as s:
        for q, qv in zip(QUERIES, qvecs):
            r = s.run(
                'CALL db.index.vector.queryNodes("vector_index_chunk", 5, $q) '
                'YIELD node, score RETURN node.program_name AS p, node.citation AS c, '
                'node.session_id AS s, node.chunk_type AS t, score AS sc ORDER BY sc DESC', q=qv)
            print(f"\nQ: {q}")
            for row in r.data():
                print(f"  {row['sc']:.4f} | {row['p']} | {row['c']} | "
                      f"{row['t']} | sess={row['s']}")
    drv.close()


if __name__ == "__main__":
    main()
