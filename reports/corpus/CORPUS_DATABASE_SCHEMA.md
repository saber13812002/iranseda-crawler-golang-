# IranSeda Corpus — Stage 2: Database Schema Discovery

**Mission:** IRANSEDA CORPUS BUILDER & HUGGING FACE PUBLISHER
**Stage:** 2 — کشف ساختار واقعی دیتابیس (real schema first, no assumptions)
**Date:** 2026-11-03 19:10:52 UTC (probes `.corpus_probe2.sh` 18:20:18, `.corpus_probe5.sh` 19:10:52)
**Database:** MariaDB `iranseda` @ `127.0.0.1:3308` on server 53 (`saber@172.20.1.53`)

> **STOP rule honored:** real schema access was obtained before any data-model
> design. **Every column below was read from the live server via `DESCRIBE` /
> `information_schema`** — nothing assumed. Row counts are live values at the
> two probe timestamps (T1 = 18:20:18 UTC, T2 = 19:10:52 UTC).

---

## 1. Table inventory (18 tables)

| Table | Rows T1 | Rows T2 | Role |
|-------|---------|---------|------|
| `radio_programs` | 59 | 59 | Program registry (schedule, canonical URL) |
| `radio_program_sessions` | 10 858 | 10 858 | Episodes (audio link, filenames, pipeline status) |
| `llm_output` | 13 603 | 13 603 | **LLM-generated artifacts (corrected SRT/TXT, summary, full text, QA)** |
| `llm_job` | 1 099 | 1 099 | LLM batch-job tracker |
| `publication_task` | 69 | 69 | Reporter state machine (DO NOT TOUCH — rule 8) |
| `pipeline_runs` | 482 | **485** (+3 in 50 min — pipeline live) | Per-cron-run telemetry |
| `asr_output` | 1 | 1 | Dual-dataset ASR registry (1 failed Roshan pilot row) |
| `crop_detection` | 22 | 22 | Per-session program-boundary crop windows |
| `program_settings` | 32 | 32 | Per-program discovery/backfill settings |
| `prompts` | 4 | 4 | Prompt registry |
| `pipeline_steps` | 6 | 6 | Pipeline stage registry |
| `program_discovery` | 5 | 5 | Newly discovered program pages |
| `program_score` | 1 | 1 | Program scoring (52-dependent; 1 failed row) |
| `backfill_list` | 0 | 0 | (empty) |
| `downloaded_files` | 0 | 0 | (empty, legacy) |
| `programs` | 0 | 0 | (legacy, empty) |
| `subtitles` | 0 | 0 | (legacy, empty; the only table with a physical FK) |

Note: `notifications` (created on demand by `scripts/notify_telegram.py`)
does **not** currently exist.

---

## 2. Full column definitions (live `DESCRIBE`)

### 2.1 `radio_programs` (59 rows) — program registry

| Column | Type | Null | Key | Default | Extra |
|--------|------|------|-----|---------|-------|
| id | int | NO | PRI | — | auto_increment |
| name | varchar | YES | | | |
| url | varchar | YES | | | canonical `ch`+`m` URL |
| time | TIME | YES | | | schedule start (HH:MM:SS) |
| time_description | TEXT | YES | | | Persian free-text schedule |
| description | TEXT | YES | | | |
| created_at | TIMESTAMP | YES | | | |
| start | TIME | YES | | | (second schedule column) |
| radio | varchar | YES | | | radio name (legacy rows: empty) |
| radio_id | | YES | | | |
| is_legacy | tinyint | YES | | | 1 = pre-2026-09 rows |
| legacy_expires_at | | YES | | | |
| crop_offset | int | YES | | | seconds (1 row filled) |
| crop_enabled | tinyint | YES | | | |
| crop_auto | tinyint | YES | | | |

Fill (18:20): time 56/59, time_description 48/59, description 44/59,
start 37/59, radio 40/59, legacy_expires_at 27/59, crop_offset 1/59.

### 2.2 `radio_program_sessions` (10 858 rows) — episodes

| Column | Type | Null | Key | Notes |
|--------|------|------|-----|-------|
| id | int | NO | PRI | |
| program_id | int | YES | IDX | logical FK → `radio_programs.id` |
| link | TEXT | YES | | audio URL, e.g. `../epgarchivePart/?VALID=TRUE&ch=14&e=152507883` |
| created_at | TIMESTAMP | YES | | **crawl/insert time — NOT broadcast time** |
| filename | varchar | YES | | `radio-<ch>-<jj>-<mm>-<dd>-<hh>-<mm>-<ss>.mp3|mp4` |
| srt_filename | varchar | YES | | `radio-<ch>-<jj>-<mm>-<dd>-<hh>-<mm>-<ss>.srt` |
| is_downloaded | tinyint | YES | | |
| status | varchar | YES | IDX | subtitled / pending_download / pending_transcribe / transcribing / failed_permanent |
| is_subtitled | tinyint | YES | | |
| attempts | int | YES | | |
| last_error | TEXT | YES | | |
| updated_at | TIMESTAMP | YES | | |

Indexes: `PRIMARY(id)`, `idx_session_status(status)`, `program_id`,
**`uq_session_program_link(program_id, link)`** — the natural dedupe key.

### 2.3 `llm_output` (13 603 rows) — **corrected/derived text store**

| Column | Type | Null | Key | Notes |
|--------|------|------|-----|-------|
| id | int | NO | PRI | |
| session_id | int | NO | part of uq | logical FK → sessions |
| job_type | varchar(32) | NO | part of uq | correct_subtitles / correct_text / summary / full_text / qa |
| model | varchar(120) | NO | part of uq | `qwen38-nothinking` (old rows: `full_text` marker) |
| prompt_id | int | YES | | → `prompts.id` (1–4) |
| job_id | int | YES | | → `llm_job.id` (mostly NULL) |
| content | MEDIUMTEXT | YES | | corrected text / summary (bilingual) |
| content_en | MEDIUMTEXT | YES | | English part of summary |
| srt_content | MEDIUMTEXT | YES | | corrected SRT (job_type=correct_subtitles) |
| file_relpath | varchar | YES | | e.g. `downloads/cleaned/<stem>.correct.srt` |
| started_at / finished_at | DATETIME | YES | | |
| status | varchar | NO | | all 13 603 rows = `done` |
| error | TEXT | YES | | NULL (all done) |
| input_tokens / output_tokens | int | YES | | token accounting |

**Unique key:** `uq_out(session_id, job_type, model)` → at most one row per
(session, job_type, model). Distribution (18:20): correct_subtitles **4 245**,
correct_text **4 212**, summary **4 212**, full_text **933** (923 distinct
sessions), qa **1**.

### 2.4 `asr_output` (1 row) — ASR provider registry (dual-dataset design)

21 columns: id, session_id, program_id, provider, model_name, model_version,
pipeline_version, **audio_sha256**, processing_status, **srt_path**,
**fulltext_path**, raw_response_path, duration_ms, segment_count, word_count,
latency_ms, rtf, created_at, updated_at, error_code, error_message.
Unique: `uq_asr(session_id, provider, pipeline_version, audio_sha256)`.
The single row = Roshan pilot, `processing_status=failed`,
`error_code=UPSTREAM_503`. **Production Whisper outputs are NOT in this
table** — SRT/TXT live on disk; this table is the registry reserved for
provider comparison datasets.

### 2.5 `crop_detection` (22 rows) — per-session crop window

id PRI, **session_id UNIQUE**, program_id, start_sec int, end_sec int,
confidence enum(high,medium,low), status enum(cropped,needs_review,none),
evidence MEDIUMTEXT (JSON), updated_at.

### 2.6 `program_settings` (32 rows)

id PRI, program_id, start_mode, start_date, seeded, seeded_at,
last_discovery_at, discovery_note, created_at, updated_at.

### 2.7 `publication_task` (69 rows) — reporter state machine (rule 8: untouched)

id PRI, event_type, title, body, artifact_url, git_commit,
external_task_id, status (queued/submitted/checking/published), channels,
submitted_at, check_after, published_at, post_urls, views, last_checked_at,
error, idempotency_key, created_at, updated_at, attempts.

### 2.8 `radio_program_session_files` (0 rows)

id PRI, session_id, file_url, filename, is_downloaded. (Unused in production —
one audio file per session is modeled directly on the session row.)

### 2.9 `llm_job` (1 099 rows) — batch job tracker

id PRI, job_type, model, prompt_id, prompt_text, started_at, finished_at,
total, done, failed, note. Sample: `correct_subtitles / qwen38-nothinking /
total=2142 / done=1 / note='all-files'` (2026-10-11).

### 2.10 `pipeline_runs` (485 rows) — cron-run telemetry

id PRI, **run_id UNIQUE** (varchar 72), kind, started_at, finished_at, status,
discovered_programs, discovered_sessions, new_sessions, no_new_work,
queued_downloads, download_success, download_failure, asr_started,
asr_success, asr_failure, new_srt_count, new_txt_count,
published_output_count, **push_ok**, duration_seconds, error_summary,
created_at. Indexes: `uq_run_id`, `k_kind_start(kind,started_at)`,
`k_status(kind,status)`. 24 h window (18:20): 64 runs, 48 push_ok.

### 2.11 `pipeline_steps` (6 rows) — stage registry

id PRI, **slug UNIQUE** (varchar 48), name, input_ref (default `srt`), model,
prompt, output_suffix, output_kind, is_mechanical, enabled, sort_order,
created_at. Live rows:

| slug | input_ref | output_suffix | kind | mechanical |
|------|-----------|---------------|------|-----------|
| program_block | srt | `.program.srt` | program | 1 |
| full_text | full_text | `.full.txt` | text | 1 |
| summary | program_text | `.summary.txt` | bilingual | 0 |
| correct_text | program_text | `.correct.txt` | text | 0 |
| correct_subtitles | program_srt | `.correct.srt` | srt | 0 |
| correct_text_v2 | srt | `.correct.v2.srt` | windowed-correct | 0 |

### 2.12 `prompts` (4 rows)

id PRI, slug UNIQUE, job_type, name, prompt (mediumtext), is_default,
created_at. IDs 1–4 map to summary / correct_text / correct_subtitles / qa.

### 2.13 `program_discovery` (5 rows)

id PRI, **m UNIQUE** (varchar 8), ch, channel_name, name, url, first_seen_at,
last_seen_at (ON UPDATE CURRENT_TIMESTAMP).

### 2.14 `program_score` (1 row)

id PRI, ch, m, name, channel_name, score decimal(5,1), confidence, model,
reasons JSON, inputs JSON, status, error, created_at, scored_at.
`uq_ch_m(ch,m)`. The single row: status `pending`, error
`HTTPConnectionPool(host='172.20.1.52', port=4000)` → **server 52 down**,
scoring blocked (consistent with preflight finding).

### 2.15 `backfill_list` (0 rows)

id PRI, program_id, label, month varchar(7), status (default queued),
added_at, promoted_at, note.

### 2.16 `downloaded_files` (0 rows)

id PRI, name, link, downloaded_at. (Legacy.)

### 2.17 `programs` (0 rows) — legacy

id bigint PRI, title longtext, description longtext, created_at/updated_at
datetime(3).

### 2.18 `subtitles` (0 rows) — legacy, **the only physical FK in the schema**

id bigint PRI, program_id (FK → `programs.id`, index `fk_programs_subtitles`),
content longtext, created_at/updated_at.

---

## 3. Relationships (ER)

No foreign keys exist except `subtitles.program_id → programs.id` (both
legacy/empty). Everything else is **logical** (app-level joins):

```mermaid
erDiagram
  radio_programs ||--o{ radio_program_sessions : "program_id (logical)"
  radio_programs ||--o{ program_settings : "program_id (logical)"
  radio_program_sessions ||--o{ llm_output : "session_id (logical)"
  radio_program_sessions ||--o{ asr_output : "session_id (logical)"
  radio_program_sessions ||--o| crop_detection : "session_id (unique, logical)"
  prompts ||--o{ llm_output : "prompt_id (logical)"
  llm_job ||--o{ llm_output : "job_id (logical, mostly NULL)"
  programs ||--o{ subtitles : "FK (physical, both empty)"

  radio_programs {
    int id PK
    varchar name
    varchar url "ch + m canonical"
    time time "schedule only"
    text time_description "Persian free text"
    tinyint is_legacy
  }
  radio_program_sessions {
    int id PK
    int program_id LFK
    text link "audio URL with e= EPG id"
    varchar filename "Jalali date + time embedded"
    varchar srt_filename
    varchar status
    timestamp created_at "crawl time, NOT broadcast"
  }
  llm_output {
    int id PK
    int session_id LFK
    varchar job_type
    varchar model
    int prompt_id
    mediumtext content
    mediumtext srt_content
    mediumtext content_en
    varchar file_relpath
    datetime finished_at
  }
  asr_output {
    int id PK
    int session_id LFK
    varchar audio_sha256
    varchar srt_path
    varchar fulltext_path
    varchar processing_status
  }
  crop_detection {
    int id PK
    int session_id UK
    int start_sec
    int end_sec
    enum status
  }
  pipeline_runs {
    int id PK
    varchar run_id UK
    varchar kind
    tinyint push_ok
  }
  llm_job {
    int id PK
    varchar job_type
    int total
    int done
    int failed
  }
  prompts {
    int id PK
    varchar slug UK
    varchar job_type
  }
  pipeline_steps {
    int id PK
    varchar slug UK
    varchar output_suffix
    tinyint is_mechanical
  }
  program_discovery {
    int id PK
    varchar m UK
    int ch
  }
  program_score {
    int id PK
    int ch
    varchar m
    decimal score
  }
```

ASCII (portable):

```
radio_programs 1 ──∞ radio_program_sessions 1 ──∞ llm_output  ∞──1 prompts
        │1 ──∞ program_settings                 │∞──1 llm_job (mostly NULL)
        │1 ──∞ (backfill_list, crop via program)
        └──(ch,m)──∞ program_discovery / program_score
radio_program_sessions 1 ──∞ asr_output
radio_program_sessions 1 ──0..1 crop_detection (session_id UNIQUE)
programs 1 ──∞ subtitles   (physical FK, both tables EMPTY, legacy)
```

---

## 4. Where artifacts live (authoritative mapping)

| Artifact | Authoritative source | Path/derivation |
|----------|---------------------|-----------------|
| Original SRT | **disk**, keyed by session | `downloads/<srt_stem>.srt` or `downloads/cleaned/<srt_stem>.srt`; DB `srt_filename` filled for 4 658/10 858 but disk join (stem of filename ∪ srt_filename) gives **10 466** |
| Original TXT | **disk only** (no DB column) | `<srt_stem>.txt` alongside the SRT (top-level 7 514 + cleaned 17 026) |
| Corrected SRT | `llm_output.srt_content` (job_type=correct_subtitles) + disk | disk: `downloads/cleaned/<stem>.correct.srt` (4 284) |
| Corrected TXT | `llm_output.content` (job_type=correct_text) + disk | disk: `downloads/cleaned/<stem>.correct.txt` (4 251) |
| Bilingual summary | `llm_output.content` + `content_en` (job_type=summary) | disk: `.summary.txt` (4 251) |
| Full text (timestamps stripped) | `llm_output.content` (job_type=full_text) | disk: `.full.txt` (4 251) |
| Windowed-correct SRT v2 | disk only so far (20 files `.correct.v2.srt`; no llm_output job_type) | `downloads/cleaned/<stem>.correct.v2.srt` |
| Program-block SRT | disk (3 files `.program.srt`) | mechanical crop step |
| Audio | iranseda CDN (link) + disk mp3/mp4 | `downloads/*.mp3` (799) / `*.mp4` (2 159) |
| ASR metadata (provider, sha256) | `asr_output` (1 failed row; registry only) | Whisper outputs not registered |

**Original vs corrected independence:** corrections use distinct file
suffixes and distinct DB rows; the original SRT/TXT is never modified
(satisfies mission rule §4.2/§4.3).

**Authoritative source per corpus field:**

| Corpus field | Source |
|--------------|--------|
| program name/url/ch/m | `radio_programs` (dedupe by `(ch,m)`, keep both ids when legacy+current rows exist) |
| program schedule | `radio_programs.time` + `time_description` + `start` (schedule only, flagged as such) |
| episode id (DB) | `radio_program_sessions.id` |
| episode canonical key | `(ch, e)` from `link` (`e=` numeric EPG id); fallback `(program_id, link)` |
| audio URL | `radio_program_sessions.link` (made absolute: base `https://radio.iranseda.ir/`) |
| broadcast date/time (Jalali) | parsed from `filename` stem `jj-mm-dd-hh-mm-ss` |
| broadcast date/time (Gregorian) | **derived** (Jalali→Gregorian conversion), source recorded |
| pipeline status | `radio_program_sessions.status` + `last_error` + `attempts` |
| SRT/TXT existence | disk join at export time (not the DB column) |
| corrected versions | `llm_output` rows + `file_relpath` + `model` + `prompt_id` + token counts |
| crop window | `crop_detection` (start_sec/end_sec, confidence, status) |
| speakers | **none — no source table** (preflight finding #9) |
| provenance timestamps | session `created_at/updated_at` (crawl time), llm_output `finished_at`, asr_output `created_at` |

---

## 5. Ambiguities, gaps, data-quality findings (must be carried into the data model)

1. **No broadcast-date column** — must be parsed from filenames (Jalali).
   342 sessions have no `filename` → broadcast date unknowable (emit null).
2. **`created_at` is crawl time, not air time** — never usable as broadcast date.
3. **Legacy program duplication** — same `(ch,m)` can have two program rows
   (is_legacy=1 + 0); 32 distinct URLs for 59 rows. Corpus must merge on
   `(ch,m)` and retain both DB ids.
4. **`status='subtitled'` (9 298) ≠ SRT on disk (10 466)** — some "subtitled"
   legacy rows have empty `srt_filename` and no disk file; some disk files
   exist for rows in other states. Disk join is the truth for artifact
   existence; DB status is pipeline state.
5. **On-disk corrected artifacts (4 284/4 251) exceed `llm_output` rows
   (4 245/4 212) by 39** — orphan disk files exist (DB row deleted/deduped by
   `uq_out`, or file predates registration). DB is authoritative for
   attribution; orphans recorded in the manifest, never silently adopted.
6. **`asr_output` unused in production** — Whisper SRT provenance (model,
   sha256) is not recorded per file; corpus must state `asr: {provider:
   "whisper (on-disk, unregistered)", details_available: false}` rather than
   inventing values.
7. **Persian text quality:** program names contain embedded tabs/newlines
   (legacy rows); `time_description` is unstructured free text with occasional
   malformed entries (ids 49/50/52: `از ساعت  به مدت` with empty values;
   id 58: duplicated `به مدت`). NFC normalization + whitespace collapse are
   required (mission rule §4.9).
8. **`full_text` job has 933 rows / 923 sessions** — 10 sessions have two
   models (`full_text` marker vs `qwen38-nothinking`); all versions preserved
   per `uq_out`.
9. **`llm_job.job_id` mostly NULL in `llm_output`** — batch attribution is
   partial; keep as nullable.
10. **`program_score`/scoring depends on dead server 52** — no score data
    available; field stays null with `missing_reason`.
11. **No `updated_at` on `llm_output`** (only `finished_at`) — watermarking
    for incremental export must use `finished_at` + `id` (rule §8: "fingerprint
    if updated_at unreliable" — it is unreliable here).
12. **MariaDB quirks encountered (documented for the exporter):** no `LIMIT`
    in `IN`-subqueries (1235); `TIMESTAMP <> ''` errors (1525) — use
    `IFNULL(CAST(col AS CHAR),'')<>''`; parameterize table names carefully
    (`%s` conflicts with Python formatting).
13. **Errata:** the final `information_schema.tables` engine/size list query
    failed on column-label case (`table_name` vs `TABLE_NAME` on this
    MariaDB build). Not required by the stage checklist; engines not reported.

---

## 6. STAGE 2 VERDICT

**PASS** — complete, real schema of all 18 tables captured live (columns,
types, nullability, PKs, unique keys, indexes, row counts at two timestamps),
relations mapped (1 physical FK, rest logical), artifact storage locations
resolved (SRT/TXT on disk; corrected in `llm_output` + `downloads/cleaned/`),
authoritative source per corpus field defined, 13 documented ambiguities/gaps
carried into the Stage 3 data contract.
