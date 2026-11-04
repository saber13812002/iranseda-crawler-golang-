# Stage 1 — Class B Identity Investigation & Quarantine

**Mission:** IRANSEDA-CORPUS-2026-01 (Seven-Stage Knowledge Corpus, HF Dataset & RAG)
**Stage:** 1 of 7 — Class B identity investigation and quarantine (CRITICAL)
**Verdict:** **PARTIAL** — quarantine gate **PASS** (no record deleted, merged, or
silently reclassified); GitHub push **verified**; GitLab destination **BLOCKED**
(no mirror project for this repository exists on `git.ai.ismc.ir` — see §11/§14).

---

## 1. Date & timezone
- UTC: 2026-11-04 21:30 – 22:00 UTC
- Tehran (production): 2026-11-05 01:00 – 01:30 (UTC+3:30)
- All server timestamps below are UTC (server 53 `date`).

## 2. Environment
| Item | Value |
|---|---|
| Production server | `saber@172.20.1.53` (up 8 days at preflight, load 2.1) |
| Production checkout | `/home/saber/saberprojects/iranseda-crawler-golang-/` (trailing slash is real) |
| Python (server) | `dashboard/venv/bin/python3` — 3.12.3, stdlib + pymysql |
| Database | MySQL 8.0.46 @ `127.0.0.1:3308`, db `radio` (read-only access used) |
| Local dev | Windows 10, worktree `iranseda-corpus-wt` (branch `phase3-radio-rag-service`) |
| Git relay | GitHub DNS down locally → all pushes via 53 LAN relay + `git ls-remote` |

## 3. Repository & branch
- Primary: GitHub `saber13812002/iranseda-crawler-golang-`, branch `phase3-radio-rag-service`
- Code (corpus module + tests) lives on `phase3-radio-rag-service` (worktree layout:
  `corpus/` + `tests/corpus/` tracked there; reports tracked on `download-db`).
- Internal GitLab: `git.ai.ismc.ir` → 172.30.0.133 (local DNS `172.22.6.1`);
  `getent` resolves on 53; port 443 OPEN, port 22 CLOSED from 53.

## 4. Starting SHAs
| Ref | SHA | Note |
|---|---|---|
| worktree tip (pre-Stage 1) | `bc5e8fb00` | Class A fix + incremental.log fix |
| 53 phase3 HEAD at start | `2a8858c51` (21:00 auto-refresh) | 25 commits ahead of worktree |
| 53 phase3 HEAD at relay | `7b1b4aa6a` (21:30 auto-refresh) | auto-refresh raced once during relay |
| final base | `7b1b4aa6a` | Stage 1 commit rebased onto it (docs/downloads only, no overlap) |

## 5. What changed
1. **`corpus/identity.py` (new, ~450 lines)** — read-only, pure, deterministic
   Class B investigation module:
   - iterates **all** `radio_program_sessions` rows (10,873), groups by the
     EPG `(ch, e)` parsed from `session.link` (via `Database.parse_ch/parse_e`);
   - per group compares: `program_id`, `filename`, broadcast date (Jalali, parsed
     from the canonical filename stem — **never** `created_at`), `status`,
     `is_downloaded`, `is_subtitled`, `attempts`, SRT presence + **SRT sha256**;
   - classifies each group (most-decisive rule first):
     `same_episode_multiple_references` / `different_sessions_sharing_source_link`
     (reserved) / `same_program_repeated_broadcast` /
     `different_programs_shared_archive_reference` / `insufficient_evidence`;
   - embeds quarantine policy **PERMANENT_UNTIL_IDENTITY_PROVEN** in every group
     record. Never merges, deletes, or auto-reclassifies. `(ch, e)` is treated
     as a *source reference*, never as sole session identity.
2. **`corpus/cli.py`** — new `investigate` command (read-only; writes
   `data/corpus/class_b_investigation.jsonl`: 1 summary line + 1 line per group).
3. **`tests/corpus/test_identity.py` (new, 8 regression tests)** — distinct
   sessions never collapse; identical URLs do not equate sessions; all Class B
   members preserved with DB ids; exporter record_id uniqueness invariant holds;
   deterministic + reproducible output (byte-identical jsonl); `classify_group`
   pure rules; jsonl shape.
4. **Identity docs erratum (pre-existing uncommitted work, committed with this
   stage)** — live probes (probes 7–8 on 53) proved canonical stems have exactly
   **5 numeric tokens** (`JJ-MM-DD-HH-MM`, seconds implicitly `00`), not 6.
   Fixed in `docs/CORPUS_DATA_MODEL.md`, `docs/CORPUS_FIELD_MAPPING.md`,
   `reports/corpus/CORPUS_PREFLIGHT.md`. Backup of prior uncommitted state kept
   at `.tmp_uncommitted_backup_20261104.diff` (not committed).

### Root cause (confirmed in DB, live)
`radio_program_sessions` has `UNIQUE KEY uq_session_program_link (program_id,
link)` but **no** uniqueness on `link` alone. The same EPG archive link can
therefore exist under several programs/sessions; all such rows map to the same
`record_id = iranseda:ch{ch}:e{e}` → the exporter's (correct) duplicate guard
quarantines all but the first (lowest `id`) → the 1,147 Class B records.

### Proposed identity architecture (documented only — NO schema change)
- **`session_id` (`radio_program_sessions.id`, PK) is the authoritative session
  identity** — already carried in every v1 record as
  `database_refs.session_id` / `database_refs.tables.radio_program_sessions`.
- `episode_key {ch, e, m}` is a **source reference** (EPG slot), not identity.
- `record_id` is a derived index key, not identity.
- A future canonical resolution (Stage 3+ design input) should, per colliding
  group: (a) compare SRT sha256 / duration / program membership, (b) designate
  one **canonical `session_id`** per `(ch, e)` (human adjudication for the 51
  shared-archive groups; the 1,096 same-episode groups are near-mechanical —
  identical files), (c) map non-canonical sessions to fallback
  `iranseda:db{pid}:s{sid}` record ids (already implemented in the mapper) so
  every session keeps a unique, identity-safe key. **No table/column change is
  required or made.**

## 6. Files
Worktree commit `2c569ab4d` (branch `phase3-radio-rag-service`):
| File | Change |
|---|---|
| `corpus/identity.py` | new (~450 LOC) |
| `corpus/cli.py` | +24 (investigate command + dispatch) |
| `tests/corpus/test_identity.py` | new (8 tests) |

Report commit (branch `download-db`, this workspace): `reports/corpus/STAGE_1_CLASS_B_IDENTITY_REPORT.md`
(new) + the 3 erratum doc files above. No other files staged (no blind `git add -A`).

## 7. Database changes
**None.** Read-only SELECTs against `radio_program_sessions` (+ counts). No DDL,
no DML, no watermark/state changes.

## 8. Tests
`python tests/corpus/run_all.py` (stdlib-only runner, no pytest):
- **local (worktree, pre-push): 76/76 passed** (68 pre-existing + 8 new).
- **on server 53, post-FF: 76/76 passed in 0.1s.**

## 9. Exact results (live investigation on 53, `python -m corpus investigate`)
```
identity: 10873 sessions, 1147 (ch,e) groups with >1 session, 2294 sessions in groups
```
| Metric | Value |
|---|---|
| sessions total | 10,873 |
| colliding `(ch, e)` groups | 1,147 |
| sessions in groups | 2,294 |
| group member-count distribution | **all groups have exactly 2 members** |
| `same_episode_multiple_references` | 1,096 groups |
| `different_programs_shared_archive_reference` | 51 groups |
| `same_program_repeated_broadcast` / others | 0 groups |
| cross-check | 2,294 − 1,147 = **1,147 = invalid.jsonl line count exactly** |
| channels | ch14: 1,077 groups; ch18: 70 groups |
| same-episode evidence | 1,096/1,096 groups: both SRTs found **and** byte-identical (sha256 equal) |
| shared-archive evidence | 51 groups; 49 with identical SRT content (of 19 where both SRTs exist); program pairs 3↔31 (×31), 25↔52 (×18), 13↔40 (×2) |
| known case (mission example) | session 6217 (program 31) ↔ group `ch14:e153278467`, members [5038 (program 3), 6217 (program 31)], file `radio-maaref-04-09-05-16-00.mp4`, both downloaded+subtitled → `same_episode_multiple_references` |
| 2-digit year ambiguity | 23 groups parse to an impossible future Jalali year (e.g. `97` → 1497); flagged in the report of findings, no inference beyond `14xx` made |
| output | `data/corpus/class_b_investigation.jsonl` — 2,796,439 bytes, 1,148 lines, sha256 `da9b2a07b57cbc78f25a054e6d55b8616a63e95937d4a4bc351e14fac78a510f` |
| runtime | 1.3 s wall (read-only) |

## 10. Production evidence (before/after on 53)
- `data/corpus/` unchanged except the **new** `class_b_investigation.jsonl`:
  `corpus.jsonl` 9,721 lines / 911 MB, `invalid.jsonl` **1,147 lines / 77,166,417 bytes,
  mtime 09:01 (untouched)**, `manifest.json`/`stats.json`/`reconcile_report.json` untouched.
- Production SRT pipeline unaffected: fresh SRTs still landing
  (`radio-maaref-05-08-13-{13,14,16}-30.srt`, 21:00–21:36 window); no cron touched.
- Quarantine gate: **PASS** — zero records deleted/merged/reclassified;
  investigation output is read-only evidence.

## 11. Commit SHA
- Code: **`2c569ab4d332b0f382863036acdb4e7d70af8975`**
  `fix(corpus): preserve session identity and enforce Class B quarantine`
  (3 files, +694; rebased onto `7b1b4aa6a`).
- Report: see `download-db` commit recorded in §13 (this file).

## 12. Push verification
- `git push origin phase3-radio-rag-service` from 53 → rc 0.
- `git ls-remote origin phase3-radio-rag-service` →
  `2c569ab4d332b0f382863036acdb4e7d70af8975` (**matches local HEAD**).
- 53 local phase3 FF-merged to the same SHA (temp branch `stage1-classb` deleted).

## 13. Deploy status
No service restart, no cron/systemd change (Stage 7 territory). `investigate`
runs on demand. Auto-refresh site cron kept running unmodified throughout
(new auto-refresh commits `7b1b4aa6a` etc. were absorbed by rebase, never clobbered).
Report push: `download-db` pushed via the 53 relay (fast-forward from origin
`4840b653e`), `ls-remote` verified — see commit SHA below this table at commit time.

## 14. Output locations
- Server 53: `data/corpus/class_b_investigation.jsonl` (2.8 MB, sha256 above).
- Worktree: `corpus/identity.py`, `corpus/cli.py`, `tests/corpus/test_identity.py` (on `phase3-radio-rag-service`).
- This workspace (`download-db`): this report + 3 erratum docs.
- **Not committed to Git:** the multi-MB investigation file is a data artifact
  (kept on 53 like the other corpus outputs).

## 15. Remaining issues / blockers
1. **GitLab: BLOCKED (destination does not exist).** `git.ai.ismc.ir` is up
   (443 open; 22 closed). A root PAT is stored on 53 (`~/.git-credentials`,
   never printed); API shows **no project mirroring
   `iranseda-crawler-golang-`** (project 53 `rag/radio-rag-service` is a
   different FastAPI repo — 3 initial commits, no overlap with our SHAs;
   guessed paths 404). Per mission rule ("if GitHub succeeds but GitLab fails →
   PARTIAL, not PASS") this stage is PARTIAL. **Remediation (needs a name
   decision, so no guess):** create e.g. project `rag/iranseda-crawler` on
   `git.ai.ismc.ir`, add `gitlab` remote on 53, push `phase3-radio-rag-service`
   (and `download-db`), then `git ls-remote gitlab` verify.
2. 23 groups carry a 2-digit-year ambiguity (`97` → 1497). Flagged, not
   "fixed" (no inference beyond `14jj`, per mission rule).
3. 342 sessions have no filename → `broadcast` null (known; Stage 2 scope).
4. 51 shared-archive groups need human adjudication of the canonical
   `session_id` (Stage 3 exclusion policy consumes this file; no auto-resolution).

## 16. Rollback
- Code: `git revert 2c569ab4d` (or FF phase3 back to `7b1b4aa6a`) on 53; no
  migration to undo. `corpus investigate` simply ceases to exist.
- Report/docs: revert the `download-db` report commit.
- Data: delete `data/corpus/class_b_investigation.jsonl` (new file only).
- Nothing in production state was changed → rollback is total and trivial.

## 17. Verdict
| Gate | Result |
|---|---|
| No Class B record deleted / merged / silently reclassified | **PASS** (invalid.jsonl byte-identical count, 1,147 lines, untouched mtime) |
| Live investigation over all 10,873 sessions, all groups classified, machine-readable jsonl | **PASS** |
| 6+ regression tests, deterministic, 76/76 locally and on 53 | **PASS** |
| Identity architecture documented, no schema change | **PASS** |
| Commit + push + `ls-remote` verify (GitHub) | **PASS** (`2c569ab4d`) |
| GitLab second destination | **BLOCKED** (no mirror project; evidence + remediation above) |
| **Overall** | **PARTIAL** (quarantine integrity fully preserved; distribution incomplete per mission rule) |
