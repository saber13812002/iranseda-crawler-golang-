"""
iranseda backfill — the "monthly suggestions → pipeline" autopilot.

A page in the admin lets the user queue program *suggestions* (one row per
program, with a month/label). This module runs a slow (60s) in-process thread
inside the dashboard. Each cycle it:

  1. reads the LIVE queue (pending_download + pending_transcribe counts);
  2. only when the queue is IDLE and the autopilot is running, takes the next
     `queued` suggestion;
  3. promotes a BOUNDED batch of that program's not-yet-processed sessions
     (resetting them to `pending_download` so the Go download cron + whisper
     worker pick them up: download -> subtitle -> (later) the LLM steps);
  4. marks the suggestion `done` (promoted N) or `skipped` (nothing eligible).

It is fully stoppable (the admin toggle / `set_running(False)`) and never
loops: a suggestion is promoted at most once, and sessions already
`failed_permanent` / already subtitled are left alone. It only touches
`radio_program_sessions` status + `backfill_list` — never the model servers,
whisper, LiteLLM, or the dashboard process.

State lives in dashboard_state.json["backfill"] (single source of truth).
"""
import json
import os
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.environ.get(
    "IRANSEDA_ROOT", os.path.abspath(os.path.join(BASE_DIR, ".."))
)
LOG_PATH = os.path.join(PROJECT_ROOT, "scripts", "logs", "backfill.log")

# how many sessions to promote per suggestion (kept small on purpose: the goal
# is to trickle idle capacity, not to flood). Bounded, stoppable.
DEFAULT_MAX_PROMOTE = 5

_lock = threading.Lock()
_running = False          # thread guard
_last_snapshot = {"data": None, "ts": 0.0}
_state = {"running": False, "max_promote": DEFAULT_MAX_PROMOTE,
          "last_promote": "", "last_reason": ""}


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


def _load_state():
    """Merge the per-key defaults with whatever is on disk."""
    import logic
    return {**_state, **(logic.load_state().get("backfill") or {})}


def _save_state(patch):
    global _state
    import logic
    st = logic.load_state()
    cur = {**_state, **(st.get("backfill") or {})}
    cur.update(patch)
    st["backfill"] = cur
    logic.save_state(st)
    _state = cur


# ---------------------------------------------------------------------------
# promotion
# ---------------------------------------------------------------------------

def _promote_batch(conn, program_id, limit):
    """Reset a bounded batch of a program's not-yet-processed, non-dead
    sessions to `pending_download` so the Go cron re-downloads them.
    Returns (promoted, eligible_total)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM radio_program_sessions "
            "WHERE program_id=%s AND is_subtitled=0 AND is_downloaded=0 "
            "AND status<>'failed_permanent' AND link IS NOT NULL AND link<>''",
            (program_id,))
        eligible = int(cur.fetchone()["n"] or 0)
        cur.execute(
            "SELECT id FROM radio_program_sessions "
            "WHERE program_id=%s AND is_subtitled=0 AND is_downloaded=0 "
            "AND status<>'failed_permanent' AND link IS NOT NULL AND link<>'' "
            "ORDER BY created_at DESC LIMIT %s",
            (program_id, limit))
        ids = [r["id"] for r in cur.fetchall()]
        for sid in ids:
            cur.execute(
                "UPDATE radio_program_sessions "
                "SET status='pending_download', last_error=NULL WHERE id=%s",
                (sid,))
    conn.commit()
    return len(ids), eligible


def promote_now(program_id=None, batch_id=None):
    """Manually promote one batch now (bypasses the idle gate). Used by the
    admin "حالا" button. `batch_id` = a backfill_list row to consume, else
    `program_id` is promoted directly without touching the queue."""
    st = _load_state()
    limit = int(st.get("max_promote") or DEFAULT_MAX_PROMOTE)
    conn = _db()
    try:
        pid = program_id
        if batch_id:
            with conn.cursor() as cur:
                cur.execute("SELECT program_id, status FROM backfill_list WHERE id=%s",
                            (batch_id,))
                row = cur.fetchone()
                if not row:
                    return {"ok": False, "error": "پیشنهاد یافت نشد"}
                if row["status"] != "queued":
                    return {"ok": False, "error": "این پیشنهاد قبلا مصرف شده"}
                pid = row["program_id"]
        if not pid:
            return {"ok": False, "error": "program_id خالی است"}
        promoted, eligible = _promote_batch(conn, pid, limit)
        if batch_id:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE backfill_list SET status=%s, promoted_at=NOW(), "
                    "note=%s WHERE id=%s",
                    ("done" if promoted else "skipped",
                     f"promoted {promoted}/{eligible}" if promoted else "no eligible",
                     batch_id))
        conn.commit()
    finally:
        conn.close()
    _save_state({"last_promote": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "last_reason": f"manual: promoted {promoted} (pid={pid})"})
    _log(f"manual promote: program={pid} -> {promoted} (eligible={eligible})")
    return {"ok": True, "promoted": promoted, "eligible": eligible}


# ---------------------------------------------------------------------------
# cycle + thread
# ---------------------------------------------------------------------------

def _cycle():
    st = _load_state()
    if not st.get("running"):
        return
    limit = int(st.get("max_promote") or DEFAULT_MAX_PROMOTE)
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM radio_program_sessions "
                        "WHERE status='pending_download'")
            pd = int(cur.fetchone()["n"] or 0)
            cur.execute("SELECT COUNT(*) AS n FROM radio_program_sessions "
                        "WHERE status IN ('pending_transcribe','transcribing')")
            pt = int(cur.fetchone()["n"] or 0)
        if pd or pt:
            _save_state({"last_reason": f"queue busy (dl={pd}, tr={pt})"})
            return
        with conn.cursor() as cur:
            cur.execute("SELECT id, program_id, label FROM backfill_list "
                        "WHERE status='queued' ORDER BY id LIMIT 1")
            row = cur.fetchone()
        if not row:
            _save_state({"last_reason": "no queued suggestions"})
            return
        promoted, eligible = _promote_batch(conn, row["program_id"], limit)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE backfill_list SET status=%s, promoted_at=NOW(), note=%s "
                "WHERE id=%s",
                ("done" if promoted else "skipped",
                 f"promoted {promoted}/{eligible}" if promoted else "no eligible",
                 row["id"]))
        conn.commit()
    finally:
        conn.close()
    _save_state({"last_promote": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "last_reason": f"promoted {promoted} (pid={row['program_id']})"})
    _log(f"cycle: program={row['program_id']} label={row.get('label')} "
         f"-> promoted {promoted}/{eligible}")


def _loop():
    global _running
    _running = True
    _log("backfill autopilot started")
    while True:
        try:
            _cycle()
        except Exception as e:  # noqa: BLE001
            _log("cycle error: %r" % e)
        time.sleep(60)


def ensure_started():
    global _running
    if not _running:
        import logic
        logic.run_in_thread(_loop)


def _counts():
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM radio_program_sessions "
                        "WHERE status='pending_download'")
            pd = int(cur.fetchone()["n"] or 0)
            cur.execute("SELECT COUNT(*) AS n FROM radio_program_sessions "
                        "WHERE status IN ('pending_transcribe','transcribing')")
            pt = int(cur.fetchone()["n"] or 0)
            cur.execute("SELECT COUNT(*) AS n FROM backfill_list WHERE status='queued'")
            queued = int(cur.fetchone()["n"] or 0)
    finally:
        conn.close()
    return pd, pt, queued


def status():
    """Full status for the admin: autopilot on/off, live queue, queue rows."""
    st = _load_state()
    pd, pt, queued = _counts()
    rows = []
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, program_id, label, month, status, "
                        "promoted_at, note FROM backfill_list ORDER BY id DESC LIMIT 100")
            rows = cur.fetchall()
    finally:
        conn.close()
    return {
        "ok": True,
        "running": bool(st.get("running")),
        "max_promote": int(st.get("max_promote") or DEFAULT_MAX_PROMOTE),
        "last_promote": st.get("last_promote") or "",
        "last_reason": st.get("last_reason") or "",
        "queue": {"pending_download": pd, "pending_transcribe": pt,
                  "idle": (pd == 0 and pt == 0), "queued": queued},
        "list": rows,
    }


def set_running(flag):
    _save_state({"running": bool(flag)})
    _log("autopilot " + ("RESUMED" if flag else "PAUSED"))
    return status()


def toggle():
    st = _load_state()
    return set_running(not st.get("running"))


def set_max_promote(n):
    n = max(1, min(50, int(n)))
    _save_state({"max_promote": n})
    return status()
