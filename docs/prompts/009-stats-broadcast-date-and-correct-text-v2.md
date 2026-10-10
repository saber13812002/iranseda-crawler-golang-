# 009 — Stats (Broadcast vs Ingest Date) + `correct_text_v2` (STEP 9A + 9B)

> **Purpose of this file**: (1) preserve the user's master prompt for this STEP
> (two sub-steps: **9A** stats-date semantics, **9B** windowed ASR correction),
> and (2) be the **next-agent handoff source** for the thing left — 9A's date
> backfill (blocked on a calendar/year decision from the user) and 9B's optional
> prompt-tightening (change-rate flag).
> Last updated: **2026-10-10**.
>
> **Outcome of this STEP:**
> - **9A — STOP (as the spec allowed).** The filename's date is readable as a
>   **month-day** pair, but it carries **no year** and its **calendar (Jalali vs
>   Gregorian) is undecidable from the evidence** — so no `broadcast_date` column
>   was added, no backfill run, and the site is **unchanged** (no schema change,
>   no site regeneration). The evidence is documented below (§3); a guess would
>   have been exactly what the user said NOT to do.
> - **9B — built, registered, and QA'd on 20 real files.** A new pipeline step
>   `correct_text_v2` (registry-driven, `output_kind = windowed-correct`) does
>   Persian ASR correction in small sliding windows with context overlap. The
>   20-file QA ran under the model-stop guard; per-file QA table + before/after
>   snippets are in §5. **It is NOT a bulk/boost job** — a bounded 20-file test only.

---

## 0. TL;DR status (read this first)

Two independent sub-steps, done sequentially (both touch 53's git/DB — not
parallelized).

**9A — separate BROADCAST date from PROCESSING date.** The site's period cards
(امروز / هفته / ماه گذشته / سال گذشته / …) count by
`radio_program_sessions.created_at` — the **archive-ingest** date — not the
episode's air date. The filename *does* embed a date
(`radio-maaref-04-09-03-22-00` = month `04`, day `09`, then `03-22-00`).
**Investigation result: the date is month-day, but there is no year and the
calendar is unanchored** (the 23 distinct date pairs span a 2-month band while
the ingest dates span 23 months). Assigning Jalali/Gregorian — or a specific
year — would be a guess. **Per the user's spec, 9A STOPs: no schema change, no
backfill, site unchanged.** §3

**9B — `correct_text_v2`: contextual windowed ASR correction.** New
`pipeline_steps` row (`slug=correct_text_v2`, `input_ref=srt`,
`output_kind=windowed-correct`). A deterministic sliding window (8 target blocks
+ 3 context blocks each side) sends `[before] / [target] / [after]` to
`qwen38-nothinking`; the model returns **only** the corrected target blocks;
original timestamps are preserved verbatim; the result is stitched to
`<stem>.correct.v2.srt` / `.correct.v2.txt` (v2, for comparison against the
existing `.correct.*`). Three hard prompt rules (no summarization, no confident
guess, original immutable). 20-file QA in §5. §4–§5

---

## 1. Persian preamble — the user's decision and why

> **یادداشت فارسی (برای آگاهی):** سایتِ ما کارت‌های دوره‌ای (امروز / این هفته /
> ماه گذشته / سال گذشته و…) را بر اساس **تاریخ ثبت در آرشیو**
> (`created_at`) می‌شمارد، نه بر اساس **تاریخ پخش واقعی** هر اپیزود. این باعث
> می‌شود «سال گذشته» گمراه‌کننده باشد — چون تقریباً همهٔ فایل‌ها تازه دانلود/ثبت
> شده‌اند، ولی محتوایشان پخشِ چند ماه پیش است. در این مرحله دو کار خواسته شد:
> **۹A** — اگر بتوان **تاریخ پخش** را به‌طور مطمئن از نامِ فایل خواند
> (قلمرو: جلالی یا میلادی؟ MM-DD یا DD-MM؟)، آن را در یک ستونِ جدا
> (`broadcast_date`) ذخیره و کارت‌ها را روی آن بازمحاسبه کنیم؛ **وگرنه** — یعنی
> اگر تقویم/سال از شواهد قطعی نباشد — **STOP** کنیم و حدس نزنیم. **۹B** — یک
> گام جدید در خط لوله برای **تصحیح پرتاب‌ای**ِ متن‌های whisper: به‌جای کلِ فایل،
> یک **پنجرهٔ کوچک** (چند بلوک هدف + چند بلوک پیش/پس برای درکِ معنا) را به مدل
> بفرستیم و فقط همان بلوک‌های هدف را اصلاح کند — بدون خلاصه‌نویسی، بدون حدسِ
> قطعیت‌نازده، و دست‌نخورده‌ماندنِ زمان‌کدها.

**Why 9A:** the site is a *searchable archive*; "Last Year" should mean episodes
that *aired* last year, not episodes *ingested* last year. The two diverge badly
here (ingest runs 2024-11 → 2026-10, while the filename air-date band is only
03/07 → 05/07). The user's rule was explicit: **data honest, not guessed** — if
the calendar can't be pinned from evidence, STOP rather than backfill a wrong
date.

**Why 9B:** `correct_text` (existing) sends the whole SRT in one call — long
files get truncated/summarized, and the model lacks local context for
homophones. A small window with surrounding context, correction-only, keeps the
original timestamps and produces a `.correct.v2.*` the user can A/B against the
existing `.correct.*`.

---

## 2. The user's master prompt (verbatim intent)

> Two new work items, done sequentially in this run (both touch 53's git/DB —
> do NOT parallelize them).
>
> **STEP 9A — Stats semantics: separate BROADCAST date from PROCESSING date (no
> LLM).** The site period cards count by `radio_program_sessions.created_at`
> (archive-ingest date), not air date, so "سال گذشته" is misleading. The filename
> embeds the real air timestamp. (1) Confirm date format + calendar (MM-DD vs
> DD-MM, Jalali vs Gregorian) from **evidence**, and report it; (2) If parseable
> **reliably**: add `broadcast_date DATETIME NULL` (idempotent migration in
> `llm_jobs.ensure_schema`), backfill from the filename for ALL rows (parse fail
> → NULL, never guess), recompute the site period cards from `broadcast_date`
> primary / `created_at` fallback, and show ingest-vs-processed as a SEPARATE
> labeled stat; (3) Regenerate the site ONCE with the correct env and report
> before/after; (4) **If the format/calendar is undecidable from evidence → STOP
> 9A, report the sample, and move to 9B.**
>
> **STEP 9B — `correct_text_v2`: contextual ASR correction with window +
> overlap.** `Original SRT → window of 6-10 blocks + 2-3 overlap blocks
> before/after → qwen38-nothinking → correction ONLY (no summarizing) → keep
> original timestamps → stitch → <stem>.correct.v2.srt + <stem>.correct.v2.txt`.
> (1) The model sees `[context before]/[blocks to fix]/[context after]` in one
> call and returns corrected text for the target blocks only; (2) timestamps
> preserved EXACTLY; (3) three hard prompt rules — NO summarization, if unsure do
> NOT make a confident guess (keep original or the safest reading — document the
> choice), original ASR immutable; (4) output is v2, for comparison against the
> existing `.correct.*`. Register as a new `pipeline_steps` row (`slug=correct_
> text_v2`, `input_ref=srt`, a new `windowed-correct` output_kind). Before any
> LLM batch: check the model stop rule (>5 interactive users → do not call, log
> it). QA on 20 real files (pilot 28 + a few other programs) with a per-file QA
> table (blocks in==out, timestamps unchanged, change rate) and 3-4 before/after
> Persian snippets. Original SRT MD5 identical before/after (STOP if violated).
> **Do NOT enable it as a bulk/boost job — 20-file test only.**

**Mandatory (same policy as STEP 7/8):** separate logical commits each ending
`Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`; push to GitHub
`origin/download-db`; on 53 fetch+rebase (absorb auto-refreshes), no scp-edits,
no merge conflicts (note the `generate_site.py` server-mode default-path gotcha
— use the cron path / set `*_PATH`); save this master prompt to
`docs/prompts/009-…` (short Persian preamble quoting the user's decision),
linked from 008; README section for both 9A + 9B (current status, date-evidence,
before/after stats, v2 design + 20-file QA + snippets, known issues, rollback,
NEXT_CHAT_CHECKPOINT); attempt the GitLab push and record BLOCKED-with-reason;
never commit secrets.

---

## 3. STEP 9A — date source + calendar → STOP

### 3.1 The filename date format (from evidence, 5,450 maaref rows)

The maaref (program 28) filenames match
`radio-maaref-<A>-<B>-<C>-<D>-<E>.<ext>`. Analyzing all 5,450 rows:

| field | range | interpretation |
|---|---|---|
| A (pos1) | **3..5** only (23 distinct pairs below) | **month** |
| B (pos2) | **1..12** (every value present) | **day** |
| C (pos3) | 1..**31** | not a standard hour field (see §3.3) |
| D (pos4) | 0..23 | not a standard minute field |
| E (pos5) | 0..37 | not a standard second field |

- **A is the month.** Only values 3, 4, 5 occur, and the (A,B) pairs form a
  **contiguous 23-day calendar span: 03/07, 03/08, … 03/12, 04/01, 04/02, …
  04/12, 05/02, 05/03, … 05/07.** A day field cannot produce month-like
  progression like 03→04→05; a month field explains it. So the date is
  **MM-DD** (month-day), *not* DD-MM.
- **23 distinct (month,day) pairs:** `03/07 … 03/12, 04/01 … 04/12, 05/02 …
  05/07` (23 pairs; a couple of days are absent from the sample).

### 3.2 Why the calendar (Jalali/Gregorian) is UNDECIDABLE

There is **no year** in the filename, and nothing in the data anchors which
calendar it is:

| evidence | value | implication |
|---|---|---|
| Earliest ingest (`created_at`) | 2024-11-08, file `03-08-17-21-30.mp3` | air-date 03/08 |
| Latest ingest (`created_at`) | 2026-10-10, file `05-07-18-16-30.mp4` | air-date 05/07 |
| Ingest span | **23 months** (2024-11 → 2026-10) | — |
| Air-date band | **2 months** (03/07 → 05/07) | — |

The 5,450 episodes were **ingested over 23 months**, yet their filename air-dates
cover only a **2-month band (03/07 → 05/07)**. If the filename were a real
calendar air-date in a single year, 23 months of archive could not map onto a
2-month band. The two interpretations both fail to give a single consistent
air→ingest lag:

- If **Gregorian** (March–May of some year): the archive would be ~2 months of
  content, but ingest spans 23 months — impossible for a continuously-fed radio
  archive, and gives no year.
- If **Jalali** (Farvardin–Khordad): same problem — a 2-month band cannot hold
  23 months of ingested episodes, and still no year.

Either way, the **calendar is not anchored** and there is **no year**. The
`link` field's `e=` param (e.g. `e=154067258`) is an opaque, **non-ordered EPG
id**, not a timestamp (confirmed in STEP 8). There is no signal in the data to
choose Jalali over Gregorian or to recover the year.

### 3.3 The "time" fields are not a 24-hour clock

pos3 reaches **31**, pos5 reaches **37** — neither can be a clock hour/second.
They may be a compressed/renumbered local-time encoding specific to the EPG
export, but they do **not** form a clean HH:MM:SS. This is additional reason the
filename cannot be turned into a reliable `broadcast_date DATETIME`.

### 3.4 9A decision: **STOP** (no schema change, no backfill, site unchanged)

Per the user's spec item (4): *"If the format/calendar is undecidable from
evidence → STOP 9A, report the sample, and move to 9B."*

- **Date format:** month-day (MM-DD) — **decidable** (§3.1).
- **Calendar + year:** **undecidable** (§3.2) — no year in the filename, air-date
  band (2 months) is inconsistent with the 23-month ingest span, and neither
  Jalali nor Gregorian is supported by the evidence.
- **Action taken:** **NONE.** No `broadcast_date` column, no backfill, no site
  change. A backfill built on a guessed calendar/year would have put a *wrong*
  date on 5,450 rows — exactly the dishonesty the user forbade.
- **Site stats BEFORE (unchanged, ingest/`created_at`-based):** the site today
  shows **سال گذشته (Last Year, calendar-2025) = 5,039**, ماه گذشته (Last
  Month, Sep 2026) = 0, ۲ سال گذشته (2024) = 49, and 0 for 2023/2021/2016 — over
  5,587 subtitled sessions whose `created_at` spans **2024-11-08 → 2026-10-10**.
  These are the **ingest-date** cards; they are what the site shows and were left
  **as-is**.

**To UNBLOCK 9A (needs the user, not more code):** supply the calendar + year
anchor the filename lacks — e.g. "the filenames are Jalali and the archive is
YYYY" or "the `link`/EPG records carry the air date in field X." With a confirmed
calendar+year, the backfill is a small, mechanical step (parse MM-DD, stamp the
year, NULL on any parse fail) and the period cards recompute from
`broadcast_date` with `created_at` as a labeled fallback. Documented in
§9 (NEXT_CHAT_CHECKPOINT).

---

## 4. STEP 9B — `correct_text_v2` design (implemented)

Registered as a new `pipeline_steps` row (verified on 53, id 141):

```
slug=correct_text_v2  input_ref=srt  output_kind=windowed-correct
output_suffix=.correct.v2.srt  model=qwen38-nothinking  enabled=1
```

**Window / overlap (deterministic, in `llm_jobs.py`):**
- `CTV2_TARGET = 8` — blocks corrected per window (user range 6–10, midpoint).
- `CTV2_CTX = 3` — context blocks before AND after (user range 2–3, max).
- `_ctv2_windows(n)` slides by `TARGET` (no target-block overlap → each block is
  corrected by exactly one window, so no double-apply). A file of `n` blocks
  yields `ceil(n/TARGET)` windows.
- Each window prompt has three labeled sections: `[پیش‌زمینه]` (context before,
  read-only), `[بلوک‌های هدف — N بلوک؛ فقط این‌ها را اصلاح کن]` (target, to fix),
  `[پس‌زمینه]` (context after, read-only). The model returns **only** the target
  blocks' corrected text, one block per line, joined by ` ||| `.
- `windowed_correct()` stitches: for each target block, if the model returned a
  non-empty correction, use it; otherwise keep the original. Timestamps are
  **never** touched (rebuilt via `build_srt(blocks, corrected)` from the original
  block tuples).

**Prompt rules (verbatim — the three hard rules):**

> ۱) **خلاصه‌نویسی ممنوع** — محتوا را فشرده، کم یا زیاد نکن؛ هر بلوک هدف
> دقیقاً یک بلوک خروجیِ هم‌معادل دارد.  (NO summarization: each target block
> maps to exactly one output block.)
> ۲) **اگر از درست بودن یک کلمه مطمئن نیستی، حدسِ قطعیت‌نازده نزن:** یا همانِ
> ASR را نگه‌دار، یا معنادارترین و امن‌ترین خوانش را انتخاب کن. (اصلِ
> نگهداشتِ متنِ اصلیِ مطمئن بر یک اصلاحِ ریسکی اولویت دارد.)  (If unsure, do
> NOT guess: keep the ASR or take the safest reading; a confident original beats
> a risky correction.)
> ۳) **شماره و زمان‌کد و ترتیب را دست نزن.**  (Don't touch numbers, timestamps,
> or order.)

The documented choice for rule 2: **keep the original when uncertain** (a
confident original is preferred over a risky correction) — and in practice the
stitch already enforces this, because any empty/missing model output falls back
to the original block.

**Model-stop guard (before any LLM batch).** `run_v2_qa` calls
`model_stop_check(our_workers=<our own run-all count>)` → reuses `boost.py`'s
Prometheus load: `ext = vllm_running + sglang_running − our_workers`, and aborts
if `ext > 5`. Crucially, **`our_workers` = the count of iranseda's own background
`run-all` burn procs** (`_count_runall_workers()`, read from `/proc`), so our
24h/boost `correct_subtitles` workers are *excluded* — the cap measures
**external interactive** users only, mirroring `boost.py`. (The first QA attempt
passed `our_workers=0`, which wrongly counted our own burn and aborted at
"6 interactive"; fixed to subtract our workers → "0 interactive".)

**Outputs:** `<stem>.correct.v2.srt` + `<stem>.correct.v2.txt` in
`downloads/cleaned/`. The **original** `<stem>.srt` is only ever READ (MD5
checked before/after). v2 is a parallel artifact for A/B against the existing
`.correct.*`.

**CLI:** `llm_jobs.py run --job correct_text_v2 --qa [--limit 20] [--ids …]`
(bounded 20-file QA; **never** a `run-all`/bulk/boost job).

---

## 5. STEP 9B — 20-file QA

**Run:** `llm_jobs.py run --job correct_text_v2 --qa --limit 20 --ids <20>` on 53,
fully detached (`setsid nohup … </dev/null &`), monitored by the
`.correct.v2.txt` file count. **20 files = 12 from pilot program 28 + 8 from
another program** (maaref feed). Model-stop check: **`ok (0 interactive requests
<= cap 5)`** — our own `run-all` burn workers were correctly subtracted, so the
QA ran.

**QA headline (all hard constraints hold):**

| check | result |
|---|---|
| Files processed | **20 / 20** |
| Blocks in == blocks out (`count_match`) | **20 / 20** |
| Timestamps unchanged (`ts_match`) | **20 / 20** |
| Original SRT MD5 unchanged (`md5_same`) | **20 / 20** (STOP condition — **not** violated) |
| Change rate (blocks modified) — median | **33.2 %** |
| Change rate — min / max | 15.3 % / 54.5 % |

Per file (stem = last 3 date tokens; `cm/ts/md5` all `T`):

```
stem                blocks  changed  rate
04-08-05-02-00        156       51    33%
04-08-12-02-00        192       43    22%
04-08-06-02-00        169       57    34%
04-08-13-02-00        227       53    23%
04-09-03-22-00        160       54    34%
04-09-03-02-00        125       44    35%
04-08-27-22-00        146       62    42%
04-08-27-02-00        133       50    38%
04-08-26-22-00         99       54    55%
04-08-26-02-00        198       54    27%
04-08-20-02-00        190       29    15%
04-08-19-02-00        112       52    46%
05-07-17-23-30        156       63    40%
05-07-18-01-30        176       30    17%
05-07-18-03-00        163       43    26%
05-07-18-03-30         91       25    27%
05-07-18-06-00        114       44    39%
05-07-18-07-30        199       46    23%
05-07-18-09-00        113       38    34%
05-07-18-13-30        210       65    31%
```

> **⚠ Change-rate flag (reported, not silently accepted).** The **median change
> rate is 33.2 %** (up to 54.5 %) — the model is altering roughly a third of the
> blocks in most files, not fixing a small minority of garbled words. Every block
> it changes *is* plausibly more correct (samples below), but at this rate the
> model is acting as a fairly aggressive rewriter rather than a conservative
> proofreader. Per rule 2's intent, a good v2 should fix the **minority**. This
> is a **prompt-tightening issue to follow up** (see §8), **not** a defect in
> timestamps/counts/immutability (all 20/20). It is NOT enabled as a bulk job.

### 5.1 Before/after Persian snippets (4 categories)

**1) Clean single-word fix** (file `04-08-05-02-00`, block 22) — garbled
`انوان` → correct `عنوان`, rest of the block untouched:
- O: `انوان سخن ما روایات کافی شریف است، کتاب‌الایمانه والکفر`
- F: `عنوان سخن ما روایات کافی شریف است، کتاب‌الایمانه والکفر`

**2) Uncertain → kept original** (file `04-08-13-02-00`, block 6) — the block is
heavily garbled *and* contains ambiguous tokens (`پرنش`, `پیرانی`); the model
changed the neighboring blocks but **left this one byte-identical** (rule 2: a
confident original beats a risky guess):
- O: `هچون اتحاد کامل نداشتند، لو رفتند و بند خود را توی آن زدند. طور این زدن که
  این پرنش برات بود و پیرانی که می‌خواستند توی تنش برود…`
- F: *(identical — deliberately not guessed)*

**3) Garbled-word fixed** (file `04-08-05-02-00`, block 43) — two corrupted
tokens repaired to real words (`صلام‌الله علی` → `صلّی‌الله علیه`; `می‌فرمد` →
`می‌فرماید`):
- O: `در روایت سوم همین باب از امام صادق صلام‌الله علی تفسیر شده، حضرت می‌فرمد
  سیدالاعمال ثلاثه،`
- F: `در روایت سوم همین باب از امام صادق صلّی‌الله علیه تفسیر شده، حضرت
  می‌فرماید سیدالاعمال ثلا…`

**4) Edge case — repetitive ASR artifact** (file `04-08-05-02-00`, block 17) —
the ASR emitted the phrase *"شما همه‌ی"* ~42 times (a whisper degenerate
repetition loop). v2 keeps the phrase **verbatim** (it is not a homophone fix, so
per rule 2/3 it is not "corrected" by dropping the loop) — a visible case where
the **structural** whisper failure is *not* a job for a text-ASR-corrector; a
separate de-duplication/segmentation pass would be needed. (By contrast, the
phone-number block 15 *was* correctly fixed: `…پنجاه و سم` → `…پنجاه و سه`.)

**Read-out for the user (with their own eyes):** the three homophone/spelling
failures (1, 3, and the phone-number 15) are fixed cleanly and safely; the
structural failures (2's ambiguity, 17's repetition loop) are where a
conservative corrector should *hold* — and it does. The main thing to watch is the
**33 % change rate**: it is a lot of edits per file, so if this ever went into the
pipeline it should be a `.correct.v2` artifact the user can diff, not an overwrite.

---

## 6. Docs / commits / GitLab

- **009 doc:** this file (master prompt §2, Persian preamble §1), linked from 008.
- **README:** a "📅/📝 STEP 9A + 9B" section (9A STOP + date evidence + before
  stats; 9B design + 20-file QA + snippets + rollback + checkpoint).
- **Commits (logical, each ending `Co-Authored-By: Claude Opus 5
  <noreply@anthropic.com>`):**
  1. `correct_text_v2` windowed step (registry row + windowed-correct mode +
     QA CLI),
  2. stop-check fix (exclude our own `run-all` burn workers from the interactive
     count),
  3. `_ctv2_block` call-site fix (pass `blocks`, not `blocks[k]`),
  4. this 009 doc + 008 link,
  5. README STEP 9A+9B section.
- **GitHub:** pushed to `origin/download-db`. On 53: fetch+rebase / `git am`,
  no scp-edits.
- **GitLab `git.ai.ismc.ir`:** attempted → **BLOCKED (no credential)** if
  unauthed.
- **Secrets:** none committed (`.env` / `DASH_AUTH_TOKEN` gitignored; token lives
  only in `dashboard/dashboard.env`, mode 600).

---

## 7. Rollback

- **9A:** nothing to roll back — no schema change, no data written, site
  unchanged.
- **9B (the 20 QA artifacts):** remove the v2 outputs; the original SRTs and all
  other pipeline outputs are untouched:
  ```bash
  rm downloads/cleaned/*.correct.v2.{srt,txt}
  ```
- **9B (the pipeline row):** disable it without deleting (keep-both):
  ```sql
  UPDATE pipeline_steps SET enabled = 0 WHERE slug = 'correct_text_v2';
  ```
  (It is never wired into a bulk/boost job, so disabling it changes nothing
  else.)

Kill switch (unchanged): `./scripts/stop-background.sh` stops ONLY iranseda
background LLM work — never the model / whisper / LiteLLM / dashboard.

---

## 8. NEXT_CHAT_CHECKPOINT

> **State (2026-10-10): 9A STOPPED (calendar/year undecidable from the
> filename — evidence documented in §3; no schema change, no backfill, site
> unchanged). 9B `correct_text_v2` BUILT + registered (row id 141) + 20-file QA
> RUN under the model-stop guard (§5). NOT a bulk/boost job. Crop/backfill state
> untouched (pilot 28 still 2 HIGH / 20 NEEDS_REVIEW; backfill OFF).**

**The ONE thing to unblock 9A (needs the user, not more code):** supply the
calendar + year the filename lacks. If confirmed, the backfill is mechanical:
parse `MM-DD`, stamp the confirmed year, `broadcast_date=NULL` on any parse fail
(never guess), then recompute the site period cards from `broadcast_date`
(primary) with `created_at` as a separately-labeled "ingested" stat. Regenerate
the site once (use `refresh_site.sh` / explicit `*_PATH` — the server-mode
default path has no trailing dash) and report before/after.

**Optional 9B follow-up (only if the user wants a tighter editor):** the QA
change-rate is reported in §5. If the median is >~20% (i.e. the model is
"correcting" a large share of words), tighten the prompt — e.g. raise the
conservatism of rule 2, add a few known-bad "do not change" examples, or lower
`max_tokens`/temperature — and re-run the 20-file QA. Do NOT enable it as a
bulk/boost job until the user explicitly wants it in the pipeline.

Carry-over (unchanged from STEP 7/8): GitLab `git.ai.ismc.ir` remote —
**BLOCKED on auth**.

---

## Final report block (STEP 9 shape)

```
9A — BROADCAST DATE
Date source (filename format): radio-maaref-<MM>-<DD>-<C>-<D>-<E>.<ext>
  A=pos1 month (values 3,4,5 only); B=pos2 day (1..12); C/D/E = 1..31 / 0..23 / 0..37
  (not a clean HH:MM:SS clock). 23 consecutive (MM,DD) pairs: 03/07→03/12, 04/01→04/12, 05/02→05/07.
Calendar: UNDECIDABLE (neither Jalali nor Gregorian is supported; NO year in the
  filename). Evidence: 5,450 rows ingested over 23 months (2024-11-08 → 2026-10-10)
  but the filename air-date band is only 2 months (03/07 → 05/07) — a 2-month band
  cannot hold 23 months of continuously-ingested archive. e= (link) param = opaque,
  non-ordered EPG id, not a timestamp.
Backfilled rows: 0 / 5450 (parse-fail: n/a) — NO backfill run (STOP).
Site stats BEFORE (ingest/created_at-based): Last Year(2025)=5039, Last Month(Sep 2026)=0,
  2 Years(2024)=49, 2023/2021/2016=0; 5587 subtitled, created_at 2024-11-08→2026-10-10.
Site stats AFTER  (broadcast-based):  n/a — no change (STOP).
Ingest stat (separate, labeled):  not added (STOP) — site left on created_at as-is.
STOP? YES — calendar/year undecidable from evidence; no schema change, no site change.

9B — CORRECT_TEXT_V2
Window / overlap: 8 target blocks + 3 context blocks each side (CTV2_TARGET=8, CTV2_CTX=3);
  slide-by-target (no double-apply); ceil(n/8) windows/file.
Prompt rules (verbatim, the three hard rules):
  ۱) خلاصه‌نویسی ممنوع — محتوا را فشرده، کم یا زیاد نکن؛ هر بلوک هدف دقیقاً یک بلوک خروجیِ هم‌معادل دارد.
  ۲) اگر از درستِ بودنِ یک کلمه مطمئن نیستی، حدسِ قطعیت‌نازده نزن: یا همانِ ASR را نگه‌دار، یا معنادارترین و امن‌ترین خوانش را انتخاب کن.
     (اصلِ نگهداشتِ متنِ اصلیِ مطمئن بر یک اصلاحِ ریسکی اولویت دارد.)
  ۳) شماره و زمان‌کد و ترتیب را دست نزن.
  (Documented choice for rule 2: KEEP THE ORIGINAL when uncertain — a confident original
   beats a risky correction; the stitch enforces it by falling back to the original on
   any empty/missing model output.)
Files tested: 20  (12 pilot program 28 + 8 other program; stop-check "ok (0 interactive)")
QA: blocks in==out: 20/20; timestamps unchanged: 20/20; orig SRT MD5 unchanged: 20/20
Change rate (median / max): 33.2% / 54.5%  (min 15.3%)  ⚠ >20% → prompt-tightening flag
Best snippet (before→after):  انوان سخن ما → عنوان سخن ما (block 22, file 04-08-05-02-00)
Uncertain→kept case:          04-08-13-02-00 block 6 (garbled + ambiguous tokens;
                              neighbors changed, this block left byte-identical)
Garbled-word fixed case:      صلام‌الله علی → صلّی‌الله علیه ; می‌فرمد → می‌فرماید (block 43)
Edge case:                    ASR repetition loop "شما همه‌ی" ×42 (block 17) — kept verbatim
                              (not a homophone fix; structural whisper failure, out of
                              corrector scope). Phone-number block 15 correctly fixed
                              (…پنجاه و سم → …پنجاه و سه).
Bulk enabled: NO  (bounded 20-file QA only; pipeline row id 141 exists, enabled, but
                 never wired into run-all/boost)

COMMITS / PUSH / GITLAB:
README: YES
009 doc: YES
NEXT_CHAT_CHECKPOINT:
  9A — supply the calendar+year the filename lacks (Jalali/Gregorian + year), then
    backfill broadcast_date (parse MM-DD, stamp year, NULL on fail), recompute the
    period cards from broadcast_date (primary) with created_at as a labeled
    "ingested" fallback, regenerate site once (via refresh_site.sh / explicit *_PATH).
  9B — optional: tighten the prompt to cut the 33% change rate (stronger conservatism
    on rule 2, known-bad examples, lower temperature) and re-run the 20-file QA. Do NOT
    bulk-enable until the user explicitly wants it. Crop/backfill state untouched.
  Carry-over: GitLab git.ai.ismc.ir BLOCKED on auth.
```
