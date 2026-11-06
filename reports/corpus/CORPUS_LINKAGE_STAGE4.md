# Stage 4 — IranSeda Corpus v1.1 Re-materialization, RAG Linkage Dataset & Incremental Proof

Date: 2026-11-06 (UTC) · Host: 53 (`/home/saber/saberprojects/iranseda-crawler-golang-`)
Branch: `stage2-corpus-linkage` (continued from Stage 3 tip `6ceda1fa2`)
Spec: `docs/corpus/CORPUS_LINKAGE_SPEC.md` (normative), Stages 0–3 reports in `reports/corpus/`

---

## 1. Scope & hard constraints (all honored)

Stage 4 deliverables:

- **Task A (code)** — v1.1 additive schema/validator/mapper/exporter; new
  `corpus/rag_linkage.py` (K1–K22 RAG linkage dataset + asset manifest); v1.1-compatible
  incremental/scheduler; full test suite green.
- **Task B (live, 53)** — backup → pinned v1.1 full export → invariance proof (a)–(e) →
  replace live → rag-linkage run → one real incremental pass. NO re-embed, NO Neo4j writes,
  NO service restarts, NO SRT/TXT changes, NO auto-refresh-branch touches.
- **Task C (this report)** — report + stage-distinct commits + push (no force) + SHA backfill
  + mirror to workspace `reports/corpus/`.

Hard constraints honored:

- **Additive-only v1.1** (spec §8.1): no v1.0 field renamed, removed, or re-shaped;
  canonical identity (D-1/D-2) carried in NEW additive fields; existing `record_id` values
  preserved verbatim.
- **Identity rules** — D-1: session key `(ch, e)` from `sessions.link`; D-2: program key
  `(ch, m)` from `programs.url` (59 programs).
- **GITHUB_BRANCH from live `.env`** (currently `download-db`) — never hardcoded (R7).
- **Implausible Jalali years → `"impossible"`**, never "fixed". `speakers` null-by-policy.
  Timezone `Asia/Tehran`.
- **Quarantine semantics (spec §10.1)** — membership can never shrink; policy
  `PERMANENT_UNTIL_IDENTITY_PROVEN` unchanged.
- **Read-only posture** — MySQL SELECT-only; Neo4j read-only (fail-closed Cypher
  write-token guard); no DB writes, no Neo4j writes, no re-embed.
- **No secrets committed** — `.env` never staged; tracked `venv/**/*.pyc` drift explicitly
  excluded from commits.

---

## 2. Delta forensics (delta-15, DB-evidenced)

Pre-export reconciliation (`reports/corpus/stage4_delta_forensics.txt`):

```
COUNTS {"radio_programs": 59, "radio_program_sessions": 10893, "llm_output": 13603, "asr_output": 1, "crop_detection": 22}
db_sessions 10893  max_id 10895  min_id 3
corpus 9731  quarantine 1147  covered 10878
MISSING (db not in corpus/quarantine): 15 -> [10881, ..., 10895]
EXTRA (in corpus/quarantine, not in db): 0 -> []
```

All 15 missing sessions are channel-14 radio-maaref archive episodes added to the DB by the
production auto-refresh AFTER the pinned export time (`2026-11-05T00:53:14`):

| session_id | program_id | link `e=` | status | created_at (DB) |
|---|---|---|---|---|
| 10881 | 53 | 154148426 | subtitled | 2026-11-05 02:45:38 |
| 10882 | 30 | 154148424 | subtitled | 2026-11-05 04:15:08 |
| 10883 | 58 | 154148425 | **failed_permanent** | 2026-11-05 04:15:49 |
| 10884 | 59 | 154148408 | subtitled | 2026-11-05 08:46:04 |
| 10885 | 37 | 154148402 | subtitled | 2026-11-05 11:45:13 |
| 10886 | 49 | 154148398 | subtitled | 2026-11-05 11:45:28 |
| 10887 | 60 | 154148399 | subtitled | 2026-11-05 11:45:42 |
| 10888 | 33 | 154148395 | **failed_permanent** | 2026-11-05 13:15:53 |
| 10889 | 44 | 154148373 | subtitled | 2026-11-05 20:45:33 |
| 10890 | 45 | 154148370 | subtitled | 2026-11-05 20:45:35 |
| 10891 | 57 | 154148372 | subtitled | 2026-11-05 20:45:54 |
| 10892 | 43 | 154151493 | subtitled | 2026-11-05 22:15:26 |
| 10893 | 42 | 154151490 | subtitled | 2026-11-05 23:45:19 |
| 10894 | 36 | 154151489 | subtitled | 2026-11-05 23:45:57 |
| 10895 | 41 | 154151483 | subtitled | 2026-11-06 01:15:21 |

- 13 `subtitled`, 2 `failed_permanent` (10883 / 10888 — `Invalid data found when processing
  input` on the MP4, 2 attempts each, no SRT).
- All 15 have `record_id_collides_live: false` — none collide with any live
  record_id/quarantine record_id; they are pure DB-ahead additions (spec §8.6 additive).
- **Onboarded** by the v1.1 re-export: post = 9,746 = 9,731 + 15 (invariance check (a)).

**Delta-16** (recorded during the incremental pass): session **10896**
(`iranseda:ch14:e154151476`, program 53 "مبنا", status `pending_download`) was added by the
production auto-refresh between the pinned export and the incremental pass
(watermark `sessions_updated_at 2026-11-06T02:45:49`, `sessions_max_id 10896`). It was
appended by the incremental merge (§5.6) — an honest DB-ahead delta, not a manual edit.

---

## 3. Task A — code changes (tested: 200/200 local AND on 53 venv)

Source of truth: 53 worktree `/tmp/saber_stage4_wt` (branch `stage2-corpus-linkage`),
mirrored in workspace `_work/stage4_repo/`.

### 3.1 `corpus/mapper.py` — v1.1 additive fields

For every record (v1.0 fields untouched, additive only):

- `schema_version` → `"1.1"`
- `session_uid` = `iranseda:ch{ch}:e{e}` (+`session_uid_status`, `"link"` when derived from
  `sessions.link` — D-1)
- `program_uid` = `iranseda:prog:ch{ch}:m{m}` (+`program_uid_status`) from `programs.url` —
  D-2 (59 programs)
- `linkage` block: `linkage_version "1.1"`, `timezone "Asia/Tehran"`, `links` (4 IranSeda
  link types with status/reason), `validity`, `asset_summary` (per-type counts + git
  presence), `air_date_status` (`impossible` / `unverified` / `none`)
- `broadcast.timezone`, `broadcast.validity`, `broadcast.day_of_week` (additive sub-fields)

Implausible Jalali years produce `broadcast.validity` issues + `air_date_status "impossible"`
— never a "fixed" date.

### 3.2 `corpus/validator.py` — dual-version validation

`validate_record()` dispatches on `schema_version`: v1.0 path unchanged; new
`_check_v11()` enforces the additive contract (uid shapes, linkage block, status enums).
Both legacy and new example records pass.

### 3.3 Schema artifacts

- `corpus/schema/corpus.schema.json` — v1.1 (additive properties + `x-corpus` metadata)
- `corpus/schema/field_mapping.json` — new v1.1 fields documented with source types
- New examples: `corpus/schema/examples/valid_record_1_1.json`,
  `corpus/schema/examples/quarantine_record_1_1.json` (verified by `corpus.schema.verify`)

### 3.4 `corpus/exporter.py` — merge mode + versioned manifest

- **Merge mode** (used by incremental): live lines kept verbatim, batch records
  upserted in place by `record_id`, new sessions appended at tail, quarantine membership
  never shrinks.
- **Manifest v1.1**: `manifest_version "1.1"`, `mode` (`full` / `incremental-merge`),
  `merge` block, `asset_manifest_ref` / `rag_linkage_ref`, `field_coverage`,
  `db_counts_at_run`, frozen `watermark`/`disk` blocks.
- **Previous-slot archiving** with `PREVIOUS_RETENTION = 3` (slot named after the old live
  manifest `run_id`; collision counter `-2/-3/...`; never clobbers).

### 3.5 `corpus/rag_linkage.py` (NEW) — RAG linkage dataset + asset manifest

- Builds `rag_linkage.jsonl` (one row per DB session) + `asset_manifest.jsonl`
  (one row per asset) in `data/corpus/`; atomic writes; `map_id = sha256(file content)`.
- **K1–K22 keys**, nulls OMITTED (spec §8.4); quarantined rows are link-stripped and
  flagged `quarantined: true` (R4 / spec §10.1).
- **doc_id resolution**: Neo4j `radio` graph inventory via HTTP
  (`POST .../db/radio/tx/commit`) when available, else `derive_doc_id`
  (`<filename-stem>__s<session_id>`). Neo4j unavailability NEVER aborts the run.
- **Fail-closed write guard**: statements must start with `MATCH`/`RETURN`/`SHOW`/`CALL`/
  `EXPLAIN` and may contain no write tokens (`CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`,
  `REMOVE`, `DROP`, `LOAD`, `CONSTRAINT`, `GRANT`, `REVOKE`, ...) — Neo4j writes are
  impossible from this module by construction.
- **Asset manifest** reuses Stage 3 `corpus.assets` registry + `check_disk` (sha-cap
  30 MB; head/tail fingerprint above cap); URLs from GitHub identity via
  `GITHUB_BRANCH` in the live `.env` (R7, never hardcoded).
- CLI: `corpus rag-linkage` (`corpus/cli.py`).

### 3.6 Incremental + scheduler v1.1 compatibility

`corpus/incremental.py` — state file `data/corpus/incremental_state.json`
(`watermark`, `last_run_id`, `last_records_written`); no state → full run; otherwise
watermark clause `((updated_at IS NULL) OR updated_at >= wm - 12h OR id > wm_max_id)`;
`--pin` pins `exported_at`/`run_id` from the live manifest (no-change merge is
byte-identical). `corpus/scheduler.py` cycle is v1.1-compatible.

### 3.7 Tests

`tests/corpus/run_all.py`: **200/200 green** (was 198 at Stage 3; +2 regression tests
below) — verified both locally and on the 53 venv (3.12.3). New
`tests/corpus/test_rag_linkage.py` (25 tests) covers: `derive_doc_id`, write-verb
rejection, read-verb acceptance, **Neo4j payload parsing (both key shapes)**, quarantine
link-stripping, asset-URL injection (published-only), null discipline, full
`main()` end-to-end with fake deps.

---

## 4. Task B.1 — Backup (canonical rollback)

`data/corpus_backups/pre-stage4-20261106-0204/` (7 files, SHAs verified post-copy):

| file | bytes | SHA-256 |
|---|---|---|
| `corpus.jsonl` | 911,707,256 | `60d482c9ed30ee19e70d5189714ba14173dd6220099d4fd73bd4599f5dce1ee3` |
| `quarantine.jsonl` | 77,525,494 | `7e0e6276be406281faaa7b30ee5c28572a247d60815100f686c1dc96f665d24b` |
| `stats.json` | 21,052 | `4c595dd19b99f3f82e7e017e564aa798c9a829dde9b2c7a5fb5a9976088c36ed` |
| `manifest.json` | 1,987 | `4d6a0c98b45721d740b3239dd95d6ffe18eec75ea0a197b03ed20fe0c378cf69` |
| `checksums.sha256` | 239 | `86296f6c0160e93349afcc54cf5b1aae6d77c9c72ca9578c811d6e94b9c6d259` |
| `SHASUMS256.txt` | 402 | `97cd52e1c23cc6fac1769b8218d895e637598b437227d5088adc47dfa9bb11ce` |
| `SIZES.txt` | 136 | `e352413c8e1595e469fecee33df49e2424cc56b052cb1e5298d700160c430c2f` |

Pre-stage4 live = v1.0 export: 9,731 corpus records + 1,147 quarantine lines,
`run_id corpus-det-2026-11-05T00-53-14`, `exported_at "2026-11-05T00:53:14"` (T-form —
the pin target for the re-export).

## 5. Task B.2–B.6 — Live operations

### 5.1 Pinned v1.1 full export (run 1 misstep + run 2 repair)

- **Run 1** (02:26Z): pinned with a **space-form** `exported_at "2026-11-05 00:53:14"` —
  a format mismatch vs the live v1.0 `provenance.exported_at` (T-form). Succeeded
  (9,746 / 0 invalid / 1,147 quarantined, 133.5 s) but the provenance pin was wrong.
- **Run 2** (02:36Z): re-pinned with the exact T-form `"2026-11-05T00:53:14"` +
  `run_id corpus-det-2026-11-05T00-53-14`:
  `9,746 ok, 0 invalid, 1,147 quarantined, 10,893 seen` in **132.1 s**;
  `deterministic: true`, mode `full`. Live replaced by auto-promote after staged
  validation; run-1 output archived, pre-stage4 v1.0 archived (slot `-2`).

### 5.2 Invariance proof (a)–(e) — ALL PASS

`reports/corpus/stage4_invariance_proof.{txt,json}` (backup v1.0 vs new v1.1 live):

```
[PASS] a_post_superset_of_pre removed=0
[PASS] a_additions_eq_delta_session_ids added_rids=15 added_sessions=[10881, ..., 10895]
[PASS] b_pre_v10_fields_byte_identical compared=9731 unexplained_diffs=0
[PASS] b2_audio_local_exists_flips_explained_by_disk flips=250 distinct_files=250 gone_from_disk=250 still_on_disk=0
[PASS] c_quarantine_membership_and_policy_identical pre=1147 post=1147 policy=['PERMANENT_UNTIL_IDENTITY_PROVEN'] unexplained=0
[PASS] c2_quarantine_local_exists_flips_explained flips=7 gone_from_disk=7 still_on_disk=0
[PASS] d_coverage_table_computed fields=24 (see report json)
[PASS] e_counts_reconcile pre=9731 + delta15 -> post=9746 ; post+1147 quar = 10893 ; db=10893
RESULT: ALL PASS
```

- (b) method: project each v1.1 record back to its v1.0 view (drop the additive keys
  `session_uid*`, `program_uid*`, `linkage`, `broadcast.{timezone,validity,day_of_week}`,
  reset `schema_version`) and canonical-JSON compare — **all 9,731 pre records
  byte-identical**; every pre record gained the additive fields.
- **Documented exception (production disk cleanup, NOT a defect)**: 250 corpus + 7
  quarantine records flipped `audio.local_exists` True→False between the two scans.
  Every one of the 257 flipped files was cross-verified **GONE from disk** (0 still on
  disk; `stage4_diskcheck.txt`). Indexed disk moved 42,368 → 42,155 files
  (24,661 → 24,674 stems) — the production disk-cleanup job ran between the pre-stage4
  scan and run 2.

### 5.3 v1.1 re-materialization diff (what changed for existing records)

- `corpus.jsonl`: all 9,731 records re-materialized as v1.1 — additive fields above;
  `schema_version 1.0 → 1.1`; +15 delta-15 records appended → 9,746.
  Full diff-path aggregate (`stage4_v10_diff_aggregate.txt`): exactly
  `250 × .audio.local_exists` (the disk cleanup) — nothing else.
- `quarantine.jsonl`: all 1,147 lines re-materialized; each record gained the same
  additive keys (v1.0 view preserved); 7 records also show the disk-cleanup flip.
  Membership, `problems`, and policy untouched.

### 5.4 RAG linkage — run 1 exposed a real parser bug (found, fixed, re-verified)

- **Run 1** (02:51Z): `Neo4j radio -> 0 distinct doc_id (4148 rows)` — all doc_ids
  silently fell back to `db_derived`.
- **Forensics** (`stage4_neoprobe.txt` / `stage4_neoprobe2.txt`): parsed rows were all
  `{}`; the raw `tx/commit` payload proves the endpoint returns
  **`"columns"`, not `"fields"`**:
  ```json
  {"results":[{"columns":["doc_id","session_id"],"data":[{"row":["radio-maaref-03-09-06-06-00__s26",26],"meta":[null,null]}]}],"errors":[],"lastBookmarks":["FB:kcwQmBru22JVQc2Fr7rygptFWskEb5A="]}
  ```
- **Fix** in `corpus/rag_linkage.py::neo4j_query()` (accept both payload shapes):
  ```python
  # tx/commit payloads carry "columns" (neo4j 5.x); older
  # tooling used "fields" - accept both.
  fields = (results[0].get("columns")
            or results[0].get("fields") or [])
  ```
  + 2 regression tests (`test_neo4j_query_parses_columns_payload`,
  `test_neo4j_query_parses_legacy_fields_payload`) → **200/200 green** locally and on
  the 53 venv.
- **Run 2** (03:12Z, post-fix) — atomically overwrote run-1 outputs:
  `Neo4j radio -> 4148 distinct doc_id (4148 rows)`, 43.2 s. (See §6 for the dataset.)

### 5.5 RAG linkage outputs (run 2, final)

See §6 (counts + samples). Both files atomic-written to `data/corpus/`; manifest
updated with `rag_linkage_ref` / `asset_manifest_ref`; `run_id`/`exported_at` still
pinned.

### 5.6 Incremental — state init + one real merge pass (verified PASS)

- **Pre** (`stage4_inc_pre.{json,txt}`): no state file existed; live snapshot taken
  (corpus `0cdddca2...`, 9,746 lines); `incremental_state.json` hand-initialized to the
  then-current DB high watermark
  (`sessions_updated_at 2026-11-06T02:45:49`, `sessions_max_id 10896`,
  `llm_finished_at 2026-10-11T11:30:01`, `llm_max_id 15324`),
  state sha pre `eb6389c4f1968b93437f1760bbbf75e650ce8adb6e97c3f6d93a620a28123650`.
- **Pass**: `incremental --pin --assets` (53.5 s):
  `WHERE ((updated_at IS NULL) OR updated_at >= 2026-11-05 14:45:49 OR id > 10896)`
  → 8 watermark-selected sessions →
  `[merge: +7 updated, +1 appended, +0 invalid, +0 quarantined]` → 9,747 records.
- **Verification** (`stage4_inc_verify.txt`) — **RESULT: PASS**:
  - corpus: 9,746 → 9,747 lines, subsequence-preserving (every pre line verbatim, in
    order); the 7 updated records came back **byte-identical** (idempotent upsert);
    the 1 appended line is a NEW session — `sid=10896 rid=iranseda:ch14:e154151476
    status=pending_download` (delta-16).
  - quarantine: 1,147 lines **verbatim, 0 added** (membership never shrinks).
  - state advanced: `last_records_written 9747`, `updated_at 2026-11-06 03:00:16`
    (watermark unchanged — no further DB updates during the pass).
  - manifest: mode `incremental-merge`, provenance pin intact
    (`run_id corpus-det-2026-11-05T00-53-14`, `exported_at 2026-11-05T00:53:14`).
- **previous/ slots after the pass** (retention 3; the pre-existing base slot
  `corpus-det-2026-11-05T00-53-14` was pruned):
  - `-2`: 911,707,256 / 1,987 / 77,525,494 / 21,052 — pre-stage4 v1.0 (== backup)
  - `-3`: 926,663,865 / 2,995 — pinned-export run 1 (space-pin)
  - `-4`: 926,663,870 / 2,995 — pinned-export run 2 (pre-incremental live)

---

## 6. RAG linkage dataset + asset manifest (final, run 2)

`data/corpus/rag_linkage.jsonl` — **10,894 rows** (one per DB session), 12,226,280 B:

```
sha256: 05caa88dfa6afc965d7a36be6f63f5c8f118da66f2727cbc4b72c68492c0ebd8   (== map_id)
rag_rows: 10894        rag_quarantined: 2294 (= 2 × 1,147; both members of every
                       Class-B pair are link-stripped + flagged per R4)
corpus_records_read: 9747
doc_id: source=neo4j, neo4j_distinct=4148, from_neo4j=4148,
        from_db_derived=6420, missing=326   (4148+6420+326 = 10,894 ✓)
air_date_status_counts: {impossible: 105, none: 1442, unverified: 9347}
git_branch: download-db (from live .env GITHUB_BRANCH — R7)
git_tree_paths: 37,747      sha_cap: 31,457,280
map_id: 05caa88dfa6afc965d7a36be6f63f5c8f118da66f2727cbc4b72c68492c0ebd8
generated_at: 2026-11-06T03:12:32Z  duration: 43.2 s
```

Sample (first row):

```json
{"record_id": "iranseda:ch14:e152507883", "session_id": 3, "session_uid": "iranseda:ch14:e152507883",
 "program_id": 1, "program_title": "بر كرانه نور", "program_uid": "iranseda:prog:ch14:m044116",
 "broadcast_date_persian": "1403-08-17", "broadcast_date_gregorian": "2024-11-07",
 "broadcast_time": "21:30:00", "timezone": "Asia/Tehran", "program_page_url": "https://radio.iranseda.ir/Program/?VALID=TR...
```

Sample quarantined row (all asset/episode links stripped, doc_id retained):

```json
{"record_id": "iranseda:ch14:e152802657", "session_id": 88, "quarantined": true,
 "air_date_status": "unverified", "linkage_version": "1.1",
 "doc_id": "radio-maaref-04-01-20-16-30__s88", "doc_id_mapped_from": "db_derived", ...}
```

`data/corpus/asset_manifest.jsonl` — **39,447 rows** (one per asset):

```
sha256: 8a43dca52f7f06494b4113fb1156a364dd6809f80a8ff319231c1a32d24f99c5
asset_manifest_rows: 39,447   asset_published: 16,265   asset_excluded: 7,719
```

---

## 7. Final live state (authoritative, re-snapshotted 2026-11-06 03:21Z)

`data/corpus/` (post every operation):

| file | bytes | SHA-256 |
|---|---|---|
| `corpus.jsonl` | 926,667,693 | `753fb9deff885d33473e453e8006a9e77a87126ae2c21c9b2eeedd398d9196fb` |
| `quarantine.jsonl` | 79,145,066 | `ff07659990f8e04543f8e47cd2fb6839acb2b1f791d942ddce235a561a1208c1` |
| `stats.json` | 21,052 | `f29f0dfc345af05e24dcb6f1da86a6b1f10343457f5a16664f8e3c6c73c369d4` |
| `manifest.json` | 3,392 | `d5a53f7d6425a08c3c0d8ce3de6ba68e92ec98e6476355ca3f927c38f29887f8` |
| `checksums.sha256` | 239 | `facffb3340e6c0d68058d6b9f6d75bd8bafda85776c7d4d1044a1fd9b67f7bcb` |
| `incremental_state.json` | 296 | `d045e37431da23b6b8a18c00c74632cfc715d1f05cc3e630a7fcad776efe42ab` |
| `metrics.prom` | 1,727 | `be48a01f489ce9242e7db294a5ebae841920b929ae8e5c6d495d312289256fce` |
| `rag_linkage.jsonl` | 12,226,280 | `05caa88dfa6afc965d7a36be6f63f5c8f118da66f2727cbc4b72c68492c0ebd8` |
| `asset_manifest.jsonl` | 32,624,442 | `8a43dca52f7f06494b4113fb1156a364dd6809f80a8ff319231c1a32d24f99c5` |
| `class_b_investigation.jsonl` | 2,796,439 | `da9b2a07b57cbc78f25a054e6d55b8616a63e95937d4a4bc351e14fac78a510f` (pre-existing, untouched) |
| `reconcile_report.json` | 291 | `ff9d46a29042dafaa274cb3198040ea36e8c043bed94c581ebb2ae90cdf8adbc` (pre-existing, untouched) |

`quarantine.jsonl` SHA unchanged by the incremental pass (merge appends only to corpus).
Pre-incremental live (archived in slot `-4`): corpus `0cdddca2...` (926,663,870 B),
manifest `c3f66923...` (2,995 B), checksums `09a25f7b...`, stats `2c6925ba...`.

### 7.1 Coverage table (24 fields, over 9,746 records — invariance check (d))

| field | filled | pct | | field | filled | pct |
|---|---|---|---|---|---|---|
| record_id | 9,746 | 100.00 | | audio.url | 9,746 | 100.00 |
| episode_key.source | 9,746 | 100.00 | | audio.local_exists | 9,746 | 100.00 |
| database_refs.session_id | 9,746 | 100.00 | | transcripts.originals.srt | 9,746 | 100.00 |
| database_refs.program_id | 9,746 | 100.00 | | transcripts.originals.txt | 9,746 | 100.00 |
| program | 9,746 | 100.00 | | transcripts.llm_outputs | 4,251 | 43.62 |
| program.schedule | 9,746 | 100.00 | | crop | 22 | 0.23 |
| broadcast | 9,452 | 96.98 | | session_uid | 9,746 | 100.00 |
| broadcast.jalali | 9,452 | 96.98 | | program_uid | 9,746 | 100.00 |
| broadcast.gregorian | 9,452 | 96.98 | | linkage | 9,746 | 100.00 |
| broadcast.timezone | 9,452 | 96.98 | | linkage.links | 9,746 | 100.00 |
| broadcast.validity | 9,452 | 96.98 | | linkage.air_date_status | 9,746 | 100.00 |
| broadcast.day_of_week | 9,347 | 95.91 | | linkage.asset_summary | 9,746 | 100.00 |

Stats headline: `by_status {subtitled: 9,118, pending_download: 573,
failed_permanent: 55}`; `audio_local_exists 2,650`; `records_with_broadcast 9,452`
(without: 294); `episode_key_link 9,746` (fallback 0); `program_missing 0`;
`records_complete 9,410`; `records_with_original_srt/txt 9,411`.

---

## 8. HuggingFace publisher status — BLOCKED (unchanged from Stage 0 B-1)

- No `data/corpus/hf/` bundle exists; no `HF_TOKEN` in the environment; no
  `datasets`/`huggingface_hub` packages in the 53 venv; rights/licensing unverified.
- Stage 4 did **not** touch `corpus/publisher.py` — status unchanged.
- Per R4/spec §10.1, quarantined records (1,147) are excluded from any future HF
  dataset; the RAG linkage dataset carries the `quarantined` flag for 2,294 rows
  (both members of each Class-B pair).

## 9. BLOCKED items

No NEW blockers from Stage 4. Outstanding (carried): HF publisher (Stage 0 B-1) —
blocked on token + rights verification.

## 10. Request budget (politeness)

- **MySQL**: SELECT-only (`radio_programs`, `radio_program_sessions`, `llm_output`,
  `high_watermark`, table counts). Zero writes.
- **Neo4j**: 2 read-only `MATCH` invocations via the HTTP `tx/commit` API (rag runs)
  + 2 diagnostic probes. **Zero writes** — the module's write-token guard makes writes
  impossible by construction.
- **Git**: `git ls-tree -r --name-only download-db` (read-only) — 5 invocations
  (export runs, incremental, rag runs); 37,747 paths each. No pushes to the asset repo,
  no branch changes.
- **Live site (radio.iranseda.ir)**: **zero HTTP requests** in Stage 4 — no link
  re-validation was performed; `air_date_status` reflects the spec §6.6 cache-miss
  discipline (`unverified`), filename-derived `impossible` dates, or `none` when no
  broadcast date exists.
- **Disk**: read-only scans (`DiskIndex`, `check_disk` with 30 MB sha cap). No files
  created/modified in `downloads/`.

## 11. Git (Task C)

Work performed on 53 worktree `/tmp/saber_stage4_wt`, branch
`stage2-corpus-linkage` (continued from Stage 3 tip `6ceda1fa2`). Explicit `git add`
of curated paths only; tracked `venv/**/*.pyc` drift and `.env` never staged.

Stage-distinct commits (SHAs backfilled below after commit):

1. **Code** — v1.1 mapper/validator/schema/exporter + `corpus/rag_linkage.py` +
   incremental/scheduler/cli: `corpus/{cli,exporter,incremental,mapper,schema,validator,rag_linkage}.py`,
   `corpus/schema/{corpus.schema.json,field_mapping.json}`,
   `corpus/schema/examples/{valid_record_1_1.json,quarantine_record_1_1.json}`.
   SHA: `TBD_COMMIT_1`
2. **Tests** — `tests/corpus/test_rag_linkage.py` (new, 25 tests incl. Neo4j payload
   regression), `tests/corpus/test_schema.py` (v1.1 examples).
   SHA: `TBD_COMMIT_2`
3. **Report + evidence** — `reports/corpus/CORPUS_LINKAGE_STAGE4.md` + curated
   `stage4_*` evidence (delta forensics, diskcheck, final state, gitcheck, inc
   pre/verify, incremental log, invariance proof json/txt, livestate, neo probes,
   pinned export logs, rag logs, v10 diff aggregate).
   SHA: `TBD_COMMIT_3`
4. **Backfill** — commit SHAs recorded in this report (no placeholders left).
   SHA: `TBD_COMMIT_4`

Push: `git push origin stage2-corpus-linkage` (no force). `TBD_PUSH_OUTPUT`

## 12. What did NOT change in production

- **No DB writes** — MySQL used strictly read-only (SELECT). `radio_program_sessions`
  went 10,893 → 10,894 only via the production auto-refresh (session 10896), not by
  this work.
- **No Neo4j writes** — read-only HTTP reads only; write guard by construction.
- **No re-embedding** — no vector store touched.
- **No service restarts** — crawler, ASR, RAG stack untouched.
- **No SRT/TXT or any `downloads/` file created, modified, or deleted** — the
  257-file disk reduction is the production disk-cleanup job (documented exception,
  cross-verified in §5.2).
- **No auto-refresh-branch touches** — `GITHUB_BRANCH` (`download-db`) read from the
  live `.env`, never modified.
- **Main worktree untouched** — all code runs from `/tmp/saber_stage4_wt`; the live
  repo's own (older) `corpus/` package was not replaced.
- **No secrets committed** — `.env` never staged; `venv/**/*.pyc` tracked-file drift
  explicitly excluded.
- **Pre-existing live files untouched**: `class_b_investigation.jsonl`,
  `reconcile_report.json` (SHAs in §7).

## 13. Post-note — production auto-refresh drift (recorded post-commit)

Between the pinned export (02:36Z) and the incremental pass (02:59Z) the production
auto-refresh added session 10896 (delta-16, `pending_download`) — captured by the
watermark clause and appended by the merge, exactly as designed (§8.6 additive).
No further drift observed by the final-state snapshot (03:21Z).

---

### Evidence index (53, `/tmp/saber_stage4_wt/reports/corpus/`)

| file | content |
|---|---|
| `stage4_delta_forensics.txt` | delta-15 counts + 15 DB-evidenced rows |
| `stage4_pinned_export.log` / `stage4_pinned_export_run2.log` | run 1 (space-pin) / run 2 (T-form) |
| `stage4_invariance_proof.{txt,json}` | invariance (a)–(e) — ALL PASS |
| `stage4_v10_diff_aggregate.txt` | diff-path aggregate (250 + 7 disk flips only) |
| `stage4_diskcheck.txt` | 257 flipped files all GONE from disk |
| `stage4_livestate.txt` | live SHAs + coverage + stats (post-export) |
| `stage4_rag_linkage.log` / `stage4_rag_linkage_run2.log` | rag run 1 (bug) / run 2 (fixed) |
| `stage4_neoprobe.txt` / `stage4_neoprobe2.txt` | parser-bug forensics (raw payload) |
| `stage4_ragcheck.txt` | final rag/asset outputs verification + samples |
| `stage4_inc_pre.{json,txt}` | pre-incremental snapshot + state init (sha `eb6389c4...`) |
| `stage4_incremental.log` | merge pass log (+7 / +1 / +0 / +0) |
| `stage4_inc_verify.txt` | incremental verification — PASS |
| `stage4_gitcheck.txt` | branch/status/tests (200/200) at check time |
| `stage4_final_state.txt` | authoritative final SHAs (03:21Z) |
