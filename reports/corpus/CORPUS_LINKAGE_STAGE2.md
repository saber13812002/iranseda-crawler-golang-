# Stage 2 — IranSeda Corpus Source-Linkage & RAG Citation

**Date:** 2026-11-05 (UTC) · **Status:** COMPLETE (no BLOCKED items)
**Owning repo:** `git@github.com:saber13812002/iranseda-crawler-golang-.git`
**Branch:** `stage2-corpus-linkage` (cut from `phase3-radio-rag-service` @ `BRANCH_BASE`)
**Commits:** `SHA1` (module+CLI) · `SHA2` (tests) · `SHA3` (report+data) · +1 metadata commit (SHA/push backfill = branch HEAD)
**Push:** `origin stage2-corpus-linkage` → pushed, no force (output in §8)

> Companion spec: [`CORPUS_LINKAGE_SPEC.md`](../../docs/corpus/CORPUS_LINKAGE_SPEC.md)
> (Stages 0–1 delivered earlier; this is Stage 2 only.)

---

## 1. Scope & hard constraints (all honored)

- **NO** production deploys, **NO** running-service changes, **NO** DB writes,
  **NO** re-export/re-index, **NO** Stage 3+ work.
- All site probes **read-only** HTTP (GET/HEAD), sequential, 1 s delay,
  per-request timeout capped at 15 s, ≤ 2 concurrency (actually 1).
- Total site requests: **128 / 400 budget** (§7).
- No secrets, tokens, or `.env` committed anywhere.

## 2. Open questions resolved (Task A)

| OQ | Question | Resolution | Evidence |
|----|----------|------------|----------|
| OQ-1 | `d=` param date format | **Gregorian, month-first `M/D/YYYY`, UNPADDED** (supersedes the spec §6.2 day-first/zero-padded assumption — documented spec discrepancy) | [`evidence/oq1_d_mdy_month_first_unpadded.txt`](evidence/oq1_d_mdy_month_first_unpadded.txt) |
| OQ-2 | Episode title & e-id | Title = `آرشیو رادیو - برنامه {program_name} -`; e-id present **2×** (meta `androidAddress` + body); e= not in DB still yields a valid page | [`evidence/oq2_episode_title_and_eid.txt`](evidence/oq2_episode_title_and_eid.txt) |
| OQ-3 | Program page | `radio_programs.url` verbatim = **live program intro page** (200; name in title; `m` in body ~29×); no verified listing page → A8 stays null-by-policy | [`evidence/oq3_program_page_live_intro.txt`](evidence/oq3_program_page_live_intro.txt) |
| OQ-7 | HEAD supported? | **Yes** — `Content-Length` from HEAD equals GET body size exactly (46575/46575, 65019/65019). GET remains the default for content checks | [`evidence/oq7_head_supported.txt`](evidence/oq7_head_supported.txt) |
| OQ-8 | Site wall clock | **Asia/Tehran local**; timeslot page renders the requested Gregorian day as Jalali + exact slot: `آرشیو رادیو   - پنجشنبه 14 آبان 1405 - ساعت 12:30` | [`evidence/oq8_site_clock_tehran.txt`](evidence/oq8_site_clock_tehran.txt) |
| OQ-11 | `m=` in session links? | **0 / 10,886** session links contain `m=`; all carry `ch=`+`e=` | [`evidence/oq11_no_m_in_session_links.txt`](evidence/oq11_no_m_in_session_links.txt) |

**Not closed (deliberately — later stages):** OQ-4/5/6/10/12.

Key verbatim evidence:

- OQ-1 — `d=14/8/1405` (Jalali) → 88-byte ASP.NET exception body:
  `<!DOCTYPE html>Conversion failed when converting date and/or time from character string.`
  `d=5/11/2026` → 70,107-byte page whose `d=` hrefs are the 7-day window
  `10/30/2026 … 11/5/2026` **centered on the requested date**.
- OQ-2 — `e=154148409` (absent from DB) → 200, title `آرشیو رادیو - برنامه به امید دیدار  -`.
- Site "empty page" pattern — 200 with a **15-byte** body `<!DOCTYPE html>`
  [`evidence/empty_15b_page.txt`](evidence/empty_15b_page.txt).

## 3. Deliverable module (Task B)

New files in the owning repo (all in commit `SHA1`, tests in `SHA2`):

| File | Purpose |
|------|---------|
| [`corpus/linkage.py`](../../corpus/linkage.py) | URL builders + `validate_link` + `classify_date` (spec §6.1–6.7) |
| [`corpus/validate_links.py`](../../corpus/validate_links.py) | Bounded, resumable live-validation CLI |
| [`tests/corpus/test_linkage.py`](../../tests/corpus/test_linkage.py) | 37 **offline** unit tests (fake fetch, no network) |

### 3.1 `corpus/linkage.py`

- **Builders** (raw vs normalized kept separate):
  `build_episode_url(ch, e)`, `build_day_archive_url(ch, gregorian_date)`,
  `build_time_slot_url(ch, start_time, gregorian_date)` (range-checked),
  `build_program_page_url(program)` → `{"raw": verbatim|None, "normalized": …}`.
- **Templates:** `epgarchivePart/?VALID=TRUE&ch={ch}&e={e}` ·
  `timeArchive/?VALID=TRUE&ch={ch}&d={M/D/YYYY}` ·
  `timeArchivePart/?VALID=TRUE&ch={ch}&ti={HH:MM}&d={M/D/YYYY}` ·
  program page = `radio_programs.url` verbatim.
- **`validate_link(url, session, program, link_type, fetch, timeout)`**
  (spec §6.5/§6.7): pre-fetch identity cross-checks (no request on mismatch) →
  real HTTP GET (≤3 redirects, on-host, browser UA) → status mapping →
  type-specific strict checker. Returns
  `valid | invalid | unverified` + `reason` + `warnings[]` + `evidence` +
  `last_verified_at` (UTC).
- **Status discipline:** 404→`invalid:not_found`; 401/403/407/429→
  `unverified:blocked`; timeout→`unverified:timeout`; network error→
  `unverified:http_error`; other non-200→`invalid:http_error`;
  off-host redirect→`invalid:redirect_out`; content mismatch→
  `invalid:<type reason>`.
- **Strict checks per type:**
  - *episode* — e-id digit-boundary match (expected 2×) + program name in title;
  - *day_archive* — 7-day `d=` href window centered on target (consecutive
    prev ≥ 3 AND next ≥ 3, `datetime.timedelta` scan of parsed dates);
  - *time_slot* — title contains `ساعت HH:MM` **and** the Jalali date
    `"{d} {month-name} {year}"` converted from the target Gregorian date
    (site clock = Asia/Tehran, OQ-8);
  - *program_page* — program name in title + `m`-id in body.
  - Soft checks (program name in body for day/timeslot; day-archive title is
    channel-level by design) → `warnings[]` only.
- **`classify_date(session)`** (spec §4.2): `confirmed | unverified |
  impossible | none`, with reasons (`implausible_year`, `month_gt_12`,
  `day_gt_31`, `gregorian_jalali_mismatch`, …); windows Jalali [1390, 1407] /
  Gregorian [1990, 2037]; raw filename/stem always preserved; timezone
  constant `Asia/Tehran`.
- **Normalization** (§6.5.4): NFC → strip Mn/Me/Cf (diacritics, ZWNJ/ZWJ,
  U+FEFF, tatweel) → casefold → Persian + Arabic-Indic digit folding →
  whitespace collapse.

### 3.2 `corpus/validate_links.py` (CLI)

Args: `--sample`, `--out` (required), `--timeout` (hard-capped 15 s),
`--delay` (default 1.0 s), `--max-requests` (budget), `--site-base`,
`--episode/--day-archive/--time-slot` (synthetic mission links, repeatable).
Sequential; URL-deduplicated plan (synthetics first); **resumable** (reuses
per-URL results already in `--out`); writes
`reports/corpus/stage2_link_validation.json` (run meta + per-type coverage +
per-URL results, no secrets).

### 3.3 Tests

37 offline tests (injected `FakeFetch`; zero network). Coverage: builders
(incl. range errors), month-first unpadded date, `link_type_of`, `hhmm`
(truncation + rejects), normalization (ZWNJ/ZWJ/BOM/digits), title
extraction, `classify_date` (canonical unverified / impossible / none /
gregorian cross-check mismatch), and all four type checkers (valid, each
mismatch kind, 404, blocked, other HTTP error, timeout, network error,
redirect-out, unsupported URL, pre-fetch no-request mismatches, empty page).

- **Laptop (Python 3.13.7, Windows):** 37/37 pass.
- **53 venv (Python 3.12.3, Linux):** full corpus suite **127/127 pass**
  (90 pre-existing + 37 new) + `py_compile` + import smoke — run from the
  repo on 53, no production service touched.

## 4. Live validation (Task C)

Sample: **35 real sessions** (stratified: 24 strata, 4 implausible-year
`1497/1498/1499`, 4 named mission stems incl. `radio-maaref-05-07-19-13-30`
and `radio-maaref-05-03-10-05-30`, 1 Varzesh, 2 recent) + **1 synthetic
mission episode** (`ch=14&e=154148409`). The 4 implausible-year sessions
correctly produced **no** day/timeslot links (`impossible date:
implausible_year`).

Plan: **101 unique URLs** = 36 episode · 23 day_archive · 29 time_slot ·
13 program_page (deduped).

Run 1: 2026-11-05T18:10:32Z→18:16:35Z (363 s, 101 new requests, 1 s delay,
15 s timeout). Run 2 (resumable, re-validated only the 3 flaky URLs):
18:31:40Z→18:31:55Z (+3 requests). Final per-URL results are in
[`stage2_link_validation.json`](stage2_link_validation.json).

### 4.1 Final coverage matrix

| Link type | Planned | Verified | Valid | Invalid | Unverified | Failure reasons |
|-----------|--------:|---------:|------:|--------:|-----------:|-----------------|
| episode | 36 | 36 | 28 | 8 | 0 | `title_mismatch` ×7, `id_mismatch` ×1 |
| day_archive | 23 | 23 | 23 | 0 | 0 | — |
| time_slot | 29 | 29 | 29 | 0 | 0 | — |
| program_page | 13 | 13 | 13 | 0 | 0 | — |
| **Total** | **101** | **101** | **93** | **8** | **0** | |

All HTTP 200; zero timeouts/blocks/redirect-outs. **Do NOT extrapolate to
the full 10,886-session corpus** (per-URL results only).

### 4.2 Failure analysis (the 8 invalid episode links)

1. **Program-name drift on-site (7×, `title_mismatch`) — genuine data
   findings**, e-id checks pass, titles differ only in name spelling:

   | session | DB `program_name` | Live title name |
   |---------|-------------------|-----------------|
   | 238 (e=146649527) | `امیر مؤمنان` | `امیرمؤمنان` |
   | 239 (e=145189232) | `امیر مؤمنان` | `امیر مومنان` |
   | 240 (e=139510046) | `امیر مؤمنان` | `امیر مومنان` |
   | 5290 (e=153642040) | `امیر جان ها` | `امیر جانها` |
   | 9426 (e=149625684) | `پرسمان تاریخی` | `پرسمان- تاریخی` |
   | 9427 (e=149616218) | `پرسمان تاریخی` | `پرسمان- تاریخی` |
   | 9428 (e=149603226) | `پرسمان تاریخی` | `پرسمان- تاریخی` |

   (The §6.5.4 normalizer collapses spaces/diacritics but deliberately does
   **not** invent name aliases — a literal normalized compare is the
   spec-mandated strict check; these are reported, not silently passed.)

2. **`e=154067181` (session 5793, `پیام ولایت`) — `id_mismatch`**:
   consistent 15-byte empty page (two re-fetches), e-id absent. The URL is
   routable but the archive content is gone on the site.

### 4.3 Flaky title-less 200 responses (site behavior, not validator bugs)

3 URLs returned a **title-less, incomplete 200** during run 1 and were
flagged accordingly; re-fetched 20 minutes later they served full valid
pages, and run 2 (resumable) re-validated them **valid**:

| URL | Run 1 | Re-probe | Run 2 |
|-----|-------|----------|-------|
| `timeArchive/?VALID=TRUE&ch=14&d=11/2/2024` | `invalid:date_mismatch` (0 `d=` hrefs parsed) | 68,178 B, 7-day window present | **valid** |
| `timeArchivePart/?VALID=TRUE&ch=18&ti=07:30&d=10/30/2026` | `invalid:time_mismatch` (title None) | title `… جمعه 8 آبان 1405 - ساعت 07:30` | **valid** |
| `timeArchivePart/?VALID=TRUE&ch=14&ti=15:30&d=11/5/2026` | `invalid:time_mismatch` (title None) | title `… پنجشنبه 14 آبان 1405 - ساعت 15:30` | **valid** |

Implication for Stage 3 (RAG citation re-checks): a title-less 200 should
be treated as *unverified/transient*, re-tried once before declaring
invalid. The 15-byte empty body, by contrast, is the site's **consistent**
no-content state.

### 4.4 Warnings (soft checks)

- `day_archive`: `program_name_not_on_page` ×23, `m_id_not_in_body` ×23 —
  by design: day-archive pages are **channel-level** calendars
  (title `رادیو  معارف  - آرشیو زمانی`); program attribution is not
  rendered there. Kept as warnings, never failures.
- `time_slot`: `program_name_not_on_page` ×4 — same reason on slot pages.

## 5. Coverage statement (what this proves, what it doesn't)

- **Proven (on this sample, 2026-11-05):** all four URL templates build
  live, valid pages for the sampled sessions; the strict checkers
  discriminate correctly (real mismatches are caught, flaky fetches flip on
  re-fetch); 93/101 links are valid as-is; 8 invalid links are
  **diagnosed** (7 name-drift, 1 empty page) — none are validator defects.
- **Not proven / out of scope:** the full 10,886-session corpus (no
  extrapolation), the 4 impossible-year sessions' archives (date unbuildable
  by definition), listing-page existence (A8 stays null), and anything
  Stage 3+ (citation embedding, re-index, deploys).

## 6. BLOCKED items

**None.** Every Task A/B/C/D objective completed within budget and
constraints.

## 7. Request budget (politeness)

| Bucket | Requests |
|--------|---------:|
| Task A probes (OQ-1/2/3/7/8/11) | 19 |
| Task C fetch smoke | 1 |
| Task C run 1 (101 unique URLs) | 101 |
| Invalid-4 forensic re-probe | 4 |
| Task C run 2 (resumable, 3 flaky URLs) | 3 |
| **Total** | **128 / 400** |

Sequential, ≥1 s delay, 15 s timeout cap, on-host redirects only.

## 8. Git (Task D)

- Branch `stage2-corpus-linkage` cut from `phase3-radio-rag-service` @
  `2ddc114dabb0d850f6f3a5a4f30af497c61764f8` (the hourly
  "auto: refresh site + subtitles" commit at branch time) via `git
  worktree` — the main worktree was left untouched so the refresh loop
  never raced the commits.
- Commits (4, independent, in the owning repo only):
  1. `SHA1` — `corpus/linkage.py` + `corpus/validate_links.py`
  2. `SHA2` — `tests/corpus/test_linkage.py`
  3. `SHA3` — `reports/corpus/CORPUS_LINKAGE_STAGE2.md` +
     `reports/corpus/stage2_link_validation.json` + `reports/corpus/evidence/*`
  4. `SHA4` — backfill of the commit SHAs and push output into this report
     (a report cannot contain its own commit SHA; `SHA4` = this commit)
- Push: `git push origin stage2-corpus-linkage` (first push of a new
  branch; **no force**). Output below.

```
PUSH_OUTPUT
```

### What did NOT change in production

- No deploy, no service restart, no running crawler/RAG job touched.
- No writes to any database (`radio` db untouched; probes were `SELECT`
  only).
- No re-export, no SRT/TXT regeneration, no re-index, no config change.
- No files modified in the repo's main worktree beyond the 3 new untracked
  deliverables (which the hourly refresh loop has never committed — it adds
  only its own paths). The committed history lives solely on the new branch
  `stage2-corpus-linkage`; `phase3-radio-rag-service` is unchanged.
- No secrets/`.env`/tokens in any committed path.
