# IranSeda Corpus — Stage 6: Validation Report

**Mission:** IRANSEDA CORPUS BUILDER & HUGGING FACE PUBLISHER
**Stage:** 6 — Structural validation of the full corpus export (18 gates + quarantine + errata)
**Date:** 2026-11-04, full export run `corpus-20261104-085940`, 08:59–09:01 UTC
**Target:** server 53 (`saber@172.20.1.53`, hostname `llm`), production checkout
`/home/saber/saberprojects/iranseda-crawler-golang-`, branch `phase3-radio-rag-service`
**Code:** commit `bc5e8fb0032448978c33a8fdf1873fa49abdf037` (corpus: mask server-private
paths in last_error + fix incremental.log attribute)

> **Rule compliance (mission §0):** every number below is LIVE, re-measured on 53 by
> the Stage 5 job (`.corpus_full53.sh`) and read-only probes. The corpus is built
> read-only against the production DB (`db=radio`, `127.0.0.1:3308`, `n8nuser`); no
> production state was modified. No secrets appear in this report (`db_pass` is
> redacted in the manifest and omitted here). All numbers were re-verified after the
> two full-export bug fixes (see §6 Errata).

---

## 1. Run metadata (live)

| Field | Value |
|-------|-------|
| run_id | `corpus-20261104-085940` |
| exported_at | 2026-11-04 08:59:40 |
| mode | full |
| records_written | **9 721** |
| records_invalid (quarantined) | **1 147** |
| sessions_seen / total_in_db | **10 868 / 10 868** (100 %) |
| duration (per run) | ~84 s (run1 84.2 s, run2 83.7 s) |
| corpus dir | `data/corpus` (corpus.jsonl + manifest.json + stats.json + metrics.prom + invalid.jsonl) |
| DB counts at run | radio_programs 59, radio_program_sessions 10 868, llm_output 13 603, asr_output 1, crop_detection 22 |
| Disk scan | 42 452 files indexed, 24 652 stems, 0 scan errors |
| Watermark | sessions_updated_at 2026-11-04T05:30:18, sessions_max_id 10870 |

**Headline:** all 10 868 sessions were emitted as records. 9 721 passed validation
into `corpus.jsonl`; 1 147 were quarantined to `invalid.jsonl` **entirely as
Class B (duplicate record_id)** — see §4. No record was dropped for missing
subtitles/corrections (mission rule §4.1).

---

## 2. The 18 validation gates

Each gate is enforced by the pure-stdlib validator (`corpus/validator.py`,
`validate_record`/`validate_batch`) plus mapper invariants (`corpus/mapper.py`).
Status reflects the live run above. **18/18 PASS.**

| # | Gate | What is enforced | Evidence (live run) |
|---|------|------------------|---------------------|
| 1 | Required top-level keys | `schema_version, record_id, episode_key, database_refs, program, audio, transcripts, provenance, quality` all present | 9 721/9 721 records pass; 0 `missing_required_key` in invalid.jsonl |
| 2 | record_id pattern | `^iranseda:(ch[0-9]+:e[0-9]+\|db[0-9]+:s[0-9]+)$` | 0 pattern violations |
| 3 | record_id uniqueness (batch) | no two records share a record_id | all 9 721 unique; the 1 147 dups are quarantined **before** this gate (see §4 Class B) |
| 4 | episode_key from link | `ch`+`e` parsed from the public EPG link, source `link`; DB fallback only when no link | `episode_key_link` 9 721, `episode_key_fallback` 0 |
| 5 | broadcast from filename | broadcast date/time parsed from the canonical filename stem, **not** `created_at` | `records_with_broadcast` 9 427, `records_without_broadcast` 294 (missing flagged) |
| 6 | gregorian ↔ jalali cross-check | the two calendar forms must agree (vendored `jalali.py`) | 0 `broadcast_gregorian_must_match_jalali` failures |
| 7 | broadcast null allowed | null broadcast is legal **only** with a `missing` flag | 294 null-broadcast records, each carrying `missing: broadcast.date` |
| 8 | original never replaced | if a corrected SRT exists, the original SRT is still its own artifact entry | `records_with_original_srt` 9 387 coexist with `records_with_corrected_srt` 4 245 |
| 9 | SRT must parse | original + corrected SRT content parses to valid cues (`corpus/srt.py`) | 0 `srt_must_parse` failures across 9 387 originals / 4 245 corrected |
| 10 | no server-private paths | no string may contain `/home/`, `/root/`, `/var/www/`, `C:\`, `C:/Users` | 0 such prefixes in corpus.jsonl (was 53 — fixed, see §4 Class A) |
| 11 | no secrets | no `api_key/token/password/secret` assignments or `sk-`/`hf_`/`ghp_` tokens | 0 secret leaks |
| 12 | text_normalized == NFC | all Persian text NFC-normalized, ZWNJ (U+200C) preserved | `quality.text_normalized = "NFC"` on all records |
| 13 | schedule is program-level | `program.schedule` is the program's recurring slot, **not** the episode broadcast time | 0 schedule/episode collisions |
| 14 | speakers empty-with-reason | no speaker source exists (preflight #9); speakers must be empty + `missing_reason` | 0 invalid speaker records |
| 15 | audio URL absolute + local flag | canonical absolute audio URL; `local_exists` reflects real disk | `audio_local_exists` 2 990 (rest flagged false) |
| 16 | missing artifacts tracked | every absent artifact has an explicit `missing` flag, never a silent drop | `missing_kinds`: broadcast.date 294, originals.srt 334, originals.txt 334, qa.disk 1 |
| 17 | unknown job_type warns not fails | a future/unknown `llm_output.job_type` warns, does not invalidate | 0 `unknown_job_type` failures (warning path exercised in tests) |
| 18 | idempotency + reconciliation | re-export yields identical fingerprints; reconcile reports the diff | run1=9721 run2=9721 differing=0; reconcile +0 −0 ~0 =9721 (see §5) |

---

## 3. Status / coverage distribution (live stats.json)

| Dimension | Breakdown |
|-----------|-----------|
| by_status | subtitled 9 095, pending_download 573, failed_permanent 53 |
| by_job_type | summary 4 212, correct_text 4 212, correct_subtitles 4 245, full_text 933, qa 1 |
| records_complete | 9 386 (original SRT+TXT + at least one LLM output) |
| records_with_corrected_srt | 4 245 |
| records_with_corrected_txt | 4 212 |
| records_with_summary | 4 212 |
| records_with_full_text | 923 |
| records_with_qa | 1 |
| warning_kinds | legacy_program_duplicate_merged 9 438 (legacy (ch,m) merge is expected, §6) |
| missing_kinds | broadcast.date 294, originals.srt 334, originals.txt 334, qa.disk 1 |

---

## 4. Quarantine findings (invalid.jsonl) — **both classes documented**

The first clean full export (pre-fix) quarantined **1 200** records. Probe 19
categorized them into two independent classes. Per the operator directive of
2026-11-04, **Class A was fixed** (sanitize) and **Class B was kept quarantined**
(documented here). After the fix, `invalid.jsonl` holds exactly **1 147** records,
all Class B.

### 4.1 Class A — server-private path leak in `last_error` (53 records) — **FIXED**

* **Signal (validator):** `$.pipeline_state.last_error: server-private path leaked`.
* **Cause:** 53 sessions in `failed_permanent` status carry an ffmpeg error in
  `last_error` that embeds an absolute server path, e.g.
  `[Errno 1094995529] Invalid data found when processing input: '/home/saber/.../downloads/....mp3'`.
  The validator's `PRIVATE_PATH_RE` (gate 10) correctly rejects any record string
  containing `/home/`, so these 53 records were quarantined.
* **Fix (commit `bc5e8fb00`):** added `normalizer.sanitize_private_paths()` and wired
  it into the mapper for `last_error` only. The path token is masked to
  `<server-path>` while the surrounding error message is preserved. The raw DB
  value is untouched (read-only); only the corpus representation is sanitized.
* **Result (live re-run):** all 53 records now pass and are in `corpus.jsonl`.
  `grep -c 'server-path' corpus.jsonl` = **53**; `grep -cE '/home/|/root/|/var/www/|C:/'
  corpus.jsonl` = **0**. Sample (masked):
  `[Errno 1094995529] Invalid data found when processing input: '<server-path>'`.
  `grep -c 'server-private path' invalid.jsonl` = **0**.
* **Regression tests:** `test_normalizer::test_sanitize_private_paths_*` (3 cases) and
  `test_mapper::test_last_error_server_path_masked` (asserts the exact probe-19 message
  is masked and the record passes `validate_record`).

### 4.2 Class B — duplicate `record_id` (1 147 records) — **KEPT QUARANTINED (documented)**

* **Signal (validator):** batch-level `duplicate record_id`.
* **Cause:** distinct `radio_program_sessions` rows (all `program_id` 31, sessions
  from ~6217 onward) share the **same** public EPG link `(ch, e)` — e.g. record
  `iranseda:ch14:e153278467` is claimed by session 6217 and another session. The
  mapper derives `record_id` from `(ch, e)`, so two different physical sessions map
  to the same `record_id`. The validator correctly refuses to let two records share
  an id, so all but one of each colliding group are quarantined.
* **Why kept (operator decision, 2026-11-04):** this is a genuine **source-data
  ambiguity** in the production DB (the same episode link was ingested into multiple
  session rows), not an exporter defect. Resolving it requires a business decision
  about which session row is canonical for a given `(ch, e)` — out of scope for the
  corpus builder, and fabricating a de-dup rule would risk silently discarding real
  transcripts. Hence quarantined and reported, not force-merged.
* **Scope (live):** 1 147 records, 100 % of `invalid.jsonl` (`grep -c
  'duplicate record_id' invalid.jsonl` = 1 147). Every quarantined record is fully
  written to `invalid.jsonl` with its problems list, so **no data is lost** — it is
  retained for a future canonical-key decision.
* **Disposition:** documented here and left in `invalid.jsonl`. A follow-up
  (post-Stage 12, or on operator instruction) will define the canonical
  session-per-`(ch,e)` rule, re-emit the affected group, and reconcile.

---

## 5. Idempotency + reconciliation (live)

* **Idempotency:** two independent full exports produced identical per-record
  fingerprints — `IDEMPOTENT: True run1=9721 run2=9721 differing=0`.
* **Reconcile** (`incremental.py reconcile`, re-scan + fingerprint diff):
  `reconcile: +0 -0 ~0 =9721 in 101.3s`; `reconcile_report.json`:
  previous_records 9721, current_records 9721, added 0, removed 0, changed 0,
  unchanged 9721. Deletions are *recorded*, never physically removed (mission §0).
* **Note:** the reconcile step previously crashed at `incremental.py:113`
  (`AttributeError: 'Extractor' object has no attribute 'log'` — `self.ex.ex.log`
  should be `self.ex.log`). Fixed in `bc5e8fb00` (3 sites: L64, L70, L113); the
  re-run above completed reconcile cleanly.

---

## 6. Errata (corrections to earlier corpus assumptions)

| # | Earlier assumption | Live reality (verified on 53) |
|---|--------------------|-------------------------------|
| E1 | filename stem is 5 tokens | canonical stems can carry a 6th token; the jalali parser handles the live stems (test `test_parse_broadcast_real_stems`) |
| E2 | DB name `iranseda` | production DB is **`radio`** (`db_name=radio`, `127.0.0.1:3308`) |
| E3 | `crop_offset` is varchar (per stale SQL dump) | `radio_programs.crop_offset` is a **TIME** column; pymysql decodes it as `datetime.timedelta`. Fixed by `mapper._time_to_seconds()` → int seconds (commit `fb26bdcd4`; was crashing `json.dumps` at record 418) |
| E4 | `time`, `start` are simple text | `radio_programs.time` / `start` are TIME columns (timedelta); `time_description` is TEXT (str/None) — handled by `_time_of_day` |
| E5 | `cleaned/` holds only corrected SRT | some `downloads/cleaned/*.srt` are **free-text** artifacts (no timing); mapper prefers the parsable SRT and flags the text one (test `test_original_srt_prefers_parsable_candidate`) |
| E6 | session count 10 858 (Nov 3) | live is now **10 868** (pipeline keeps ingesting); all counts in this report are from the 2026-11-04 run |
| E7 | 100 % of records valid | 9 721 valid / 1 147 quarantined (Class B); the 53 Class A records are now valid after sanitization |

---

## 7. Test suite

`python tests/corpus/run_all.py` → **68/68 passing** (0.8 s), including the two new
regression tests from the Class A fix and the prior `crop_offset` timedelta fix.

---

## 8. Verdict

**Stage 6 PASS.** The full corpus export is structurally valid against the v1
contract (18/18 gates), idempotent (differing=0 across two runs), and reconciles
cleanly (+0 −0 ~0). The only quarantined records are the 1 147 Class B duplicates
caused by source-DB ambiguity (documented in §4.2, no data lost). The 53 Class A
records that previously leaked server paths are now sanitized and included.

**Next:** Stage 7 (Hugging Face publication — expected BLOCKED pending rights
clearance; will emit a local dataset snapshot + recorded blocker per mission §7).
