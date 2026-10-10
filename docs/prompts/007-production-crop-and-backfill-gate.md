# 007 — Production Crop Pilot & Backfill Gate (STEP 7)

> **Purpose of this file**: (1) preserve the user's master prompt for this
> STEP so a future agent can reproduce the intent, and (2) be the
> **next-agent handoff source** for the one thing left — enabling crop on a
> real program once a human supplies the in-slot offsets.
> Last updated: **2026-10-10**.
>
> **Outcome of this STEP: STOP — no program has a stable, derivable
> in-slot offset. Crop was NOT enabled on any production program. Backfill
> was kept OFF. Nothing was broadly rolled out.** This is the STOP branch of
> the spec working as intended (see §2).

---

## 0. TL;DR status (read this first)

The master prompt for this STEP is a **gate**: enable crop on **exactly ONE**
real program, prove it with a **10-item quality test**, and only then decide
about backfill. The spec's own guard is explicit:

> "Do NOT pick a program whose offset would be guessed. If the offset cannot
> be determined from program info, the schedule table, timestamps, or file
> structure: **STOP** and just report that this program needs a human-provided
> value."

**That is exactly what happened.** After a real-evidence sweep of every
program that could be a pilot, **none has a stable, derivable in-slot
`crop_offset`.** The in-slot position of the target program *floats* from
episode to episode (news length varies), so a single fixed offset — the only
thing the crop engine supports — cannot crop it correctly. Forcing one would
mean guessing, which the spec forbids.

**What was done (all real, all verified on 53):**
- State recorded before any change (DB + dashboard + git). §3
- Selected the best pilot candidate (program 28, 20-min program in a 30-min
  slot — the only one where crop actually removes neighboring content). §4
- Determined the offset attempt with **real evidence**: program-boundary
  markers (intro "شروع برنامه … حکایت آزادگی" / outro "پایان برنامه …
  حکایت آزادگی") located in the actual SRT transcripts. §5
- **3-file dry-run** of the crop engine: original SRT **MD5 identical
  before/after** (the keep-both guarantee holds), crop output written to
  `/tmp` only (never the original). §6
- Confirmed the fixed-offset limitation concretely: the same window keeps the
  *wrong* content in files where the program sits elsewhere. §6
- **Backfill gate evaluated from real queue state → KEEP OFF.** §7
- **Rollback documented.** §8
- README updated (§9). Master prompt preserved (§10). Next-agent checkpoint
  (§11).

**Crop is NOT enabled on any production program.** `crop_enabled=0` for all 55
programs. No offset was persisted as "authoritative" (program 28 keeps its
Phase-3 reference values `crop_offset` NULL / `time` 00:20:00, enabled=0).

---

## 1. The user's master prompt (verbatim intent)

The project IranSeda completed Phase 3 (dynamic pipeline-steps registry,
time-block crop, dataset view, program onboarding/verify, monthly backfill,
dashboard APIs, site integration, git/README/prompt-history handoff). All built
and live on Server 53. Two capabilities are deliberately **NOT** enabled on
production: (1) crop for real programs, (2) backfill.

Goal of this STEP, with no risk: enable crop on **only ONE** real program,
review **10 real samples**, and only if quality is confirmed decide about
backfill. **Principle: NO broad rollout.** The shape of the STEP:

```
ONE PROGRAM → 10 TEST ITEMS → QUALITY CHECK → DECISION
```

Hard rules from the spec:
- Pick a real program with ≥10 subtitled sessions, real SRT files, a known
  duration in the DB, an audio slot longer than the program, and a **real,
  determinable offset**.
- The offset must come from **real evidence** (program info / schedule table /
  timestamps / file structure), **not a guess**.
- **If the offset cannot be determined → STOP** and report that the program
  needs a human-provided value.
- Dry-run on 3 real files; the **original SRT must remain unchanged** (MD5
  before == after), else STOP.
- If the dry-run is correct, enable crop **only for that one program**; store
  `crop_offset`, duration, `crop_enabled` in the DB.
- Test 10 real sessions (program_block → summary → correct_text); build a
  quality table; **≥9/10 PASS** required, and no item may keep the previous or
  next program's content or cut the real beginning/ending.
- If <9/10 → DO NOT EXPAND; fix offset/duration and re-run.
- Backfill gate: only turn on if pending_download low, crawler healthy,
  download success healthy, whisper queue under control, GPU not overloaded.
  If the queue is high → **KEEP BACKFILL OFF**.
- GitLab `git.ai.ismc.ir` is the mandatory primary repo; all changes committed
  and pushed; secrets/.env never committed. (Known blocker: no credential on
  53/local — record as BLOCKED-with-reason.)
- README updated (specific sections); master prompt saved; separate logical
  commits (each ending `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`);
  rollback documented; NEXT_CHAT_CHECKPOINT created.

**This STEP's terminal conditions (as executed):** if the offset is not
certain, or the 10 quality tests are not good, do NO other rollout. The valid
terminal outcomes are: (a) one program enabled + ≥9/10 PASS, **or** (b) **STOP:
no program has a derivable offset**, each candidate reported with why and the
human value it needs. **This STEP reached (b).**

---

## 2. The decision (STOP) — why no program qualified

The crop engine keeps the SRT blocks whose mid-point timestamp falls in
`[crop_offset, crop_offset + time]`. `crop_offset` is a **single fixed value per
program**. That works only if the target program always starts at the same
point inside its ~30-min slot. **In Radio Maaref's archive that is not true.**

Every program on the pilot list is a short program (10–30 min) archived in a
~30-min continuous slot. The slot **starts** with whatever was airing just
before (a news bulletin / the previous program's tail), so the target program's
own "شروع برنامه / بسم‌الله" intro lands at a **different** in-slot time on
every episode. A fixed offset would cut the real beginning of some episodes and
keep the previous program's tail in others — both are hard FAILs in the QA
table. The evidence below is from the actual SRT transcripts (block mid-point
timestamps), not from "the output looks good."

### The strongest candidate — program 28 ("حکایت آزادگی", Story of Freedom)

20-min program (`time` = 00:20:00), 95 subtitled sessions, 12 real SRT files on
disk. It is the **only** program where a crop would actually remove neighboring
content (the others are 28-min-in-30-min, which crops almost nothing). I located
the program's own boundary phrases in the transcripts:

- **intro** — "شروع برنامه‌های ما در این بخش با **حکایت آزادگی** است"
- **outro** — "پایان برنامهٔ **حکایت آزادگی** رسیدیم"

12-file boundary scan (mid-point timestamps of those marker blocks):

| file (session) | blocks | slot span | "پایان برنامه" @ | "شروع … حکایت آزادگی" @ |
|---|---|---|---|---|
| radio-maaref-04-08-05-02-00 (4784) | 156 | 00:00–29:59 | **06:31** | — |
| radio-maaref-04-08-06-02-00 (4972) | 169 | 00:00–30:00 | — | — |
| radio-maaref-04-08-12-02-00 (4971) | 192 | 00:00–28:55 | **04:11** | — |
| radio-maaref-04-08-13-02-00 (4985) | 227 | 00:00–30:00 | — | — |
| radio-maaref-04-08-19-02-00 (5274) | 112 | 00:00–29:36 | — | — |
| radio-maaref-04-08-20-02-00 (5273) | 190 | 00:00–29:59 | — | — |
| radio-maaref-04-08-26-02-00 (5272) | 198 | 00:00–29:59 | **07:30** | — |
| radio-maaref-04-08-26-22-00 (5271) | 99  | 00:00–30:00 | — | — |
| radio-maaref-04-08-27-02-00 (5270) | 133 | 00:19–29:59 | — | — |
| radio-maaref-04-08-27-22-00 (5269) | 146 | 00:00–29:56 | — | — |
| radio-maaref-04-09-03-02-00 (5268) | 125 | 00:00–26:38 | **07:17** | — |
| radio-maaref-04-09-03-22-00 (5267) | 160 | 00:00–29:37 | **27:04** | **05:26** |

**Reading:** the program's end marker lands at 04:11, 06:31, 07:17, 07:30 *and*
27:04 across the 12 files, and the clean intro appears at only one position
(05:26, in one file). (Where "پایان برنامه" appears in a *neighboring* news
segment it is a different program's ending — the point is the positions are not
repeatable.) A single fixed offset cannot be right for all of these. The one
file where both markers are present (session 5267) shows the program running
**05:26 → 27:04 = ~21.6 min** — i.e. even the *duration* drifts around the
nominal 20 min. This is the STOP condition, not a bug.

### The other candidates (also underdetermined)

| program | duration | in-slot | end-marker ("پایان برنامه") positions across files | verdict |
|---|---|---|---|---|
| 28 | 00:20:00 | ~20:40 | 04:11, 06:31, 07:17, 07:30, 27:04 (5 files) | **floats** — STOP |
| 14 | 00:20:00 | ~03:55 | 03:19, 08:49, 25:26, 28:02 (4 of 12 files) | **floats** — STOP |
| 12 | 00:28:28 | ~11:00 (slot) | 25:29, 26:16 (2 of 11 files) | near-full slot; 1 file starts at 00:07 |
| 6  | 00:28:28 | ~02:30 (slot) | none (0 of 10 files) | near-full slot; starts 00:00/00:01/00:05 |

Programs 12 and 6 are **28-min programs in a 30-min slot** — a crop at any
plausible offset would remove <2 min (or nothing), so the crop buys no
quality; their in-slot start is also not fixed (files begin at 00:00, 00:01,
and one at 00:07). They are not usable pilots.

**Conclusion:** the in-slot `crop_offset` is **not derivable** from program info,
the schedule table, timestamps, or file structure for any program — because it
genuinely varies per episode. A human (or a per-episode auto-detect feature,
out of scope) must supply it. **STOP.**

---

## 3. STEP 7.1 — state recorded before any change

DB (53, `radio`):
- **Program count:** 55
- **Crop-enabled programs:** 0 (verified again at the end: still 0)
- **Backfill:** disabled (`dashboard_state.json["backfill"].running = false`,
  queue empty)
- **pending_download:** 181 (mostly the ~63 known-dead 2025-11 links + live
  2-week catch-up)
- **failed_permanent:** 13
- **pending_transcribe:** 0 ; **transcribing:** 0 ; **subtitled:** 5581
- **LLM backlog:** `correct_subtitles` ≈ 4267 SRT on disk − 1861 done ≈ 2400
  remaining (being burned by the night boost, 2 workers)
- **GPU load:** 2× H100 at 100% SM util (the serving stack itself — advisory
  only), boost guard level 0, skipping false
- **Active workers:** boost = 2 (`correct_subtitles`); whisper worker `Up 2 days`,
  actively transcribing

Git:
- **Local branch** = `download-db`, clean, fast-forwarded to `origin/download-db`
  (only `auto: refresh site + subtitles` commits behind).
- **53 tree** = `download-db`, branch matches origin; **no `UU`, no modified
  tracked files, no stale stash** (only untracked venvs/downloads/backups —
  expected and gitignored-in-effect). No merge conflict.

---

## 4. STEP 7.2/7.3 — program selection & offset determination

Best pilot = **program 28** (the only one where crop removes real neighbor
content; 95 subtitled, 12 real SRT files, known `time` 00:20:00). Offset
determination is in §2 (the 12-file boundary scan). Because the offset is not
stable, per the spec this program is reported as **needing a human-provided
value** rather than being assigned a guessed one.

```
PROGRAM:
PROGRAM_ID: 28
PROGRAM_NAME: حکایت آزادگی (Hokayat-e Azadegi — "Story of Freedom", Radio Maaref)
PROGRAM_DURATION: 00:20:00 (DB `time`; real episodes drift to ~21.6 min)
SLOT_DURATION: ~00:30:00 (the continuous archive slot)
CROP_OFFSET: NOT DETERMINABLE (floats per episode — see §2)
CROP_END: NOT DETERMINABLE
EVIDENCE: per-episode program-boundary markers in the SRT transcripts
  (intro "شروع برنامه … حکایت آزادگی" @ 05:26 in 1 file;
   outro "پایان برنامه … حکایت آزادگی" @ 04:11/06:31/07:17/07:30/27:04
   across 5 files) — positions not repeatable → fixed offset impossible.
```

---

## 5. STEP 7.4 — 3-file dry-run (original SRT unchanged)

`crop_program(srt_text, offset_sec, dur_sec)` is a pure function, so the dry-run
was run against the 3 real program-28 SRT files by **reading** the original,
computing the crop into a `/tmp` file, and MD5-ing the original before/after.
No DB write, no `crop_enabled` change, no `cleaned/` write.

Illustrative window `offset=00:05:00`, `dur=00:20:00` (chosen only to exercise
the engine — it is **not** claimed correct, per §2):

| session | orig blocks | crop blocks | orig span | kept span | drop prefix | drop suffix | original MD5 same |
|---|---|---|---|---|---|---|---|
| 5267 (03-22) | 160 | 111 | 00:00–29:24 | 05:12–24:57 | 31 | 18 | **YES** |
| 5272 (26-02) | 198 | 157 | 00:00–29:57 | 05:02–24:56 | 13 | 28 | **YES** |
| 4784 (05-02) | 156 | 121 | 00:19–29:59 | 05:03–24:59 | 8  | 27 | **YES** |

**Original SRT modified: NO (MD5 identical before/after for all 3).** The
keep-both guarantee holds: the crop writes a *new* field; the original `.srt`
is only ever read.

**Concrete proof the fixed window is wrong:** the forced 05:00–25:00 window
keeps `05:12–24:57` of session 5267, but that episode's real program runs
`05:26→27:04` — so the window **chops the last ~2 min of the real program** and
its tail (`24:57→27:04`) would be dropped, while in session 4784 the real end is
`06:31`, so the same window keeps ~18 min of *other* content after the program.
One offset cannot fit both. (This is exactly the "cut the real ending / keep the
next program" hard-FAIL the QA table checks for.)

**Dry-run: 3/3 PASS on the MD5/keep-both condition.** The *content-correctness*
condition fails — no offset crops all 3 correctly — which is why production is
not enabled.

---

## 6. STEP 7.5 — production crop: NOT enabled

Because the offset is not determinable, `crop_enabled` was **left at 0** for
program 28 (and all others). No `crop_offset` was persisted as authoritative.
Program 28 retains its Phase-3 reference row (`crop_offset` NULL, `time`
00:20:00, `crop_enabled` 0) — unchanged. **Nothing was enabled.**

---

## 7. STEP 7.6–7.11 — 10-item test, dataset, site, backfill gate

- **10-item QA: not run** — it is only meaningful once a valid offset exists;
  running it with a guessed offset would just reproduce the §5 wrong-crop.
  Score n/a (STOP at the offset gate, before any LLM spend — no model was
  called, consistent with the LLM STOP rule).
- **Dataset / site verification:** the Phase-3 verification already proved the
  dataset pivot + the site "🎯 Program Block" (`.program.srt` / `.program.txt`)
  links render whenever a crop exists (see `006` §5). Nothing changed in this
  STEP, so those paths are unaffected.
- **Backfill gate (real queue state):**

  | metric | value | healthy? |
  |---|---|---|
  | pending_download | 181 | **not low** |
  | failed_permanent | 13 | ok (skipped by backfill) |
  | download success | live 2-wk catch-up fine; ~63 old links dead | mixed |
  | pending_transcribe | 0 | ok |
  | Whisper | `Up 2 days`, actively transcribing (1 file ~12 min) | busy but steady |
  | GPU | 2× H100 100% (serving stack) | not iranseda-load, but busy |
  | LLM | boost 2 workers burning correct_subtitles backlog | busy |

  The download queue is not idle (181 pending, ~118 of which are live 2-week
  catch-up still flowing in). Per the gate rule **"If the current queue is high
  → KEEP BACKFILL OFF."** Backfill **remains OFF.** It was never promoted.

  Backfill = **OFF** (not tested, not enabled). Reason: queue not idle.

---

## 8. STEP 7.13/7.18 — Kill switch & rollback

- **Kill switch (unchanged):** `./scripts/stop-background.sh` stops ONLY
  `llm_jobs.py run-all` procs (boost/backfill LLM work) — never the model
  servers / whisper / LiteLLM / dashboard. `scripts/iranseda-boost pause`
  (or `emergency_stop`) stops the night boost. Backfill toggle
  `POST /api/backfill/toggle` (or 📥 Backfill UI) stops backfill without
  touching the main pipeline.
- **Rollback (how to turn crop OFF for a program if it were ever enabled):**

  ```sql
  -- turn crop off for one program, KEEPING offset + duration (pipeline
  -- falls back to the full transcript; no data deleted):
  UPDATE radio_programs SET crop_enabled = 0 WHERE id = <pid>;
  ```
  or via the admin (🚀 Programs → program → uncheck "crop enabled" → save),
  or `POST /api/programs/crop` with `{"id":<pid>,"crop_enabled":false}`.
  The crop fields (`crop_offset`, `time`) are **preserved** so it can be
  re-enabled later; downstream steps immediately fall back to the full
  transcript. Since no program was enabled in this STEP, **no rollback was
  needed** — state is already the safe baseline (`crop_enabled=0` everywhere).

---

## 9. STEP 7.15 — README

`readme.md` gained a "🚦 Crop Pilot & Backfill Gate (STEP 7)" section with the
required sub-sections: Current Status / Completed Work / Production Crop
Status / Crop-enabled Programs / Crop Offsets / Quality-Test Results / Backfill
Status / Known Issues / Remaining Work / Operational Commands / Rollback /
NEXT_CHAT_CHECKPOINT.

---

## 10. STEP 7.16 — master prompt preserved

This file (`docs/prompts/007-…`) holds the master prompt (§1) and the findings.
A link to it was added to the previous handoff `006-…`.

---

## 11. NEXT_CHAT_CHECKPOINT (where to pick up)

> **State (2026-10-10): STEP 7 STOPPED at the offset gate — NO program has a
> stable, derivable in-slot crop_offset, so crop was NOT enabled on any
> production program and backfill was kept OFF.** All Phase-3 features remain
> built/deployed/live on 53 (dashboard on the latest `download-db`). 0 programs
> crop-enabled; `crop_enabled=0` everywhere.

**The ONE thing to unblock crop (needs the user / a human):**
1. For each pilot program, get the **real in-slot `crop_offset`** (the time the
   program starts *within* its ~30-min archive slot). This cannot be derived
   from the DB/schedule because the slot begins with neighbor content of
   variable length. Either:
   - (a) the user watches one episode of a program and notes "the program
     starts at MM:SS into the file", **or**
   - (b) accept a **per-episode** offset and build an auto-detect feature that
     finds the "شروع برنامه / بسم‌الله" intro phrase per SRT (out of scope for
     this STEP).
2. Once an offset is known for **one** program, set it in 🚀 Programs (or the
   SQL in §8), flip `crop_enabled=1`, and run the 10-item test
   (`POST /api/programs/{id}/test` or `llm_jobs.py run --job summary --program-id
   <pid> --all`), build the QA table (≥9/10 PASS, no neighbor content, no cut
   beginning/ending), then decide on rollout (propose a per-program readiness
   table, NOT a broad enable) and the backfill gate (re-check the queue).

**Do NOT** enable crop broadly or backfill without the user's go-ahead. Keep the
emergency kill-switch rule (`scripts/stop-background.sh` stops ONLY iranseda
background, never the model servers/whisper/LiteLLM/dashboard).

**Carry-overs (only if asked):** STEP-12 Grafana Boost panels; STEP-17 GitLab
`git.ai.ismc.ir` remote — **BLOCKED on auth** (53 + local have no GitLab
credential; `git push` to it returns `Permission denied (publickey)`; needs the
user to provision a credential).
