# Radio Mar'ef RAG — Master Project Document

Documented Q&A over the **full Radio Mar'ef** archive: 4,002 broadcast sessions
(27 programs) → 76,543 chunks, each a ~1 min subtitle window, embedded with
Qwen3-Embedding-0.6B (1024-dim) and served as **grounded, cited, Persian
answers**.

**Phases**
- **STEP 1 (pilot)** — extract → chunk → embed a 50-episode sample, verify
  retrieval. See `STEP1_PILOT_REPORT.md`.
- **STEP 2 (full run)** — full 4,002-session dump (152 MB) + full embeddings
  (1.63 GB), no ES/production. See `STEP2_FULL_RUN_REPORT.md`.
- **Phase 3 (this branch)** — independent live service on 53, Neo4j `radio` DB,
  Persian frontend, `radio.ai.ismc.ir` domain plan, rag-portal integration
  design. See `PHASE3_RADIO_SERVICE_REPORT.md` (the Phase 3 master report).

## Repository layout (this `radio-rag/` dir)

```
radio-rag/
  README.md                     <- this file
  PHASE3_RADIO_SERVICE_REPORT.md<- Phase 3 master report (state/design/rollback)
  STEP1_PILOT_REPORT.md          pilot report
  STEP2_FULL_RUN_REPORT.md       full-run report
  RadioMaaref_RAG_Report.md      original pipeline report
  extract.py, chunk.py           STEP 1 extract + chunk
  full_audit.py, full_dump.py,   STEP 2 full audit / dump / embed
  full_embed.py, retrieve_test.py
  definitive_test.py, retrieval_test.py
  service/                      <- PHASE 3 deployable service
    import_radio_neo4j.py        full dump -> Neo4j `radio` DB (run in langgraph_app)
    radio_vector_search.py       validate vector search over the `radio` DB
    backend/
      api.py                     FastAPI backend (retrieval + FA gen + citations)
      docker-compose.radio.yml   radio_api (8043) + radio_frontend (8044)
      nginx.conf                 frontend nginx (proxies /api/ -> radio_api:8003)
      entrypoint.sh              renders API_UPSTREAM into the nginx conf
    frontend/
      index.html, app.js, style.css   Persian RTL SPA (SSE chat + citations)
  state/                         manifests only (dump/vectors are gitignored)
```

## How it works (Phase 3)

1. **Retrieval** — question embedded with `Qwen3-Embedding-0.6B` (1024) via the
   shared LiteLLM gateway, then KNN over the Neo4j `radio` DB's
   `vector_index_chunk` (1024-dim COSINE, HNSW m=16, quantized).
2. **Generation** — `qwen38` (same gateway) answers **only** from the retrieved
   chunks, Persian, with inline `[n]` citations and `enable_thinking:false`.
3. **Citations** — each source = program + air date (FA + Gregorian when valid,
   else «نامشخص») + `start_hms`–`end_hms` time range + `session_id` + score.
   Simulcasts (same stem, different `session_id`) are never merged.
4. **Independence** — separate containers/ports (8043/8044), separate Neo4j DB,
   reuses the existing LiteLLM models. No existing product is modified.

## Deploy (server 53)

```bash
# data already imported into the Neo4j `radio` DB; to (re)import after a new dump:
docker cp <dump>/dump_v2.jsonl langgraph_app:/tmp/radio_dump.jsonl
docker exec langgraph_app python /tmp/import_radio_neo4j.py \
    --data /tmp/radio_dump.jsonl --collection radio --reset

# service (from /home/saber/saberprojects/radio-rag-service on 53):
docker compose -p radio -f docker-compose.radio.yml --env-file .env.radio up -d
# rollback:
docker compose -p radio -f docker-compose.radio.yml --env-file .env.radio down
```

`.env.radio` holds `NEO4J_PASSWORD` + `LITELLM_API_KEY` (and, when the §6
portal wiring is done, `RAG_SERVICE_TOKEN`). It is **gitignored** — never
commit secrets, dumps, vectors, or private keys.

## Status

- **Live on 53:** `radio_api:8043`, `radio_frontend:8044` — healthy; 4/4 real
  Persian questions pass; existing products unaffected.
- **`radio.ai.ismc.ir` domain/HTTPS:** BLOCKED on root/sudo access to server 52
  (BT-panel Nginx + certbot). The vhost + certbot steps are written in
  `PHASE3_RADIO_SERVICE_REPORT.md` §4, ready to run once root is provided.
- **rag.ai.ismc.ir `rag-radio`:** designed + endpoint proven (token-guarded,
  inert); **not** wired into production (STOP before risky change, per Phase 3
  instruction). See report §6.
