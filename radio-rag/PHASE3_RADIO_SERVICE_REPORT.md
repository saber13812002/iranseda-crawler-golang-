# Radio Mar'ef RAG — Phase 3: Independent Service, Domain, HTTPS, Integration

> **Phase 3** (executable). Goal: `radio.ai.ismc.ir` must **really open** and give
> **documented answers** over the **full** radio corpus. A dump file or an "up"
> container alone is not done. This report records exactly what was built, what
> works, what is blocked, and how to roll back each production change.

**Date:** 2026-10-22 · **Branch:** `phase3-radio-rag-service` · **Repo:** `iranseda-crawler-golang-`

---

## 1. Verified real state (baseline)

| Item | Real value (verified on 53) |
|---|---|
| Corpus sessions | 4,002 (of 4,100 episodes; 478 air-date unknown, 3,624 valid) |
| Documents (doc_id) | 4,002 (doc_id = `<stem>__s<session_id>`) |
| Chunks | **76,543** (dump_v2.jsonl, ~152 MB) |
| Embeddings | 76,543 × **1024**-dim, Qwen3-Embedding-0.6B, L2-normalized (~1.63 GB) |
| Programs | 27 |
| Simulcast stems | 652 stems map to >1 session (max 9) — keyed on `session_id` |
| Dump sha256 / vectors sha256 | match `manifest_v2.json` / `embed_manifest.json` |
| 52 ↔ 53 connectivity | OK (53 = `jump53` LLM host; 52 via `ssh 172.20.1.52` from 53) |
| `radio.ai.ismc.ir` DNS | **already** resolves to `172.20.1.52` (same as taghrir/rag/mesbah) — no DNS change needed |
| Free ports on 53 | 8043/8044 were free → **chosen** for radio backend/frontend |
| Existing baseline health | mesbah/taghrir/eiis/ragportal all `/api/health` → 200 |

No re-embedding was done (the user instruction forbids it unless validation
requires — it did not).

## 2. Retrieval target — independent Neo4j `radio` database

Chose the **existing shared Neo4j server** (`neo4j_db`, `bolt://neo4j_db:7687`)
with a **brand-new, independent database named `radio`**. This is the same
per-corpus pattern the other products use (mesbah, taghrir, eiis each get their
own DB). 343 GB free; no existing index/volume/image was touched; `taghrir-es`
was **not** restarted.

- **Vector index:** `vector_index_chunk` on `Chunk.embedding`, **1024 dims**,
  `vector.hnsw.m=16`, `vector.quantization.enabled=true`, **COSINE** —
  byte-identical config to the mesbah index.
- **Import:** `service/import_radio_neo4j.py` (runs inside the `langgraph_app`
  container, which already has the neo4j driver + network). **Full 76,543
  chunks imported in 196 s → 1.2 GB on disk**, index **ONLINE 100 %**,
  **0 null embeddings**, 4,002 distinct doc_id / 4,002 distinct session_id.
- **Session identity verified:** the stem `radio-maaref-04-07-11-11-00` holds
  **9 sessions / 171 chunks** — two airings of the same show are *distinct*
  sources and are never merged. `radio_vector_search.py` confirms real Persian
  queries retrieve on-topic chunks (scores 0.78–0.83) with correct
  program + citation + session_id.

The 1.63 GB of vectors is **not** loaded in memory — the vectors live in the
Neo4j HNSW index on disk and only the queried neighbourhood is touched.

## 3. Independent radio service (LIVE on 53)

A **separate** FastAPI service — not a 4th scale of the shared
`langgraph-neo4j-qa` app, and it does **not** touch taghrir/mesbah/eiis/rag-portal.

| Container | Port (host 53) | Role |
|---|---|---|
| `radio_api` | **8043** → 8003 | FastAPI backend (retrieval + FA generation + citations) |
| `radio_frontend` | **8044** → 80 | nginx:alpine serving the Persian SPA, proxies `/api/` → `radio_api:8003` |

- **Config:** `service/backend/docker-compose.radio.yml` + `.env.radio`
  (gitignored; holds `NEO4J_PASSWORD` + `LITELLM_API_KEY`).
- **Model:** uses the **existing** LiteLLM gateway `http://172.20.1.52:4000/v1`
  for **both** embedding (`Qwen3-Embedding-0.6B`, 1024) and generation
  (`qwen38`). No new model is loaded.
- **Answer contract:** Persian, grounded **only** in retrieved chunks, inline
  `[n]` citations; each source shows **program name + air date (FA + Gregorian
  when valid, else «نامشخص») + time range + session_id + score**. **No date is
  ever fabricated** — unknown air dates are shown as «نامشخص».
- **Endpoints:** `POST /api/chat`, `POST /api/chat/stream` (SSE),
  `GET /api/health`, `GET /api/site`, `GET /api/programs`, and (for §6)
  `POST /api/v1/chat/completions` + `GET /api/v1/models` (guarded by
  `RAG_SERVICE_TOKEN`, **inert/403 when unset**).
- **Ops:** `restart: unless-stopped`, healthcheck on `/api/health`,
  `start_period: 120 s` (first boot runs a runtime `pip install`), full logs via
  `docker logs radio_api`.
- **Thread-safety:** each request opens its **own** Neo4j transaction
  (`execute_read`); a shared persistent session caused a "Session closed" 500
  under uvicorn's threadpool and was fixed.
- **Reasoning-model fix:** `qwen38` is a reasoning model; the request sets
  `chat_template_kwargs: {enable_thinking: false}` so tokens go to `content`
  (not `reasoning_content`), with a safe fallback.

**Verified:** 4 real Persian questions (wudu/prayer, wilayat al-faqih, family
& child-rearing, Quran exegesis) each returned a grounded FA answer with 5 real
sources (distinct `session_id`, time ranges, scores ~0.76–0.80). SSE stream
verified. **All 4 existing products still `/api/health` → 200** (no disturbance).

### Bring up / tear down (53)
```bash
cd /home/saber/saberprojects/radio-rag-service
docker compose -p radio -f docker-compose.radio.yml --env-file .env.radio up -d
docker compose -p radio -f docker-compose.radio.yml --env-file .env.radio down   # rollback
```

## 4. Domain + Nginx + Let's Encrypt — **BLOCKED (needs root on 52)**

`radio.ai.ismc.ir` currently returns **connection failure (HTTP 000)** on
52:443 — there is **no vhost and no certificate** for it (the default 52:443
cert is for `admin.ai.ismc.ir` / `git.ai.ismc.ir`). Bringing it up requires, on
server 52 (BT-panel Nginx at `/www/server/nginx/`, vhosts in
`/www/server/panel/vhost/nginx/`, certbot webroot `/www/acme`):

1. Create the `radio.ai.ismc.ir` vhost (independent — do **not** edit shared
   vhosts), proxying to 53:8044 (frontend) with `/api/` SSE streaming
   (`proxy_buffering off; proxy_read_timeout 300s;`).
2. `nginx -t` then `nginx -s reload` (backup the config first).
3. `certbot --webroot -w /www/acme -d radio.ai.ismc.ir --non-interactive
   --agree-tos -m <email> --key-type ecdsa` (reuse the existing ACME account
   `5b51c0b79a2656a3aab5b589cd7f05cd`), then enable HTTP→HTTPS redirect.
4. Verify the cert path/private key/auto-renew; keep the private key **out** of
   Git.

**Why blocked:** the `saber` account on 52 has **no passwordless sudo**
(`sudo -n` → "a password is required"); the vhost dir is not writable by
`saber`; `nginx -t`, `nginx -s reload`, and `certbot` all require root. Only a
git-user deploy key exists. **This step needs either root/sudo on 52, or the
BT-panel account** to create the site + SSL. The vhost + certbot commands above
are ready to run the moment root access is provided.

> Per the instruction, if ACME ever fails it must be diagnosed and fixed
> **without** bypassing validation (no self-signed). Nothing was bypassed.

## 5. End-to-end tests (from the real domain)

**BLOCKED by §4** — the domain is not publicly reachable (000) until the vhost
+ cert are in place. The **in-service** equivalents (against `http://53:8044`)
already PASS and are the same tests that will run against the domain once §4
clears:

| # | Test | In-service (53:8044) | From domain |
|---|---|---|---|
| 1 | HTTP→HTTPS redirect | n/a (no TLS yet) | **PENDING** §4 |
| 2 | HTTPS valid cert + hostname | n/a | **PENDING** §4 |
| 3 | Homepage HTTP 200 | **PASS** (200) | **PENDING** §4 |
| 4 | Backend `/api/health` ok | **PASS** (200, `neo4j_online:true`) | **PENDING** §4 |
| 5 | Real Persian questions | **PASS** (4/4, on-topic) | **PENDING** §4 |
| 6 | Answer relevant + valid citation | **PASS** (inline `[n]` + 5 sources) | **PENDING** §4 |
| 7 | Citation timestamp matches subtitle | **PASS** (start_hms/end_hms from dump) | **PENDING** §4 |
| 8 | Simulcasts not confused | **PASS** (s3188 vs s3198 kept distinct) | **PENDING** §4 |
| 9 | Streaming completes | **PASS** (SSE deltas → sources → done) | **PENDING** §4 |
| 10 | Other products still healthy | **PASS** (mesbah/taghrir/eiis/ragportal 200) | **PENDING** §4 |

Unexecuted tests are **not** marked PASS.

## 6. rag.ai.ismc.ir integration (`rag-radio`) — designed, **not** wired

The portal registers corpora via per-corpus LiteLLM `rag-*` aliases pointing at
each product's OpenAI-compatible `POST /api/v1/chat/completions`
(`rag-taghrir` → `http://172.20.1.52:8023`, etc.). To add **radio** without
mixing or replacing any other product:

1. Radio backend already exposes `POST /api/v1/chat/completions` +
   `GET /api/v1/models`, returning the **same** `rag.citations` shape the
   portal's `call_rag` expects. It is **token-guarded and inert (403)** until
   `RAG_SERVICE_TOKEN` is set.
2. Low-risk wiring (needs root/52 + a capacity check first, **not done**):
   - add a `rag-radio` model alias in LiteLLM → `http://172.20.1.53:8043/api/v1/chat/completions`;
   - `INSERT INTO corpus (name_fa, model, ...) VALUES ('رادیو معارف','rag-radio',...)` in the portal DB;
   - the shared QA bank would then store/filter radio QA under its own
     `corpus_id` (product ID) + independent source — no cross-product mixing.
3. **Not performed:** adding the alias, the corpus row, or touching the nightly
   QA job / GPU policy (the instruction says to STOP before a risky production
   change and do a capacity check first). The nightly job was **not** restarted.

## 7. Git / docs

- Independent branch `phase3-radio-rag-service` (off `radio-rag-step1-pilot`).
- New code lives under `radio-rag/service/` (backend + frontend + import +
  validation). `.env.radio`, dumps, vectors, and the private key are **not** in
  Git (covered by `radio-rag/.gitignore` + `service/backend/.gitignore`).
- `main` was **not** changed or merged.

## 8. Rollback (each production change)

| Change | Rollback |
|---|---|
| `radio` Neo4j database | `DROP DATABASE radio` on `neo4j_db` (independent DB; other DBs untouched) |
| `radio_api` / `radio_frontend` containers | `docker compose -p radio -f docker-compose.radio.yml down` (frees 8043/8044) |
| (future) 52 vhost | remove the single new `radio.ai.ismc.ir` vhost file + `nginx -s reload` (backup taken first) |
| (future) LE cert | `certbot delete --cert-name radio.ai.ismc.ir` |
| (future, §6) rag-radio alias + corpus row | remove the LiteLLM alias + `DELETE FROM corpus WHERE model='rag-radio'` |

## 9. Next step (nightly QA / go-live)

1. **Unblock §4:** provide root/sudo (or BT-panel access) on 52 → run the
   vhost + certbot steps → then execute the 10 e2e tests **from the real
   domain** and record PASS/FAIL.
2. After the domain is green, do the §6 `rag-radio` wiring **after** a capacity
   check (GPU + Neo4j load), so it never destabilizes the nightly QA job.
3. The full radio corpus is already importable/refreshable: re-run
   `service/import_radio_neo4j.py --reset` after a new dump to update the `radio`
   DB.
