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
    rc, o, e = _run(f"crontab -")  # noop guard
    import io
    proc = subprocess.run("crontab -", input="\n".join(out) + "\n", text=True,
                          capture_output=True)
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
