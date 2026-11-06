# STAGE 4 — PRODUCTION ACCEPTANCE (IDEMPOTENT INCREMENTAL EXPORT + RECONCILE) — SERVER 53

Mission: IRANSEDA-CORPUS-2026-01 · Stage 4 of 7
Acceptance executed: 2026-11-06, 10:40–12:00 UTC (14:10–15:30 Asia/Tehran, UTC+3:30)

---

## 1. Scope & verdict

Stage 4 adds to the corpus pipeline: idempotent incremental merge export (record-level,
first-seen-wins, cross-run collisions → permanent Class-B quarantine), a no-change
fast path (DB watermark + disk signature), multi-signal change detection
(sessions / llm / asr / crop), an exclusive `export.lock` with live-pid refusal and
stale takeover, `corpus.cli reconcile` (content-fingerprint diff →
`reconcile_report.json`), and a bounded incremental window (`max_incremental_sessions`).

**Acceptance verdict: PASS** — all Step-7 acceptance criteria verified with real
command output on server 53 against the production database. One documented
deviation (§8): because the *live* `data/corpus/` asset is produced by a **different,
unlocated RAG builder at `schema_version: 1.1`**, real exports were run against the
production DB into an **isolated** output dir `data/corpus-stage4-acc/` (via
`CORPUS_OUT_DIR`). The live schema-1.1 RAG asset was proven byte-identical before
and after (never touched).

## 2. Environment

| Item | Value |
|---|---|
| Code worktree | `iranseda-corpus-wt` (branch `phase3-radio-rag-service`), base `7879d0fe4` (Stage 3) |
| Production server | 53 (`172.20.1.53`), checkout `/home/saber/saberprojects/iranseda-crawler-golang-/` (trailing slash is real) |
| Production interpreter | `dashboard/venv/bin/python3` (stdlib + pymysql; stdlib test runner, no pytest) |
| Database | MySQL @ `127.0.0.1:3308`, db `radio`, user `n8nuser` (read-only from corpus code) |
| Disk | `/dev/mapper/ubuntu--vg-ubuntu--lv` 1.5T, ~290G free (80% used) at AFTER time |

## 3. Git truth (Step 1 & 3)

### 3.1 Starting state

| Ref | SHA |
|---|---|
| Worktree HEAD before Stage 4 commit (Stage 3 base) | `7879d0fe4` |
| 53 `phase3-radio-rag-service` at BEFORE snapshot (10:49Z) | `b7c99e7e1` — `auto: refresh site + subtitles (2026-11-06_11:00)` |

### 3.2 Stage 4 commit & push

- Commit: **`9bd4c0bb2faf81ee27828ac2a526d5ff16d1937e`** — `Stage 4: idempotent incremental merge export + reconcile, exclusive job lock, multi-signal change detection`
  - Files: `corpus/config.py` (+`max_incremental_sessions`), `corpus/database.py` (+`changed_session_ids`), `corpus/exporter.py` (lock, merge-based `run_incremental`), `corpus/incremental.py` (change detection, no-change skip, bounded fallback, `reconcile()`), `corpus/scheduler.py` (Windows pid liveness), `tests/corpus/test_incremental.py` (8 new tests)
  - Stat: 6 files, **+1236 / −111**
- First push was **rejected** (remote advanced to `b7c99e7e1` via the 30-minute
  auto-refresh cron); re-based and pushed.
- **Remote verification at push time:** `git ls-remote origin
  refs/heads/phase3-radio-rag-service` → `9bd4c0bb2faf81ee27828ac2a526d5ff16d1937e`
  (== local pushed SHA).

### 3.3 Branch advanced after deploy (documented, not a failure)

The same auto-refresh cron later pushed `a1b9a003a` — `auto: refresh site + subtitles
(2026-11-06_11:30)`. At the AFTER probe:

```
53 HEAD = a1b9a003abef892f28668b15c945da50f138359f
remote head = a1b9a003abef892f28668b15c945da50f138359f   (match)
git merge-base --is-ancestor 9bd4c0bb2 HEAD → STAGE4_IS_ANCESTOR=YES
git diff --stat 9bd4c0bb2..a1b9a003a -- corpus/ tests/corpus/ → (empty: corpus package untouched)
```

So all acceptance runs executed on code that contains Stage 4 at `9bd4c0bb2` (HEAD at
run time was `9bd4c0bb2`; the 11:30 auto-refresh commit only touched site/subtitle
data, verified by the empty corpus diff).

## 4. BEFORE snapshot (Step 1, 10:49:55Z)

Live corpus (`data/corpus/`, **schema_version 1.1**, manifest `mode: incremental-merge`):

| File | Size (bytes) | sha256 |
|---|---|---|
| `corpus.jsonl` | 926,667,693 (9747 records) | `753fb9deff885d33473e453e8006a9e77a87126ae2c21c9b2eeedd398d9196fb` |
| `quarantine.jsonl` | 79,145,066 (**1147 lines**) | `ff07659990f8e04543f8e47cd2fb6839acb2b1f791d942ddce235a561a1208c1` |
| `checksums.sha256` | 239 | `facffb3340e6c0d68058d6b9f6d75bd8bafda85776c7d4d1044a1fd9b67f7bcb` |

The live 1.1 asset also carries `rag_linkage.jsonl` + `asset_manifest.jsonl` and
extra record fields (`linkage`, `pipeline_state`, `program_uid`, `session_uid`,
`source_metadata`, `speakers`). Probes found **no writer of this schema on 53**
(not the Stage 3 code, not Stage 4 — a separate, unlocated RAG builder).

Production health (BEFORE):

| Metric | Value |
|---|---|
| `session_status` | `{"subtitled": 9359, "pending_download": 1480, "failed_permanent": 57}` |
| `llm_24h` | 0 |
| `asr_24h` | 0 |
| `crop_detection` total | 22 |
| Pipeline | `run_pipeline.sh` + `download_db.go` + dashboard uvicorn all running |

## 5. Linux validation (Step 2)

On 53, after deploying the pushed SHA, full corpus suite via
`dashboard/venv/bin/python3` (stdlib runner): **98/98 passed in 0.2 s**.

## 6. Backup (Step 4)

| Item | Value |
|---|---|
| Path (on 53) | `data/corpus-backups/stage4-pre-20261106-104955.tar.gz` |
| Size | **952,616,886 bytes** |
| sha256 | **`942ab94095d7c4c92dc2aa57e77db952796572d15b222bfa294e567223911464`** |
| Contents | 28 entries verified (full `data/corpus/` tree incl. `previous/` history) |

## 7. Deploy (Step 5)

Only the corpus package was deployed on 53 (FF-merge/checkout to `9bd4c0bb2` on
`phase3-radio-rag-service`). No crawler/dashboard/whisper service was touched or
restarted. Post-deploy: `git rev-parse HEAD` = `9bd4c0bb2…`; `git diff --stat
9bd4c0bb2..HEAD -- corpus/ tests/corpus/` remains **empty** at AFTER time.

## 8. Real exports against the production DB (Step 6)

**Isolation decision (documented deviation):** a full export into the live dir would
have replaced the live schema-1.1 RAG asset with a 1.0 build (downgrade of a live
asset from another builder). All real runs therefore used `CORPUS_OUT_DIR=
data/corpus-stage4-acc` — same production DB, same downloads tree, isolated output.
The live dir was SHA-snapshotted at each checkpoint and is byte-identical at AFTER
time (§11).

### 7.1 Real full export

`python3 -m corpus.cli export` (production DB) — run_id `corpus-20261106-112250`:

```
exporter: done in 131.1s — 9749 ok, 0 invalid, 1147 quarantined, 10896 seen (total 10896)
manifest: mode "full", records_written 9749, records_invalid 0, records_quarantined 1147,
          sessions_seen 10896, watermark sessions_updated_at 2026-11-06T07:17:00 / max_id 10898
```

A second full run (`corpus-20261106-112502`, 125.6 s) reproduced identical counts
(9749 / 0 / 1147) — deterministic re-derivation of the same corpus.

### 7.2 Real incremental — B1 (idempotent skip)

State seeded identical to the current watermark + disk signature
(`[42141, 1793949405]`):

```
incremental: no changes (watermark + disk signature unchanged) — skipping export
{"skipped": true, "reason": "no changes detected", ...}
sha256sum -c checksums.sha256 → corpus.jsonl OK, quarantine.jsonl OK
B1_BYTES_UNTOUCHED=TRUE
state last_action: "skip"
```

### 7.3 Real incremental — B2 (real merge)

State seeded with `sessions_updated_at` rolled back 1 h (`06:17:00` vs current
`07:17:00`) → change detection found **60 changed sessions**:

```
exporter: incremental merge done in 53.0s — 9749 -> 9749 records (60 changed sessions, 0 cross-run collisions quarantined)
manifest (corpus-inc-20261106-113152, mode "incremental"):
  records_written 9749, records_quarantined 1147, sessions_seen 60
  change_detection.signals: {sessions: "ok", llm: "ok", asr: "ok", crop: "ok"}
  changed_session_count: 60 (ids incl. 5292…5793 and 10889…10898)
  incremental: {records_before: 9749, records_after: 9749,
                quarantined_before: 1147, quarantined_after: 1147,
                invalid_before: 0, invalid_after: 0, cross_run_collisions: 0}
```

## 9. Acceptance checks (Step 7) — all evidenced

| Check | Result | Evidence |
|---|---|---|
| **Idempotency** | PASS | B1: `skipped: true, reason: "no changes detected"`; `sha256sum -c` OK on corpus+quarantine; `B1_BYTES_UNTOUCHED=TRUE` |
| **Lock (no leftover)** | PASS | `NO_EXPORT_LOCK_AFTER_RUNS (GOOD)` after all runs |
| **Lock (concurrent refusal)** | PASS | Seeded live-pid lock (pid 998410, `SEED_PID_LIVE=YES`); concurrent `export` → `RuntimeError: export.lock held by another live process — refusing to run a concurrent export`, `exit=1`, `CONCURRENT_REFUSAL=CONFIRMED`; `LOCK_CLEANED (GOOD)` |
| **Reconcile** | PASS | `corpus.cli reconcile` → `reconcile: +0 -0 ~2 =9747 in 146.7s`; `reconcile_report.json` (357 B): `added: []`, `removed: []`, `changed: ["iranseda:ch14:e152466453", "iranseda:ch14:e152482330"]`, `unchanged: 9747` |
| **Quarantine integrity (re-derived)** | PASS | Isolated `quarantine.jsonl`: **1147 lines, 1147 unique (record_id, session_id), all class "B"** (`PERMANENT_UNTIL_IDENTITY_PROVEN`); **0 overlap** with corpus (9749 unique keys); spot-check 5/5 quarantined pairs absent from corpus |
| **Quarantine integrity (live)** | PASS | Live `quarantine.jsonl` still **1147 lines**, sha256 `ff076599…` unchanged; no quarantined record auto-merged anywhere (no 1.1-dir writes at all) |
| **Change-detection signals** | PASS | B2 manifest: `sessions: ok, llm: ok, asr: ok, crop: ok` — no `error:` signals |

**Reconcile note (honest):** the `~2 changed` records are *content* changes to two
existing records made by the live pipeline during the ~16-minute acceptance window
(reconcile re-ran a full export and fingerprint-compared) — exactly the behaviour
reconcile is designed to report. No additions or removals; nothing physically deleted.

## 10. Production health AFTER (Step 8) — 11:50Z

| Metric | BEFORE | AFTER | Delta |
|---|---|---|---|
| `session_status` | `{"subtitled": 9359, "pending_download": 1480, "failed_permanent": 57}` | `{"subtitled": 9359, "pending_download": 1481, "failed_permanent": 57}` | queue +1 (1 new session discovered by the 11:45 pipeline run) |
| `llm_24h` | 0 | 0 | 0 |
| `asr_24h` | 0 | 0 | 0 |
| `crop_detection` | 22 | 22 | 0 |
| DB watermark (sessions) | (recorded at BEFORE probe) | `2026-11-06T11:46:05` / max_id 10899 | advancing (live pipeline) |
| SRT/TXT generation | active (pipeline running) | **10 SRTs in last 24 h** (radio-maaref backfill); newest SRT+TXT pair `radio-maaref-05-08-15-06-00`; 0 in last 120 min (no episodes in that window) | no degradation |
| Pipeline | running | running: 11:19 run `END ok` (3844 s); 11:45 run `START → scan OK (1 new session) → discover DONE (0 new episodes across 32 programs)` | healthy |
| Workers | up | up: `download_db.go`, `run_pipeline.sh`, dashboard uvicorn (8990, 3 d uptime), all other uvicorn services | nothing restarted |

**Health verdict: PASS** — the main pipeline kept downloading/scanning/refreshing
through the entire acceptance window (including concurrent with the reconcile full
scan); no queue growth, no worker restarts, no SRT/TXT stall attributable to the
corpus deploy.

## 11. Live-dir non-interference proof

| Checkpoint | `corpus.jsonl` sha256 | `quarantine.jsonl` sha256 | `checksums.sha256` sha256 |
|---|---|---|---|
| BEFORE (10:49Z) | `753fb9de…` | `ff076599…` | `facffb33…` |
| AFTER (11:50Z) | `753fb9deff885d33473e453e8006a9e77a87126ae2c21c9b2eeedd398d9196fb` | `ff07659990f8e04543f8e47cd2fb6839acb2b1f791d942ddce235a561a1208c1` | `facffb3340e6c0d68058d6b9f6d75bd8bafda85776c7d4d1044a1fd9b67f7bcb` |

Byte-identical. Live `incremental_state.json` (from the 1.1 builder's own
03:00 run) also untouched. No physical deletions anywhere: Stage 4 archives every
superseded output to `previous/<run_id>/` (3-slot retention).

## 12. Constraints honored

- **Never auto-merge/reclassify quarantine** — all 1147 Class B records preserved
  verbatim (policy `PERMANENT_UNTIL_IDENTITY_PROVEN`); cross-run collisions would
  go to quarantine first-seen-wins (0 occurred in B2).
- **Never physically delete corpus history** — reconcile records changes in
  `reconcile_report.json`; every replaced output archived under `previous/`.
- **Never deploy/restart non-corpus services** — only `corpus/` +
  `tests/corpus/` deployed; verified empty diff and unchanged worker set.
- **No hard blockers** encountered; no step was skipped.

## 13. Artifacts & follow-ups

| Item | Location (on 53) |
|---|---|
| Pre-deploy backup | `data/corpus-backups/stage4-pre-20261106-104955.tar.gz` (952,616,886 B, sha256 `942ab940…`) |
| Acceptance evidence dir | `data/corpus-stage4-acc/` — `corpus.jsonl` (912,605,762 B), `quarantine.jsonl` (77,516,329 B), `manifest.json` (reconcile full run `corpus-20261106-114447`), `reconcile_report.json`, `checksums.sha256` (all `sha256sum -c` OK), `previous/` slots: `corpus-20261106-112250`, `corpus-20261106-112502`, `corpus-inc-20261106-113152` |

**Follow-up (owner decision, not a Stage 4 defect):** the live RAG asset is built at
schema 1.1 by an unlocated builder. Before Stage 4 output is ever promoted into the
live `data/corpus/`, the 1.1 builder must be located and either (a) aligned to the
1.0 contract or (b) the 1.1 fields folded into the shared schema. Until then,
isolated-dir exports remain the safe production mode.

## 14. Report delivery

- Report: `reports/corpus/STAGE_4_PRODUCTION_ACCEPTANCE.md` on branch `download-db`
  (main workspace `iranseda`), same relay as STAGE 1/2/3 reports.
- Remote SHA verified via `git ls-remote origin refs/heads/download-db` after push:
  `__REMOTE_SHA__` (== local commit SHA recorded at push time).
