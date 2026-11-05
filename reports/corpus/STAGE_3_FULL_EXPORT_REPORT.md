# STAGE 3 — FULL JSON CORPUS EXPORT — EXECUTION REPORT

Mission: IRANSEDA-CORPUS-2026-01 · Stage 3 of 7

---

## 1. Date & timezone

- Executed: 2026-11-05 (local 00:40–02:10 Asia/Tehran, UTC+3:30; 21:10–22:10 UTC)
- All timestamps in server output are server-local (Asia/Tehran) unless noted.

## 2. Environment

| Item | Value |
|---|---|
| Local build/test host | Windows 10, Python (local), worktree `iranseda-corpus-wt` |
| Production server | 53 (`172.20.1.53`), Ubuntu, checkout `/home/saber/saberprojects/iranseda-crawler-golang-/` (trailing slash is real) |
| Production interpreter | `dashboard/venv/bin/python3` (Python 3.12.3, stdlib + pymysql; no jsonschema/pytest — stdlib test runner) |
| Database | MySQL 8.0.46 @ `127.0.0.1:3308`, db `radio`, user `n8nuser` (read-only from corpus code) |
| Disk before runs | `/dev/mapper/ubuntu--vg-ubuntu--lv` 1.5T, 307G free (79% used) |

## 3. Repository & branch

- Primary remote (GitHub): `github.com:saber13812002/iranseda-crawler-golang-`
- Internal remote (GitLab): `git.ai.ismc.ir` — **BLOCKED** (no project mirrors this repo; carried from Stage 1/2).
- Code branch: `phase3-radio-rag-service` (worktree `iranseda-corpus-wt`)
- Report branch: `download-db` (main workspace `iranseda`)

## 4. Starting SHAs

| Ref | SHA |
|---|---|
| Stage 2 code head (local) | `ffdd61be5` — `feat(corpus): define versioned metadata and transcript schema` |
| 53 `phase3-radio-rag-service` at commit time (auto-refresh) | `66dcd0bbe` — `auto: refresh site + subtitles (2026-11-05_01:30)` |
| Base of Stage 3 commit before rebase | `66dcd0bbe` |

## 5. What changed

- **Quarantine split (Class B policy):** export records whose validation problem is `duplicate record_id` now go to `quarantine.jsonl` as `{"record", "problems", "quarantine": {policy: "PERMANENT_UNTIL_IDENTITY_PROVEN", class: "B", reason, session_id, record_id, investigation_ref → STAGE_1 report, quarantined_at}}`. All other validation problems still go to `invalid.jsonl` (`{"record","problems"}` shape unchanged). No Class B record is ever deleted, merged, or auto-reclassified.
- **Atomic export:** every run builds ALL outputs in `data/corpus/.staging.<run_id>/` → full re-read + re-validation of the staged corpus/invalid/quarantine files → current live outputs are archived to `data/corpus/previous/<old-run-id>/` (slot named after the *replaced* run, read from its live `manifest.json`; collision suffixes `-2/-3`; `orphan-<ts>` fallback) → staged files promoted with `os.replace` (atomic on same filesystem) → checksums written → retention prunes `previous/` to the last 3 slots. Any failure removes the staging dir and leaves live outputs untouched.
- **Checksums:** `checksums.sha256` in `sha256sum` format (`<hex>  <name>`) covering `corpus.jsonl` (or `corpus-NNNN.jsonl` shards), `invalid.jsonl`, `quarantine.jsonl`, `stats.json`. `manifest.json` is deliberately excluded — it carries wall-clock `duration_sec`/scan time; exclusion is documented in the module docstring.
- **Deterministic builds:** `exported_at` pins both the manifest and every record's `provenance.exported_at`; when pinned, the manifest watermark gets a frozen note and `disk.scanned_at` becomes a frozen marker. The default deterministic `run_id` is derived from the pinned timestamp (`corpus-det-<ts>`, `:` → `-` so it is filesystem-safe), and since each record embeds `export_version: run_id`, two runs over unchanged data produce **byte-identical** data files and identical `checksums.sha256`.
- **CLI:** `python -m corpus.cli export [--limit N] [--deterministic] [--run-id ID]`. `--deterministic` pins `exported_at` to the DB high watermark (`sessions_updated_at`, fallback `llm_finished_at`) and derives the run_id; exits 2 if the watermark is empty.
- **Tests:** 7 new exporter tests (quarantine split, structural→invalid split, checksum match, determinism byte-identity, previous/ retention, retention pruning, failed-run leaves live untouched) and `test_identity` updated to the quarantine contract.

## 6. Files

| File | Change |
|---|---|
| `corpus/exporter.py` | rewritten: quarantine split, atomic staging→validate→archive→promote, checksums, deterministic mode, `previous/` retention (407 lines changed) |
| `corpus/cli.py` | `cmd_export(limit, deterministic, run_id)`, `--deterministic` / `--run-id` parsing, docstring |
| `tests/corpus/test_exporter.py` | +215 lines: 7 new tests |
| `tests/corpus/test_identity.py` | `test_record_ids_unique_in_valid_corpus` updated to quarantine contract |

## 7. Database changes

None. The exporter is strictly read-only (`SELECT` on `radio_program_sessions`, `radio_programs`, `llm_output`, `asr_output`, `crop_detection`). DB watermark before and after all live runs: `sessions_updated_at=2026-11-05T00:53:14, sessions_max_id=10880, llm_finished_at=2026-10-11T11:30:01, llm_max_id=15324` — unchanged by the exports.

## 8. Tests

- Runner: `tests/corpus/run_all.py` (stdlib, no pytest) — 90 tests total (83 baseline + 7 new).
- Local (Windows worktree): **90/90 passed in 1.8s** (re-run after rebase, same result).
- Production 53 (`dashboard/venv/bin/python3 tests/corpus/run_all.py`): **90/90 passed**.

## 9. Exact results

Live runs on 53 (server-local times, 2026-11-05):

| Run | Command | written | invalid | quarantined | duration | run_id | previous_export |
|---|---|---|---|---|---|---|---|
| A | `corpus.cli export` | 9731 | 0 | 1147 | 129.2 s | `corpus-20261105-015400` | `previous/corpus-20261104-085940` |
| D1 | `corpus.cli export --deterministic` | 9731 | 0 | 1147 | 125.8 s | `corpus-det-2026-11-05T00-53-14` | `previous/corpus-20261105-015400` |
| D2 | `corpus.cli export --deterministic` | 9731 | 0 | 1147 | 125.8 s | `corpus-det-2026-11-05T00-53-14` | `previous/corpus-det-2026-11-05T00-53-14` |

**Determinism proof (production data, 911 MB corpus + 77 MB quarantine):**

```
D1: 60d482c9ed30…  corpus.jsonl
D2: 60d482c9ed30…  corpus.jsonl   (identical)
D1: 7e0e6276be40…  quarantine.jsonl
D2: 7e0e6276be40…  quarantine.jsonl (identical)
diff D1/D2 checksums.sha256 → BYTE_IDENTICAL
```

**Key data-quality finding:** the pre-existing 09:01 export had `records_invalid=1147`. Under the Stage 3 contract, **all 1147** are identity collisions (`duplicate record_id`) — 100% of the former "invalid" batch is Class B, now permanently quarantined with policy metadata (`quarantine_policy=PERMANENT_UNTIL_IDENTITY_PROVEN`, class `B`, investigation_ref → `STAGE_1_CLASS_B_IDENTITY_REPORT.md`). Zero structural invalid records remain. `records_written` grew 9721 → 9731 (10 new sessions ingested between 2026-11-04 09:01 and 2026-11-05 01:54 by the running pipeline).

`previous/` retention after runs (3 slots, retention=3):

```
previous/corpus-20261104-085940/        run_id=corpus-20261104-085940  written=9721  (pre-existing export, fully preserved)
previous/corpus-20261105-015400/        run_id=corpus-20261105-015400  written=9731
previous/corpus-det-2026-11-05T00-53-14/ run_id=corpus-det-2026-11-05T00-53-14 written=9731
```

## 10. Production evidence (before / after on 53)

**Before** (probe at 01:47 local): `data/corpus/` held the 2026-11-04 09:01 export — `corpus.jsonl` 911 MB (9721 records), `invalid.jsonl` 77 MB (1147), `manifest.json` (`records_quarantined: null`, `deterministic: null`), no `checksums.sha256`, no `previous/`.

**After** (02:00 local): `data/corpus/` —

```
checksums.sha256      239 B
corpus.jsonl          911707256 B  (9731 records)
quarantine.jsonl      77525494 B   (1147 records, policy-annotated)
manifest.json         1987 B
metrics.prom          updated by cmd_export
stats.json            21052 B
previous/             3 slots (see §9)
total                 3.7G
```

**Production preservation (checked 02:03 local, after all runs):**

- Auto-refresh pipeline alive and committing: 53 head advanced to `5643ab307` (`auto: refresh site + subtitles (2026-11-05_02:00)`) — the cron that ran on schedule during and after the exports.
- Dashboard service alive: `uvicorn app:app --port 8990` uptime 2-08:06:35.
- Site generation active: `docs/index.html` regenerated within the last 60 minutes.
- No corpus job competed with SRT/ASR: the three exports are read-only SELECTs; nothing in the SRT pipeline was touched.

## 11. Commit SHA

- `7879d0fe4d0a92dc8f141bb38815d16dbef50130` — `feat(corpus): generate validated deterministic JSONL corpus` (4 files, +616/−51), committed in the worktree, rebased onto `66dcd0bbe` (53's auto-refresh head at that moment), re-tested 90/90 post-rebase.

## 12. Push verification

- Relay: local `git push -f HEAD:corpus-stage3-relay` over LAN → 53 relay script: `git checkout phase3-radio-rag-service` → `git merge --ff-only corpus-stage3-relay` (FF from `66dcd0bbe` to `7879d0fe4`) → 90/90 tests on 53 → `git push origin phase3-radio-rag-service` → `git ls-remote origin` → **VERIFIED_MATCH** (local == remote == `7879d0fe4…`) → auto-refresh checkout restored, temp branch deleted.
- GitLab `git.ai.ismc.ir`: **BLOCKED** (carried; no project mirrors this repo — see §15).

## 13. Deploy status

- Code live in the 53 production checkout (53's `phase3-radio-rag-service` contains `7879d0fe4`; auto-refresh has since stacked `5643ab307` on top, which includes it).
- New exporter contract exercised against the real production DB (3 full runs, ~10.9k sessions each, ~2 min each); live outputs now conform to the Stage 3 layout. No services restarted; nothing restarted was needed.

## 14. Output locations

- Live corpus: `/home/saber/saberprojects/iranseda-crawler-golang-/data/corpus/` (`corpus.jsonl`, `quarantine.jsonl`, `stats.json`, `manifest.json`, `checksums.sha256`, `metrics.prom`)
- Archived runs: `data/corpus/previous/<run-id>/` (retention 3)
- Class B investigation artifact (Stage 1, untouched): `data/corpus/class_b_investigation.jsonl`
- Reports: `reports/corpus/STAGE_3_FULL_EXPORT_REPORT.md` (this file, on `download-db`)
- Multi-GB data files are **not** committed to any repository (gitignored; only code + reports are versioned).

## 15. Remaining issues / blockers

1. **GitLab (carried, BLOCKED):** internal remote has no project mirroring this repo; destination decision needed (create project vs mirror). Per mission rule, stage verdict is PARTIAL, not PASS, until both remotes verify.
2. **1147 quarantined records** remain permanently quarantined until identity is proven (Class B policy). Their resolution is a human/data investigation (Stage 1 found 51 shared-archive groups needing adjudication); the corpus export will keep them out of the valid corpus and inside `quarantine.jsonl` automatically.
3. **`manifest.json` excluded from `checksums.sha256`** by design (wall-clock `duration_sec`, scan time); data-file integrity is fully covered.
4. **Doc drift (minor):** some Stage 1 docstrings in `corpus/identity.py` still refer to `invalid.jsonl` as the quarantine store; `quarantine.jsonl` is now the canonical location. Noted here rather than in a separate commit to avoid commit sprawl.
5. 53's auto-refresh cron commits to `phase3-radio-rag-service` every 30 minutes; every future push must fetch/rebase first (handled in this stage's procedure).

## 16. Rollback

- Code: `git revert 7879d0fe4` (or FF-restore branch to `66dcd0bbe`) on `phase3-radio-rag-service`; relay as usual. The old exporter remains fully functional on `66dcd0bbe`.
- Data: the pre-existing 2026-11-04 09:01 export is preserved byte-for-byte at `data/corpus/previous/corpus-20261104-085940/`; restoring it = move its files back to `data/corpus/`. No DB rollback needed (read-only).

## 17. Verdict

**PARTIAL** — All Stage 3 acceptance criteria met with real evidence (quarantine split, atomicity, checksums, determinism proven on 911 MB of production data, old export preserved, production pipeline undisturbed, GitHub pushed and verified). **PARTIAL rather than PASS solely because the internal GitLab push is blocked** (destination project undecided), carried from Stages 1–2 per the mission's dual-remote rule.
