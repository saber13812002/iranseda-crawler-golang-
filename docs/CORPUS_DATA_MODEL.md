# IranSeda Corpus — Data Model (v1.0)

**Stage:** 3 — Data contract
**Date:** 2026-11-03
**Companion files:** [`iranseda-corpus-v1.schema.json`](../schemas/iranseda-corpus-v1.schema.json) (machine contract), [`CORPUS_FIELD_MAPPING.md`](CORPUS_FIELD_MAPPING.md) (per-field sourcing)

---

## 1. What a record is

One corpus record = **one episode** (one row of `radio_program_sessions`),
including its program, broadcast time, audio pointer, and **every** transcript
artifact the pipeline produced for it. Records are JSON Lines: one JSON
object per line in `data/corpus/corpus.jsonl` (sharded when large).

**Cardinality rule:** exactly one record per session row. A session that
failed at every step still gets a record (with `quality.missing` populated) —
the corpus is a *catalog of the whole database*, not just the successful
parts. Program rows are **merged** into their sessions (never their own
records) because the corpus unit of analysis is the episode.

## 2. Identity (stable across extraction order)

```
record_id  =  iranseda:ch{ch}:e{e}            preferred  (from session.link  ?e=<numeric EPG id>)
           =  iranseda:db{program_id}:s{session_id}   fallback (no e= id)
```

- `ch`/`e` come from the **canonical audio link**
  (`../epgarchivePart/?VALID=TRUE&ch=14&e=152507883`).
- `e` is kept as a **string** (preserve digit sequence, avoid int overflow).
- `m` (program id, 6 digits) travels in `episode_key.m` / `program.m`.
- The DB dedupe key `uq_session_program_link(program_id, link)` guarantees a
  record never gets a second identity.
- Re-exporting the same DB state MUST produce the same `record_id` set and the
  same per-record content hash (determinism, mission rule §6.12).

## 3. The three time axes (never conflated)

| Axis | Meaning | Source | Where in record |
|------|---------|--------|-----------------|
| **Broadcast (Jalali)** | when the episode aired | parsed from `filename` stem `jj-mm-dd-hh-mm-ss` (year ← 2 digits → `14jj`) | `broadcast.jalali` |
| **Broadcast (Gregorian)** | same, converted | Jalali→Gregorian conversion (library pinned in `gregorian.conversion`) | `broadcast.gregorian` |
| **Schedule** | when the *program* airs (weekly slot) | `radio_programs.time` + `time_description` (Persian free text) | `program.schedule` |
| **Crawl/ingest** | when the DB row was created/updated | `sessions.created_at/updated_at` | `provenance.*` |

**Hard rule:** `created_at` is crawl time. It is NEVER emitted as a broadcast
date. If no filename exists (342 sessions), `broadcast` is `null` and
`quality.missing` contains `broadcast.date`.

## 4. Versioning of content (original vs corrected)

```
transcripts
├── originals                 # ASR output — the ground-truth original
│   ├── srt                   # exists / relpath / content? / sha256
│   └── txt                   # (TXT has NO DB column — disk-derived from SRT stem)
├── llm_outputs[]             # one entry per (job_type, model) row
│   ├── correct_subtitles     # srt_content — corrected SRT
│   ├── correct_text          # content   — corrected TXT
│   ├── summary               # content + content_en — bilingual
│   ├── full_text             # content   — timestamps stripped
│   └── qa                    # content
├── asr_outputs[]             # asr_output registry rows (1 failed pilot row in prod)
└── whisper_provenance        # honest "unregistered" marker — no invented model/sha
```

- The **original is never replaced**: corrections are sibling entries with
  their own `file_relpath` (`.correct.srt`, `.correct.txt`, …), DB id, model,
  prompt, tokens, and finish time.
- A session with **two** `full_text` rows (10 such sessions, two different
  models) keeps both — `uq_out(session_id, job_type, model)` allows it.
- Disk artifacts that have **no** `llm_output` row (39 orphan corrected
  files) are NOT merged in; they are counted in the manifest's
  `orphan_disk_artifacts` section. DB stays authoritative for attribution.

## 5. Speakers — policy

`speakers.items` is populated **only** from a verified, crawlable source
(page URL + extraction method + confidence recorded per item). As of this
build there is **no speaker table or crawl** (Stage 1 finding #9), so every
record carries:

```json
"speakers": {
  "items": [],
  "missing_reason": "no verified source table in database (stage-1 finding #9)"
}
```

Guessing names from ASR text is forbidden.

## 6. Normalization (Persian text)

- All Persian text fields are **NFC-normalized** (Unicode NFC) and
  whitespace-collapsed (legacy program names contain embedded tabs/newlines).
- The **original** DB value is preserved in `name_raw` /
  `*_raw` fields where normalization is applied, so the original is
  recoverable (mission rule §4.9).
- `quality.text_normalized` is always `"NFC"`.
- BOM/zero-width characters: zero-width non-joiner (`\u200c`, used in
  Persian e.g. `تصحیح پرتاب‌ای`) is **preserved** — it is part of the text.

## 7. Paths and URLs (no server-private paths)

- `audio.url` and `source_metadata.episode_url` are **absolute**
  (`https://radio.iranseda.ir/…` — relative `../epgarchivePart/?…` links are
  resolved against the site base).
- Artifact locations are **server-relative** (`downloads/cleaned/<stem>.*`)
  or absent. Absolute host paths (`/home/saber/…`) must never appear in
  corpus output.
- `disk_exists` / `local_exists` are build-time booleans on the export host —
  informational, not part of identity.

## 8. Missing data policy

Every gap is explicit, two-level:

1. `quality.missing[]` — machine-readable list of missing artifacts
   (`transcripts.originals.srt.content`, `broadcast.date`, …).
2. `quality.warnings[]` — non-fatal anomalies
   (`legacy_program_duplicate_merged`, `orphan_corrected_disk_file`,
   `time_description_malformed`, `llm_model_marker_full_text` …).

A record is *valid* (schema-wise) with missing data; it is *complete* only
when `missing` is empty. Stats report both populations.

## 9. Sensitive data

- No DB credentials, no LLM API keys, no Telegram tokens anywhere in records.
- `llm_output.prompt_text` / `prompts.prompt` are **not** inlined (prompt
  registry reference only: `prompt_id`) — prompts may contain operational
  detail; they stay in the DB and are referenced by id.
- `pipeline_runs`, `publication_task`, `program_score` are **out of scope**
  for corpus records (operational telemetry, not content). They remain
  available in the DB.

## 10. Extensibility

- `schema_version` is a const per file batch; new versions get new files
  (`corpus-v2.jsonl`) — v1 files are never mutated.
- New job types (e.g. future `correct_text_v2` outputs) extend
  `llm_outputs[].job_type` as `"unknown"`-safe strings; the schema enum
  includes the current five plus a documented escape valve (records with a
  new job type get the literal type and a warning, not a validation failure —
  see validator policy in `CORPUS_QUALITY_POLICY.md`).
- New tables/fields: add to `database_refs.tables` and `provenance.sources`.
