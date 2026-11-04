# Stage 2 — Corpus Schema & Metadata Design (IRANSEDA-CORPUS-2026-01)

## 1. Date & timezone
- 2026-11-04, ~15:10–16:25 local (Asia/Tehran, UTC+3:30); UTC 2026-11-04T12:10–15:25.

## 2. Environment
- Local dev: Windows 10, workspace `iranseda` (branch `download-db`) + worktree `iranseda-corpus-wt` (branch `phase3-radio-rag-service`), Python 3.12 (stdlib-only test suite).
- Production relay: server 53 (`saber@172.20.1.53`), checkout `/home/saber/saberprojects/iranseda-crawler-golang-` (note the real trailing slash), tests run with `dashboard/venv/bin/python3` (py3.12.3, stdlib + pymysql; no jsonschema, no pytest).
- MySQL 8.0.46 @127.0.0.1:3308 db `radio` user `n8nuser` — **not touched** (Stage 2 is schema/design; no queries needed beyond the Stage 1 live investigation).

## 3. Repository & branch
- Code: worktree `iranseda-corpus-wt`, branch `phase3-radio-rag-service`.
- Report: main workspace `iranseda`, branch `download-db`.
- Dual-branch layout unchanged (code in worktree, reports in main workspace).

## 4. Starting SHAs
- Worktree `phase3-radio-rag-service`: `2c569ab4d` (Stage 1 code) at start of work.
- 53 `phase3-radio-rag-service` advanced by its 30-min auto-refresh cron during the window: `4ee318650` (22:00) → `0b0903301` (22:30) → `e7c9a67ac` (23:00). Rebased onto `e7c9a67ac` before pushing.
- Main workspace `download-db`: `a6a963f75` (Stage 1 report fixup).

## 5. What changed
Stage 2 deliverable: a **versioned, self-contained corpus schema package** under `corpus/schema/` in the worktree, plus a loader/verifier and tests.

- `corpus/schema/corpus.schema.json` — Draft 2020-12 record schema **v1.0** (311 lines):
  - `$schema` = 2020-12 dialect, `$id`, `title`, and a `description` embedding the Stage 1 identity policy (session identity = `database_refs.session_id`; `(ch,e)` = source reference only; colliding records quarantined permanently until identity is proven; 5-token stem erratum; `created_at` never used as broadcast date).
  - `x-corpus` metadata block: `schema_version` 1.0, base data contract (`schemas/iranseda-corpus-v1.schema.json`, unchanged), `identity_policy: PERMANENT_UNTIL_IDENTITY_PROVEN` + ref to the Stage 1 report, record granularity (one record per actual session), refs to field mapping and examples.
  - `required` = validator's `REQUIRED_TOP` **+ `speakers`** (the stdlib validator reads `rec["speakers"]` directly, so it is de-facto required — now made explicit).
  - Full property set carried from the v1 data contract with Stage 1 annotations: `record_id` (INDEX key, not identity; fallback `db{pid}:s{sid}`), `broadcast` (Jalali `source: "filename"` const + Gregorian `source: "derived_from_jalali_filename"` const + `filename_stem` audit field), `database_refs.session_id` (authoritative identity), `pipeline_state.last_error` (sanitized), `$defs.artifact` (exists/db_filename/relpath/content/sha256/char_count/segment_count/duration_sec/missing_reason).
- `corpus/schema/field_mapping.json` — machine-readable mapping (145 lines) converted from `docs/CORPUS_FIELD_MAPPING.md`. Every field carries `{field, status, source_type, source, rule}`:
  - status ∈ `available | derivable | missing | unverified | not_applicable | const` (legend included);
  - honest gaps declared, nothing invented: `speakers.items` = **missing** (no source table), `whisper_provenance` = **unverified** (stated as unavailable), 8 out-of-scope tables = **not_applicable** (incl. the `programs` note: its columns ARE used — the "programs" legacy-table row in the docs' §9 is about treating it as an *additional* source);
  - `broadcast` is `derivable` from `sessions.filename` and its rule explicitly forbids `created_at`.
- `corpus/schema/examples/` — two reference records:
  - `valid_record.json` — full session record (session 1234, program 11, `radio-maaref-05-01-01-09-00` stem → Jalali 1405-01-01 09:00:00 → Gregorian 2026-03-21 (validator-recomputed cross-check), 2-cue Persian original SRT inlined with `segment_count`/`duration_sec`, one `correct_subtitles` LLM output with parseable corrected SRT, `speakers {items: [], missing_reason}`, `quality.text_normalized: "NFC"`). Passes `corpus.validator.validate_record`.
  - `quarantine_record.json` — the `{record, problems}` line shape of `data/corpus/invalid.jsonl` / `quarantine.jsonl`, modelled on the live ch14:e153278467 case (session 6217/pid 31 vs 5038/pid 3): record is structurally valid, quarantined at batch level for `duplicate record_id`, with the `PERMANENT_UNTIL_IDENTITY_PROVEN` policy stated in `quality.warnings`.
- `corpus/schema.py` (207 lines, pure stdlib) — loader + `verify()` gate: schema is well-formed 2020-12 JSON with `x-corpus` metadata consistent with `properties.schema_version.const`; field mapping covers all 13 top-level properties, uses only declared statuses, and names a source for every db/disk-sourced field; examples pass the structural record validator. Used by tests and by later stages to catch silent schema drift.
- `tests/corpus/test_schema.py` — 7 new tests (verify clean; schema metadata/contract; field-mapping coverage + honest-gap declarations + broadcast-never-from-created_at; examples present; valid example passes validator with the time/calendar contract asserted; quarantine example shape + policy warning + session_id identity; verify() rejects a broken and a contract-violating example file).

## 6. Files
Worktree (committed):
- `corpus/schema/corpus.schema.json` (new, 311)
- `corpus/schema/field_mapping.json` (new, 145)
- `corpus/schema/examples/valid_record.json` (new, 133)
- `corpus/schema/examples/quarantine_record.json` (new, 120)
- `corpus/schema.py` (new, 207)
- `tests/corpus/test_schema.py` (new, 135)
Total: 6 files, 1051 insertions, 0 deletions.

Main workspace (this report):
- `reports/corpus/STAGE_2_SCHEMA_REPORT.md` (new)

## 7. Database changes
**None.** Stage 2 is schema/metadata design. The live DB on 53 was not queried, written, or altered in this stage (the Stage 1 read-only investigation data is the only DB-derived input).

## 8. Tests
- Suite: `python tests/corpus/run_all.py` (stdlib-only runner, auto-discovers `test_*.py`).
- Local (worktree): **83/83 passed in 0.8s** (76 pre-existing + 7 new).
- On 53 after FF-merge: **83/83 passed in 0.1s** via `dashboard/venv/bin/python3`.
- Note: the relay's first attempt used system `python3` (no pymysql) and failed at import — corrected to the venv interpreter; not a code failure.

## 9. Exact results
- `verify()` → `[]` (schema + mapping + examples all consistent).
- New tests: `PASS test_schema::test_verify_passes_clean`, `test_schema_metadata_and_contract`, `test_field_mapping_covers_all_fields`, `test_examples_present_and_named`, `test_valid_example_passes_validator`, `test_quarantine_example_shape`, `test_verify_rejects_bad_example`.
- Time/calendar contract proven by example: stem `radio-maaref-05-01-01-09-00` → Jalali `1405-01-01` 09:00:00 (5-token stem, seconds 00, year 14JJ) → Gregorian `2026-03-21` (recomputed by the validator via `corpus.jalali`, vendored jdatetime 6.1.1 algorithm).
- Field mapping stats: 93 field entries (1 schema const + 84 record fields + 8 out-of-scope table markers); statuses — available 40, derivable 31, const 7, missing 1, unverified 1, not_applicable 8.

## 10. Production evidence (before/after on 53)
- Before: `phase3-radio-rag-service` @ `e7c9a67ac` (23:00 auto-refresh), corpus tests 76/76 on the pre-merge tree (verified during Stage 1), `data/corpus/` exports untouched (invalid.jsonl mtime 09:01 unchanged since Stage 1).
- After: `phase3-radio-rag-service` @ `ffdd61be5` (FF-merge only, no conflicts — the 3 auto-refresh commits touch only `docs/` + `downloads/`, zero overlap with `corpus/` or `tests/corpus/`), tests 83/83, SRT/whisper pipeline unaffected (no production services touched at all in this stage).

## 11. Commit SHA
- Code (worktree, `phase3-radio-rag-service`): **`ffdd61be53236cd012a82eab5b15c8ffef01ac09`** — `feat(corpus): define versioned metadata and transcript schema` (rebased from `7b7300ad5` onto `e7c9a67ac` after the 23:00 auto-refresh).
- Report (main workspace, `download-db`): this file, committed as `docs(corpus): stage 2 schema report` on `download-db`; the exact SHA is the head recorded in the §12 `ls-remote` verification (the report commit cannot embed its own SHA).

## 12. Push verification
- Temp branch `stage2-schema` pushed local→53 (LAN, GitHub DNS unavailable locally), then relay on 53:
  - `git merge --ff-only ffdd61be5` on `phase3-radio-rag-service` → FF, clean.
  - `git push origin phase3-radio-rag-service` → rc 0.
  - `git ls-remote origin phase3-radio-rag-service` → `ffdd61be53236cd012a82eab5b15c8ffef01ac09 refs/heads/phase3-radio-rag-service` = local head → **VERIFIED_MATCH**.
- Report branch `download-db`: pushed via the same relay pattern (temp branch → 53 → FF-merge on `download-db` → `git push origin download-db` → `git ls-remote origin download-db`); the recorded head is the report commit SHA referenced in §11.
- **GitLab `git.ai.ismc.ir`: BLOCKED (unchanged from Stage 1).** Re-confirmed capability (root PAT in `~/.git-credentials`, port 443 open) but **no GitLab project mirrors this repo** (the `rag/radio-rag-service` project is a different FastAPI repo; our SHAs 404 there). Remediation requires a project-name decision (e.g. create `rag/iranseda-crawler` + add `gitlab` remote on 53 + push both branches + `ls-remote` verify). Per mission rule: GitHub verified + GitLab blocked → stage code verdict would be PARTIAL if GitLab counted alone; here the schema deliverable is fully verified on GitHub + 53, and the GitLab gap is carried identically from Stage 1 with the same remediation.

## 13. Deploy status
- No deployment action needed: the schema package is inert (no runtime wiring; later stages consume it via `corpus.schema`).
- 53's working tree now contains the schema files at `ffdd61be5`; the 30-min auto-refresh cron continues to run on top of it (only `docs/`/`downloads/`), verified non-conflicting by the clean FF-merge.

## 14. Output locations
- `corpus/schema/corpus.schema.json`, `corpus/schema/field_mapping.json`, `corpus/schema/examples/{valid_record,quarantine_record}.json`, `corpus/schema.py`, `tests/corpus/test_schema.py` — in the worktree and on 53 at `ffdd61be5` (GitHub `saber13812002/iranseda-crawler-golang-`, branch `phase3-radio-rag-service`).
- This report: `reports/corpus/STAGE_2_SCHEMA_REPORT.md` on `download-db` (GitHub) and 53.

## 15. Remaining issues / blockers
- **GitLab mirror BLOCKED** (carried from Stage 1, same evidence & remediation): no destination project exists for this repo on `git.ai.ismc.ir`; a name must be chosen before a mirror push can happen. Applies to every stage until decided.
- Schema v1.0 is frozen as the data contract for Stages 3–6. Any future change to `corpus.schema.json` must bump `x-corpus.schema_version` and `field_mapping.version` together (enforced direction documented in `corpus/schema.py` docstring).
- `asr_outputs[]` stays thin by design (1 failed Roshan pilot row in prod); whisper model details are declared `unverified`, not invented.

## 16. Rollback
- Code: revert `ffdd61be5` on `phase3-radio-rag-service` (`git revert -m 1`/or FF back to `e7c9a67ac` since nothing else landed between). The commit is additive-only (6 new files, 0 deletions) — reverting cannot affect the exporter, SRT pipeline, or any export.
- 53: `git merge --ff-only e7c9a67ac` restores the pre-Stage-2 tree exactly.
- Report: delete the report file commit on `download-db` (additive-only).

## 17. Verdict
**PARTIAL** — all Stage 2 engineering deliverables are **DONE and verified** (versioned Draft 2020-12 schema v1.0 + `x-corpus` identity-policy metadata, complete honest field mapping with explicit missing/unverified/NA gaps, two validator-passing example records, stdlib loader + `verify()` drift gate, 83/83 tests on local and 53, GitHub push `ls-remote`-verified at `ffdd61be5`), but the mission's **GitLab push requirement remains BLOCKED** by the missing mirror project (identical to Stage 1, needs a project-name decision). No production system was touched; no DB changes; no data files committed.
