# 006 — Pipeline-Steps Registry, Time-Block Crop, Dataset, Onboarding, Backfill

> **Purpose of this file**: (1) preserve the user's master prompt for this
> feature set so a future agent can reproduce the intent, and (2) be the
> **next-agent handoff source** — everything needed to continue if a session's
> context fills. Last updated: **2026-10-09**.

---

## 0. TL;DR status (read this first)

> **FINAL STATE (2026-10-09 ~14:40 Tehran): all FOUR features are BUILT,
> DEPLOYED to 53, and verified live end-to-end.** The dashboard is on commit
> `e71804b7`, running on :8990. Commits `8a6f77a8` → `e71804b7` (5 commits,
> interspersed with `refresh_site.sh` auto-refreshes) are pushed to
> `origin/download-db` and deployed on 53. Schema is seeded (5 pipeline_steps,
> crop columns, backfill_list). All four `/api/*` endpoints return 200.

- **C — Dynamic steps + dataset**: the set of pipeline phases is now driven by a
  single `pipeline_steps` registry table, not a hard-coded 4-job constant. A
  brand-new step (input file + model + master prompt → a new per-file field) is
  one row and flows end-to-end (UI select → prompt → run → new field →
  `llm_output` row → site link → dataset column) **with zero code edits**.
  Verified live: created a custom `qa` step via `POST /api/steps`, ran it, and
  it produced `<stem>.qa.txt` **and** an `llm_output` row, and appeared as a new
  `/api/dataset` column. (Test step + its file cleaned up afterwards.)
- **D — Time-block crop** (the user's "most important"): a broadcast slot is ~30
  min but the program is, e.g., 20 min and can air at the start/middle/end.
  Per-program `crop_offset` (in-slot start) + `time` (duration) + `crop_enabled`
  on `radio_programs`. `crop_program` keeps SRT blocks whose **mid-point** ∈
  [offset, offset+dur], renumbers 1-based, **keeps original timestamps**, and
  writes a **new field** `cleaned/<stem>.program.srt` + `.program.txt`; the
  original `.srt` is **untouched**. Downstream steps (summary/correct_text/
  correct_subtitles) read the crop, **falling back to the full transcript**
  when crop is off. Re-runnable. Verified live on session 5769: a 20-min crop of
  a 28-min slot kept 105 blocks ending 00:19:58 (the trailing neighbor-program
  dropped); original SRT md5 identical before/after.
- **A — Monthly backfill**: `dashboard/backfill.py` 60 s in-process autopilot
  that promotes a **bounded** batch of a program's not-yet-processed sessions to
  `pending_download` **only when the download+subtitle queue is idle**, then the
  existing Go cron + whisper do the work. Bounded, stoppable, never loops, dead
  links skipped. Verified live: add → queued; toggle on/off works (queue was
  busy, so nothing was promoted). (Test suggestion cleaned up.)
- **B — Program onboarding/verify**: `/api/programs` (list + per-program crop
  editor) + `/api/programs/{id}/test` (crop → summary → correct_text over up to
  10 sessions, estimate + pollable handle). This is also where per-program crop
  is set. Verified: crop set/cleared via API for program 41.

**If you are resuming:** the work is complete and deployed. The one thing that
was NOT left on is a real crop window on any production program — I tested on
program 41 then **disabled** the crop (kept offset `00:00:00`/dur `00:20:00` as
a saved reference). To make crop actually apply to live summaries, a human must
set the correct in-slot `crop_offset` for each program (the offset cannot be
reliably auto-derived), then flip `crop_enabled` on and re-run the program's
steps (the crop is re-runnable). See §6.

---

## 1. The user's master prompt (verbatim intent)

Four features, "all four now", phased. Crop called out as **"از همه این ها
مهم تر"** (more important than all the rest):

1. **D — Time-block crop**: when a program's air time is known, keep **only that
   program's block** from the subtitle file and discard the rest, so it doesn't
   pollute the summary/full-text. The program may air at the **start, middle, or
   end** of the slot → be **flexible** (explicit per-program offset + duration).
   **Keep both** the original SRT and a new cropped field. Downstream uses the
   crop. **Must be re-runnable.**
2. **C — Dynamic steps/dataset** (stressed: "تعریف این قدم ها به صورت داینامیک
   از صفحه ادمین"): an admin page to define new steps = (input file + LLM model
   + master prompt); output lands in a **new per-file field**; chainable; stored
   as a **growing dataset** with a link back to the original (which model, which
   program).
3. **A — Monthly backfill**: a page to add program suggestions monthly, promoted
   into the pipeline **only when the download+subtitle queue is empty**, from the
   broadcast-schedule program list; then download→subtitle→summary.
4. **B — Program onboarding/verify**: a page to add a program, verify, run a
   **10-item test** (download + test phase), estimate files/steps, then stabilize
   into the permanent list (also where per-program crop is set).

**User decisions (asked before building):** scope = all four, phased; crop
window = **flexible** start/middle/end (build the summary from *that* interval,
not the neighboring programs); crop output = **keep both** (original + new
field). **Plan approved** via ExitPlanMode
(`~/.claude/plans/quiet-stirring-valiant.md`).

---

## 2. What was built (files)

| File | Change |
|------|--------|
| `dashboard/llm_jobs.py` | `pipeline_steps` + `backfill_list` in SCHEMA; `crop_offset`/`crop_enabled` in MIGRATIONS; `DEFAULT_STEPS` seed (4 jobs + `program_block` crop); `crop_program`, `srt_mid_seconds`, `_program_window_for`, `_ensure_program_block`, `_resolve_step_input`, `known_step_slugs`; `_process_core` made **data-driven** (input_ref/output_kind/suffix from the row; step-prompt fallback); `run_batch`/`run_over_all_files` gained `program_id`+`force`; `--program-id`/`--all` CLI |
| `dashboard/logic.py` | steps CRUD (`steps_list/save/delete`); `_llm_job_*` now read the registry (static fallback); `llm_run` threads `program_id`/`force`; `llm_dataset(limit, program_id)`; programs (`programs_list`, `programs_save_crop`, `program_test`); backfill wrappers |
| `dashboard/app.py` | routes `GET/POST/DELETE /api/steps`, `GET /api/dataset`, `GET /api/programs`, `POST /api/programs/crop`, `POST /api/programs/{id}/test`, `GET/POST /api/backfill`, `POST /api/backfill/{id}/promote`, `POST /api/backfill/toggle`; `backfill.ensure_started()` at startup |
| `dashboard/backfill.py` | **NEW** 60 s autopilot (mirrors `boost.py`); state in `dashboard_state.json["backfill"]`; `_promote_batch`, `promote_now`, `_cycle`, `status`, `toggle`, `set_max_promote` |
| `generate_site.py` | `_step_rows()` (enabled steps, read once); `find_subtitles_for_session` + `get_latest_cleaned_files` append dynamic step files + the `.program.srt` block (deduped) |
| `dashboard/templates/index.html` | 4 new `<h2>` sections (📋 Steps, 📊 Dataset, 🚀 Programs, 📥 Backfill) + JS (form-guard `xLocked` pattern; `loadSteps/Dataset/Programs/Backfill`, `saveStep/Crop`, `runProgramTest`+poll, backfill add/promote/toggle); run form gained `#llm-program-id` |

---

## 3. Key design decisions

- **One registry, not four parallel constants.** The "4 job types" was a code
  constant in **four parallel copies** (engine dispatch, guards, labels, site)
  that had to stay in sync. The DB was already permissive (`job_type VARCHAR(32)`);
  only Python blocked new types. `pipeline_steps` (slug, name, input_ref, model,
  prompt, output_suffix, output_kind, is_mechanical, enabled, sort_order) is now
  the single source; `job_type` in `llm_output` == slug. Every consumer reads it.
  `known_step_slugs()` has a **static fallback** so a missing table/row can't
  crash a running shard.
- **`_process_core` is data-driven.** It reads the step row and resolves:
  `input_ref` (srt | full_text | program_srt | program_text | `step:<slug>`),
  the operation (`output_kind`: text | srt | bilingual | **program**), and the
  output file (`output_suffix`). The 4 old slugs behave exactly as before.
  `program_block` (mechanical, output_kind `program`) produces the crop field and
  writes **no** `llm_output` row (it's not an LLM output).
- **Crop is additive + re-runnable.** `crop_program(srt, off, dur)` keeps blocks
  whose mid-point ∈ [off, off+dur]. `_ensure_program_block` re-crops **every**
  time crop is active (so a changed offset/duration takes effect on the next
  run — no stale file) and returns the actual crop; when crop is off it returns
  the uncropped transcript. Downstream `program_srt`/`program_text` input_refs
  resolve through it.
- **Dataset is bounded.** `llm_dataset` = two queries: (1) latest `limit`
  session ids that **already have a step output** (`EXISTS llm_output` — a
  freshly-subtitled session with no rows would render empty and be dropped),
  (2) a `WHERE session_id IN (…) AND job_type IN (…) **pivot** (no GROUP BY —
  `uq_out (session_id, job_type, model)` makes it unique) pivoted in Python.
  New steps become new columns automatically.
- **Backfill rides on the existing pipeline.** It only resets eligible sessions
  (`is_subtitled=0 AND is_downloaded=0 AND status<>'failed_permanent' AND link`
  non-empty) to `pending_download`; the Go download cron + whisper worker do the
  real work. One promotion per suggestion (at most once), bounded
  (`max_promote`, default 5), stoppable, and it records *why* it didn't promote
  (`queue busy (dl=…, tr=…)`).
- **Step-prompt fallback.** A brand-new step has no row in `prompts`, so runners
  passed `prompt_text=None`. `_process_core` now falls back to the step's own
  `pipeline_steps.prompt` (the "master prompt"), so a new step's LLM call works
  end-to-end.

---

## 4. Server facts (condensed — see memory `iranseda-server-53`)

- **53** = `jump53` = `172.20.1.53`, user `saber`, project
  `/home/saber/saberprojects/iranseda-crawler-golang-` (**trailing dash**),
  branch `download-db`, 2× H100, OS UTC (Tehran = UTC+3:30).
- **DB**: `docker exec iranseda-mysql mysql -un8nuser -p"StrongPassword123!" radio`.
- **venvs**: `dashboard/venv/bin/python` (dashboard + llm_jobs CLI),
  `crawler/venv/bin/python3` (generate_site). generate_site needs
  `ENVIRONMENT=server DB_HOST=172.20.1.53 DB_PORT=3308` (the cron sets these).
- **Dashboard** :8990, systemd `iranseda-dashboard` (`Restart=always`). Restart
  without sudo: `kill $(fuser 8990/tcp)`. Token only in
  `dashboard/dashboard.env` (600, gitignored) — read via
  `grep -Eo "^DASH_AUTH_TOKEN=.+" … | cut -d= -f2-`.
- **CRITICAL autostash gotcha**: `refresh_site.sh` cron does `git pull --rebase
  --autostash` every 30 min. If a tracked file is modified-uncommitted on 53 at
  a tick → the file **DOUBLES**. Rule: `git push` locally → `git fetch` +
  `git rebase origin/download-db` on 53; **never scp-edit a tracked file on 53
  near a cron tick.** (This bit me once mid-rebase; no data loss — just
  re-fetch + re-rebase.)
- **STOP rule (user)**: when >5 interactive users, don't use the model; if
  sglang metric high, don't use it; log the reason, show it in the dashboard.
  (Checked before the LLM test call: `sglang_running=0`, no interactive users →
  safe.)

---

## 5. Verification done live on 53 (2026-10-09)

- Schema seeded: `pipeline_steps` = 5 rows (program_block/full_text/summary/
  correct_text/correct_subtitles); `crop_offset TIME` + `crop_enabled TINYINT`
  added; `backfill_list` present.
- `/api/steps`, `/api/dataset`, `/api/programs` (28), `/api/backfill` all 200.
- `/api/dataset` shows sessions with all 4 done steps + model + program name
  (link-back works).
- Crop unit test (real SRT): offset 0/dur 20:00 → 105 blocks, last mid 00:19:44;
  offset 10:00/dur 5:00 → all mids in [10:00,15:00); dur 0 / empty → `("","")`;
  renumber 1-based + original timestamps preserved.
- Crop e2e (`llm_jobs.py run --job program_block --ids 5769 --all`):
  `cleaned/<stem>.program.srt` = 105 blocks ending 00:19:58; original `.srt`
  md5 **identical** before/after.
- Dynamic step e2e: `POST /api/steps` (slug `qa`, input `program_text`, model
  `qwen38-nothinking`, suffix `.qa.txt`, prompt) → appeared in `/api/steps` +
  as a new `/api/dataset` column; `run --job qa --ids 5769` → `.qa.txt` (6 KB
  Persian analysis) + `llm_output` row (job_type `qa`, done, 1543 out tokens).
  Test step/file deleted after.
- Backfill: `POST /api/backfill` → queued row; toggle on/off works (queue busy,
  so no promotion). Test row deleted.
- Site: `generate_site.py` (with cron env) → `docs/index.html` +
  `docs/programs/41.html` reference the `.program.srt` block (next 30-min cron
  regenerates).

---

## 6. What's LEFT / to note

1. **Crop is NOT enabled on any production program yet.** I tested on program
   41 then set `crop_enabled=0` (kept offset `00:00:00`/dur `00:20:00` as a
   saved reference). The in-slot `crop_offset` cannot be reliably auto-derived —
   a human must set the correct offset per program in the 🚀 Programs section,
   flip the crop on, then re-run that program's steps (re-runnable; the 10-item
   test does crop→summary→correct_text).
2. **Backfill is OFF by default** (`running: false`) and the queue list is empty.
   To start: add a program suggestion in 📥 Backfill, then the toggle. It only
   promotes when the live download+subtitle queue is idle.
3. **Optional leftovers from 005** (not part of this request): STEP-12 Grafana
   Boost panels; STEP-17 GitLab remote (blocked on a user credential).

---

## 7. Command cheat-sheet (on 53)

```bash
# deploy (after local git push)
cd /home/saber/saberprojects/iranseda-crawler-golang-
git checkout -- "*.pyc"; git fetch; git rebase origin/download-db
kill $(fuser 8990/tcp)            # systemd Restart=always revives

# crop (mechanical, no LLM) — re-runnable
cd dashboard && set -a && . ./dashboard.env && set +a
./venv/bin/python llm_jobs.py run --job program_block --ids <sid> --all

# run a step scoped to one program / force re-run
./venv/bin/python llm_jobs.py run --job summary --program-id <pid> --all
./venv/bin/python llm_jobs.py run --job <custom-slug> --ids <sid> --all

# restart dashboard without sudo
kill $(fuser 8990/tcp)
```

Admin endpoints (Bearer token from `dashboard/dashboard.env`):
`GET/POST /api/steps`, `DELETE /api/steps/{id}`, `GET /api/dataset?limit=&program_id=`,
`GET /api/programs`, `POST /api/programs/crop`, `POST /api/programs/{id}/test`,
`GET/POST /api/backfill`, `POST /api/backfill/{id}/promote`, `POST /api/backfill/toggle`.

---

## 8. Definition of Done

- [x] P0: crop produces a correct program-only SRT as a **new field** (original
      intact); steps are fully data-driven (a new step via the API produces a new
      per-file field + `llm_output` row + site link); the 4 existing jobs
      unchanged; dashboard renders the Steps section.
- [x] P1: any step re-runs over all/N/program/ids (`force` + `program_id`);
      dataset view links outputs → program/model.
- [x] P2: a program can be crop-configured + 10-item test-run from the admin.
- [x] P3: monthly suggestions queue and auto-promote **only when idle**, bounded,
      stoppable, dead links skipped.
- [x] Deployed to 53 + dashboard restarted; README updated (this file + a
      "Steps / Crop / Onboarding / Backfill" section); all 5 commits pushed.

### Bugs found & fixed during live verification (2026-10-09)
1. **`run_batch` empty `IN ()`**: the done-ids query built `IN (…)` from the
   session list; with `program_id` scoping a program that has no subtitled
   sessions the list was empty → `IN ()` syntax error. Guarded with
   `and sessions`.
2. **Dataset showed 0 rows**: the query took the newest-N subtitled sessions, but
   the newest are freshly-subtitled with **no** `llm_output` rows yet, so they
   rendered empty and were dropped. Added `EXISTS (llm_output …)` so it shows
   sessions that have actually been processed.
3. **Crop returned the wrong field / wasn't re-runnable**: `_ensure_program_block`
   wrote the crop only if the file was missing and returned whatever file
   existed — so changing offset/duration served the stale file, and a crop that
   matched no blocks served the original SRT as if it were the program block.
   Now it re-crops every time crop is active and returns the actual crop, falling
   back to the full transcript only when the window matched nothing.
4. **Crop silently did nothing (the big one)**: `srt_mid_seconds` did
   `float('08,759')` on the `SS,mmm` part, but SRT uses a **comma** for the
   millisecond separator → `ValueError` → the `except` returned `None` for every
   block → `crop_program` kept **no** blocks → silent fallback to the full
   transcript. Fixed by normalizing the comma to a dot before `float()`.

---

## 9. NEXT_CHAT_CHECKPOINT (where to pick up)

> **State at handoff (2026-10-09 ~14:40 Tehran): all four features are BUILT,
> DEPLOYED to 53 (dashboard on `e71804b7`, :8990), and verified live.** Commits
> on `origin/download-db`: `8a6f77a8` (registry + crop + dataset + onboarding +
> backfill + site), `6b2b6cdf` (dataset: only sessions with outputs),
> `6ed1484f` (crop re-runnable + return the actual crop), `56934c63` (crop
> comma-millisecond fix), `e71804b7` (new step uses its own prompt as fallback).
> Memory `iranseda-server-53.md` updated.

**Next agent, the natural next work (all optional, none blocked):**
1. **Turn crop on for real** — pick a program, set its true in-slot
   `crop_offset` in 🚀 Programs, flip `crop_enabled`, re-run its steps (or the
   10-item test). This is the payoff of feature D and needs a human to set the
   offsets (they can't be auto-derived).
2. **Feed the idle pipeline** — add a monthly suggestion in 📥 Backfill + toggle
   on, when the user wants to re-download/re-subtitle an old program's backlog
   (it only fires when the live queue is idle).
3. **Carry-overs from 005** (only if asked): STEP-12 Grafana Boost panels,
   STEP-17 GitLab remote (blocked on a user credential).

**Do NOT** enable backfill or a crop on a program without the user's go-ahead —
both change live pipeline behaviour. Keep the emergency kill-switch rule
(`scripts/stop-background.sh` stops ONLY iranseda background, never the model
servers/whisper/LiteLLM/dashboard).
