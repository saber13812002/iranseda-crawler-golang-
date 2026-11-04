# IranSeda Corpus — Stage 1: Preflight (Live State)

**Mission:** IRANSEDA CORPUS BUILDER & HUGGING FACE PUBLISHER
**Stage:** 1 — Preflight و حفاظت از وضعیت فعلی (inspect live state BEFORE any change)
**Date:** 2026-11-03, probes run 18:12–19:06 UTC (all numbers below are LIVE, freshly re-verified)
**Target:** server 53 (`saber@172.20.1.53`, hostname `llm`), production checkout
`/home/saber/saberprojects/iranseda-crawler-golang-`

> **Rule compliance:** Per mission rule 2, the Phase 8 reports (Nov 3, SHAs
> `62b69d1b1`/`fe795f2ba`/`f47d78659`/`0d38ad40c`/`868b22081`) are used as
> HISTORICAL BASELINE ONLY. Every number in this report was re-measured live by
> read-only probes (`.corpus_probe0.sh` … `.corpus_probe4.sh`, kept untracked in
> the local workspace for reproducibility; transport =
> `.corpus_sshrun.py`, UTF-8 end-to-end, 120 s wait-free cap). **No modification
> of any production state occurred during this stage** — all probes are
> SELECT/find/HTTP-GET only.

---

## 1. MANDATORY CORPUS COUNTS (live, 2026-11-03 19:04–19:06 UTC)

| # | Mandatory count | Value | Source (live) |
|---|-----------------|-------|---------------|
| 1 | Registered programs | **59** rows, **32** distinct `(ch,m)` URLs | `COUNT(*)` / `COUNT(DISTINCT url)` on `radio_programs` |
| 2 | Sessions (episodes) | **10 858** | `COUNT(*)` on `radio_program_sessions` |
| 3 | Sessions with SRT (on disk) | **10 466** | full disk-scan join (stem of `filename`/`srt_filename` ∈ `downloads/*.srt` ∪ `downloads/cleaned/*.srt`) |
| 4 | Sessions with TXT (on disk) | **10 466** | same join vs `*.txt` (top-level 7 514 + cleaned 17 026) |
| 5 | Corrected SRTs | **4 245** distinct sessions (rows = 4 245, all `status=done`) | `llm_output` where `job_type='correct_subtitles'`; on disk: `downloads/cleaned/*.correct.srt` = **4 284** |
| 6 | Corrected TXTs | **4 212** distinct sessions (all `done`) | `llm_output` where `job_type='correct_text'`; on disk: `downloads/cleaned/*.correct.txt` = **4 251** |
| 7 | Programs with schedule info | **56/59** with `time`, **48/59** with `time_description` | `SUM(time IS NOT NULL)` etc. on `radio_programs` |
| 8 | Episodes with audio links | **10 858 / 10 858** (100 %) | `SUM(link IS NOT NULL AND link<>'')` on `radio_program_sessions` |
| 9 | Records with speaker info | **0 — NO SOURCE EXISTS** | `information_schema.tables` LIKE `%speaker%/%host%/%guest%` → no rows. Speaker fields must stay empty or come only from future verified crawl sources. |
| 10 | Incomplete records | see §1.1 breakdown | derived (below) |
| 11 | Main pipeline queue states | see §2.1 | live (below) |

### 1.1 "Incomplete records" breakdown (live)

Definition: a session is *incomplete* when any corpus-relevant artifact is
missing. Measured:

| Gap | Sessions | % of 10 858 |
|-----|----------|-------------|
| No `filename` at all | **342** (10 858 − 10 516 filled) | 3.2 % |
| No SRT on disk | **392** (10 858 − 10 466) | 3.6 % |
| No TXT on disk | **392** (10 858 − 10 466) | 3.6 % |
| No LLM summary | **6 646** (10 858 − 4 212) | 61.2 % |
| No corrected TXT | **6 646** | 61.2 % |
| No corrected SRT | **6 613** (10 858 − 4 245) | 61.0 % |
| Status `failed_permanent` | **52** | 0.5 % |
| Status `pending_download` (queue) | **1 497** | 13.8 % |

`full_text` covers **923** distinct sessions (933 rows — 10 sessions have two
`full_text` rows from two different models), `qa` covers 1.

**Consequence for the corpus build (rule §4.1):** records must NOT be dropped
for missing subtitles/corrections — the extractor must emit all 10 858 sessions
with explicit `missing` flags per artifact.

### 1.2 Session status distribution (19:04:33 UTC)

| status | count |
|--------|-------|
| subtitled | 9 298 |
| pending_download | 1 497 |
| pending_transcribe | 10 |
| failed_permanent | 52 |
| transcribing | 1 |

DB column fill (19:04): `filename` 10 516/10 858, `srt_filename` 4 658/10 858,
`last_error` 1 225/10 858.

> Note: `status='subtitled'` (9 298) ≠ "SRT on disk" (10 466). Status is the
> pipeline state; the on-disk join is the truth for artifact existence.

---

## 2. LIVE SYSTEM STATE (18:12–19:06 UTC)

### 2.1 Queues & workers

| Component | Live state |
|-----------|-----------|
| `pipeline_runs` (24 h) | **64 runs, 48 pushes_ok** (probe 2, 18:20:18) |
| Reporter (`/api/reporter`) | **69 queued**; newest task 77 = `transcribe_batch` for session 5940 → the Whisper re-transcribe hook is working in production |
| `publication_task` | 69 rows (untouched — mission rule 8) |
| Whisper containers | `worker` Up ~1 h (recent restart), `api` Up 7 days |
| Dashboard (systemd, :8990) | HTTP **200** |
| Cron (user `saber`) | `*/30 … refresh_site.sh` and `15,45 … run_pipeline.sh` — both present |
| Git auto-push | autonomous: `99dc9a322` (18:00), `bc96246ec` (17:30) on `phase3-radio-rag-service` — pipeline is live and self-maintaining |

### 2.2 Host / checkout

- Branch: `phase3-radio-rag-service`, HEAD `99dc9a322` at probe time
  (18:12:22 UTC). Working tree: untracked `.backup_*`, `.pipeline.lock`,
  `.refresh_site.lock`, `Dockerfile.whisper.bak/.orig.bak`, `_patch_worker.py`,
  `_wsdump.py` (pre-existing, untouched).
- MariaDB at `127.0.0.1:3308`, database `iranseda`, 18 tables (full list in
  Stage 2 report). Session `created_at` range **2024-11-08 → 2026-11-03**,
  `updated_at` up to 2026-11-03 18:54.
- `llm_output` (corrected artifacts store) finished-range: **2026-10-07 →
  2026-10-11** — i.e. LLM correction of older stock happened in one batch
  window; new corrections currently flow only for newly processed episodes.

### 2.3 On-disk artifact inventory (19:04–19:06 UTC)

Top-level `downloads/` (19:05:56): srt **7 514**, txt **7 514**, mp4 **2 159**,
mp3 **799**, wav 6, `.failed` 16, lock 2, `mp4_redownload` 1.
`downloads/cleaned/` (19:04:33): srt **7 640**, txt **17 026**,
`.correct.srt` **4 284**, `.correct.txt` **4 251**, `.summary.txt` **4 251**,
`.full.txt` **4 251**, `.program.srt` 3, `.correct.v2.srt` 20.
`downloads/asr/` also present (Whisper raw outputs).

> **Discrepancy to carry into Stage 2/4:** on-disk corrected artifacts
> (4 284/4 251) EXCEED the `llm_output` row counts (4 245/4 212) by 39/39.
> DB `uq_out(session_id, job_type, model)` dedupes; disk files may outlive DB
> rows or predate them. DB remains the authoritative source for *which*
> correction belongs to which session; orphan disk files are recorded, not
> adopted silently.

---

## 3. KEY STRUCTURAL FINDINGS (drive the data model)

1. **Canonical episode identity** — two complementary keys exist:
   - program page URL: `https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044116`
     (`ch` = channel id, `m` = 6-digit program id) — from `radio_programs.url`;
   - episode audio link: `../epgarchivePart/?VALID=TRUE&ch=14&e=152507883`
     (relative, `e` = numeric EPG episode id) — from `radio_program_sessions.link`.
   - DB-level dedupe key: `uq_session_program_link(program_id, link)`.
2. **Broadcast date/time is NOT a column** — it is embedded in the canonical
   filename `radio-<channel>-<jj>-<mm>-<dd>-<hh>-<mm>.{mp3|mp4}` where
   `jj-mm-dd` is a **Jalali** date and `hh:mm` the start time (seconds
   implicitly `00`) (e.g. `radio-maaref-05-08-12-14-30.mp4` = 1405/08/12
   14:30:00). **Erratum 2026-11-04 (probes 7-8 on 53):** the earlier
   `hh:mm:ss` (6-token) reading was wrong — 100% of all DB audio filenames
   and all on-disk audio files carry exactly 5 numeric tokens with 0
   exceptions. Gregorian conversion must be computed and stored as a
   separate derived field with `source: filename`. **Never** use
   `created_at` as broadcast date (range proves it is crawl time:
   2024-11-08 → 2026-11-03).
3. **Schedule ≠ episode time** — `radio_programs.time` (TIME) + `time_description`
   (Persian free text, e.g. `شنبه و یكشنبه از ساعت 17:40 به مدت 30`) is the
   program's broadcast *schedule*; the episode's actual air time is in the
   filename. They are stored separately in the corpus (mission rule §4.6).
   Note data quality issues: some legacy rows carry a *single episode date* in
   `time_description` (e.g. `یکشنبه 21 اردیبهشت 1404 ساعت 04:55`) and 3 rows
   (49, 50, 52) have empty time slots.
4. **Legacy program duplication** — program ids 1–30 are `is_legacy=1`
   (empty `radio`, Persian names padded with tabs/newlines), 31–60 mostly
   `is_legacy=0`; the same program can appear twice (e.g. `بر بال سخن`
   ids 16 & 43, same `m=044114`). The corpus must dedupe programs by `(ch,m)`
   and keep both DB ids in `database_refs`.
5. **No speaker data anywhere** (finding 9) — `speakers` in corpus records
   will be `null` + `missing_reason: "no verified source table"`.
6. **`asr_output` table has exactly 1 row** (Roshan pilot, FAILED
   `UPSTREAM_503`) — production Whisper output is NOT in this table; SRT/TXT
   live on disk, keyed by `srt_filename`/stem. The corpus must model ASR
   provenance from disk + session columns, not from `asr_output`.
7. **`llm_output` is the corrected-output store** — `correct_subtitles`
   (4 245, `srt_content`), `correct_text` (4 212, `content`), `summary`
   (4 212, bilingual `content`/`content_en`), `full_text` (933), `qa` (1);
   model `qwen38-nothinking` (older rows: model=`full_text` marker), prompts
   ids 1–4, with `file_relpath` pointing to `downloads/cleaned/<stem>.*`.
   Original SRT/TXT are **never overwritten** — corrections carry distinct
   suffixes. This satisfies the "original never replaced" rule.

---

## 4. COMPARISON vs Phase 8 HISTORICAL BASELINE (re-verification)

| Metric | Phase 8 (Nov 3, 17:22–17:31 UTC) | NOW (19:04–19:06 UTC) | Δ |
|--------|----------------------------------|------------------------|---|
| pending_download queue | 1 514 (17:22) → 1 513 (17:31) | **1 497** | −17 over ~1.7 h (organic drain, discovery still adding) |
| Reporter queued | 65 (17:31) | **69** | +4 (new transcribe task queued — healthy) |
| Git HEAD (53) | `bc96246ec` (17:30) | `99dc9a322` (18:00) | autonomous cron pushes continue |
| Dashboard | 200 | 200 | stable |
| Last SRT activity | 18:12:29 (probe 1) | `updated_at` max 18:54:37 | transcription still active |

No regression against baseline; all differences are organic pipeline growth.

---

## 5. STAGE 1 VERDICT

**PASS** — live state fully inspected before any change:
- [x] git/branch/HEAD + working tree recorded (53)
- [x] cron entries verified
- [x] dashboard HTTP 200
- [x] MySQL reachable, 18 tables enumerated with counts
- [x] Whisper containers up (worker ~1 h, api 7 d)
- [x] reporter + publication_task queues observed (not touched)
- [x] SRT/TXT/corrected artifact inventories measured (DB + disk join)
- [x] all 11 mandatory §1 counts produced from live sources
- [x] zero modification of production state

**Known risks for later stages:** (a) LLM correction batch window ended
2026-10-11 — the ~6.6 k uncorrected sessions are a real gap, not a bug;
(b) 342 sessions lack `filename` entirely → no derivable broadcast date, must
be emitted with `broadcast: null` + missing flag; (c) server 52 confirmed
unreachable (evidence: `program_score` row error
`HTTPConnectionPool(host='172.20.1.52', port=4000)`), so Grafana deployment
stays BLOCKED; (d) no HF credentials present in environment yet — Stage 7
will record a real BLOCKED unless a token/repo is provided.
