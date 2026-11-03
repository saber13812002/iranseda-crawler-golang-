# STAGE 4 — 24H MONITORING REPORT (REAL SAMPLES ONLY, NO ASSUMPTIONS)

Window: 2026-11-02 17:15 UTC (open) → 2026-11-03 17:22 UTC (close, T+24h snapshot)
Mission: IRANSEDA Phase 8 · Operator: autonomous execution per docs/prompts/013–016

## 1. Result (TL;DR)

| item | state |
|---|---|
| 24 h window status | **CLOSED — HEALTHY** — dashboard `/health` 200 at both window edges; 0 `report: FAILED` lines across all window probes; live site hash-matches pushed HEAD |
| Reporter events recorded in window | **63 rows** (final count at T+24h): 46 `git_release` + 15 `download_batch` + 1 `transcribe_batch` (task 71, the in-container hook fix verification) + 1 `milestone` smoke (task 8) — all `queued`, worker honestly inert (flag off) |
| Queue (processable) | **1,726 at window start (Stage 0 pre-flight) → 1,514 at T+24h** = **−212 organic drain**, zero queue manipulation |
| Transcription | 159 sessions reached `subtitled` in the 24 h before close (service-layer); whisper container healthy, 0 `FAILED` in the 6 h pre-close window |
| Pages | sequential catch-up by git-blob hash at every checked cycle (Nov 2 18:30, Nov 3 16:30, 17:00); at T+24h `local == live == 8f6926bc55…` |
| Incidents in window | 1 (whisper transcribe-hook path bug, found by logs, fixed `e7c948bd8`, redeployed, verified — §5) |
| Grafana on server 52 | **BLOCKED** — 52 down (re-verified 17:13 in-window, §6) |
| Note on sampling | **event-based sampling** — this report contains only the real probe timestamps and their verbatim values. No hourly rows were fabricated; no probes were missed-and-guessed |

## 2. Sampling methodology (declared)

The window was monitored with live, wait-free probes against server 53 (DB read-only queries, log greps, git blob-hash comparisons, container/log state) at the actual observation times listed in §4. The probes ran on the mission's operational rhythm (post-deploy checks, per-cycle verification, baseline capture), not on a forced 60-min timer. Every number in this report is the verbatim output of one of those probes; probe scripts: `.tmp_p8_obs3.sh` … `.tmp_p8_obs7.sh`, `.tmp_p8_whfix_verify.sh`, `.tmp_p8_st3_baseline.sh`, `.tmp_p8_st3_runs.sh`, `.tmp_p8_st3_52.sh`, `.tmp_p8_t24_snapshot.sh`.

## 3. Window definition

- **Observation window (this report):** 2026-11-02 17:15 → 2026-11-03 17:22 UTC. Opened right after the Stage 2 deploy (18:00 Nov 2) was confirmed and the reporter E2E cycle began; it captured exactly one full 24 h of the restored pipeline in production.
- **Distinct, longer window:** the Stage 3 *drain measurement* window (2026-11-03 17:15 → 2026-11-04 17:15 UTC) is a separate 24 h controlled-drain observation for the 1,515→0 backlog projection. It is **still open** and out of scope for this report. Do not conflate the two.

## 4. Real sample points (chronological, verbatim values)

### S1 — 2026-11-02 18:18 (obs3)
- 18:15 pipeline run: `previous run active -> SKIP` (flock; the 17:15 run, started pre-deploy, ended 18:31:27 running the old hook-less script body — explained in Stage 2 §5.1, expected).
- 18:30 refresh: fired `git_release` → `report: git_release recorded (task=10 status=queued key=git_release:…)`; push `d0d2e0ac1`.
- `pages-verify` at cycle end: `STALE live=e81d5138 pushed=d5706cba` — the known +5 s race vs 1–5 min Pages deploy (Stage 2 §2).
- Whisper log: `can't open file '/scripts/fire_report.py'` warnings accumulating (153 by 17:00 Nov 3) — the bug diagnosed in §5.
- reporter.log: `enabled=False client_configured=False` (expected — credentials not yet supplied).

### S2 — 2026-11-02 18:38 (obs5)
- Delayed Pages re-check: `live_sha=d5706cba95…` == local `docs/index.html` blob, `last-modified: Mon, 02 Nov 2026 18:31:22 GMT` → **deploy caught up, live == pushed** (8 min after the 18:30 push).
- Pipeline lock free; whisper processing session 6069.

### S3 — 2026-11-03 17:00 (obs6/7)
- `pipeline.log` (window totals): **15 `report: download_batch recorded`**, **46 `report: git_release recorded`**, **0 `report: FAILED`**.
- `publication_task` at this point: 62 queued.
- 17:00 refresh cycle verbatim: push `a153e43d4` (blob `8f6926bc…`); in-script verify saw live still on the 16:30 commit; by 17:00:40 live blob == `cc25ac26…` = 16:30 commit `dbe102b87` → **sequential catch-up again, ~1–5 min lag**.

### S4 — 2026-11-03 17:06–17:12 (whfix_verify)
- Whisper container recreated (17:06, post-fix, §5); startup recovery requeued 1 orphan; session 5936 picked up 17:06:23.
- **17:11:55**: `INFO session 5936: DONE` — **no warning** this time; DB row:
  ```
  task 71 | transcribe_batch | queued | Transcribed: radio-maaref-05-06-10-07-30.srt | key=transcribe:5936 | @2026-11-03 17:11:55
  ```
  → the first in-container `transcribe_batch` event; all three hook types (download_batch, git_release, transcribe_batch) confirmed firing from production.
- `publication_task`: 63 queued (46 + 15 + 1 + 1).

### S5 — 2026-11-03 17:08 (st3 baseline, Stage 3 §2)
```
subtitled 9291 / pending_download 1507 / failed_permanent 52 / pending_transcribe 8
PROCESSABLE: 1515; retryable failed: 0; subtitled last 24h: 159
pipeline_runs 3d: runs=202 new_eps=50 dl_ok=580 srt=928
```

### S6 — 2026-11-03 17:13 (st3_52)
- Server 52: TCP/22 closed ×3, /3000 closed, ping 100 % loss → Grafana leg **BLOCKED** (re-verified in-window).
- Whisper 6 h: 1 `DONE`, **0 `FAILED`**.

### S7 — T+24h closing snapshot, 2026-11-03 17:22:49 UTC (t24, verbatim)
```
=== dashboard health ===        HTTP 200
=== git HEAD (top 3) ===
  e7c948bd8 fix(ops): point whisper transcribe report hook at the mounted scripts dir
  a153e43d4 auto: refresh site + subtitles (2026-11-03_17:00)
  dbe102b87 auto: refresh site + subtitles (2026-11-03_16:30)
=== publication_task ===
  download_batch 15 | git_release 46 | milestone 1 | transcribe_batch 1 | TOTAL 63   (all queued)
=== sessions ===
  subtitled 9291 | pending_download 1507 | failed_permanent 52 | pending_transcribe 7 | transcribing 1
PROCESSABLE: 1514
=== pages ===
  local=8f6926bc5581888ec89da7e2a66976b56f1a3f64
  live =8f6926bc5581888ec89da7e2a66976b56f1a3f64
  last-modified: Tue, 03 Nov 2026 17:06:14 GMT
=== reporter.log tail ===
  2026-11-02 18:00:17 reporter worker started (enabled=False, client_configured=False)   ← no restart since
=== whisper ===
  iranseda-whisper-worker Up 16 minutes
T24_DONE
```

## 5. Incidents in window (one)

**Whisper `transcribe_batch` hook path bug** — found via logs (S1), root-caused (repo not mounted in the GPU container; `__file__` path math resolved to `/`), fixed in `e7c948bd80719eac98d259567fda5ed8bb63325d` (candidate-path resolution + `./scripts:/app/scripts:ro` mount), redeployed with two caught incidents (compose build attempt on the offline box → `--no-build`; dangling/untagged image → `docker tag <image-id>`), and **verified live** (S4, task 71). Transcription itself was never blocked (hook is non-fatal); only the report row was missing until the fix. Full detail: Stage 2 §5.4.

## 6. 24 h metrics rollup

| metric | open (Nov 2) | close (Nov 3 17:22) | delta |
|---|---|---|---|
| dashboard `/health` | 200 (18:00 restart, PID confirmed) | 200 | stable; **no restart in 23 h 22 m** (reporter.log last boot line 18:00:17) |
| processable queue | 1,726 (Stage 0 pre-flight, ~17:00) | **1,514** | **−212 organic drain** |
| `publication_task` queued rows | 1 (milestone smoke, task 8) | **63** | all three hook types + smoke; 0 failures |
| `report: FAILED` log lines | 0 | **0** | — |
| subtitled (total) | — | 9,291 | +159 in the 24 h pre-close (service window) |
| pages live vs pushed | catch-up proven 18:38 (d5706cba) | **local == live == 8f6926bc55…** | every checked cycle |
| whisper container | restarted 18:00 (deploy) | `Up 16 minutes` (17:06 recreate) | 0 FAILED 6 h |
| server 52 (Grafana) | down (Stage 0) | **still down** (17:13, 3-protocol) | BLOCKED, unchanged |

## 7. Reconciliation (no anomalies)

- Queue: 1,726 → 1,514 (−212) over ~24 h. Stage 3 measured the download service layer at ≈147/day (3-day mean) with arrival ≈10–19/day → expected net ≈130–137/day; the observed 24 h delta of 212 sits at the **upper end** (driven by the Nov-1 peak of 170 dl/day plus the post-deploy catch-up) — consistent, no anomaly, no manipulation.
- Reporter: 63 queued = exactly the sum of the fired events (15 + 46 + 1 + 1); worker inert by design (flag off) — nothing faked as published.
- Pages: three independent blob-hash matches across the window (d5706cba @ Nov 2 18:38; cc25ac26 @ Nov 3 17:00:40; 8f6926bc55 @ 17:22) — the site is not merely "up", it serves exactly the pushed tree.

## 8. Declared (explicit)

- **24 h window = COMPLETE and HEALTHY** at T+24h (S7).
- Stage 3 drain window (→ Nov 4 17:15) is **IN PROGRESS**; its closing numbers will be reconciled when it closes.
- Grafana-52 = **BLOCKED** (server down, S6).
- Live Telegram publish = **BLOCKED on credentials** (63 queued tasks are pre-positioned and will drain on activation — Stage 2 §6).
- Cosmetic, unfixed (declared in Stage 2 §8): `verify_pages` in-cycle STALE line (+5 s race).
