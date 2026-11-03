# STAGE 3 — SRT QUEUE DRAIN & MONITORING (REAL STATE, NO ASSUMPTIONS)

Date: 2026-11-03 17:08–17:15 (UTC) · Mission: IRANSEDA Phase 8 · Operator: autonomous execution per docs/prompts/013–016

## 1. Result (TL;DR)

| item | state |
|---|---|
| SRT queue baseline (real, live DB) | **1,515 processable** (1,507 `pending_download` + 8 `pending_transcribe`); 9,291 `subtitled`; 52 `failed_permanent`; **0 retryable failed** |
| Queue trend | **already draining** — 1,726 at pre-flight → **1,515** now (−211 in ~23 h, no operator action beyond Stage 2 recovery) |
| Bottleneck (proven) | **download**, not transcription — whisper idles waiting for media (only 8 `pending_transcribe` while 1,507 wait on `pending_download`) |
| Service / arrival / drain math | measured, §3 |
| 24 h controlled drain observation | **IN PROGRESS** — window opens 2026-11-03 17:15 UTC, closes 2026-11-04 17:15 UTC; sampled hourly by the Stage 4 independent monitor and reported in `24H_MONITORING_REPORT.md` (this report carries the baseline + projection; the live 24 h delta lands there) |
| Grafana on server 52 | **BLOCKED — server 52 is down** (re-verified 2026-11-03 17:13, §4). Prometheus endpoint on 53 + dashboard `/metrics` remain the live monitoring surface. |
| Commit | report on `download-db` (SHA below, `ls-remote` verified) |

No secrets. Every number below is a live query/log from server 53 captured at the timestamp shown; the two probe scripts and their verbatim outputs are quoted.

## 2. Baseline (captured 2026-11-03 17:08 UTC, live DB via dashboard venv)

### 2.1 Session status counts (verbatim)
```
== session status counts ==
  subtitled              9291
  pending_download       1507
  failed_permanent         52
  pending_transcribe        8
PROCESSABLE (pending_download+pending_transcribe): 1515
retryable failed (attempts<3): 0
subtitled last 24h (service): 159
created last 7d (arrival): 747
created range: oldest=2024-11-08 19:39:19 newest=2026-11-03 12:45:55
```

### 2.2 `pipeline_runs` (real column names `discovered_sessions`/`download_success`/`new_srt_count`)
```
pipeline_runs last 3d: runs=202 new_eps=50 dl_ok=580 srt=928 t0=2026-10-31 17:15:01 t1=2026-11-03 17:00:11
per-day:
  2026-11-03 (partial→17:00)  runs=46  new_eps=10  dl=110  srt=205
  2026-11-02                  runs=64  new_eps=15  dl=160  srt=260
  2026-11-01                  runs=65  new_eps=19  dl=170  srt=378
  2026-10-31                  runs=96  new_eps=577 dl=480 srt=666   <- initial backfill day
  2026-10-30                  runs=96  new_eps=14  dl=480 srt=849   <- initial backfill
  2026-10-29                  runs=96  new_eps=16  dl=480 srt=423   <- initial backfill
site pushes (push_ok=1) last 24h: 48
```

## 3. Arrival / service / drain-time math (from the measured numbers, not assumed)

**Arrival.** Two different signals, reported honestly:
- `created last 7d = 747` → 106.7/day *looks* high, but it is inflated by the **Oct-31 initial backfill** (`new_eps=577` that single day). Excluding the backfill, the steady-state discovery rate is the per-day `new_eps` for the post-backfill days: **10, 15, 19/day** (Nov 3 partial, Nov 2, Nov 1) → **≈ 10–19 new episodes/day** steady state.
- I use **≈15/day** as the planning arrival rate and show the backfill-inflated 106.7/day only as the worst-case bound.

**Service (two independent layers, measured):**
- **Download layer (the bottleneck):** `dl_ok` = 110 / 160 / 170 per day (Nov 3 partial, Nov 2, Nov 1) → **≈ 147/day** (3-day mean). Capped by `MAX_DOWNLOADS=25` per pipeline run × (15,45) cron, but in practice limited by pending-media availability, not the cap.
- **Transcription layer:** `new_srt` = 205 / 260 / 378 per day (same three days) → **≈ 281/day**; the final-status `subtitled last 24h = 159` is lower only because `updated_at`-windowed finalization lags SRT production by the crop/LLM steps. Whisper is **not** the constraint (see §2.1: 8 vs 1,507).

**Drain-time (queue = 1,515):**
- Planning (steady-state): net drain = service − arrival = 147 − 15 ≈ **132/day** → 1,515 / 132 ≈ **11.5 days** → ETA ≈ **2026-11-14/15 UTC**.
- Optimistic bound (if download throughput holds the Nov-1 peak of 170/day and arrivals stay at the low end 10/day): net 160/day → ≈ 9.5 days → ETA ≈ 2026-11-13.
- Pessimistic bound (if arrivals spike to the backfill-inflated 106.7/day): net = 147 − 106.7 ≈ 40/day → ≈ 38 days → ETA ≈ 2026-12-11. **This bound is not expected** — 106.7/day was a one-time backfill artifact, not a recurring rate.
- **Headline projection: ≈ 10–12 days to clear the 1,515-episode backlog**, dominated by the download layer; the transcription and site layers have headroom.

**Why it is already draining without intervention:** Stage 2 restored the full chain (download → transcribe → site → push). The −211 (1,726 → 1,515) over the ~23 h since pre-flight is that restored chain working, verified by the per-day `dl_ok`/`srt` above. No queue manipulation, no deletions, no status rewrites were performed.

## 4. Grafana on server 52 — BLOCKED (re-verified, fresh evidence)

The Grafana dashboard target (server 52, `172.20.1.52`) is **down**. Fresh reachability check from server 53 at 2026-11-03 17:13 UTC (verbatim):
```
=== server 52 reachability (from 53, 3 attempts) ===
attempt 1: TCP/22 closed/timeout
attempt 2: TCP/22 closed/timeout
attempt 3: TCP/22 closed/timeout
grafana/3000 closed/timeout
=== ping 52 (2 packets) ===
2 packets transmitted, 0 received, +2 errors, 100% packet loss
```
This matches the Stage 0 pre-flight finding. **Declared BLOCKED** — Grafana cannot be deployed/verified on 52 while the host is unreachable (no SSH, no ICMP, no Grafana port). I will **not** fake a Grafana-up state. When 52 returns, the `dashboard/grafana/iranseda-pipeline.json` dashboard (present in the reconciled repo, all panels verified in Stage 1) is ready to import; the only dependency is a reachable 52.

**Live monitoring surface that IS up (used throughout this stage):**
- Prometheus endpoint: `GET :8990/metrics` on server 53 (dashboard) — `iranseda_pipeline_runs_*`, SRT-produced, zero-output-days, public-site probe (the exact metric family the Grafana panels query).
- Reporter state: `GET :8990/api/reporter` (auth) — publication_task queue, statuses.
- Per-run ground truth: `pipeline_runs` table (`record_run.py`) — the source every dashboard/Grafana panel reads.

## 5. Whisper health (supports the "download-bound" conclusion)
- Container healthy after the Stage 2 hook fix; first in-container `transcribe_batch` event confirmed (Stage 2 §5.4, task 71).
- 6-hour window: 1 `: DONE` (session 5936), **0 `FAILED`** — consistent with the near-empty `pending_transcribe` queue (8), i.e. transcription is ahead of supply, not behind it.

## 6. Verification chain (all real outputs)
1. `.tmp_p8_st3_baseline.sh` — live DB status/arrival/service counts (verbatim §2.1).
2. `.tmp_p8_st3_runs.sh` — `pipeline_runs` per-day dl/srt/arrivals + 24 h push count (verbatim §2.2).
3. `.tmp_p8_st3_52.sh` — 52 reachability (TCP/22 ×3, /3000, ping) + whisper 6 h DONE/FAILED (verbatim §4/§5).
4. Cross-check: queue delta 1,726 → 1,515 consistent with the measured ~147/day download service over ~23 h (≈ 140–215 expected) — **within range, no anomaly**.

## 7. Declared (explicit)
- **24 h drain observation = IN PROGRESS**, not yet complete at report time; the live 24 h before/after delta and hourly samples are delivered in `24H_MONITORING_REPORT.md` (Stage 4), then reconciled here.
- **Grafana on 52 = BLOCKED** (server down, §4). Not faked, not assumed.
- **No queue manipulation performed** — drain is organic from the restored pipeline; all counts are read-only queries.
- Pre-existing (flagged, untouched): plaintext `DB_PASS` in `docker-compose.whisper.yml`.
