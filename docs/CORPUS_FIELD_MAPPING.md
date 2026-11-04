# IranSeda Corpus — Field Mapping (v1.0)

**Stage:** 3 — Data contract
**Date:** 2026-11-03
Maps every corpus record field to its **live** source (table.column, disk
derivation, or computed rule), per Stage 2 schema discovery
([`CORPUS_DATABASE_SCHEMA.md`](../reports/corpus/CORPUS_DATABASE_SCHEMA.md)).

Legend: **DB** = column value; **DISK** = file on export host; **CMP** =
computed from DB/disk; **NULL** = no source (explicit null + missing reason).

---

## 1. Identity

| Corpus field | Source | Rule / notes |
|--------------|--------|--------------|
| `record_id` | CMP from `sessions.link` | `?ch=(\d+)&e=(\d+)` → `iranseda:ch{ch}:e{e}`; else `iranseda:db{program_id}:s{id}` |
| `episode_key.ch` | DB `sessions.link` (regex `ch=(\d+)`) | int |
| `episode_key.e` | DB `sessions.link` (regex `e=(\d+)`) | string; null → `episode_key.source="fallback_db"` |
| `episode_key.m` | DB `programs.url` (regex `m=(\d+)`) | string (leading zeros preserved) |
| `episode_key.source` | CMP | `"link"` if ch+e found, else `"fallback_db"` |
| `database_refs.session_id` | DB `sessions.id` | |
| `database_refs.program_id` | DB `sessions.program_id` | the row the session actually references |
| `database_refs.program_ids_all` | DB `programs.id` WHERE url = merged program url | legacy+current duplicates both listed |
| `database_refs.tables.llm_output` | DB `llm_output.id` WHERE session_id = id | all job_types/models |
| `database_refs.tables.crop_detection` | DB `crop_detection.id` WHERE session_id = id | null if absent |
| `database_refs.tables.asr_output` | DB `asr_output.id` WHERE session_id = id | empty in practice |

## 2. Program (rows merged on canonical URL / (ch,m))

| Corpus field | Source | Rule / notes |
|--------------|--------|--------------|
| `program.name` | DB `programs.name` | NFC + whitespace collapse (strip tabs/newlines/extra spaces) |
| `program.name_raw` | DB `programs.name` | untouched original (recoverability) |
| `program.url` | DB `programs.url` | canonical `ch`+`m` URL |
| `program.ch` / `program.m` | CMP regex on url | |
| `program.radio` | DB `programs.radio` | null when empty (legacy rows) |
| `program.description` | DB `programs.description` | NFC-normalized |
| `program.schedule.start_time` | DB `programs.time` | TIME → `HH:MM:SS` |
| `program.schedule.description_raw` | DB `programs.time_description` | untouched |
| `program.schedule.description_normalized` | CMP | NFC + collapse |
| `program.schedule.source` | CMP | `programs.time` if time set, else `programs.time_description` if set, else `none` |
| `program.crop.*` | DB `programs.crop_offset/crop_enabled/crop_auto` | 1 row filled in prod |

Merge rule: when legacy (is_legacy=1) and current rows share `(ch,m)`,
prefer the non-legacy row for `name/radio/time*`; union `program_ids_all`;
warning `legacy_program_duplicate_merged`.

## 3. Broadcast

| Corpus field | Source | Rule / notes |
|--------------|--------|--------------|
| `broadcast` | CMP from `sessions.filename` | null + `quality.missing+=broadcast.date` when filename empty (342 rows) |
| `broadcast.jalali.date` | CMP | stem `radio-<chan>-JJ-MM-DD-HH-MM` → `14JJ-MM-DD` (erratum 2026-11-04: live stems have exactly 5 numeric tokens, no seconds) |
| `broadcast.jalali.time` | CMP | `HH:MM:00` from stem (seconds implicitly 00) |
| `broadcast.jalali.source` | const | `"filename"` |
| `broadcast.gregorian.date` | CMP | Jalali→Gregorian (library pinned in `conversion`) |
| `broadcast.gregorian.source` | const | `"derived_from_jalali_filename"` |
| `broadcast.filename_stem` | DB `sessions.filename` | exact stem used (audit) |

Parsing safety: if stem does not match the 6-numeric-tuple pattern,
`broadcast=null` + warning `filename_pattern_mismatch` (never guess).

## 4. Audio

| Corpus field | Source | Rule / notes |
|--------------|--------|--------------|
| `audio.url` | CMP | `sessions.link` resolved against `https://radio.iranseda.ir/` (relative `../` → site base) |
| `audio.link_raw` | DB `sessions.link` | original value |
| `audio.filename` | DB `sessions.filename` | null when empty |
| `audio.local_exists` | DISK | `os.path.exists(downloads/<filename>)` at build time |

## 5. Speakers

| Corpus field | Source | Rule / notes |
|--------------|--------|--------------|
| `speakers.items` | **NULL** (no source) | always `[]` today; future crawl-only population with `name/role/source_page/extraction_method/confidence` |
| `speakers.missing_reason` | const | `no verified source table in database (stage-1 finding #9)` |

## 6. Transcripts

### 6.1 Originals

| Corpus field | Source | Rule / notes |
|--------------|--------|--------------|
| `originals.srt.exists` | DISK/DB | `srt_filename` filled → check `downloads/cleaned/` then `downloads/`; else stem-of-`filename` in both dirs |
| `originals.srt.db_filename` | DB `sessions.srt_filename` | |
| `originals.srt.relpath` | CMP | server-relative (`downloads/…`) |
| `originals.srt.content` | DISK | full SRT, NFC-normalized, inlined when build config `inline_originals=true`; else null |
| `originals.srt.sha256` | CMP | hash of inlined content (or of file bytes when not inlined) |
| `originals.srt.segment_count` | CMP | count SRT cue blocks |
| `originals.srt.duration_sec` | CMP | last cue end timestamp → seconds |
| `originals.txt.exists` | DISK | `<srt_stem>.txt` in same dir as the SRT |
| `originals.txt.content` | DISK | inlined per build config; null when absent |
| `originals.txt.missing_reason` | CMP | `derived_txt_not_on_disk` / `no_srt` |

### 6.2 LLM outputs (`llm_outputs[]`, one per `llm_output` row)

| Corpus field | Source | Rule / notes |
|--------------|--------|--------------|
| `llm_output_id` | DB `llm_output.id` | |
| `job_type` | DB `llm_output.job_type` | enum {correct_subtitles, correct_text, summary, full_text, qa}; novel values pass through + warning |
| `model` | DB `llm_output.model` | `qwen38-nothinking` / legacy `full_text` marker |
| `prompt_id` | DB `llm_output.prompt_id` | references `prompts` (prompts text NOT inlined) |
| `status` | DB `llm_output.status` | all `done` in prod |
| `content` | DB `llm_output.content` | NFC-normalized when inlined (build config `inline_llm=true`) |
| `content_en` | DB `llm_output.content_en` | summary English part |
| `srt_content` | DB `llm_output.srt_content` | corrected SRT (NFC) |
| `file_relpath` | DB `llm_output.file_relpath` | server-relative |
| `disk_exists` | DISK | `os.path.exists(<root>/<file_relpath>)` |
| `input_tokens`/`output_tokens` | DB | null when NULL |
| `started_at`/`finished_at` | DB | ISO 8601 UTC |

### 6.3 ASR outputs (`asr_outputs[]`)

| Corpus field | Source | Rule / notes |
|--------------|--------|--------------|
| all fields | DB `asr_output` row | 1 row in prod (failed Roshan pilot) |
| `whisper_provenance` | CMP (constant) | `{provider: "whisper (local pipeline, output not registered in asr_output)", details_available: false}` |

## 7. Crop

| Corpus field | Source | Rule / notes |
|--------------|--------|--------------|
| `crop.start_sec` / `crop.end_sec` | DB `crop_detection` | null when absent |
| `crop.confidence` / `crop.status` | DB | enum values |
| `crop.evidence` | DB `crop_detection.evidence` | parsed JSON (invalid JSON → null + warning) |

## 8. Source metadata / pipeline state / provenance / quality

| Corpus field | Source | Rule / notes |
|--------------|--------|--------------|
| `source_metadata.episode_url` | CMP | = `audio.url` |
| `source_metadata.program_url` | DB `programs.url` | |
| `source_metadata.site_base` | const | `https://radio.iranseda.ir/` |
| `pipeline_state.status` | DB `sessions.status` | |
| `pipeline_state.is_downloaded` | DB `sessions.is_downloaded` | |
| `pipeline_state.attempts` | DB `sessions.attempts` | |
| `pipeline_state.last_error` | DB `sessions.last_error` | NFC-normalized |
| `provenance.exported_at` | CMP | build timestamp UTC |
| `provenance.export_version` | CMP | git SHA of exporter code + run id |
| `provenance.sources` | CMP | list of contributing table rows + disk files |
| `provenance.session_created_at` | DB `sessions.created_at` | crawl time (audit only) |
| `provenance.session_updated_at` | DB `sessions.updated_at` | watermark basis for incremental export |
| `quality.missing` | CMP | derived per §8 of data model |
| `quality.warnings` | CMP | anomalies observed during mapping |
| `quality.text_normalized` | const | `"NFC"` |

## 9. Explicitly OUT of scope (kept in DB only)

| Table | Why excluded from records |
|-------|---------------------------|
| `pipeline_runs` | operational telemetry, not content (available in DB + Grafana) |
| `publication_task` | reporter state machine — mission rule 8: do not expose/modify |
| `llm_job` | batch bookkeeping; referenced indirectly via `llm_output.job_id` (mostly NULL) |
| `program_score` | 52-dependent scoring, 1 failed row; no reliable data |
| `prompts` (text) | operational detail — referenced by `prompt_id` only |
| `backfill_list`, `downloaded_files`, `programs`, `subtitles` | empty/legacy |
