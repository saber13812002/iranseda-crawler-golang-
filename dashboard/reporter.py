"""
iranseda Project Reporter / Publication Bot — SKELETON (STEP 9C).

Goal (eventually): when something notable happens in the pipeline (a download
batch lands, transcriptions finish, a program's summary/correction is done, a
dataset is ready, a git release ships, a milestone), IranSeda should fan a short
report out to the user's messaging channels (Telegram / Bale / Eitaa / Soroush)
through the user's OWN external publication web service (5 years old, hosted in
Germany).

Architecture (the user's, end to end):

    IranSeda code
        └─ report_event(...)            # idempotent, one DB row per event
             └─ publication_task row (status=queued)
                  └─ Publication Worker (60s thread, this module)
                       └─ PublisherClient.publish(task)      # -> external task id
                            └─ user's German publication web service
                                 └─ fans out to Telegram/Bale/Eitaa/Soroush
                  └─ worker polls PublisherClient.check_status(external_task_id)
                       └─ state -> published, with post_urls {channel: url}

WHY THIS IS A SKELETON
  The external service's CONTRACT is not available yet: we do not know its POST
  endpoint, auth scheme, payload shape, where the task id comes back, its
  status-check endpoint, or its exact channel names. So this step builds
  everything EXCEPT the real transport:

    * the `publication_task` table (idempotent, unique idempotency_key),
    * the `report_event()` entry point (idempotent insert),
    * the state machine (bounded retries, no infinite loops),
    * the 60s worker (gated by env, INERT by default),
    * the dashboard API + UI section,
    * a `PublisherClient` ABSTRACT interface with a no-op `StubClient`.

  The REAL transport is a small, separate adapter to be written the moment the
  contract arrives. NO endpoint, auth scheme, or payload shape is assumed
  anywhere in this file. The stub NEVER fakes a published state.

State machine (documented per spec)
  queued -> submitting -> submitted -> checking -> published | failed
  `skipped` is a terminal state for a task the worker cannot / will not send
  (e.g. the transport is the stub, or a manual disable). A `failed` task goes
  back to `queued` only up to MAX_ATTEMPTS (3); after that it stays `failed`
  forever (it never loops). `check_after` schedule is bounded: first check ~5
  min after submit, then +15 min, then +1h, then stays +1h.

Safety
  * Gated by env IRANSEDA_REPORTER_ENABLED (default OFF). Off -> the worker does
    nothing. On + stub -> new `queued` tasks are marked `skipped` with the clear
    reason "publisher not configured"; the stub is NEVER retried (no churn).
  * No live pipeline event fires in this step. The known event types are defined
    as constants, but NO download/whisper/LLM code calls report_event yet. The
    ONLY thing that can create a row today is the admin "self-test" POST.
"""
import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.environ.get(
    "IRANSEDA_ROOT", os.path.abspath(os.path.join(BASE_DIR, ".."))
)
LOG_PATH = os.path.join(PROJECT_ROOT, "scripts", "logs", "reporter.log")

# Environment gate. Default OFF -> the worker is fully inert. Only when set to a
# truthy value does the worker act (and, with the stub, it marks new tasks
# `skipped` rather than looping).
ENABLED_ENV = "IRANSEDA_REPORTER_ENABLED"

# Bounded retry policy: a failed task returns to `queued` at most this many
# times before it is left `failed` permanently (never an infinite loop).
MAX_ATTEMPTS = 3

# check_after schedule (minutes): first check 5 min after submit, then 15,
# then 1 h, and stay at 1 h. Indexed by attempt count (clamped).
_CHECK_SCHEDULE_MIN = [5, 15, 60, 60]

# Terminal states (never advanced again by the worker).
_TERMINAL = {"published", "failed", "skipped"}

# The user's known event types. Defined so future pipeline code has stable
# names to call report_event with. NOTHING calls report_event for these yet in
# this step — they are just constants (see the module docstring).
EVENT_TYPES = (
    "download_batch",
    "transcribe_batch",
    "program_summary_done",
    "program_correct_done",
    "dataset_ready",
    "git_release",
    "milestone",
)

_lock = threading.Lock()
_running = False           # thread guard (ensure_started idempotent)
_stub_logged = False       # log the "inert stub" note at most once


# ---------------------------------------------------------------------------
# low-level helpers
# ---------------------------------------------------------------------------

def _log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:  # noqa: BLE001
        pass


def _db():
    import llm_jobs  # sibling module, same venv — reuse its pymysql path
    return llm_jobs._db_conn()


def enabled():
    """True when IRANSEDA_REPORTER_ENABLED is a truthy value."""
    return os.environ.get(ENABLED_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _check_after_minutes(attempts):
    """Bounded check-after: 5 -> 15 -> 60 -> 60 (minutes)."""
    idx = min(int(attempts), len(_CHECK_SCHEDULE_MIN) - 1)
    return _CHECK_SCHEDULE_MIN[idx]


# ---------------------------------------------------------------------------
# PublisherClient — the transport interface (the real one is a separate adapter)
# ---------------------------------------------------------------------------

class PublisherClient:
    """Abstract transport to the user's external publication web service.

    ONLY these two methods exist. The REAL implementation is a SEPARATE
    adapter that will be added when the German service's contract arrives
    (endpoint, auth, payload, response task-id location, status-check shape,
    channel names). Nothing in this file assumes any of that — no URL, no
    headers, no auth scheme, no payload.

    Contract the future adapter must honour:
      * publish(task)  -> dict with at least {"external_task_id": str|None}.
        A raise or a returned "error" key means the submit failed. It MUST NOT
        fabricate a published state.
      * check_status(external_task_id) -> dict with at least:
            {"state": "pending"|"published"|"failed",
             "post_urls": {channel: url} (may be {} while pending),
             "error": str|None}
    """

    def publish(self, task):
        raise NotImplementedError

    def check_status(self, external_task_id):
        raise NotImplementedError


class StubClient(PublisherClient):
    """The only concrete client in this step: a no-op that is honest.

    publish() does not contact anything and returns an explicit
    "publisher not configured" error so the worker marks the task `skipped`
    (terminal). It NEVER fakes a published state and NEVER returns a fake
    task id. check_status() is defensive: if it were ever called, it reports
    "pending" (no fabrication) — but the worker should never reach it because
    a stubbed task is `skipped`, not `submitted`.
    """

    def publish(self, task):
        return {"external_task_id": None, "error": "publisher not configured"}

    def check_status(self, external_task_id):
        # Never fabricate a success. Report indeterminate pending.
        return {"state": "pending", "post_urls": {}, "error": None}


# The active client. Swap this for the real adapter when the contract lands —
# the worker, state machine, table, and API all key off PublisherClient.
_client = StubClient()


def get_client():
    return _client


def set_client(client):
    """Inject a concrete PublisherClient (used by the real adapter later and
    by tests)."""
    global _client
    _client = client


def client_configured():
    """True when a real (non-stub) transport is installed."""
    return not isinstance(_client, StubClient)


# ---------------------------------------------------------------------------
# report_event — the single idempotent entry point
# ---------------------------------------------------------------------------

def default_idempotency_key(event_type, title, artifact_url=None, git_commit=None):
    return hashlib.sha1(
        ("%s%s%s%s" % (event_type, title, artifact_url or "", git_commit or "")).encode("utf-8")
    ).hexdigest()


def report_event(event_type, title, body="", artifact_url=None, git_commit=None,
                 channels=None, idempotency_key=None):
    """Idempotently record a report event -> one publication_task row.

    This is the ONLY call site future pipeline code will use. It is safe to
    call repeatedly with the same logical event: the UNIQUE idempotency_key
    guarantees one row, and a duplicate call only refreshes `title`/`body` —
    it NEVER re-submits a task that is already submitted/checking/published.

    Returns {"created": bool, "task_id": int, "status": str, "key": str}.
    """
    if not event_type:
        raise ValueError("event_type is required")
    key = idempotency_key or default_idempotency_key(
        event_type, title or "", artifact_url, git_commit)
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO publication_task "
                "(event_type, title, body, artifact_url, git_commit, channels, "
                " idempotency_key, status, attempts) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'queued',0) "
                "ON DUPLICATE KEY UPDATE title=VALUES(title), body=VALUES(body)",
                (event_type, (title or "")[:200], body,
                 (artifact_url or "")[:512] or None, (git_commit or "")[:64] or None,
                 channels, key))
            conn.commit()
            cur.execute(
                "SELECT id, status FROM publication_task WHERE idempotency_key=%s", (key,))
            row = cur.fetchone()
        # A duplicate insert never moves a task out of an in-flight/terminal
        # state (the UPDATE only touched title/body), so status is authoritative.
        return {"created": True, "task_id": row["id"],
                "status": row["status"], "key": key}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# worker — the 60s state-machine thread (inert by default)
# ---------------------------------------------------------------------------

def _advance_task(client, cur, task):
    """Advance one task one step along the state machine. Returns a log line
    (or None if nothing changed). `cur` is an open cursor on an open conn."""
    status = task["status"]
    tid = task["id"]

    if status == "queued":
        # Submit to the external service.
        try:
            res = client.publish(task) or {}
        except Exception as e:  # noqa: BLE001
            res = {"error": repr(e)[:300]}
        err = res.get("error")
        ext = res.get("external_task_id")
        if err and not ext:
            # Stub path (no transport) OR a hard submit failure. With the stub
            # this is terminal: skip, do NOT loop. With a real client we let it
            # retry up to MAX_ATTEMPTS.
            if not client_configured():
                cur.execute(
                    "UPDATE publication_task SET status='skipped', error=%s, "
                    "updated_at=NOW() WHERE id=%s",
                    ("publisher not configured", tid))
                return "task %d -> skipped (publisher not configured)" % tid
            attempts = int(task.get("attempts") or 0) + 1
            if attempts >= MAX_ATTEMPTS:
                cur.execute(
                    "UPDATE publication_task SET status='failed', error=%s, "
                    "attempts=%s, updated_at=NOW() WHERE id=%s",
                    ((err or "")[:500], attempts, tid))
                return "task %d -> failed (submit, %d attempts)" % (tid, attempts)
            cur.execute(
                "UPDATE publication_task SET status='queued', attempts=%s, "
                "check_after=NOW(), error=%s, updated_at=NOW() WHERE id=%s",
                (attempts, (err or "")[:500], tid))
            return "task %d submit failed, attempt %d -> retry queued" % (tid, attempts)
        # submit ok
        cur.execute(
            "UPDATE publication_task SET status='submitted', "
            "external_task_id=%s, submitted_at=NOW(), "
            "check_after=DATE_ADD(NOW(), INTERVAL 5 MINUTE), "
            "attempts=attempts+1, error=NULL, updated_at=NOW() WHERE id=%s",
            (str(ext)[:128] if ext is not None else None, tid))
        return "task %d -> submitted (ext=%s)" % (tid, ext)

    if status == "submitted" or status == "checking":
        # Poll the external status.
        ext = task.get("external_task_id")
        if not ext:
            # No external id (shouldn't happen for submitted); park it.
            return None
        try:
            st = client.check_status(ext) or {}
        except Exception as e:  # noqa: BLE001
            st = {"state": "pending", "error": repr(e)[:300]}
        state = st.get("state")
        cur.execute(
            "UPDATE publication_task SET status='checking', last_checked_at=NOW(), "
            "updated_at=NOW() WHERE id=%s", (tid,))
        if state == "published":
            urls = st.get("post_urls") or {}
            cur.execute(
                "UPDATE publication_task SET status='published', published_at=NOW(), "
                "post_urls=%s, error=NULL, updated_at=NOW() WHERE id=%s",
                (json.dumps(urls, ensure_ascii=False), tid))
            return "task %d -> published" % tid
        if state == "failed":
            cur.execute(
                "UPDATE publication_task SET status='failed', error=%s, "
                "updated_at=NOW() WHERE id=%s",
                ((st.get("error") or "external reported failure")[:500], tid))
            return "task %d -> failed (external)" % tid
        # pending -> schedule the next bounded check
        attempts = int(task.get("attempts") or 1)
        mins = _check_after_minutes(attempts)
        cur.execute(
            "UPDATE publication_task SET check_after=DATE_ADD(NOW(), INTERVAL %d MINUTE) "
            "WHERE id=%s", (mins, tid))
        return "task %d pending, next check in %dm" % (tid, mins)

    return None


def _worker_cycle():
    """One worker cycle. Inert unless enabled. With the stub it drains new
    `queued` rows to `skipped` exactly once (terminal, no retry)."""
    if not enabled():
        return
    client = get_client()
    conn = _db()
    try:
        with conn.cursor() as cur:
            # The stub only needs to drain brand-new `queued` rows to `skipped`
            # once each — they are terminal and never re-queued, so this cannot
            # churn. A real client may also advance submitted/checking rows.
            if not client_configured():
                cur.execute(
                    "SELECT id FROM publication_task WHERE status='queued' "
                    "ORDER BY id LIMIT 50")
                ids = [r["id"] for r in cur.fetchall()]
                for tid in ids:
                    cur.execute(
                        "UPDATE publication_task SET status='skipped', "
                        "error='publisher not configured', updated_at=NOW() "
                        "WHERE id=%s AND status='queued'", (tid,))
                if ids:
                    conn.commit()
                    _log("stub enabled: marked %d queued task(s) skipped "
                         "(publisher not configured)" % len(ids))
                return
            # Real transport: pick due rows in any active state.
            cur.execute(
                "SELECT * FROM publication_task "
                "WHERE status IN ('queued','submitted','checking') "
                "AND (check_after IS NULL OR check_after <= NOW()) "
                "ORDER BY id LIMIT 25")
            tasks = cur.fetchall()
            changed = []
            for t in tasks:
                line = _advance_task(client, cur, t)
                if line:
                    changed.append(line)
            if changed:
                conn.commit()
                for line in changed:
                    _log(line)
    except Exception as e:  # noqa: BLE001
        _log("cycle error: %r" % e)
    finally:
        conn.close()


def _loop():
    global _running, _stub_logged
    _running = True
    _log("reporter worker started (enabled=%s, client_configured=%s)"
         % (enabled(), client_configured()))
    while True:
        try:
            _worker_cycle()
        except Exception as e:  # noqa: BLE001
            _log("cycle error: %r" % e)
        if enabled() and not client_configured() and not _stub_logged:
            _stub_logged = True
            _log("enabled but publisher is the stub: new events will be marked "
                 "skipped (publisher not configured) — real adapter not wired yet")
        time.sleep(60)


def ensure_started():
    """Idempotent: start the 60s worker thread once (called from app.py
    _startup, alongside boost/backfill). The thread itself is gated by env."""
    global _running
    if not _running:
        import logic
        logic.run_in_thread(_loop)


# ---------------------------------------------------------------------------
# status / counts for the API + self-test
# ---------------------------------------------------------------------------

def _row_to_json(r):
    out = dict(r)
    for k in ("post_urls", "views"):
        v = out.get(k)
        if v:
            try:
                out[k] = json.loads(v)
            except Exception:  # noqa: BLE001
                pass
    for k in ("created_at", "updated_at", "submitted_at", "check_after",
              "published_at", "last_checked_at"):
        if isinstance(out.get(k), datetime):
            out[k] = out[k].strftime("%Y-%m-%d %H:%M:%S")
    return out


def status(limit=20):
    """Per-status counts + last N tasks + enabled/configured flags."""
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, COUNT(*) AS n FROM publication_task "
                "GROUP BY status")
            counts = {r["status"]: int(r["n"]) for r in cur.fetchall()}
            total = sum(counts.values())
            cur.execute(
                "SELECT * FROM publication_task ORDER BY id DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return {
        "ok": True,
        "enabled": enabled(),
        "client_configured": client_configured(),
        "max_attempts": MAX_ATTEMPTS,
        "event_types": list(EVENT_TYPES),
        "counts": counts,
        "total": total,
        "tasks": [_row_to_json(r) for r in rows],
    }


def selftest():
    """Fire one `selftest` event, idempotent per minute, so a human can watch
    the whole path land (as `skipped` while the stub is active) without any
    real transport. Returns the created/refreshed row."""
    minute = datetime.now().strftime("%Y-%m-%dT%H:%M")
    key = "selftest:" + minute
    res = report_event("selftest", "Self-test (dashboard)",
                       body="Reporter self-test fired from the dashboard.",
                       git_commit=None, channels=None, idempotency_key=key)
    _log("selftest fired: task_id=%s status=%s key=%s"
         % (res.get("task_id"), res.get("status"), key))
    return res
