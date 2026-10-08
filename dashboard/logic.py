"""
iranseda dashboard — backend logic.

All dashboard state lives in a single JSON file (dashboard_state.json) next to
this file. It is the single source of truth for:
  - schedule: cron expressions for the pipeline / site-refresh jobs
  - jobs: last-run snapshots scraped from the existing logs
  - manual runs: one-shot triggers
  - litellm: model records added through the dashboard

The MySQL `radio` DB and the pipeline's .env / crontab / docker-compose are
read/written directly (not mirrored here) — this file only holds dashboard
specifics so nothing duplicates live state.
"""
import json
import os
import re
import subprocess
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "dashboard_state.json")
PROJECT_ROOT = os.environ.get(
    "IRANSEDA_ROOT",
    os.path.abspath(os.path.join(BASE_DIR, "..")),
)

DEFAULT_STATE = {
    "schedule": {
        "pipeline": "15,45 * * * *",
        "refresh_site": "*/30 * * * *",
    },
    "jobs": {},
    "runs": {},
    "litellm": {"master_key": "", "base_url": "http://172.20.1.52:4000"},
}

_state_lock = threading.Lock()


# --------------------------------------------------------------------------
# state file
# --------------------------------------------------------------------------

def load_state():
    with _state_lock:
        if os.path.exists(STATE_PATH):
            try:
                with open(STATE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = json.loads(json.dumps(DEFAULT_STATE))
                merged.update(data)
                return merged
            except (json.JSONDecodeError, OSError):
                pass
        return json.loads(json.dumps(DEFAULT_STATE))


def save_state(state):
    with _state_lock:
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_PATH)


def run_in_thread(fn, *args, **kwargs):
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()
    return t


def _run(cmd, timeout=60):
    """Run a shell command, return (rc, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except Exception as e:  # noqa: BLE001
        return 1, "", str(e)


# --------------------------------------------------------------------------
# MySQL (radio DB) — accessed through the mysql container
# --------------------------------------------------------------------------

def _mysql_query(sql):
    """Query the radio DB, return list-of-lists (headers prepended as first row)."""
    inner = sql.replace('"', '\\"')
    cmd = (
        f"docker exec -i iranseda-mysql mysql -un8nuser -p'StrongPassword123!' "
        f"--default-character-set=utf8mb4 radio -e \"{inner}\""
    )
    rc, out, err = _run(cmd, timeout=60)
    if rc != 0:
        raise RuntimeError(f"mysql query failed: {err.strip()[:300]}")
    rows = []
    for line in out.splitlines():
        line = line.rstrip("\n")
        if not line:
            continue
        rows.append(line.split("\t"))
    if not rows:
        return []
    headers = rows[0]
    return [dict(zip(headers, r)) for r in rows[1:]]


def db_health():
    """Return dict with db reachable + quick counts, or error string."""
    try:
        q = _mysql_query(
            "SELECT 1 AS ok, NOW() AS server_now, "
            "(SELECT COUNT(*) FROM radio_program_sessions) AS total_sessions, "
            "(SELECT MAX(id) FROM radio_program_sessions) AS max_id"
        )
        row = q[0] if q else {}
        return {
            "ok": True,
            "server_now": row.get("server_now"),
            "total_sessions": int(row.get("total_sessions") or 0),
            "max_id": int(row.get("max_id") or 0),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


def db_metrics():
    """All DB-derived metrics in one shot (used by /api/stats)."""
    m = {}
    try:
        m["status"] = [
            {"status": r["status"], "count": int(r["c"])}
            for r in _mysql_query(
                "SELECT status, COUNT(*) AS c FROM radio_program_sessions "
                "GROUP BY status ORDER BY c DESC"
            )
        ]
        m["last30d_created"] = [
            {"day": r["d"], "count": int(r["c"])}
            for r in _mysql_query(
                "SELECT DATE(created_at) AS d, COUNT(*) AS c FROM radio_program_sessions "
                "WHERE created_at >= NOW() - INTERVAL 30 DAY GROUP BY DATE(created_at) ORDER BY d"
            )
        ]
        m["last30d_subtitled"] = [
            {"day": r["d"], "count": int(r["c"])}
            for r in _mysql_query(
                "SELECT DATE(updated_at) AS d, COUNT(*) AS c FROM radio_program_sessions "
                "WHERE is_subtitled=1 AND updated_at >= NOW() - INTERVAL 30 DAY "
                "GROUP BY DATE(updated_at) ORDER BY d"
            )
        ]
        m["monthly_maxid"] = [
            {"month": r["m"], "count": int(r["c"]), "maxid": int(r["maxid"])}
            for r in _mysql_query(
                "SELECT DATE_FORMAT(created_at, '%Y-%m') AS m, COUNT(*) AS c, MAX(id) AS maxid "
                "FROM radio_program_sessions GROUP BY DATE_FORMAT(created_at, '%Y-%m') ORDER BY m"
            )
        ]
        m["failures"] = [
            {"id": r["id"], "status": r["status"], "error": r["err"]}
            for r in _mysql_query(
                "SELECT id, status, LEFT(IFNULL(last_error,''),120) AS err FROM radio_program_sessions "
                "WHERE last_error IS NOT NULL ORDER BY id DESC LIMIT 10"
            )
        ]
        m["created_last_24h"] = int(
            _mysql_query(
                "SELECT COUNT(*) AS c FROM radio_program_sessions "
                "WHERE created_at >= NOW() - INTERVAL 24 HOUR"
            )[0]["c"]
            or 0
        )
        m["recent_new"] = [
            {
                "id": int(r["id"]),
                "program_id": int(r["program_id"]),
                "status": r["status"],
                "created_at": r["created_at"],
                "filename": r["filename"] or "",
            }
            for r in _mysql_query(
                "SELECT id, program_id, status, created_at, filename FROM radio_program_sessions "
                "ORDER BY id DESC LIMIT 12"
            )
        ]
        h = db_health()
        m.update(h)
    except Exception as e:  # noqa: BLE001
        m["error"] = str(e)[:300]
    return m


# --------------------------------------------------------------------------
# LLM post-processing metrics (files on disk + llm_output rows + live shards)
# --------------------------------------------------------------------------

_llm_metrics_cache = {"data": None, "ts": 0.0}
LLM_METRICS_TTL = 30  # seconds — file counts change slowly; don't re-glob per scrape


def _count_by_suffix(directory, suffix):
    """Count files in `directory` ending in `suffix` (one listdir, no recursion)."""
    try:
        return sum(1 for n in os.listdir(directory) if n.endswith(suffix))
    except OSError:
        return 0


def llm_file_counts():
    """Count LLM outputs on disk + llm_output rows + running shard workers.

    Cached for LLM_METRICS_TTL so the /metrics scrape doesn't re-glob thousands
    of files (or re-query the DB / re-run ps) on every 15s Prometheus poll.
    Returns a dict, or {} if the dir is missing (metrics endpoint skips then).
    """
    now = time.time()
    if _llm_metrics_cache["data"] is not None and now - _llm_metrics_cache["ts"] < LLM_METRICS_TTL:
        return _llm_metrics_cache["data"]
    d = {}
    cleaned = os.path.join(PROJECT_ROOT, "downloads", "cleaned")
    d["full_text"] = _count_by_suffix(cleaned, ".full.txt")
    d["summary_fa"] = _count_by_suffix(cleaned, ".summary.txt")
    d["summary_en"] = _count_by_suffix(cleaned, ".summary.en.txt")
    d["correct_text"] = _count_by_suffix(cleaned, ".correct.txt")
    d["correct_subtitles"] = _count_by_suffix(cleaned, ".correct.srt")
    d["total_srt"] = _count_by_suffix(os.path.join(PROJECT_ROOT, "downloads"), ".srt")
    # llm_output rows by job (DB ground truth)
    try:
        d["db_by_job"] = {
            r["job_type"]: int(r["c"])
            for r in _mysql_query("SELECT job_type, COUNT(*) AS c FROM llm_output GROUP BY job_type")
        }
    except Exception:  # noqa: BLE001
        d["db_by_job"] = {}
    # live LLM shard workers (ps available on this box; pgrep is not)
    try:
        d["workers"] = int((_run("ps -C python3 -o args= 2>/dev/null | grep -c 'run-all --job'", timeout=10)[1]).strip() or 0)
    except Exception:  # noqa: BLE001
        d["workers"] = 0
    _llm_metrics_cache.update(data=d, ts=now)
    return d


# --------------------------------------------------------------------------
# Settings: .env / crontab / compose / env files
# --------------------------------------------------------------------------

ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
COMPOSE_PATH = os.path.join(PROJECT_ROOT, "docker-compose.whisper.yml")
DASH_ENV_PATH = os.path.join(BASE_DIR, "dashboard.env")

# keys the dashboard lets you edit in .env (safe pipeline knobs)
EDITABLE_ENV_KEYS = [
    "MAX_DOWNLOADS",
    "DOWNLOAD_DELAY",
    "AUDIO_RETENTION_DAYS",
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_NAME",
    "GITHUB_BRANCH",
]


def _read_env_file(path):
    out = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def _write_env_file(path, mapping):
    """Rewrite the env file preserving existing lines; update given keys; append new."""
    lines = []
    seen = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    out = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in mapping:
                out.append(f"{k}={mapping[k]}\n")
                seen.add(k)
                continue
        out.append(line if line.endswith("\n") or not line else line + "\n")
    for k, v in mapping.items():
        if k not in seen:
            out.append(f"{k}={v}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)


def get_env():
    return _read_env_file(ENV_PATH)


def save_env(updates):
    """updates: dict of key->value (only EDITABLE_ENV_KEYS honored)."""
    clean = {k: str(v) for k, v in updates.items() if k in EDITABLE_ENV_KEYS}
    _write_env_file(ENV_PATH, clean)
    return get_env()


def get_dashboard_env():
    return _read_env_file(DASH_ENV_PATH)


def save_dashboard_env(updates):
    clean = {k: str(v) for k, v in updates.items() if k}
    _write_env_file(DASH_ENV_PATH, clean)
    return _read_env_file(DASH_ENV_PATH)


def get_compose_whisper():
    """Parse whisper compose env + restart policy per service."""
    data = {"worker": {}, "api": {}, "error": None}
    if not os.path.exists(COMPOSE_PATH):
        data["error"] = "compose file not found"
        return data
    try:
        import yaml  # pyyaml
    except ImportError:
        data["error"] = "pyyaml not installed in dashboard venv"
        return data
    with open(COMPOSE_PATH, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    services = (doc or {}).get("services", {})
    for name in ("iranseda-whisper-worker", "iranseda-whisper-api"):
        svc = services.get(name, {})
        data[name.replace("iranseda-whisper-", "")] = {
            "env": svc.get("environment", {}) or {},
            "restart": svc.get("restart"),
        }
    return data


def save_compose_whisper(updates):
    """updates: {'worker': {ENV: val}, 'api': {ENV: val}} — rewrite compose env, restart containers."""
    import yaml
    with open(COMPOSE_PATH, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    services = doc.setdefault("services", {})
    touched = []
    for svc_name, key in (("iranseda-whisper-worker", "worker"), ("iranseda-whisper-api", "api")):
        env_updates = updates.get(key) or {}
        if not env_updates:
            continue
        svc = services.setdefault(svc_name, {})
        env = svc.setdefault("environment", {})
        if isinstance(env, list):
            env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in env}
            svc["environment"] = env
        for k, v in env_updates.items():
            env[k] = str(v)
        touched.append(svc_name)
    with open(COMPOSE_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    # apply: recreate affected containers so env changes take effect
    cmd = f"cd {PROJECT_ROOT} && docker compose -f docker-compose.whisper.yml "
    if touched:
        names = " ".join(touched)
        cmd += f"restart {names}"
    else:
        return {"applied": False, "note": "no env changed"}
    rc, out, err = _run(cmd, timeout=180)
    return {"applied": rc == 0, "touched": touched, "output": (out + err).strip()[:400]}


def get_cron():
    rc, out, err = _run("crontab -l 2>/dev/null")
    return out.splitlines() if rc == 0 else []


_PIPELINE_RE = re.compile(r"(\S+\s+\S+\s+\S+\s+\S+\s+\S+)\s+(\S+run_pipeline\.sh).*")
_REFRESH_RE = re.compile(r"(\S+\s+\S+\s+\S+\s+\S+\s+\S+)\s+(\S+refresh_site\.sh).*")


def get_schedule():
    """Return {'pipeline': expr, 'refresh_site': expr} from live crontab."""
    state = load_state()
    fallback = state["schedule"]
    result = dict(fallback)
    for line in get_cron():
        m = _PIPELINE_RE.search(line)
        if m:
            result["pipeline"] = m.group(1)
        m = _REFRESH_RE.search(line)
        if m:
            result["refresh_site"] = m.group(1)
    return result


def _set_cron_line(expr, script_path):
    """Replace (or append) the cron line for a script. Returns new crontab."""
    lines = get_cron()
    key = os.path.basename(script_path)
    pat = re.compile(rf".*{key}.*")
    new_line = f"{expr} {script_path} >/dev/null 2>&1"
    out = [l for l in lines if not pat.search(l)]
    out.append(new_line)
    proc = subprocess.run(["crontab", "-"], input="\n".join(out) + "\n",
                          text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"crontab write failed: {proc.stderr[:200]}")
    return proc


def save_schedule(updates):
    """updates: {'pipeline': 'expr', 'refresh_site': 'expr'}. Updates crontab."""
    R = PROJECT_ROOT
    targets = {
        "pipeline": os.path.join(R, "scripts/run_pipeline.sh"),
        "refresh_site": os.path.join(R, "scripts/refresh_site.sh"),
    }
    applied = {}
    for key, expr in updates.items():
        if key in targets and expr and re.match(r"^\S+\s+\S+\s+\S+\s+\S+\s+\S+$", expr.strip()):
            _set_cron_line(expr.strip(), targets[key])
            applied[key] = expr.strip()
    state = load_state()
    state["schedule"].update(applied)
    save_state(state)
    return get_schedule()


# --------------------------------------------------------------------------
# Active time-window + named "sessions" (سانس) that gate the GPU transcriber.
#
# The whisper worker is the ONLY thing gated. Discover / download / site-refresh
# run 24/7 regardless (see scripts/). "Active" time = the union of all ENABLED
# blocks. When the master switch is OFF the gate never stops the worker
# (self-heals it if it's down), so the pipeline runs 24/7 until you opt in.
#
# The server runs in UTC but the user thinks in Tehran time, so everything here
# is computed in Asia/Tehran (UTC+3:30). The gate runs as an in-process 60s
# thread (start_gate_loop); when the dashboard is down the worker simply runs
# 24/7 — the safe default.
# --------------------------------------------------------------------------

TEHRAN = "Asia/Tehran"
DEFAULT_BLOCK = {"id": "main", "name": "پنجره‌ی اصلی", "start": "12:00", "end": "06:00", "enabled": True}
GATE_TZ = None  # the timezone the in-process gate thread uses (set at startup)


def _tznow(tz=TEHRAN):
    from datetime import datetime, timezone, timedelta
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz))
    except Exception:
        # fallback: fixed UTC+3:30 (Iran has no DST)
        return datetime.now(timezone.utc) - timedelta(hours=3, minutes=30)


def _hhmm_to_min(s):
    """Parse 'HH:MM' to minutes, or None if invalid (incl. out-of-range 0-23 / 0-59)."""
    try:
        h, m = str(s).strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h * 60 + m
        return None
    except Exception:
        return None


def _in_block(now_min, start, end):
    a = _hhmm_to_min(start)
    b = _hhmm_to_min(end)
    if a is None or b is None:
        return False
    if a == b:
        return True  # treat 06:00–06:00 as full-day
    if a < b:
        return a <= now_min < b
    return now_min >= a or now_min < b  # wraps midnight


def _worker_running():
    rc, out, _ = _run(
        "docker inspect -f '{{.State.Status}}' iranseda-whisper-worker 2>/dev/null", timeout=15
    )
    return out.strip().lower() == "running"


def _union_active(blocks, now_min):
    return any(b.get("enabled") and _in_block(now_min, b.get("start"), b.get("end")) for b in blocks)


_gate_running = False
_gate_last_action = None  # (HH:MM:SS, message) — last gate action for the UI


def get_window():
    state = load_state()
    w = state.get("window") or {}
    tz = w.get("tz", TEHRAN)
    enabled = bool(w.get("enabled", False))
    blocks = w.get("blocks") or [json.loads(json.dumps(DEFAULT_BLOCK))]
    now = _tznow(tz)
    now_min = now.hour * 60 + now.minute
    return {
        "tz": tz,
        "enabled": enabled,
        "blocks": blocks,
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "in_window": _union_active(blocks, now_min),
        "worker_running": _worker_running(),
        "gate_active": _gate_running,
        "last_action": _gate_last_action,
    }


def set_window(payload):
    """payload: {enabled, tz, blocks:[{id,name,start,end,enabled}]}."""
    blocks = []
    for i, b in enumerate(payload.get("blocks") or []):
        name = (b.get("name") or ("سانس " + str(i + 1))).strip()
        start = b.get("start")
        end = b.get("end")
        if _hhmm_to_min(start) is None or _hhmm_to_min(end) is None:
            raise ValueError(f"ساعت نامعتبر برای «{name}» (باید HH:MM باشد)")
        blocks.append({
            "id": str(b.get("id") or ("b" + str(i))),
            "name": name[:40],
            "start": start,
            "end": end,
            "enabled": bool(b.get("enabled", True)),
        })
    if not blocks:
        blocks = [json.loads(json.dumps(DEFAULT_BLOCK))]
    w = {
        "tz": (payload.get("tz") or TEHRAN)[:40] or TEHRAN,
        "enabled": bool(payload.get("enabled", False)),
        "blocks": blocks,
    }
    state = load_state()
    state["window"] = w
    save_state(state)
    return get_window()


def _gate_cycle():
    """One gate decision: start/stop the worker to match the window.
    Stops unconditionally when out of window — the worker's startup recovery
    requeues any file it was mid-way through, so stopping mid-file is safe
    (the file is simply redone on the next start, reusing on-disk media).
    Runs every ~60s in a thread."""
    global _gate_last_action
    try:
        w = load_state().get("window") or {}
        if not w.get("enabled"):
            # feature off -> self-heal: keep the worker up
            if not _worker_running():
                _run("docker start iranseda-whisper-worker", timeout=60)
                _gate_last_action = (time.strftime("%H:%M:%S"), "استارت (پنجره خاموش — خودکفایی)")
            return
        tz = w.get("tz", TEHRAN)
        now = _tznow(tz)
        now_min = now.hour * 60 + now.minute
        running = _worker_running()
        if _union_active(w.get("blocks") or [], now_min):
            if not running:
                _run("docker start iranseda-whisper-worker", timeout=60)
                _gate_last_action = (time.strftime("%H:%M:%S"), "استارت (در پنجره فعال)")
        else:
            if running:
                _run("docker stop iranseda-whisper-worker", timeout=90)
                _gate_last_action = (time.strftime("%H:%M:%S"), "استاپ (خارج از پنجره)")
    except Exception as e:  # noqa: BLE001
        _gate_last_action = (time.strftime("%H:%M:%S"), "خطا: " + str(e)[:80])


def _gate_loop():
    global _gate_running
    _gate_running = True
    while True:
        _gate_cycle()
        time.sleep(60)


def start_gate_loop():
    """Start the in-process gate thread (idempotent)."""
    global _gate_running
    if not _gate_running:
        run_in_thread(_gate_loop)


def worker_set(action):
    if action not in ("start", "stop"):
        raise ValueError("action must be start or stop")
    rc, out, err = _run(f"docker {action} iranseda-whisper-worker", timeout=60)
    if rc != 0:
        raise RuntimeError((out + err).strip()[:200])
    return get_window()


def _tz_offset_str(tz):
    """Fixed UTC offset string for CONVERT_TZ, e.g. '+03:30'. Iran has no DST,
    so a fixed offset is exact. Falls back to +03:30 (Tehran) on any problem."""
    known = {"Asia/Tehran": "+03:30", "UTC": "+00:00", "Etc/UTC": "+00:00", "GMT": "+00:00"}
    if tz in known:
        return known[tz]
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        off = datetime(2020, 1, 1, tzinfo=ZoneInfo(tz)).utcoffset()
        total = int(off.total_seconds())
        sign = "+" if total >= 0 else "-"
        total = abs(total)
        return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"
    except Exception:
        return "+03:30"


def window_activity(offset=0):
    """Per-hour (configured tz) transcription + discovery for a day, 0..23.
    offset: 0=today, -1=yesterday, -N=N days ago (calendar day in that tz).
    The DB stores UTC; CONVERT_TZ maps it into the configured tz."""
    w = load_state().get("window") or {}
    tz = w.get("tz", TEHRAN)
    off = _tz_offset_str(tz)
    from datetime import timedelta
    now = _tznow(tz)
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0
    day = (now + timedelta(days=offset)).strftime("%Y-%m-%d")
    tzcol = f"CONVERT_TZ(updated_at, '+00:00', '{off}')"
    tzcol_c = f"CONVERT_TZ(created_at, '+00:00', '{off}')"
    trans = {int(r["h"]): int(r["c"]) for r in _mysql_query(
        f"SELECT HOUR({tzcol}) AS h, COUNT(*) c FROM radio_program_sessions "
        f"WHERE is_subtitled=1 AND DATE({tzcol})='{day}' GROUP BY h")}
    disc = {int(r["h"]): int(r["c"]) for r in _mysql_query(
        f"SELECT HOUR({tzcol_c}) AS h, COUNT(*) c FROM radio_program_sessions "
        f"WHERE DATE({tzcol_c})='{day}' GROUP BY h")}
    blocks = w.get("blocks") or []
    hours = []
    for h in range(24):
        hours.append({
            "h": h,
            "label": f"{h:02d}:00",
            "transcribed": trans.get(h, 0),
            "discovered": disc.get(h, 0),
            "in_window": _union_active(blocks, h * 60 + 30),
        })
    return {
        "day": day,
        "tz": tz,
        "offset": off,
        "hours": hours,
        "total_transcribed": sum(trans.values()),
        "total_discovered": sum(disc.values()),
    }


# --------------------------------------------------------------------------
# Jobs: container status, log tails, manual trigger
# --------------------------------------------------------------------------

JOB_SCRIPTS = {
    "pipeline": "scripts/run_pipeline.sh",
    "refresh_site": "scripts/refresh_site.sh",
}


def _parse_last_end(log_path):
    """Find the last 'END' timestamp line in a log."""
    if not os.path.exists(log_path):
        return None
    last = None
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*(pipeline|refresh) END", line)
                if m:
                    last = m.group(1)
    except OSError:
        return None
    return last


def jobs_status():
    """Container health + last-run info for each pipeline job."""
    jobs = {}
    # container status
    rc, out, _ = _run("docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -i iranseda", timeout=30)
    containers = {}
    for line in (out or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            containers[parts[0]] = parts[1].strip()

    jobs["iranseda-mysql"] = {"kind": "container", "status": containers.get("iranseda-mysql", "unknown")}
    jobs["iranseda-whisper-worker"] = {
        "kind": "container",
        "status": containers.get("iranseda-whisper-worker", "unknown"),
    }
    # whisper worker activity: DONE count in last 5m
    rc, out, _ = _run(
        "docker logs iranseda-whisper-worker --since 5m 2>&1 | grep -c DONE", timeout=30
    )
    try:
        jobs["iranseda-whisper-worker"]["transcribed_last_5m"] = int(out.strip() or 0)
    except ValueError:
        jobs["iranseda-whisper-worker"]["transcribed_last_5m"] = 0
    rc, out, _ = _run("docker logs iranseda-whisper-worker --tail 3 2>&1", timeout=30)
    jobs["iranseda-whisper-worker"]["last_log"] = (out or "").strip().splitlines()[-3:]

    # script jobs
    for key, script in JOB_SCRIPTS.items():
        log_path = os.path.join(PROJECT_ROOT, "scripts/logs", f"{key}.log" if key == "pipeline" else "refresh_site.log")
        log_path = os.path.join(PROJECT_ROOT, "scripts/logs", "pipeline.log" if key == "pipeline" else "refresh_site.log")
        jobs[key] = {
            "kind": "cron-script",
            "script": script,
            "last_end": _parse_last_end(log_path),
            "status": "ok",
        }
    return jobs


def trigger_run(job):
    """Manually trigger a pipeline job in the background. Returns run id."""
    if job not in JOB_SCRIPTS:
        raise ValueError(f"unknown job: {job}")
    state = load_state()
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + job
    state.setdefault("runs", {})[run_id] = {
        "job": job,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "running",
        "finished_at": None,
        "note": None,
    }
    save_state(state)

    def _do():
        script = os.path.join(PROJECT_ROOT, JOB_SCRIPTS[job])
        rc, out, err = _run(f"bash {script}", timeout=1800)
        st = load_state()
        st.setdefault("runs", {}).setdefault(run_id, {})
        st["runs"][run_id].update({
            "status": "done" if rc == 0 else "failed",
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": ((out + err).strip()[-400:]) or None,
        })
        save_state(st)

    run_in_thread(_do)
    return run_id


def recent_runs(limit=20):
    state = load_state()
    runs = state.get("runs", {})
    items = sorted(runs.values(), key=lambda r: r.get("started_at") or "", reverse=True)
    return items[:limit]


# --------------------------------------------------------------------------
# LiteLLM integration
# --------------------------------------------------------------------------

def _litellm_cfg():
    env = get_dashboard_env()
    state = load_state()
    llm = state.get("litellm", {})
    return {
        "base_url": env.get("LITELLM_BASE_URL") or llm.get("base_url") or "http://172.20.1.52:4000",
        "master_key": env.get("LITELLM_MASTER_KEY") or llm.get("master_key") or "",
    }


def _litellm_headers():
    cfg = _litellm_cfg()
    return {"Authorization": f"Bearer {cfg['master_key']}"}


def _litellm_get(path, params=None):
    import urllib.parse
    import requests
    cfg = _litellm_cfg()
    url = cfg["base_url"].rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    r = requests.get(url, headers=_litellm_headers(), timeout=20)
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


def _litellm_post(path, payload):
    import requests
    cfg = _litellm_cfg()
    url = cfg["base_url"].rstrip("/") + path
    r = requests.post(url, headers=_litellm_headers(), json=payload, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, r.text[:400]


def litellm_health():
    import requests
    cfg = _litellm_cfg()
    out = {"base_url": cfg["base_url"], "ok": False, "liveliness": None, "readiness": None}
    for key, path in (("liveliness", "/health/liveliness"), ("readiness", "/health/readiness")):
        try:
            r = requests.get(cfg["base_url"].rstrip("/") + path, timeout=10)
            out[key] = r.status_code
            out["ok"] = out["ok"] or r.status_code == 200
        except Exception as e:  # noqa: BLE001
            out[key] = f"error: {str(e)[:80]}"
    return out


def litellm_models():
    code, data = _litellm_get("/v1/models")
    if code == 200 and isinstance(data, dict):
        return {"ok": True, "models": [m.get("id") for m in data.get("data", [])]}
    return {"ok": False, "error": str(data)[:300]}


def litellm_model_info(model_name):
    code, data = _litellm_get("/model/info", {"model_name": model_name})
    return {"ok": code == 200, "code": code, "data": data}


def litellm_add_model(payload):
    """payload: {model_name, model, api_base, litellm_params?, mode?}."""
    body = {
        "model_name": payload["model_name"],
        "litellm_params": {
            "model": payload["model"],
            **({"api_base": payload["api_base"]} if payload.get("api_base") else {}),
            **(payload.get("litellm_params_extra") or {}),
        },
    }
    if payload.get("mode"):
        body["mode"] = payload["mode"]
    code, data = _litellm_post("/model/new", body)
    return {"ok": code == 200, "code": code, "data": data}


def litellm_delete_model(model_name, model_id):
    body = {"model_name": model_name}
    if model_id:
        body["model_id"] = model_id
    code, data = _litellm_post("/model/delete", body)
    return {"ok": code == 200, "code": code, "data": data}


# --------------------------------------------------------------------------
# System health (aggregated)
# --------------------------------------------------------------------------

def system_health():
    h = {}
    # disk
    rc, out, _ = _run("df -h /home | tail -1", timeout=15)
    if rc == 0 and out.strip():
        parts = out.split()
        if len(parts) >= 5:
            h["disk"] = {"size": parts[1], "used": parts[2], "avail": parts[3], "pct": parts[4]}
    # site reachability
    import requests
    try:
        r = requests.get("https://radio.iranseda.ir/", timeout=10)
        h["site"] = {"reachable": True, "http": r.status_code}
    except Exception as e:  # noqa: BLE001
        h["site"] = {"reachable": False, "error": str(e)[:80]}
    # db
    h["db"] = db_health()
    # containers
    rc, out, _ = _run("docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -i iranseda", timeout=20)
    h["containers"] = {}
    for line in (out or "").splitlines():
        p = line.split("\t")
        if len(p) >= 2:
            h["containers"][p[0]] = p[1].strip()
    return h


# --------------------------------------------------------------------------
# LLM post-processing jobs
#   full_text / summary / correct_text / correct_subtitles — each a separate
#   phase + job + output (files under downloads/cleaned/ AND rows in llm_output).
#   Prompts live in the DB (prompts table, one default per job_type).
#   All heavy lifting is in llm_jobs.py (imported lazily, same venv).
# --------------------------------------------------------------------------

LLM_JOB_TYPES = ["full_text", "summary", "correct_text", "correct_subtitles"]
_LLM_JOB_LABELS = {
    "full_text": "متن کامل (حذف تایم‌کد)",
    "summary": "خلاصه‌نویسی",
    "correct_text": "تصحیح متن کامل",
    "correct_subtitles": "تصحیح زیرنویس (SRT)",
}

_LLM_MOD = None
_llm_run_state = {}
_llm_run_lock = threading.Lock()


def _now_iso():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _llm():
    """Lazily import llm_jobs (sibling module, same dashboard/ dir + venv)."""
    global _LLM_MOD
    if _LLM_MOD is None:
        import sys
        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)
        import llm_jobs
        _LLM_MOD = llm_jobs
    return _LLM_MOD


def llm_discover_models():
    """Auto-discovery: read the LiteLLM proxy's /v1/models."""
    try:
        return _llm().discover_models()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


def llm_prompts():
    conn = _llm()._db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, slug, job_type, name, prompt, is_default, created_at "
                "FROM prompts ORDER BY job_type, is_default DESC, id")
            rows = cur.fetchall()
    finally:
        conn.close()
    return {"ok": True, "prompts": rows, "job_types": LLM_JOB_TYPES, "labels": _LLM_JOB_LABELS}


def llm_save_prompt(payload):
    """payload: {id?, job_type, name, prompt, is_default?} — update if id, else insert."""
    job = (payload.get("job_type") or "").strip()
    if job not in LLM_JOB_TYPES:
        raise ValueError("bad job_type")
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("پرامپت خالی است")
    name = (payload.get("name") or job).strip() or job
    is_default = 1 if payload.get("is_default") else 0
    conn = _llm()._db_conn()
    try:
        with conn.cursor() as cur:
            if payload.get("id"):
                cur.execute("UPDATE prompts SET name=%s, prompt=%s, is_default=%s WHERE id=%s",
                            (name, prompt, is_default, payload["id"]))
            else:
                slug = (payload.get("slug") or "").strip() or f"{job}-{int(time.time())}"
                cur.execute(
                    "INSERT INTO prompts (slug, job_type, name, prompt, is_default) "
                    "VALUES (%s,%s,%s,%s,%s)", (slug, job, name, prompt, is_default))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def llm_set_default_prompt(prompt_id):
    conn = _llm()._db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT job_type FROM prompts WHERE id=%s", (prompt_id,))
            r = cur.fetchone()
            if not r:
                raise ValueError("پرامپت یافت نشد")
            cur.execute("UPDATE prompts SET is_default=0 WHERE job_type=%s", (r["job_type"],))
            cur.execute("UPDATE prompts SET is_default=1 WHERE id=%s", (prompt_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def llm_delete_prompt(prompt_id):
    conn = _llm()._db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT is_default FROM prompts WHERE id=%s", (prompt_id,))
            r = cur.fetchone()
            if r and r["is_default"]:
                raise ValueError("پرامپت پیش‌فرض حذف نمی‌شود؛ ابتدا دیگری را پیش‌فرض کنید")
            cur.execute("DELETE FROM prompts WHERE id=%s", (prompt_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def llm_run(payload):
    """Start a job batch in a background thread (define-a-job-from-prompt).
    payload: {job_type, model?, prompt_id?, prompt?, limit?, ids?[], all?}."""
    job = (payload.get("job_type") or "").strip()
    if job not in LLM_JOB_TYPES:
        raise ValueError("bad job_type")
    model = (payload.get("model") or "qwen38-nothinking").strip()
    prompt_text = None
    if payload.get("prompt"):
        prompt_text = payload["prompt"].strip()
    elif payload.get("prompt_id"):
        conn = _llm()._db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT prompt FROM prompts WHERE id=%s", (payload["prompt_id"],))
                r = cur.fetchone()
            prompt_text = r["prompt"] if r else None
        finally:
            conn.close()
    limit = int(payload.get("limit") or 10)
    ids = payload.get("ids") or None
    if ids:
        ids = [int(x) for x in ids]
    all_files = bool(payload.get("all_files"))
    all_flag = bool(payload.get("all"))
    handle = f"{job}-{int(time.time())}"
    with _llm_run_lock:
        _llm_run_state[handle] = {
            "job_type": job, "label": _LLM_JOB_LABELS.get(job, job), "model": model,
            "status": "running", "started_at": _now_iso(), "detail": "در صف", "result": None,
        }

    def _work():
        with _llm_run_lock:
            _llm_run_state[handle]["detail"] = "شروع شد"
        try:
            if all_files:
                res = _llm().run_over_all_files(job, model=model, prompt_text=prompt_text,
                                                 limit=limit, only_new=not all_flag)
            else:
                res = _llm().run_batch(job, model=model, prompt_text=prompt_text,
                                       limit=None if ids else limit, session_ids=ids,
                                       only_new=not all_flag)
            with _llm_run_lock:
                _llm_run_state[handle].update(
                    {"status": "done", "finished_at": _now_iso(), "result": res,
                     "detail": f"{res.get('done',0)} انجام شد، {res.get('failed',0)} خطا"})
        except Exception as e:  # noqa: BLE001
            with _llm_run_lock:
                _llm_run_state[handle].update(
                    {"status": "error", "finished_at": _now_iso(), "detail": str(e)[:300]})

    run_in_thread(_work)
    return {"ok": True, "handle": handle}


def llm_runs(limit=8):
    with _llm_run_lock:
        items = sorted(_llm_run_state.items(),
                       key=lambda kv: kv[1].get("started_at", ""), reverse=True)
    return {"ok": True, "runs": items[:limit]}


def llm_outputs(limit=30):
    conn = _llm()._db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT o.session_id, s.filename, o.job_type, o.model, o.status, o.error, "
                "o.input_tokens, o.output_tokens, o.finished_at, o.file_relpath "
                "FROM llm_output o LEFT JOIN radio_program_sessions s ON s.id=o.session_id "
                "ORDER BY o.id DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
    finally:
        conn.close()
    for r in rows:
        r["input_tokens"] = r.get("input_tokens") or 0
        r["output_tokens"] = r.get("output_tokens") or 0
        if r.get("error") is None:
            r["error"] = ""
    return {"ok": True, "outputs": rows}


def llm_report(n=1):
    try:
        items = _llm().report(n)
        return {"ok": True, "items": items, "markdown": _llm().report_markdown(items)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}
