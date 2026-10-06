"""
iranseda dashboard — FastAPI app.

Run (server 53) via the systemd service, or manually:
    cd dashboard
    IRANSEDA_ROOT=/home/saber/saberprojects/iranseda-crawler-golang- \
    DASH_AUTH_TOKEN=*** \
    venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8990

Endpoints:
  - `GET /`                     the single-page dashboard (open in browser once)
  - `GET /health`               liveness (always open, no auth)
  - `GET /metrics`              Prometheus text-format metrics (no auth)
  - `GET /api/health`           system health aggregate (JSON)
  - `GET /api/stats`            DB metrics + trends (JSON)
  - `GET /api/jobs`             container + cron job status (JSON)
  - `POST /api/jobs/{job}/run`  manually trigger a pipeline job
  - `GET /api/runs`             recent manual runs
  - `GET  /api/settings`        .env + cron + compose + dashboard.env (JSON)
  - `PUT  /api/settings/env`    update .env keys
  - `PUT  /api/settings/cron`   update schedule (pipeline / refresh_site)
  - `PUT  /api/settings/whisper`update whisper compose env (+ restart containers)
  - `PUT  /api/settings/envvars`update dashboard.env (LITELLM_*)
  - `GET /api/litellm/health`   LiteLLM liveness
  - `GET /api/litellm/models`   list models
  - `POST /api/litellm/models`  add a model
  - `DELETE /api/litellm/models/{name}`  delete a model

Auth: every route EXCEPT /, /health and /metrics requires `Authorization:
Bearer <DASH_AUTH_TOKEN>` (header or ?token=*** When DASH_AUTH_TOKEN is
unset the dashboard runs open (only for LAN testing).
"""
import os
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

import logic

app = FastAPI(title="iranseda dashboard")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

AUTH_TOKEN = os.environ.get("DASH_AUTH_TOKEN", "")
OPEN_PATHS = {"/", "/health", "/metrics"}

# tiny cache so the auto-refresh (every 30s) doesn't hammer the DB
_cache = {"stats": None, "health": None, "ts": 0.0}
CACHE_TTL = 15  # seconds


@app.middleware("http")
async def _auth(request: Request, call_next):
    if request.url.path not in OPEN_PATHS:
        if AUTH_TOKEN:
            provided = request.headers.get("authorization", "")
            if provided.startswith("Bearer "):
                provided = provided[len("Bearer "):]
            elif request.query_params.get("token"):
                provided = request.query_params.get("token")
            else:
                provided = ""
            if provided != AUTH_TOKEN:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


def _cached_stats():
    now = time.time()
    if _cache["stats"] is None or now - _cache["ts"] > CACHE_TTL:
        _cache["stats"] = logic.db_metrics()
        _cache["ts"] = now
    return _cache["stats"]


def _cached_health():
    now = time.time()
    if _cache["health"] is None or now - _cache["ts"] > CACHE_TTL:
        _cache["health"] = logic.system_health()
        _cache["ts"] = now
    return _cache["health"]


# ---------------------------------------------------------------------------
# pages + monitoring endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health", response_class=PlainTextResponse)
def health():
    h = _cached_health()
    if h.get("db", {}).get("ok"):
        return "ok\n"
    return "degraded (db not reachable)\n"


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus text-format endpoint."""
    s = _cached_stats()
    h = _cached_health()
    jobs = logic.jobs_status()
    lines = []

    def g(name, value, help_str, labels=""):
        lines.append(f"# HELP {name} {help_str}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name}{labels} {value}")

    # db
    db_ok = 1 if h.get("db", {}).get("ok") else 0
    g("iranseda_db_ok", db_ok, "DB reachable (1) or not (0)")
    if s.get("ok"):
        g("iranseda_db_total_sessions", s.get("total_sessions", 0), "Total radio_program_sessions rows")
        g("iranseda_db_max_id", s.get("max_id", 0), "Highest session id (monotonic growth marker)")
        for row in s.get("status", []):
            g("iranseda_db_sessions_by_status", row["count"], "Sessions by status",
              labels=f'{{status="{row["status"]}"}}')
        depth = {r["status"]: r["count"] for r in s.get("status", [])}
        g("iranseda_queue_pending_download", depth.get("pending_download", 0), "Pending download queue")
        g("iranseda_queue_pending_transcribe", depth.get("pending_transcribe", 0), "Pending transcribe queue")
        g("iranseda_queue_transcribing", depth.get("transcribing", 0), "Currently transcribing")
        g("iranseda_queue_failed_permanent", depth.get("failed_permanent", 0), "Failed permanent (parked)")
        g("iranseda_sessions_created_last_24h", s.get("created_last_24h", 0), "New sessions in last 24h")
        subtitled_series = s.get("last30d_subtitled", [])
        g("iranseda_subtitled_last_7d", sum(r["count"] for r in subtitled_series[-7:]) if subtitled_series else 0,
          "Subtitled in last 7 days")
    # containers
    for name, status in (h.get("containers") or {}).items():
        up = 1 if status.lower().startswith("up") else 0
        g("iranseda_container_up", up, f"Container {name} up (1) or down (0)", labels=f'{{name="{name}"}}')
    # whisper throughput
    worker = jobs.get("iranseda-whisper-worker", {})
    g("iranseda_whisper_transcribed_last_5m", worker.get("transcribed_last_5m", 0), "Files transcribed in last 5 min")
    # site
    g("iranseda_site_reachable", 1 if h.get("site", {}).get("reachable") else 0, "radio.iranseda.ir reachable (1) or not (0)")
    # disk
    disk = h.get("disk", {})
    if disk and disk.get("pct"):
        try:
            pct = int(str(disk.get("pct")).rstrip("%")) / 100.0
            g("iranseda_disk_used_ratio", pct, "Disk usage ratio (0-1) for /home")
        except (ValueError, TypeError):
            pass
    g("iranseda_dashboard_up", 1, "Dashboard up")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# stats / jobs / runs
# ---------------------------------------------------------------------------

@app.get("/api/health")
def api_health():
    return _cached_health()


@app.get("/api/stats")
def api_stats():
    return _cached_stats()


@app.get("/api/jobs")
def api_jobs():
    return logic.jobs_status()


@app.post("/api/jobs/{job}/run")
def api_trigger(job: str):
    try:
        run_id = logic.trigger_run(job)
        return {"ok": True, "run_id": run_id}
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


@app.get("/api/runs")
def api_runs():
    return logic.recent_runs()


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def api_settings():
    return {
        "env": logic.get_env(),
        "editable_env": logic.EDITABLE_ENV_KEYS,
        "schedule": logic.get_schedule(),
        "whisper": logic.get_compose_whisper(),
        "dashboard_env": logic.get_dashboard_env(),
    }


@app.put("/api/settings/env")
async def api_save_env(request: Request):
    body = await request.json()
    try:
        updated = logic.save_env(body)
        return {"ok": True, "env": updated}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)[:300])


@app.put("/api/settings/cron")
async def api_save_cron(request: Request):
    body = await request.json()
    try:
        sched = logic.save_schedule(body)
        return {"ok": True, "schedule": sched}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)[:300])


@app.put("/api/settings/whisper")
async def api_save_whisper(request: Request):
    body = await request.json()
    try:
        result = logic.save_compose_whisper(body)
        return {"ok": True, **result}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)[:300])


@app.put("/api/settings/envvars")
async def api_save_envvars(request: Request):
    body = await request.json()
    try:
        updated = logic.save_dashboard_env(body)
        return {"ok": True, "dashboard_env": updated}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)[:300])


# ---------------------------------------------------------------------------
# LiteLLM
# ---------------------------------------------------------------------------

@app.get("/api/litellm/health")
def api_litellm_health():
    return logic.litellm_health()


@app.get("/api/litellm/models")
def api_litellm_models():
    return logic.litellm_models()


@app.post("/api/litellm/models")
async def api_litellm_add(request: Request):
    body = await request.json()
    try:
        result = logic.litellm_add_model(body)
        return result
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)[:300])


@app.delete("/api/litellm/models/{model_name}")
def api_litellm_delete(model_name: str, model_id: str = ""):
    return logic.litellm_delete_model(model_name, model_id)


@app.on_event("startup")
def _startup():
    logic.run_in_thread(_warm)


def _warm():
    try:
        _cached_stats()
        _cached_health()
    except Exception:  # noqa: BLE001
        pass
