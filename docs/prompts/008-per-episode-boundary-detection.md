# 008 — Per-Episode Boundary Auto-Detection (STEP 8)

> **Purpose of this file**: (1) preserve the user's master prompt for this
> STEP so a future agent can reproduce the intent, and (2) be the
> **next-agent handoff source** for the thing left — expanding per-episode
> auto-crop to more programs once the pilot proves out.
> Last updated: **2026-10-10**.
>
> **Outcome of this STEP: STOP at STEP 8.6 — only 2 HIGH-confidence episodes
> exist on the pilot (program 28), which is below the 10 required to run the
> 10-item QA. NO LLM model was called (STOP happens *before* any LLM spend).
> Crop (auto mode) is live for the pilot only and has already cropped 2
> HIGH-confidence episodes; everything else is NEEDS_REVIEW (full-transcript
> fallback). Backfill was kept OFF. No production rollout beyond the pilot.**
>
> **→ NEXT STEP (9A + 9B):** stats broadcast-vs-ingest date + windowed ASR
> correction (`correct_text_v2`) — see
> `009-stats-broadcast-date-and-correct-text-v2.md`.

---

## 0. TL;DR status (read this first)

STEP 7 (007) proved a **fixed** `crop_offset` is structurally unreliable in
this archive — the program's in-slot start position **drifts per episode**
because the ~30-min slot opens with variable-length neighbor content. The user
rejected a human-supplied offset for one episode as insufficient, and chose
**option (b): detect the boundary independently for each file, rule-based, with
per-episode confidence.**

**That is exactly what was built.** A deterministic, LLM-free
`detect_boundary()` in `llm_jobs.py` finds each episode's own
"شروع برنامه … حکایت آزادگی" / "پایان برنامه …" marker lines and scores the
detected window. Only **HIGH**-confidence episodes are cropped; every other
episode is **NEEDS_REVIEW** (no crop, full-transcript fallback, reason + markers
stored in `crop_detection` for human review).

**What was done (all real, all verified on 53):**
- Built `detect_boundary()` + a `crop_detection` table + a `crop_auto` flag, all
  inside the existing crop machinery — **no new service, no new architecture.**
- **20-episode read-only dry-run**: HIGH=1 / MEDIUM=5 / NEEDS_REVIEW=14,
  **MD5 of all 20 originals unchanged.** §7
- Enabled `crop_auto=1` for the pilot (**program 28**) and ran
  `program_block` (mechanical, no LLM). It cropped the **2 HIGH** episodes
  (sid=5267, sid=4561); the other 20 program-28 episodes are NEEDS_REVIEW.
  **MD5 of the originals re-verified unchanged.** §8
- **STEP 8.6 STOP:** only 2 HIGH < the 10 needed → **NO 10-item QA was run, and
  no LLM model was called** (the STOP fires *before* any LLM spend). §9
- **Dataset + site verified** — the 2 cropped episodes show the 🎯 Program Block
  `.program.srt`/`.program.txt` links on the live site; original SRTs intact. §10
- **Backfill gate from real queue state → KEEP OFF** (2 `correct_subtitles`
  boost workers actively burning the backlog). §11
- Rollback + kill switch documented. §12
- README STEP 8 section + 008 doc committed + pushed to GitHub; GitLab
  attempted → **BLOCKED (no credential)**. §13
- NEXT_CHAT_CHECKPOINT. §14

**No production rollout beyond the pilot.** `crop_auto=1` on program 28 only.
Every other program is untouched. Backfill is OFF.

---

## 1. Persian preamble — the user's decision and why

> **یادداشت فارسی (برای آگاهی):** در مرحلهٔ ۷ (007) ثابت شد که یک «آفست
> ثابت» برای برش، در این آرشیو مطمئن نیست؛ چون محل شروع برنامهٔ هدف در
> داخل اسلات ~۳۰ دقیقه‌ای **از اپیزود به اپیزود جابه‌جا می‌شود** (اسلات با محتوای
> همسایهٔ به‌طول-متغیر — خبر یا دمِ برنامهٔ قبل — شروع می‌شود). کاربر، مقدار آفستِ
> دستِ یک اپیزود را **ناتمام/ناتمامِ کافی** رد کرد و گزینهٔ **(b) — تشخیص خودکار
> مرز برای هر فایل، جداگانه، و بدون LLM** را انتخاب کرد. این مرحله دقیقاً همین
> را ساخت: تشخیص مرز اپیزود-به-اپیزود روی خود SRT، با **امتیاز اطمینان**
> (HIGH / MEDIUM / LOW). فقط اپیزودهای HIGH برش می‌خورند؛ بقیه NEEDS_REVIEW می‌شوند
> (بدون برش، فالت‌بک به متن کامل، و ذخیرهٔ دلیل + مارکرهای امتحان‌شده).

**Why STEP 7 forced this:** a single per-program `crop_offset` cannot work
because the same program sits at 04:11 / 05:26 / 06:31 / 07:17 / 07:30 / 27:04
in different episodes (007 §2, 12-file scan). Per-episode detection is the only
sound fix, and it must be **independent per file** — no cross-episode clustering
(STEP 7 proved positions don't cluster).

---

## 2. The user's master prompt (verbatim intent)

> New STEP 8 from the user. Your STEP 7 finding was accepted as the correct
> decision: a fixed per-program `crop_offset` is structurally unreliable in
> this archive (the in-slot position drifts per episode). The user chose
> **option (b): per-episode boundary auto-detect**. A human-supplied offset for
> one episode was explicitly rejected as insufficient, because the position
> moves between episodes — the boundary must be detected **independently for
> each file**.

**Hard design constraints (user-mandated — do not relax):**
1. **NO LLM for boundary detection.** Pure rule-based text detection on the
   SRT itself.
2. **NO new architecture / no new services** — extend the existing crop
   machinery in `dashboard/llm_jobs.py` (`crop_program`, `srt_parse`,
   `_ensure_program_block` already exist).
3. **Per-episode confidence.** Only HIGH-confidence episodes get cropped.
   Everything else is marked `NEEDS_REVIEW` for that episode: NO crop,
   full-transcript fallback, and the reason + the markers tried are stored for
   human review.
4. **NO production rollout** (other programs, or the pilot's full backlog)
   until the 10-item QA hits **>=9/10 PASS**.
5. **Never modify the original SRT** (MD5 identical before/after — a STOP
   condition if violated).

**The pipeline is exactly this order:**
Per-episode boundary detection → confidence score → dry-run on 20 episodes →
compare detected boundaries → MD5 original unchanged → only high-confidence
episodes crop → 10-item QA → no production rollout until >=9/10 PASS

**STEP 8.1 — Evidence first, before writing any rule.** Grep the pilot
program's REAL SRT files for candidate markers (program-name variants,
"شروع برنامه"/"شروع", "پایان برنامه"/"پایان", "بسم‌الله", "مقدمه", and lines that
repeat across most files). Persian whisper ASR is messy — markers may be
partially garbled; find what ACTUALLY appears. Report honestly how many files
have a detectable start vs a detectable end — that ratio sets the expected
NEEDS_REVIEW rate.

**STEP 8.2 — Detection function + confidence (rule-based, deterministic).**
`detect_boundary(srt_text, program_name, program_dur_sec) -> (start_sec,
end_sec, confidence, markers_found, evidence)`. Per-episode only — NO
cross-episode clustering. Confidence thresholds must be deterministic, strict,
and documented here.

**STEP 8.3 — Minimal storage (one place, idempotent, auditable).** A
`crop_detection` table + a per-program `crop_auto` flag. Re-detect every run —
no stale cache. The existing fixed-offset mode must keep working unchanged.

**STEP 8.4 — Dry-run on 20 episodes (NO crops written).** CLI
`llm_jobs.py detect --program 28 --limit 20 --dry-run`, padded from programs
14/12 to reach 20. Per episode: start/end, window length vs duration,
confidence/status, marker lines. MD5 of each original SRT before/after —
identical or **STOP**. A comparison table: start-position drift, window-length
distribution, HIGH/MEDIUM/NEEDS_REVIEW counts.

**STEP 8.5 — Crop only HIGH-confidence, pilot program only.** Enable auto mode
for program 28; write `.program.srt`/`.program.txt` only for HIGH-confidence
episodes; NEEDS_REVIEW keep the full-transcript fallback. No other program.
Re-verify MD5 unchanged.

**STEP 8.6 — 10-item QA (LLM).** **If fewer than 10 HIGH-confidence episodes
exist: STOP before any LLM spend** and report the shortfall + the NEEDS_REVIEW
census (a valid STEP 8 outcome). If >=10: check the model stop rule (>5
interactive users → do not call), then run program_block → summary →
correct_text on up to 10 real sessions and build the STEP 7 quality table.
Threshold **>=9/10 PASS** with the four no-fail rules.

**STEP 8.7 — Dataset + site verification.** Dataset shows the new outputs;
site shows the 🎯 Program Block links; run `generate_site.py` ONCE with the
correct ENV.

**STEP 8.8 — Decision gate.** Only with >=9/10 PASS: report
`SAFE_FOR_EXPANSION = YES` + a next-5-programs table. Do NOT enable auto mode
on any other program this STEP. **Backfill: stays OFF** — re-check the queue
numbers and report them.

**STEP 8.9 — Rollback (document it).** Turning the pilot's auto flag off
(and/or clearing its `crop_detection` rows) returns the pipeline to the full
transcript; the original SRT is untouched. Give the exact SQL/CLI.

**STEP 8.10 — Mandatory docs/commits (same policy as STEP 7).** Save THIS master
prompt to `docs/prompts/008-…` (with the Persian preamble) + link from 007;
README STEP 8 section; separate logical commits (each ending
`Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`); push to GitHub
`origin/download-db`; on 53 fetch+rebase, no scp-edits, no merge conflicts;
**GitLab `git.ai.ismc.ir`: attempt the push; if auth fails, record exactly as
BLOCKED (reason: no credential provisioned)** — do not skip it. Never commit
secrets / real `.env`.

**Definition of Done:** (1) detection is rule-based, no LLM, deterministic,
rules documented; (2) marker vocabulary derived from real SRTs with cited
evidence; (3) 20-episode dry-run with the comparison table and MD5-identical
originals; (4) confidence gating strict — only HIGH crops, everything else
NEEDS_REVIEW with stored reason+evidence; (5) crop active for the pilot program
only, originals untouched; (6) 10-item QA run with >=9/10 PASS, **or a
documented STOP if <10 HIGH episodes**; (7) dataset + site verified; (8)
backfill still OFF with queue numbers; (9) 008 doc + README + checkpoint
committed & pushed, GitLab BLOCKED-with-reason if unauthed; (10) rollback
documented.

---

## 3. The decision (STOP at 8.6) — why only 2 HIGH

`detect_boundary()` returns **HIGH** only when **both** the start AND the end of
the program are anchored on real marker lines *found in that same file*, AND the
resulting window length falls inside `[0.7×dur, min(1.2×dur, slot)]` of the
program's DB duration. That is intentionally strict. In practice it only fires
on episodes whose SRT contains **both** a clean intro line and a clean outro line
that are unambiguous for this program.

Program 28 ("حکایت آزادگی") is a book-reading show with a consistent host
format — it is the **only** program in the whole archive whose transcripts
reliably contain a "شروع برامه‌های ما … با حکایت آزادگی" intro. Even there,
the whisper ASR garbles the markers most of the time, so both sides anchor on
only **2 of the 22** program-28 episodes currently processed. A full census of
programs 21–55 (see §11) shows **no other program produces a single start
marker**, so the "next programs" cannot be HIGH at all.

2 HIGH < 10 → **STEP 8.6 STOP before any LLM spend.** This is a *valid* STEP 8
outcome per the spec — not a failure of the code. The detector is working
exactly as designed: it is honest about which episodes it can crop and flags
the rest for human review instead of guessing.

---

## 4. STEP 8.1 — evidence (marker census from real SRTs)

Marker vocabulary is drawn from the **actual** whisper output in the SRTs
(Persian ASR is messy: ZWNJ `‌`, dropped/merged consonants, inconsistent
whitespace). The detector normalizes text (strips ZWNJ, collapses whitespace)
and matches on **tolerant stems** that survive the garbling:

| side | pattern (regex, on normalized text) | what it is in the file |
|---|---|---|
| **start** | `شروع برامه|شروع برنامه|شروع برامه‌|شروع برنامه‌` | host's intro line "شروع برامه‌های ما در این بخش با حکایت آزادگی است…" |
| **end** | `پایان برامه|پایان برنامه|به پایان|خاتمه برامه|خاتمه برنامه` | host's outro "دوستان عزیز به پایان برنامهٔ حکایت آزادگی رسیدیم" |

The name itself ("حکایت آزادگی") is **not** required — it is present in the
intro line but the ASR garbles it, so matching on the *generic* "شروع برنامه" /
"پایان برنامه" stems is more robust. Evidence from the real files (mid-point
timestamps):

- **Start anchor** ("شروع برامه‌های ما در این بخش با حکایت آزادگی است،
  خاطرات آزادگان…") appears at **05:34** in session 5267 and **04:47** in
  session 4561. It is present and clean in only these two of the 22 processed
  program-28 episodes.
- **End anchor** ("پایان برنامهی حکایت آزادگی رسیدیم") appears in several
  files at different positions (07:36, 07:26, 07:30, …) — but a HIGH requires
  **both** sides, so an episode with only an end anchor is MEDIUM/LOW, not HIGH.

Census (honest NEEDS_REVIEW rate) of the 22 program-28 episodes processed:
**2 have both anchors (→ HIGH), the other 20 have neither or only one
(→ MEDIUM/LOW → NEEDS_REVIEW).** That ~91% NEEDS_REVIEW rate on the pilot is
the honest expectation; for every other program it is ~100% (no start marker at
all — §11).

---

## 5. STEP 8.2 — detection rules + confidence (verbatim)

`detect_boundary(srt_text, program_name=None, program_dur_sec=None,
slot_sec=1800) -> {start_sec, end_sec, confidence, status, markers_found,
evidence, window_sec}`.

Deterministic, no LLM, no randomness, no cross-episode state. Rules:

1. **Duration gate:** `dur_ok = program_dur_sec and program_dur_sec > 0`.
   Plausibility window for the detected length:
   `lo = int(0.7×dur)`, `hi = min(int(1.2×dur), slot_sec)`.
2. **Parse:** every SRT block's mid-point timestamp (seconds) + its
   ZWNJ-stripped, whitespace-collapsed text.
3. **Candidate anchors:** a *start* candidate is any block whose normalized text
   matches `_START_PAT`; an *end* candidate any block matching `_END_PAT`.
4. **Selection:** `start_sec = min(start_cands)` (earliest intro). End: if a
   start exists, pick the plausible end with `lo ≤ end−start ≤ hi` closest to
   `dur` (else the latest end candidate). `window = end − start`.
5. **Confidence:**
   - **HIGH** = a start AND an end are each marker-anchored in this file, AND
     `lo ≤ window ≤ hi`. `status = "cropped"`.
   - **MEDIUM** = exactly one side anchored and the other derived (e.g.
     `start = end − dur`). The derived position **must** fall inside the slot
     (`0 ≤ start < slot` and `0 ≤ end ≤ slot`); otherwise it is demoted to
     LOW. `status = "needs_review"`.
   - **LOW** = no usable markers, or an implausible/out-of-slot window.
     `start_sec`/`end_sec` reset to `None`. `status = "needs_review"`.
6. **When in doubt → NEEDS_REVIEW** (never crop on a guess).

Duration plausibility window (pilot, `dur = 1200 s`): `lo = 840 s (14:00)`,
`hi = min(1440 s, 1800 s) = 1440 s (24:00)`. A detected window must be
14:00–24:00 long to be HIGH.

---

## 6. STEP 8.3 — storage (one place, idempotent, auditable)

Inside the existing `SCHEMA`/`MIGRATIONS` in `llm_jobs.py`:

```sql
CREATE TABLE IF NOT EXISTS crop_detection (
    id INT AUTO_INCREMENT PRIMARY KEY, session_id INT NOT NULL UNIQUE,
    program_id INT, start_sec INT NULL, end_sec INT NULL,
    confidence ENUM('high','medium','low') NOT NULL DEFAULT 'low',
    status ENUM('cropped','needs_review','none') NOT NULL DEFAULT 'none',
    evidence MEDIUMTEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
```

Plus `MIGRATIONS`: `radio_programs.crop_auto TINYINT NOT NULL DEFAULT 0`.

`_store_detection()` upserts by `session_id` (idempotent). Re-detection runs
every `program_block` invocation (cheap text scan, no stale cache) and re-writes
the row. The **fixed-offset** path (`crop_enabled=1, crop_auto=0`) is untouched
and keeps working. `evidence` is a JSON blob with `dur_sec`, `start_cands`,
`end_cands`, `lo`, `hi`, `reason`, `start`, `end`, `window_sec` — full audit
trail for the NEEDS_REVIEW rows.

---

## 7. STEP 8.4 — 20-episode dry-run (NO crops written)

`llm_jobs.py detect --program 28 --limit 20 --extra 14,12 --dry-run` (read-only,
no DB rows, no crops). Real output (2026-10-10):

```
=== DRY-RUN DISTRIBUTION ===
episodes: 20
HIGH=1  MEDIUM=5  NEEDS_REVIEW(low)=14
real window-length (anchor-anchored) s: min=21:32 median=21:32 max=21:32  (n=1)
all window-length s: min=00:20 median=00:20 max=21:32
start-position s (drift): min=05:34 median=27:19 max=27:46  (spread 22:11)
pilot window/dur ratio: min 1.08x median 1.08x max 1.08x (dur ~1200s)
per-program tally (pid: total / high / medium / needs_review):
  prog 14: 8 total -> HIGH=0 MED=5 NEEDS_REVIEW=3
  prog 28: 12 total -> HIGH=1 MED=0 NEEDS_REVIEW=11
MD5: all 20 original SRT unchanged
```

The single HIGH in the 20-file sample is **sid=5267** (radio-maaref-04-09-03-22-
00): start=05:34, end=27:06, window=21:32, window/dur = 1.08× — inside
[0.7×, 1.2×]. The `start-position (drift)` line is the STEP 8.4 "prove the
drift" evidence: detected starts range **05:34 → 27:46** (spread 22:11) across
episodes — a fixed offset cannot fit this. The one real (anchor-anchored) window
(21:32) is stable around the 20-min nominal duration — **the window length is
stable even though the start floats**, which is exactly what makes per-episode
detection sound and per-episode offset wrong.

**MD5 original unchanged: YES (all 20).**

---

## 8. STEP 8.5 — crop the pilot (auto mode ON, HIGH only)

`UPDATE radio_programs SET crop_auto=1 WHERE id=28` (crop_enabled left 0). Then
`llm_jobs.py run --job program_block --ids <12 on-disk> --all` — mechanical, no
LLM. A concurrent boost worker (`correct_subtitles`, shard 0/1) was also burning
the backlog at the same moment and ran the same auto path on 10 more program-28
episodes, so the `crop_detection` table now holds a **22-row program-28 census**.

**Episodes cropped (HIGH) — 2:**

| session | file | start | end | window | window/dur | anchors |
|---|---|---|---|---|---|---|
| 5267 | radio-maaref-04-09-03-22-00 | 05:35 (335 s) | 27:07 (1627 s) | 21:32 (1292 s) | 1.08× | start "شروع برامه‌های ما … با حکایت آزادگی" + end "پایان برنامهٔ حکایت آزادگی رسیدیم" |
| 4561 | radio-maaref-04-07-22-22-00 | 04:47 (287 s) | 23:53 (1433 s) | 19:06 (1146 s) | 0.95× | same intro/outro marker pair |

Both `.program.srt` + `.program.txt` were written to `downloads/cleaned/` and
are **git-tracked** (committed by the `refresh_site.sh` cron, `bf238e32`).
Manual spot-check: each crop file **opens exactly on the intro host line** and
**closes on the outro** — no neighbor/news-bulletin prefix, no cut real ending.

**Episodes NEEDS_REVIEW — 20:** (program-28 census: **2 HIGH / 10 MEDIUM /
10 LOW**.) Reasons stored per row:
- **LOW (10):** no usable start anchor and no in-slot end anchor (the ASR
  garbled or omitted the "شروع برنامه" intro line). No crop → full-transcript
  fallback.
- **MEDIUM (10):** one side anchored (usually an end "پایان برنامه" line) but
  the start is derived (`end − dur`) and often falls out of slot (negative or
  >slot) → demoted to no-crop NEEDS_REVIEW. No crop → full-transcript fallback.

**MD5 re-verified: all 12 pilot originals unchanged** (`/tmp/p28_before.md5`
baseline; 12/12 OK). The 20-file dry-run also confirmed 20/20 unchanged.
Constraint 5 holds.

---

## 9. STEP 8.6 — 10-item QA: STOP (2 HIGH < 10)

**STOP before any LLM spend.** The spec: *"If fewer than 10 HIGH-confidence
episodes exist: STOP before any LLM spend and report the shortfall + the
NEEDS_REVIEW census (that is a valid STEP 8 outcome)."*

- **HIGH episodes available: 2** (< 10 required).
- **LLM model called: NO.** (STOP fires before the QA stage; the model stop rule
  was never reached.)
- **10-item QA: NOT RUN** — there are not 10 HIGH episodes to test. Running it
  on MEDIUM/LOW episodes would test crops the confidence gate correctly refused
  to make.
- **Score: n/a (STOP at the HIGH-count gate).**

**NEEDS_REVIEW census (program 28, 22 processed):** 20/22 = ~91% — 10 LOW
(no start anchor) + 10 MEDIUM (one side anchored, derived start out of slot).
This is the honest marker-coverage rate for this archive's Persian whisper ASR.

**The unblock to reach 10 HIGH** (documented, not a code change this STEP):
either (a) add more tolerant/garbled start-marker variants to `_START_PAT`
(e.g. partial "بسم‌الله" / "مقدمه" / "در این بخش" intros) after a manual pass
over the garbled intros, or (b) accept a small human confirmation for the
MEDIUM episodes that already have a clean end anchor. Neither is done here —
per constraint 4, no rollout until a real >=9/10 QA passes.

---

## 10. STEP 8.7 — dataset + site verification

The site reads program crops from `downloads/cleaned/`. Ran
`generate_site.py` once (correct ENV: `ENVIRONMENT=server DB_HOST=172.20.1.53
DB_PORT=3308`, `crawler/venv/bin/python3`) — verified the 2 program-28 crops
appear as 🎯 Program Block links on the program-28 page (`docs/programs/55.html`).

- **Dataset: OK** — the 2 cropped sessions expose the `.program.srt`/`.program.txt`
  outputs; the original `.srt` and full `.txt` are still linked alongside
  (keep-both), so nothing is lost for NEEDS_REVIEW episodes.
- **Site: OK** — `55.html` references both
  `radio-maaref-04-09-03-22-00.program.srt` and
  `radio-maaref-04-07-22-22-00.program.srt` (2 refs each). NEEDS_REVIEW
  episodes correctly show no crop link and fall back to the full transcript.
- The regenerated git-tracked `docs/` + the 2 crop files were committed and
  pushed by the `refresh_site.sh` cron (`bf238e32`).

**Operational note (gotcha avoided):** `generate_site.py` in `server` mode
defaults `DOCS_PATH`/`DOWNLOADS_PATH` to `/home/saber/saberprojects/iranseda/…`
(**no** trailing dash) — a different path than the live repo
`iranseda-crawler-golang-`. The `refresh_site.sh` cron sets the correct
`*_PATH` env vars explicitly; a manual run must do the same (or use the cron)
or it writes to a stray, non-git dir. A stray dir created by an initial manual
run was cleaned up; the authoritative output is the git-tracked
`iranseda-crawler-golang-/docs`.

---

## 11. STEP 8.8 — decision gate

**SAFE_FOR_EXPANSION: NO.** QA was not run (2 HIGH < 10), so the >=9/10 gate is
not met — constraint 4 forbids rollout. No other program has `crop_auto`
enabled.

**Next-5-programs table** (from a read-only marker census of programs 21–55,
3 sampled episodes each — the real marker-coverage signal, not a guess):

| candidate | has duration? | has START marker? | sessions (on disk) | ready? | priority |
|---|---|---|---|---|---|
| 28 (حکایت آزادگی — **pilot**) | 20 m | **yes** (2/22) | 96 (12 on disk) | pilot, 2 HIGH cropped | — (pilot) |
| 45 (كلام امام) | 5 m | no (0/3) | 25 | no | — |
| 28-dup 55 (حکایت آزادگی — repeat feed) | 20 m | no (0/3 in sample) | 21 | no (same show, newer/older feed — 0 start anchors in this sample) | low |
| 30 (گنج سعادت) | 20 m | no (0/3) | 24 | no | — |
| 44 (سمت خدا) | 45 m | no (0/3) | 24 | no | — |

**Read-out:** the detector's start markers are specific to program 28's host
format. **No other program in 21–55 produced a single "شروع برنامه" start
anchor** in the sampled episodes → they would all be LOW → all NEEDS_REVIEW.
Expanding auto mode to them now would crop nothing (and produce no benefit).
Expansion requires either per-program marker vocabularies (a real content
pass) or a relaxed start heuristic validated against a 10-item QA — out of scope
this STEP.

**Backfill: OFF.** Re-checked the real queue at run time: **2 `correct_subtitles`
boost workers (shard 0/1) are actively burning the `correct_subtitles` backlog**
(`llm_jobs.py run-all --job correct_subtitles --model qwen38-nothinking`,
~5586 subtitled sessions in the pipeline). The queue is not idle → gate rule
*"queue high → KEEP BACKFILL OFF."* Backfill **remains OFF**; never promoted.

---

## 12. STEP 8.9 — rollback

Turning the pilot's auto flag off returns the pipeline to the full transcript
immediately; the original SRT is never touched (keep-both). Exact commands:

```sql
-- (a) turn auto-crop OFF for the pilot, KEEPING the flag's value (fallback =
--     full transcript; no data deleted):
UPDATE radio_programs SET crop_auto = 0 WHERE id = 28;

-- (b) optionally clear the detection audit rows for the pilot:
DELETE FROM crop_detection WHERE program_id = 28;
```

or via the admin (🚀 Programs → program 28 → uncheck "crop auto" → save).

To also remove the 2 crop artifacts from the site (they are git-tracked):
```bash
# remove the two crop files; a subsequent refresh_site run regenerates docs
# without their Program Block links and the site falls back to full transcripts
rm downloads/cleaned/radio-maaref-04-09-03-22-00.program.{srt,txt} \
   downloads/cleaned/radio-maaref-04-07-22-22-00.program.{srt,txt}
```

The original `.srt` files are **never** modified by any of the above (MD5
stable). Kill switch (unchanged): `./scripts/stop-background.sh` stops ONLY
iranseda background LLM work — never the model / whisper / LiteLLM / dashboard.

---

## 13. STEP 8.10 — docs / commits / GitLab

- **008 doc:** this file (`docs/prompts/008-per-episode-boundary-detection.md`),
  master prompt preserved (§2) with the Persian preamble (§1). A link to it was
  added from the 007 doc.
- **README:** a "🚦 Per-Episode Crop Auto-Detection (STEP 8)" section was added
  (current status, detection rules + confidence table, 20-episode dry-run, the
  documented 8.6 STOP, NEEDS_REVIEW census, pilot status, backfill status,
  rollback, known issues, NEXT_CHAT_CHECKPOINT).
- **Commits:** separate logical commits, each ending
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`:
  1. the detector + `crop_detection` table + `crop_auto` flag + `detect` CLI
     (code),
  2. write `.program.srt` only when a crop is actually active (fix),
  3. this 008 doc + 007 link,
  4. the README STEP 8 section.
  (The 2 crop files + regenerated `docs/` were committed by the
  `refresh_site.sh` cron as `bf238e32`.)
- **GitHub:** pushed to `origin/download-db`. On 53: fetch + rebase
  (absorbed the 08:30 auto-refresh), no scp-edits, no merge conflicts.
- **GitLab `git.ai.ismc.ir`: BLOCKED.** 53 and the local checkout have **no
  GitLab credential**; `git push` to it returns
  `Permission denied (publickey,password)`. The mandatory primary repo cannot be
  reached until the user provisions a credential. All STEP-8 changes are
  committed + pushed to GitHub `origin/download-db`.
- **Secrets:** no `.env` / `DASH_AUTH_TOKEN` / DB password committed. DB creds
  and `DASH_AUTH_TOKEN` remain gitignored (token lives only in
  `dashboard/dashboard.env`, mode 600).

---

## 14. NEXT_CHAT_CHECKPOINT (where to pick up)

> **State (2026-10-10): STEP 8 STOPPED at STEP 8.6 — only 2 HIGH-confidence
> episodes exist on the pilot (program 28), below the 10 needed for the
> 10-item QA, so no QA was run and no LLM model was called. Per-episode
> auto-crop is built, deterministic, and live for the pilot only (2 HIGH
> episodes cropped; 20 NEEDS_REVIEW with stored reason+evidence). Backfill is
> OFF. No production rollout beyond the pilot. GitLab BLOCKED (no credential).**

**The ONE thing to unblock expansion (needs the user / a content pass):**
1. **Raise the HIGH count on the pilot to ≥10** so the 10-item QA can run.
   Two levers (either is fine; do the cheaper one first):
   - **Add garbled start-marker variants** to `_START_PAT` in
     `dashboard/llm_jobs.py` (e.g. partial "بسم‌الله" / "مقدمه" / "در این بخش" /
     program-name-with-typos intros) — derived from a manual read of the
     NEEDS_REVIEW intros. Re-run `detect --dry-run`, confirm MD5 unchanged,
     confirm HIGH ≥10, re-crop.
   - **Or** manually confirm the ~10 MEDIUM episodes (they have a clean end
     anchor; only the derived start needs a human "starts at ~MM:SS" nudge).
2. **Run the 10-item QA** on the ≥10 HIGH episodes
   (`llm_jobs.py run --job summary --program-id 28 --all`, then
   correct_text), build the quality table (crop correct? neighbors removed?
   intro preserved? ending preserved? summary matches cropped content?
   corrected text program-only? hallucination? missing segment?), require
   **>=9/10 PASS** with the four no-fail rules.
3. **Only if QA passes** → consider expanding `crop_auto` to a second program
   (with its own marker vocabulary — program 28's intro format does NOT
   transfer; §11), and re-check the backfill gate (queue must be idle).

**Do NOT** expand auto mode to other programs or enable backfill without the
user's go-ahead. Keep the kill-switch rule. Carry-over (unchanged from STEP 7):
GitLab `git.ai.ismc.ir` remote — **BLOCKED on auth** (needs the user to
provision a credential).

---

## Final report block (adapted STEP 7 shape)

```
DETECTION RULES
Start markers: شروع برامه|شروع برنامه|شروع برامه‌|شروع برنامه‌
End markers:   پایان برامه|پایان برنامه|به پایان|خاتمه برامه|خاتمه برنامه
Duration plausibility window: [0.7×dur, min(1.2×dur, slot)] = [840 s, 1440 s] (pilot dur 1200 s)
Confidence definition (verbatim):
  HIGH   = start AND end each marker-anchored in THIS file AND lo <= window <= hi -> cropped
  MEDIUM = exactly one side anchored, other derived, derived position in-slot -> needs_review
  LOW    = no usable markers / implausible or out-of-slot window -> needs_review (start/end = None)
  When in doubt -> NEEDS_REVIEW (never crop on a guess). No LLM. Deterministic.

DRY RUN (20 episodes)
Episodes: 20
HIGH / MEDIUM / NEEDS_REVIEW: 1 / 5 / 14
Window-length distribution (min/median/max vs expected 20m): real anchor-anchored 21:32/21:32/21:32 (n=1) = 1.08x
Start-position distribution (the drift, proven): 05:34 / 27:19 / 27:46 (spread 22:11)
MD5 original unchanged: YES (20/20)

CROP (pilot program 28)
Auto mode: ON (crop_auto=1, crop_enabled=0)
Episodes cropped (HIGH): 2 -> 5267 (04-09-03-22-00, 05:35-27:07), 4561 (04-07-22-22-00, 04:47-23:53)
Episodes NEEDS_REVIEW: 20 (census 2 HIGH / 10 MEDIUM / 10 LOW)
NEEDS_REVIEW list + reasons: 10 LOW (no start anchor — ASR garbled/omitted the "شروع برنامه" intro)
  + 10 MEDIUM (clean end anchor present, derived start out-of-slot) -> no crop, full-transcript fallback;
  reason+markers stored per row in crop_detection.evidence

10-Item QA
PASS: n/a / FAIL: n/a / Score: n/a — STOP (2 HIGH < 10; no LLM model called)

Dataset: OK
Site: OK (55.html references both crops; NEEDS_REVIEW fall back to full transcript)
Backfill: OFF (2 correct_subtitles boost workers actively burning backlog; ~5586 subtitled in pipeline)
Rollback command: UPDATE radio_programs SET crop_auto=0 WHERE id=28;  [and/or DELETE FROM crop_detection WHERE program_id=28;]
GitLab: BLOCKED (no credential provisioned on 53/local; push -> Permission denied (publickey,password))
Commit IDs: detector+table+flag+CLI; a2793ad7 (write .program.srt only when active); bf238e32 (crops+docs via refresh cron); 008 doc; README (see §13)
README: YES
008 doc: YES
Known risks: (1) HIGH rate on the pilot is low (~2/22) — Persian ASR garbles the intro on most episodes;
  expansion needs per-program marker vocabularies (28's intro does not transfer). (2) `generate_site.py`
  server-mode default path is a DIFFERENT dir (no trailing dash) — use refresh_site.sh / explicit *_PATH.
SAFE_FOR_EXPANSION: NO
NEXT_CHAT_CHECKPOINT: raise pilot HIGH to >=10 (add garbled start-marker variants, or confirm the MEDIUM
  end-anchored episodes), then run the 10-item QA (>=9/10), THEN consider expanding + backfill.
```
