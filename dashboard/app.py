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
  - `GET  /api/window`          active time-window (سانس) state
  - `PUT  /api/window`          set window (enabled, tz, blocks[])
  - `GET  /api/window/activity`per-hour transcription/discovery for a day
  - `POST /api/worker/start|stop`manually start/stop the whisper worker
  - `GET /api/litellm/health`   LiteLLM liveness
  - `GET /api/litellm/models`   list models
  - `POST /api/litellm/models`  add a model
  - `DELETE /api/litellm/models/{name}`  delete a model
  - `GET  /api/llm/models`      auto-discover models from LiteLLM /v1/models
  - `GET  /api/llm/prompts`     list prompts (per job_type, with defaults)
  - `POST /api/llm/prompts`     create / update a prompt
  - `POST /api/llm/prompts/{id}/default`  make a prompt the job default
  - `DELETE /api/llm/prompts/{id}`       delete a prompt
  - `POST /api/llm/run`          start a job batch (job_type/model/prompt/limit/ids)
  - `GET  /api/llm/runs`         recent job runs (in-process)
  - `GET  /api/llm/outputs`      recent llm_output rows (1:many)
  - `GET  /api/llm/report`       before/after quality report for a session

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


def _label_escape(s: str) -> str:
    """Escape a value for use in a Prometheus label (\\, ", newline)."""
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


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
    # LLM post-production (files on disk + llm_output rows + live shard workers)
    lfm = logic.llm_file_counts()
    if lfm:
        g("iranseda_llm_full_text", lfm.get("full_text", 0), "full_text outputs on disk (.full.txt)")
        g("iranseda_llm_summary_fa", lfm.get("summary_fa", 0), "Persian summary outputs on disk (.summary.txt)")
        g("iranseda_llm_summary_en", lfm.get("summary_en", 0), "English summary outputs on disk (.summary.en.txt)")
        g("iranseda_llm_correct_text", lfm.get("correct_text", 0), "correct_text outputs on disk (.correct.txt)")
        g("iranseda_llm_correct_subtitles", lfm.get("correct_subtitles", 0), "correct_subtitles outputs on disk (.correct.srt)")
        g("iranseda_llm_total_srt", lfm.get("total_srt", 0), "Total .srt files on disk (denominator for LLM progress)")
        for jt, c in (lfm.get("db_by_job") or {}).items():
            g("iranseda_llm_db_rows", c, "llm_output rows by job_type", labels=f'{{job="{jt}"}}')
        g("iranseda_llm_workers", lfm.get("workers", 0), "Running LLM run-all shard workers")
    # Site-facing period counts (by DB created_at — the same source the GitHub
    # site uses, so Grafana matches the site). Keys map to the site's stat cards.
    sps = logic.site_period_stats()
    if sps:
        site_keys = [
            ("iranseda_site_today", "today", "Subtitles added today"),
            ("iranseda_site_yesterday", "yesterday", "Subtitles added yesterday"),
            ("iranseda_site_this_week", "this_week", "Subtitles added this week"),
            ("iranseda_site_last_week", "last_week", "Subtitles added last week"),
            ("iranseda_site_this_month", "this_month", "Subtitles added this month"),
            ("iranseda_site_last_month", "last_month", "Subtitles added last month"),
            ("iranseda_site_this_year", "this_year", "Subtitles added this year"),
            ("iranseda_site_last_year", "last_year", "Subtitles added last year"),
            ("iranseda_site_2y", "y2", "Subtitles added 2 years ago"),
            ("iranseda_site_3y", "y3", "Subtitles added 3 years ago"),
            ("iranseda_site_5y", "y5", "Subtitles added 5 years ago"),
            ("iranseda_site_10y", "y10", "Subtitles added 10 years ago"),
        ]
        for name, key, help_str in site_keys:
            g(name, sps.get(key, 0), help_str)
    # Per-program episode / subtitled / full-text counts (matches site program cards)
    pms = logic.program_metrics()
    if pms:
        for name, c in pms.items():
            label = f'{{program="{_label_escape(name)}"}}'
            g("iranseda_program_episodes", c.get("episodes", 0), "Episodes per program", labels=label)
            g("iranseda_program_subtitled", c.get("subtitled", 0), "Subtitled episodes per program", labels=label)
            g("iranseda_program_fulltext", c.get("fulltext", 0), "Full-text outputs per program", labels=label)
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
# active time-window (سانس) that gates the GPU transcriber
# ---------------------------------------------------------------------------

@app.get("/api/window")
def api_window():
    return logic.get_window()


@app.put("/api/window")
async def api_save_window(request: Request):
    body = await request.json()
    try:
        return {"ok": True, "window": logic.set_window(body)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, detail=str(e)[:300])


@app.get("/api/window/activity")
def api_window_activity(offset: int = 0):
    return logic.window_activity(offset)


@app.post("/api/worker/{action}")
def api_worker(action: str):
    try:
        return {"ok": True, "window": logic.worker_set(action)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, detail=str(e)[:300])


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


# ---------------------------------------------------------------------------
# LLM post-processing jobs (full_text / summary / correct_text / correct_subtitles)
# ---------------------------------------------------------------------------

@app.get("/api/llm/models")
def api_llm_discover():
    return logic.llm_discover_models()


@app.get("/api/llm/prompts")
def api_llm_prompts():
    return logic.llm_prompts()


@app.post("/api/llm/prompts")
async def api_llm_save_prompt(request: Request):
    body = await request.json()
    try:
        return logic.llm_save_prompt(body)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)[:300])


@app.post("/api/llm/prompts/{prompt_id}/default")
def api_llm_set_default(prompt_id: int):
    try:
        return logic.llm_set_default_prompt(prompt_id)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)[:300])


@app.delete("/api/llm/prompts/{prompt_id}")
def api_llm_delete_prompt(prompt_id: int):
    try:
        return logic.llm_delete_prompt(prompt_id)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)[:300])


@app.post("/api/llm/run")
async def api_llm_run(request: Request):
    body = await request.json()
    try:
        return logic.llm_run(body)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, detail=str(e)[:300])


@app.get("/api/llm/runs")
def api_llm_runs():
    return logic.llm_runs()


@app.get("/api/llm/outputs")
def api_llm_outputs():
    return logic.llm_outputs()


@app.get("/api/llm/report")
def api_llm_report(n: int = 1):
    return logic.llm_report(n)


@app.on_event("startup")
def _startup():
    logic.run_in_thread(_warm)
    logic.start_gate_loop()


def _warm():
    try:
        _cached_stats()
        _cached_health()
    except Exception:  # noqa: BLE001
        pass
