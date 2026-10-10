# 010 — Project Reporter / Publication Bot (skeleton) — STEP 9C

> **Purpose of this file:** (1) preserve the user's master prompt for the
> **Project Reporter / Publication Bot**, and (2) document what STEP 9C **built
> (the local half — the skeleton)** versus what is deliberately **NOT wired yet
> (the real transport to the user's German publication service)**, and (3) be
> the handoff source for the small **real-adapter follow-up** that lands the
> moment the service contract arrives.
> Last updated: **2026-10-11**.

---

## 0. TL;DR status (read this first)

The user runs a **publication web service of their own** (~5 years old, hosted in
Germany) that fans a report out to **Telegram / Bale / Eitaa / Soroush**. IranSeda
should send it a report when something notable happens. **That service's contract
is NOT available yet** (no known endpoint, auth scheme, payload shape, response
task-id location, status-check shape, or exact channel names).

So STEP 9C builds **everything EXCEPT the real transport**:

| Built now (skeleton) | NOT wired yet (real adapter) |
|---|---|
| `publication_task` table (idempotent, unique `idempotency_key`) | real `PublisherClient` (endpoints/auth/payload) |
| `report_event()` idempotent entry point | live pipeline event firing (download/whisper/LLM code) |
| state machine + bounded retries (3) + `check_after` schedule | post-URL / view-count harvesting (phase 3) |
| 60s worker (env-gated, **inert by default**) | real channels fan-out |
| `PublisherClient` ABSTRACT interface + honest `StubClient` | |
| `GET /api/reporter` + `POST /api/reporter/selftest` + dashboard section | |

The **stub never fakes a published state.** With the stub, a `queued` task is
marked **`skipped (publisher not configured)`** and never retried.

**No live pipeline event fires in this step** (by design) — the only thing that
can create a row today is the dashboard **self-test** button.

---

## 1. The user's architecture (master prompt, preserved)

End-to-end intent:

```
IranSeda code (download / whisper / LLM / git / milestone)
   └─ report_event(event_type, title, body, artifact_url, git_commit, channels, idempotency_key)
        └─ one row in publication_task (status = queued)         [IDEMPOTENT]
             └─ Publication Worker (60s in-process thread, dashboard/reporter.py)
                  └─ PublisherClient.publish(task)  ──>  external task id
                       └─ USER'S German publication web service
                            └─ fans out to Telegram / Bale / Eitaa / Soroush
                  └─ worker polls PublisherClient.check_status(external_task_id)
                       └─ status -> published, with post_urls {channel: url}
Phase 3 (LATER): metrics collector — harvest view counts into publication_task.views
```

**Idempotency requirement (load-bearing):** the same logical event, reported
twice, must produce **one** row and **no duplicate side effect**. This is
guaranteed by the `UNIQUE idempotency_key` on `publication_task` plus an
`INSERT ... ON DUPLICATE KEY UPDATE` that only refreshes `title`/`body` and
**never re-submits** an in-flight or terminal task.

**Why the real client is a separate adapter:** we must not guess at a 5-year-old
service we have no contract for. Every assumption (URL, auth, payload, response
field, channel name) would be wrong and hard to find later. So the transport is an
abstract `PublisherClient` with an honest stub; the real adapter is a small,
isolated change (`reporter.set_client(GermanAdapter())` + a class implementing
two methods). Nothing else has to change.

---

## 2. State machine (documented)

```
queued ──publish ok──> submitted ──check──> checking ──published?──> published
   │                          │                  │
   │ publish hard-fail        │ external fails    │ external fails
   ▼                          ▼                  ▼
 (retry to queued ≤3)      ┌─────────────────── failed (terminal)
   │                       │
   ▼ after 3 attempts      (stub, or manual disable)
 failed (terminal)         skipped (terminal — NOT retried)
```

* `queued → submitting → submitted → checking → published | failed`
* **`skipped`** = terminal for a task the worker cannot/will not send (stub, or
  manual disable). **Never retried** (no churn loop).
* A **`failed`** task returns to `queued` **only up to `MAX_ATTEMPTS` = 3**, then
  stays `failed` **forever** — it never loops.
* **`check_after` schedule (bounded):** first check **~5 min** after submit, then
  **+15 min**, then **+1 h**, then stays **+1 h** (indexed by attempt count,
  clamped).
* The worker is **inert unless `IRANSEDA_REPORTER_ENABLED` is truthy (default
  OFF)**. ON + stub → new `queued` rows are drained to `skipped` once each
  (terminal, no retry). ON + real client → advance due rows.

---

## 3. What was built (this STEP)

### 3.1 `publication_task` table (in `llm_jobs.ensure_schema` SCHEMA)
Same idempotent DDL location as `pipeline_steps` / `backfill_list`. Columns
(user's exact list):

```
id INT AUTO_INCREMENT PRIMARY KEY
event_type VARCHAR(64)
title VARCHAR(200)
body TEXT
artifact_url VARCHAR(512) NULL
git_commit VARCHAR(64) NULL
external_task_id VARCHAR(128) NULL
status VARCHAR(24) DEFAULT 'queued'   -- queued|submitting|submitted|checking|published|failed|skipped
channels VARCHAR(255) NULL
submitted_at DATETIME NULL
check_after DATETIME NULL
published_at DATETIME NULL
post_urls TEXT NULL          -- JSON: channel -> url
views TEXT NULL              -- JSON (phase 3, left for later)
last_checked_at DATETIME NULL
error VARCHAR(500) NULL
idempotency_key VARCHAR(191) NOT NULL UNIQUE
created_at / updated_at timestamps
attempts TINYINT DEFAULT 0
KEY k_pub_status (status, check_after)
```

`CREATE TABLE IF NOT EXISTS` → running `ensure_schema` twice is a no-op (idempotent).

### 3.2 `dashboard/reporter.py` (new module, mirrors boost/backfill shape)
* **`PublisherClient`** — abstract, exactly two methods:
  ```python
  class PublisherClient:
      def publish(self, task) -> dict:            # -> {"external_task_id": "..."}
      def check_status(self, external_task_id) -> dict:
          # -> {"state": "pending|published|failed",
          #     "post_urls": {channel: url}, "error": str|None}
  ```
  The docstring states the real implementation is a **separate adapter to be
  added when the German service contract arrives** — no endpoint/auth/payload
  assumed anywhere.
* **`StubClient`** (only concrete client now): `publish` returns
  `{"external_task_id": None, "error": "publisher not configured"}` and the
  worker marks the task **`skipped`** with `error='publisher not configured'` —
  **no retry loop, never fakes a published state.**
* **`report_event(event_type, title, body, artifact_url, git_commit, channels,
  idempotency_key)`** — single idempotent entry point. Auto-generates the key as
  `sha1(event_type + title + (artifact_url or '') + (git_commit or ''))` when not
  given. `INSERT ... ON DUPLICATE KEY UPDATE` refreshes only `title`/`body`.
* **Worker** — 60s thread (boost pattern). Gated by `IRANSEDA_REPORTER_ENABLED`
  (default **off**): off → does nothing; on + stub → `queued` → `skipped` (once).
  `ensure_started()` is idempotent and called from `app.py _startup()` alongside
  `boost.ensure_started()` / `backfill.ensure_started()`.
* **`status(limit=20)`** — per-status counts + totals + last N tasks +
  `enabled`/`client_configured` flags.
* **Event-type constants** `EVENT_TYPES` (`download_batch`, `transcribe_batch`,
  `program_summary_done`, `program_correct_done`, `dataset_ready`, `git_release`,
  `milestone`) are **defined but NOT fired** — no download/whisper/LLM code calls
  `report_event` yet.

### 3.3 Dashboard API + UI (auth-gated like the other `/api/*`)
* `GET /api/reporter` → enabled?, client configured?, per-status counts, last 20 tasks.
* `POST /api/reporter/selftest` → fires one `selftest` event, **idempotent per
  minute** (key `selftest:<YYYY-MM-DDTHH:MM>`), so a human can watch it land as
  `skipped (publisher not configured)` — proves the whole path with no transport.
* **📣 Reporter** `<h2>` section in `templates/index.html`: enabled/configured
  pills, per-status counts, last-20-tasks table, a **تست خودکار** (self-test)
  button. Uses the existing `api()`, `esc()`, pill classes, 30s auto-refresh
  (`loadReporter()` in `refresh()`).

---

## 4. The `PublisherClient` interface the real adapter MUST implement

```python
from dashboard.reporter import PublisherClient, set_client

class GermanServiceAdapter(PublisherClient):
    def publish(self, task):
        # task: dict of the publication_task row (event_type, title, body,
        #       artifact_url, git_commit, channels, ...).
        # POST to the user's service (endpoint + auth per the contract).
        # Return {"external_task_id": <id the service assigned>}.
        # On failure, return {"external_task_id": None, "error": "..."} (never fake).
        ...
    def check_status(self, external_task_id):
        # Query the user's service for this task.
        # Return {"state": "pending"|"published"|"failed",
        #         "post_urls": {channel_name: url}, "error": str|None}
        ...

# At startup (or behind an env/config flag), once the contract is known:
set_client(GermanServiceAdapter())
```

Only those two methods are consumed by the worker / state machine. The adapter
owns ALL knowledge of endpoint, auth, payload, response parsing, and channel
names.

---

## 5. Open contract questions for the user's German service

These are the inputs the real adapter needs. Answering them unblocks the
follow-up; nothing here assumes an answer.

1. **Publish endpoint + auth:** exact POST URL, and the auth scheme
   (API key / bearer token / basic / mTLS?). Where does the credential live?
2. **Payload shape:** what body does `publish` expect, and how do we map
   `event_type` / `title` / `body` / `artifact_url` / `git_commit` / `channels`
   onto its fields?
3. **Response → task id:** which response field is the task id the worker
   stores in `external_task_id`?
4. **Status-check endpoint + shape:** the GET (or POST) URL to poll a task, and
   how its response encodes pending / published / failed, and the per-channel
   post URLs.
5. **Exact channel names:** the keys to use in `post_urls`
   (`telegram`? `bale`? `eitaa`? `soroush`?) and whether the request must name
   which channels to target.
6. **View counts (phase 3):** does any channel expose view counts via API, and
   via which endpoint? (Drives the `publication_task.views` column + the later
   metrics collector.)
7. **Retry / rate semantics:** does the service have a per-report rate limit or
   idempotency token of its own we should pass?

---

## 6. Deployment / verification (this STEP)

* Local == origin pushed to `origin/download-db`; 53 `git fetch; git rebase
  origin/download-db`; dashboard restarted via `kill $(fuser 8990/tcp)`
  (systemd `Restart=always`).
* Verified: `ensure_schema` idempotent (run twice, no error); `report_event`
  idempotent on `idempotency_key`; `GET /api/reporter` shows skeleton state
  (disabled / stub, 0 tasks); `POST /api/reporter/selftest` → one
  `skipped (publisher not configured)` row; a second selftest in the same
  minute does **not** duplicate; dashboard section renders; `/api/health`
  green; boost / backfill / crop untouched.
* GitLab push attempted; recorded as **BLOCKED (credential not provisioned)**
  if it fails auth (standing state, unchanged by this STEP).

---

## 7. NEXT_CHAT_CHECKPOINT

* **Skeleton complete.** To go live, obtain the German service contract (§5),
  implement `GermanServiceAdapter(PublisherClient)`, `reporter.set_client(...)`,
  set `IRANSEDA_REPORTER_ENABLED=1` in the dashboard env, then begin firing
  `report_event(...)` from the real pipeline sites (starting with the
  `EVENT_TYPES` constants).
* **Do not** bulk-wire live event firing before the real client is in place —
  with the stub it only ever produces `skipped` rows.
* Phase 3 (view-count metrics collector) is deferred; the `views` column is
  reserved and untouched.
* Carry-over: **GitLab `git.ai.ismc.ir` push BLOCKED on auth** (no credential on
  53/local).
