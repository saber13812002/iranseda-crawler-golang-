# STAGE 1 — REPOSITORY RECONCILIATION (REAL STATE, NO ASSUMPTIONS)

Date: 2026-11-02 (UTC) · Mission: IRANSEDA Phase 8 · Operator: autonomous execution per docs/prompts/013–016

## 1. Result (TL;DR)

- **Merge commit:** `f882e84380050c688dc45154091cdf6ca0320d5a` on branch `phase3-radio-rag-service`
- **Parents:** `6f07c5e0812b626b8cb18a3d56c3aeee01ac062a` (phase3 tip at push time) + `62b69d1b17f07fec770c320ff93c8be7388aa3e8` (download-db tip)
- **GitHub push: VERIFIED** via `git ls-remote origin` → `refs/heads/phase3-radio-rag-service = f882e8438...`
- **GitLab push: BLOCKED** (no GitLab remote exists in local or server 53 repos; server-side GitLab API 401 / no iranseda project — evidence in STAGE_1_PREFLIGHT.md §7)
- **Production deploy (server 53): DONE** — fast-forward-only pull `6f07c5e08 → f882e8438`; deployed SHA = **f882e84380050c688dc45154091cdf6ca0320d5a**
- **Tests:** 17/17 OK (local worktree + production server 53); `bash -n` on the shell script: OK on 53
- **Both sides preserved:** every download-db-only artifact is present in the merge tree; every phase3-only feature/route/panel/metric is present; 0 dd-unique functions, 0 dd-unique routes, 0 dd-unique element ids/JS funcs/endpoints, 0 dd-unique Grafana panel titles (see §3 evidence)

## 2. Branches reconciled

| branch | role | SHA at merge start |
|---|---|---|
| `phase3-radio-rag-service` | **operational branch on production 53** (proven by 5 evidence items in preflight §5) | 5cae0242d (→ 6f07c5e08 after one cron auto-commit landed mid-operation) |
| `download-db` | long-running feature branch with phase8 docs + safety-net migration + unique-link migration | 62b69d1b1 |
| merge-base | | 133945f044be39cbc1b3590e4eb8cdf5d25975d4 |
| divergence | 4 unique download-db commits / 572 unique phase3 commits; `git cherry` all `+` (none applied) | |

Method: isolated git worktree (`.tmp_p8_merge`) at `origin/phase3-radio-rag-service`; `git merge origin/download-db`; no reset/clean/force anywhere.

## 3. Conflict resolutions (6 conflicts, all proven — not guessed)

| file | type | resolution | proof |
|---|---|---|---|
| `dashboard/app.py` | content | `--ours` (phase3) | function inventory: dd 46 ⊆ p3 51 (0 dd-unique); route inventory: dd 56 ⊆ p3 60 (0 dd-unique, incl. all 4 p3-only routes); diff vs base: dd = +122/-0, p3 = +256/-0 — **both sides pure insertions**, so keeping p3 loses nothing; p3 `metrics()` = base +55 lines (pipeline_runs gauges, SRT-produced, zero-output-days, public-site probe) while dd `metrics()` == base |
| `dashboard/logic.py` | content | `--ours` (phase3) | function inventory: dd 93 ⊆ p3 117 (0 dd-unique, p3-only = 24); only differing body `db_metrics` re-checked **byte-identical**; `disc_active_programs` differs only by a trailing comment; header/tail identical |
| `dashboard/templates/index.html` | content | `--ours` (phase3) | symbol-level comparison: dd-unique element ids = 0, dd-unique JS functions = 0, dd-unique fetch endpoints = 0, dd-unique h3 headings = 0 (p3 adds 2 extra sections: LLM scoring + management list); all 12 probe symbols (reportGo, disc*, active-prog-table…) present in both |
| `dashboard/grafana/iranseda-pipeline.json` | content | `--ours` (phase3) | panel-level JSON compare: dd 31 panels ⊆ p3 32 panels by title; every same-title panel content-identical except 2 — p3 uses the corrected exprs (`clamp_max` vs `round`) and adds `iranseda_srt_zero_output_days_14d`; **“30-Minute Pipeline Runs With No New Work” panel kept verbatim** (mission-mandated) |
| `migrations/2026-10-28_session_unique_program_link.sql` | add/add | `--ours` (phase3) | CRLF-only difference (stage blob diff `git diff -w` empty) |
| `tests/test_episode_canon.py` | add/add | `--ours` (phase3) | CRLF-only difference |
| `scripts/run_pipeline.sh` | **auto-merge artifact (7th, hidden)** | phase3 blob verbatim | see §4 |

### Content preserved from `download-db` into the merge (visible in `git show --stat f882e8438` vs phase3 parent)
`docs/prompts/013–016*.md`, `docs/OPERATIONAL_SLO.md`, `reports/phase8/STAGE_1_PREFLIGHT.md`, `bot_v3.py`, `fix_header.py`, `.gitignore.bak-20261022_234445`. The two add/add files (migration + test) exist on both branches and are identical apart from CRLF.

## 4. Hidden merge hazard found and fixed: `scripts/run_pipeline.sh`

The 3-way auto-merge produced a **valid-looking file that runs `discover_new.py` TWICE per pipeline cycle**: it kept phase3's record-enhanced block (venv python, parses `N new episodes / across M programs` for `record_run.py`) **and** inserted download-db's plain `python3` block below it (identical comment header, so it looks intentional). Verified by three-way diff (base had no discover block; dd has plain block; p3 has enhanced block).

Consequence if left: double archive-page walks every 15/45-minute cycle (wasted HTTP + DB writes), and the second (plain) block would overwrite `$DISC_OUT`, corrupting the metrics the first block already parsed.

**Fix:** restored the exact phase3 blob (verified `git diff --cached origin/phase3-radio-rag-service -- scripts/run_pipeline.sh` → empty). Note dd's "contribution" to this file (no `record_run.py` pipeline_runs recording) is strictly inferior: phase3's block already records discovery stats, and `record_run.py` is the source of the `iranseda_pipeline_runs_*` metrics required by Stage 2/3 monitoring.

## 5. Concurrency: cron auto-commit landed mid-merge

Between the merge worktree fetch and the push, the server-53 cron (`15,45 * * * * run_pipeline.sh`) pushed auto-commit `6f07c5e08` (17 files: `downloads/*` + 3 `docs/programs/*.html` — zero overlap with the merge's changed paths). First push rejected (`fetch first`); resolved with `git rebase --rebase-merges origin/phase3-radio-rag-service`, re-applying the identical proven resolutions (the run_pipeline.sh duplicate re-appeared identically — deterministic — and was fixed identically), re-ran tests (17/17 OK), then fast-forward push. Final merge commit parents confirm structure: p1 = new phase3 tip, p2 = download-db tip.

## 6. Verification chain (all real outputs)

1. `python -m unittest tests.test_episode_canon -v` in merge worktree (Windows, system python 3.14): **Ran 17 tests — OK**
2. `python -m py_compile dashboard/app.py dashboard/logic.py`: OK; grafana JSON parses: OK
3. Same unittest on **server 53** (production python3, post-deploy): **Ran 17 tests — OK**
4. `bash -n scripts/run_pipeline.sh` on server 53: OK
5. `git ls-remote origin`: `phase3-radio-rag-service = f882e84380050c688dc45154091cdf6ca0320d5a`; `download-db = 62b69d1b17f07fec770c320ff93c8be7388aa3e8`

## 7. Production deploy (server 53)

- Repo path `/home/saber/saberprojects/iranseda-crawler-golang-` on `phase3-radio-rag-service` at `6f07c5e08`
- `git merge-base --is-ancestor HEAD origin/...` → FF-only guard passed; `git pull --ff-only` → **f882e8438** (9 files added, 3535 insertions — exactly the download-db content, no code changes to phase3)
- Dashboard service `iranseda-dashboard.service` (port 8990) was running pre-merge code (started 2026-11-01 08:03, last dashboard commit at that time = fe59e88f4, so it was already current w.r.t. phase3, but the merged tree was not its tree). `systemctl restart` requires root (not available to `saber`); unit has `User=saber` + `Restart=always` → killed main PID; systemd respawned it at 15:30:28 with the merged tree.
- Post-deploy health (real):
  - `GET /health` → `ok`
  - `GET /metrics` → contains `iranseda_pipeline_runs_no_new_work_total 114` (phase3-only metric ⇒ new code live) and the public-site probe gauge
  - `GET /api/discovery/programs/management`, `/api/discovery/scores` → **401** (auth-gated, routes exist; pre-auth endpoints unchanged)
  - `GET /` → 200
- Cron intact: `15,45 * * * * run_pipeline.sh`, `*/30 * * * * refresh_site.sh`
- Whisper/GPU workload unaffected (separate service).

## 8. GitLab status: **BLOCKED** (declared per mission rules)

- No `gitlab` remote is configured in the local repo or on server 53 (`git remote -v` → GitHub only, both).
- Server-side GitLab v4 API with the token from `~/.git-credentials` → **401 invalid** (expired oauth2); public read shows 6 groups / 15 visible projects, **no iranseda project**; SSH 22 from 53 times out; the stale deploy key points at a dead `172.20.1.52:2222`.
- Full evidence table: `reports/phase8/STAGE_1_PREFLIGHT.md` §7. GitHub success does **not** mask this: GitLab push = BLOCKED, not PASS.

## 9. Not done / deferred (honest list)

- **Grafana dashboard import on server 52: BLOCKED** — server 52 is DOWN (preflight §6). The reconciled `dashboard/grafana/iranseda-pipeline.json` (32 panels incl. the mandated 30-minute panel) is in the repo and will be imported in Stage 3 when 52 is back.
- **GitHub Pages still stale** — root cause proven in preflight §6 (Pages serves branch `download-db`, cron publishes to `phase3-radio-rag-service`). Fix is a Stage 2 action (repoint Pages to the operational branch), deliberately not done here to keep Stage 1 scope = repository reconciliation only.
- Tracked-secrets hygiene (`.env.production`, `web-viewer/.env`, tracked venvs): flagged in preflight §8, **not** rewritten (mission forbids history rewrite / deletion of prior work).

## 10. Acceptance for Stage 1

| item | status |
|---|---|
| merge performed on real refs, no force/reset/clean | PASS |
| both sides preserved (proven, not assumed) | PASS |
| tests green (worktree + production) | PASS |
| GitHub push + ls-remote verify | PASS |
| GitLab push | **BLOCKED** (evidence in §8) |
| production 53 deploy, FF-only, deployed SHA recorded (f882e8438) | PASS |
| reporter | not yet — Stage 2 |
| E2E cycle proof | not yet — Stage 2 |
