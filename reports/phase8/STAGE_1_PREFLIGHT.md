# IRANSEDA — PHASE 8 · STAGE 0/1 PRE-FLIGHT REPORT

- **Report ID:** `reports/phase8/STAGE_1_PREFLIGHT.md`
- **Generated:** 2026-11-02 14:45 UTC (21:15 Iran time)
- **Checkpoint commit:** `7c531499e346968873d2ffa456c635296ae0bb61` — `chore(checkpoint): preserve pre-phase8 work` (branch `download-db`, 5 files added: `docs/OPERATIONAL_SLO.md`, `docs/prompts/013..016`)
- **Method:** all facts below were read from the live servers / live remotes / live DB at generation time. Nothing is guessed. No secrets are included.

---

## 1. Reference docs read (Stage 0.1)

| Doc | Status |
|---|---|
| `docs/prompts/013-phase8-master-execution-job.md` | read |
| `docs/prompts/014-phase8-master-autonomous-execution.md` | read |
| `docs/prompts/015-four-stage-recovery-github-delivery.md` | read |
| `docs/prompts/016-stage1-execution-decision-and-slo.md` | read |
| `docs/OPERATIONAL_SLO.md` | read (6 permanent SLOs + 100-point Operational Health Score) |

All 5 were **untracked** in the working tree before this stage; they are now preserved by the checkpoint commit above.

## 2. Local repository (Windows workstation)

- Path: `c:/Users/s.tabatabaei/Documents/saberprojects/iranseda`
- Branch before checkpoint: `download-db` @ `d669467c6` — in sync with `origin/download-db` (ahead 0 / behind 0)
- After checkpoint: `download-db` @ `7c531499e` (+1 commit, unpushed at report time)
- Remotes: **only** `origin` = `https://github.com/saber13812002/iranseda-crawler-golang-` (no GitLab remote configured locally)
- GitHub branches observed: `download-db` = `d669467c6` (repo HEAD), `main` = `21e3a344a`, `phase3-radio-rag-service` = `72fdfeef3`, `radio-rag-step1-pilot`
- Stashes: none. Modified tracked files: none before checkpoint.
- Untracked and **deliberately not committed**: ~55 scratch files `.tmp_p8_*.{sh,py,js}` (prior-session probe scripts; verified secret-free — they read secrets at runtime, contain no literal tokens) and `.tmp_phase8_review/` (review snapshot). Kept out of Git per hygiene rules.
- **Pre-existing hygiene risk (flagged, not changed in this stage):** `.env.production` and `web-viewer/.env` are tracked in the repo and contain a DB password. Also committed in an earlier session, not introduced here. Remediation is a Stage 1/2 candidate and will NOT be force-rewritten.

## 3. Server 53 (172.20.1.53, user `saber`) — the operational server

### 3.1 Git state
- Repo: `/home/saber/saberprojects/iranseda-crawler-golang-`
- Branch: **`phase3-radio-rag-service`** @ `72fdfeef3`, in sync with `origin` (ahead 0 / behind 0)
- Remote `origin` = `git@github.com:saber13812002/iranseda-crawler-golang-.git` (SSH), `credential.helper store` configured
- Server does **not** contain docs 013–016 or `OPERATIONAL_SLO.md` (only 001–012) → they arrive via the Stage 1 merge

### 3.2 Operational branch determination (evidence, not guess)
1. Server working tree is checked out on `phase3-radio-rag-service`.
2. `crontab -l` runs only two jobs, both pointing at that repo:
   - `15,45 * * * * …/scripts/run_pipeline.sh`
   - `*/30 * * * * …/scripts/refresh_site.sh`
3. `scripts/refresh_site.sh` computes `BRANCH=$(git rev-parse --abbrev-ref HEAD)` and pushes that branch; live auto-commits (`auto: refresh site + subtitles`) are landing on `phase3-radio-rag-service` (last: `72fdfeef3` 2026-11-02 14:00 UTC).
4. `docs/index.html` commit cadence on that branch: 48 commits/day for the last 7 full days (2026-10-27 … 2026-11-01), 29 so far on 11-02 → matches the `*/30` cron.
5. `.env.production` says `GITHUB_BRANCH=main`, but no cron job reads it for the publish path; the branch actually served by cron is `phase3-radio-rag-service`. **Operational branch = `phase3-radio-rag-service`.**

### 3.3 Pipeline & SRT production (RUNNING)
- `run_pipeline.sh` at :15/:45; observed recent runs: `new_srt = 17, 7, 6, 7, 7…`; downloads ≈10/run; run duration 4200–4900 s → occasional `SKIP (previous run still active)`.
- Whisper: Docker containers `iranseda-whisper-worker` + `iranseda-whisper-api`, both **Up 5 days**; worker log shows live throughput:
  `14:36:41 session 6105 DONE · 14:37:06 session 6106 DONE · 14:37:08 session 6107 started`.
- Backfill: **PAUSED** (kill switch) — `shards: target=0 running=0 (reason: PAUSED)`.

### 3.4 GitHub Pages — STALE (root cause identified)
- `verify_pages()` in `refresh_site.sh`: `pages-verify: STALE live=da70a460 pushed=791d97d2 last-modified=Thu, 29 Oct 2026`.
- Blob hash comparison on GitHub:
  - `origin/main:docs/index.html` = `36ff6651…`
  - `origin/download-db:docs/index.html` = **`da70a460…`** ← equals the live page hash
  - `origin/phase3-radio-rag-service:docs/index.html` = `791d97d2…`
- **Conclusion (proven, not guessed): GitHub Pages source branch = `download-db`**, while cron publishes to `phase3-radio-rag-service`. The public site has been frozen since `download-db` last changed `docs/index.html` (2026-10-22) / last commit on that branch (2026-10-29).
- Pages API (`/pages/builds`) returns 404 without a valid GitHub token → branch setting itself is a repo-settings change (GitHub UI/API `pages` endpoint); recorded as a Stage 2 action item. **Fix = point Pages at `phase3-radio-rag-service` (or repoint cron to the Pages branch) — decision deferred to Stage 2 with the user-visible SLO in mind.**

### 3.5 Reporter — DISABLED
- `dashboard/reporter.py`: gated by `IRANSEDA_REPORTER_ENABLED` (not set); publisher is a **stub** (`client_configured=False`); worker log: `reporter worker started (enabled=False, client_configured=False)`; last log line 2026-11-01.
- No `reports/` output dir on the server. → Stage 2 must find/enable a real publisher (per mission: real reports, no fake cache).

### 3.6 Database (Docker MySQL, `iranseda-mysql`, host port **3308**)
Queue baseline at **2026-11-02 14:41 UTC** (read-only queries, table `radio_program_sessions`):

| Metric | Value |
|---|---|
| Total sessions | **10 843** (min id 3, max id 10 845) |
| Distinct programs | 59 |
| Distinct links | 9 696 |
| `is_subtitled=1` (completed) | **9 117** (4 477 with `srt_filename`) |
| `is_downloaded=0` (true pending download) | **499** |
| `is_downloaded=1 & is_subtitled=0` (transcribe queue) | **1 227** |
| `status` column values | subtitled 9 117 · pending_download 1 672 · failed_permanent 49 · pending_transcribe 4 · transcribing 1 |
| `last_error` rows | 1 222 → x1 173 `media not on disk; re-download required (epgarchivePart endpoint is JS-gated)`, x49 ffmpeg `Invalid data found` (= `failed_permanent`) |
| Oldest session | 2024-11-08 |
| Oldest **not-subtitled** | **2025-05-03** (~197 days) |
| Not-subtitled older than 24 h | **1 723** |

**Data-quality finding:** the `status` column is inconsistent with the flags — `status=pending_download` is 1 672 but only 499 have `is_downloaded=0`; the delta 1 173 equals the "media not on disk" error count (stale status on rows that are really blocked re-downloads). Conversely the transcribe queue per flags is 1 227 while `status` shows only 4 `pending_transcribe` + 1 `transcribing`. Stage 3 must use the **flags** (`is_downloaded`/`is_subtitled`) as ground truth and report `status`-column lag as a defect. The 1 173 JS-gated rows must **not** be mixed into the processable queue.

### 3.7 Rates (from DB)
| Window | Arrivals (`created_at`) | Completions (`updated_at`, subtitled) |
|---|---|---|
| last 1 d | 15 | 166 |
| last 7 d | 744 (avg ≈106/d) | 3 501 (avg ≈500/d) |
| last 14 d | 4 960 (avg ≈354/d, incl. backfill burst) | 4 960 |

SRT-by-day (last 14 days, `is_subtitled=1`): 4, 11, 4, 11, 209, 333, 272, 224, 240, 317, 362, 626, 522, 215, **92 (today, partial to 14:41 UTC)**.

**Drain estimate (processable backlog only):** 1 726 processable (499 download + 1 227 transcribe) vs service ≈500/d, arrival ≈106/d (7-day) → estimated drain ≈ (1 726)/(500−106) ≈ **4.4 days** at current capacity; the 1 173 JS-gated + 49 permanent failures are reported **separately** and excluded.

### 3.8 Capacity
- CPU: 40 cores · RAM: 117 GiB total, 76 GiB available
- GPU: **2× NVIDIA H100 80 GB**, both at 100 % utilization (76.5 / 65.5 GiB used) — heavily loaded; whisper transcribe runs at ~30 min audio → 20–50 s (very high throughput, likely other tenants co-located)
- Whisper worker: single container, sequential session processing in the observed log
- Bottleneck note: download step limited by cron batch (10/run); GPU is shared and saturated → concurrency increases must be controlled (Stage 3)

## 4. Server 52 (172.20.1.52) — DOWN (BLOCKS STAGE 3 MONITORING)

- From Windows: SSH times out.
- From server 53: ping 100 % loss, `No route to host`, ARP INCOMPLETE; ports 9090 / 3001 / 4000 all return `000`.
- Hosts: Prometheus, Grafana, observability repo, LLM endpoint (`172.20.1.52:4000`).
- **Impact:** Grafana dashboard/alerts work (Stage 3.5) and any LLM-dependent verification = **BLOCKED** until 52 is back up. Declared per mission rule; not masked by GitHub-side successes.

## 5. GitLab (`git.ai.ismc.ir` → 172.30.0.133)

- DNS resolves (non-authoritative); HTTPS reachable from server 53 (sign-in page 200).
- SSH port 22 from 53 **times out**; from Windows: `Permission denied (publickey,password)` (reachable, no registered key).
- Stored HTTPS credential on 53 (`~/.git-credentials`, user `oauth2`, host `git.ai.ismc.ir`) is **expired/invalid**: authenticated API `GET /user` → 401; the 200 responses came from public endpoints.
- Public project listing (15 projects across groups `ai-tools/common/devops/etc/rag`) contains **no iranseda project** → the internal repo path is unknown and will NOT be guessed.
- Existing deploy key `gitlab52_deploy` (comment `ai-dump-deploy-52`) points to the old host `gitlab52` = 172.20.1.52:2222 (the DOWN server), not to `git.ai.ismc.ir`.
- **Status: GitLab push = BLOCKED** (no valid credential + unknown project path + SSH blocked). GitHub push success will **not** mask this; mission outcome for the GitLab leg is reported PARTIAL/BLOCKED in the final report until a valid token/project path is provided.

## 6. Branch divergence (for Stage 1 reconciliation)

- `merge-base(download-db, phase3-radio-rag-service)` = `133945f04`
- `download-db` is 4 commits ahead of the base:
  - `a437977a5` local changes (+601 `logic.py`, +364 `site/programs.json`)
  - `db1f0d625` dedup canonical (ch, e) key + regression tests
  - `cd8b23c7a` UNIQUE(program_id, link) migration
  - `d669467c6` grafana 30-min panels
- `phase3-radio-rag-service` is 572 commits ahead of the base (572 auto-refresh + its own dedup fix `a317a0507` and its own grafana panels `28ecedd73`/`00a1b5503`)
- `git cherry` confirms **all 4 download-db commits are NOT applied** on phase3 (`+` all four) → a real merge is required, not a fast-forward; `dashboard/grafana/iranseda-pipeline.json` differs on both sides (1 634 ins / 1 689 del) → conflict expected there, plus `logic.py`/dedup overlap.

## 7. Health snapshot (per `OPERATIONAL_SLO.md` categories)

| Area | State |
|---|---|
| Pipeline (30-min cron) | RUNNING (with occasional skip when a run >30 min overlaps next slot) |
| SRT production | RUNNING (92 today partial; ~500/d 7-day) |
| Commit/publish to GitHub | RUNNING (phase3 branch) |
| GitHub Pages public site | **STALE since 2026-10-29** (Pages source ≠ publish branch) |
| Reporter | **DISABLED** (stub + env flag off) |
| Grafana / alerts (server 52) | **BLOCKED** (52 down) |
| Queue | 1 726 processable + 1 173 JS-gated + 49 permanent; 1 723 older than 24 h → drain required |
| Backfill | PAUSED (kill switch) |

## 8. Decisions & next actions

1. **Stage 1:** merge `download-db` → `phase3-radio-rag-service` (preserve both sides; run tests; record SHA), then push GitHub; GitLab attempt → declare BLOCKED with evidence.
2. **Stage 2:** repoint GitHub Pages to `phase3-radio-rag-service` (verified by live hash == pushed blob hash after next refresh), enable a real reporter, observe one full E2E cycle.
3. **Stage 3:** use flag-based queue truth; controlled drain; Grafana remains BLOCKED pending 52 recovery.
4. **Stage 4:** 24 h monitor + hourly GitHub status reports with hash-verified delivery.
5. **Not done yet (explicit):** GitLab push (BLOCKED), Pages repoint (Stage 2), reporter enablement (Stage 2), Grafana (BLOCKED).

*No credentials, tokens, or secrets are contained in this file.*
