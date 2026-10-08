"""
iranseda night / holiday GPU-boost controller.

A small, safe, in-process controller (no new services) that decides how many
parallel LLM "run-all" shard workers iranseda should run, so it can burn the
LLM backlog (correct_subtitles) on idle GPU during nights / holidays WITHOUT
starving the models' primary interactive users or the co-located work on the
same H100s (embeddings, finetune LoRA servers, whisper).

Modes
  NORMAL  -- `normal_workers` shards, 24/7 baseline backlog burn.
  BOOST   -- up to `boost_workers` shards, but AUTO-THROTTLED by live load:
            the target is clamped down when the models / GPUs look busy.
  PAUSED  -- 0 shards (the kill switch). Everything else (model servers,
             whisper, dashboard) keeps running; only iranseda background work
             stops.

Safety model (interactive traffic ALWAYS wins):
  The controller reads live load from Prometheus on server 52 (vllm / sglang /
  DCGM metrics -- the authoritative, already-scraped source). It computes a
  load level (LOW/MEDIUM/HIGH/CRITICAL) and maps it to a max allowed worker
  count:
        LOW -> boost_workers,  MEDIUM -> 2,  HIGH -> 1,  CRITICAL -> 0
  It specifically refuses to use the model (allowed -> 0, logged) when:
    * external interactive requests on the model in use exceed `user_request_cap`
      (running_requests - our own workers > cap) -- the explicit "don't use it
      when >5 users" rule, or
    * Prometheus is unreachable (can't see the road -> hold off).
  It tapers (1..2 workers) when sglang token usage / queue / vllm-waiting grow.
  DCGM SM utilisation is advisory-only (the H100s stay ~99% from the serving
  stack itself), so it is shown but does not force a stop.
  Every back-off / skip is logged (to scripts/logs/boost.log and to the "last"
  state) with the REASON, so the dashboard can show *why* it withheld a model.

It NEVER starts/stops the model servers, whisper, or the dashboard. It only
launches/kills iranseda `llm_jobs.py run-all` shard processes and reconciles
their count every ~30s in a thread started by the dashboard.

State lives in dashboard_state.json["boost"] (single source of truth, edited
by the dashboard UI or the CLI). Env vars IRANSEDA_BOOST_* are a one-time seed
for ops convenience; state is authoritative after first write.

CLI wrapper: scripts/iranseda-boost  (status | start | stop | normal | pause)
"""
import json
import os
import re
import shlex
import signal
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.environ.get(
    "IRANSEDA_ROOT", os.path.abspath(os.path.join(BASE_DIR, ".."))
)
DOWNLOADS = os.path.join(PROJECT_ROOT, "downloads")
CLEANED = os.path.join(DOWNLOADS, "cleaned")
LOG_PATH = os.path.join(PROJECT_ROOT, "scripts", "logs", "boost.log")
PYTHON = os.path.join(PROJECT_ROOT, "dashboard", "venv", "bin", "python3")

# Where the load signals live (Prometheus on server 52 -- reachable from 53).
PROM_URL = os.environ.get("IRANSEDA_PROM", "http://172.20.1.52:9090")
# The big Qwen model's name as it appears in the vllm/sglang metrics.
QWEN_MODEL = os.environ.get("IRANSEDA_QWEN_METRIC", "/models/Qwen3.8-27B-FP8")

TEHRAN = "Asia/Tehran"

MODES = ("NORMAL", "BOOST", "PAUSED")

# output-file suffix per job_type (matches llm_jobs.py).
JOB_SUFFIX = {
    "full_text": ".full.txt",
    "summary": ".summary.txt",
    "correct_text": ".correct.txt",
    "correct_subtitles": ".correct.srt",
}

DEFAULT_BOOST = {
    # master: is the boost scheduler on at all? (drives the night/holiday window)
    "enabled": True,
    # explicit mode override. Default PAUSED = inert until explicitly started,
    # so a fresh deploy does ZERO GPU work (the diagnosis shows the H100s are
    # often busy with co-located work; opt in deliberately).
    "mode": "PAUSED",
    "job": "correct_subtitles",
    # The reliable, fast model. qwen38 (thinking) returns no content at low
    # max_tokens and qwen38-sglang is congested (see docs/prompts/005).
    "model": "qwen38-nothinking",
    # concurrency (kept conservative on purpose).
    "normal_workers": 1,
    "boost_workers": 2,
    "min_workers": 1,
    "auto_throttle": True,
    # night / holiday window (configurable, NOT hard-coded days).
    "window": {"enabled": True, "start": "22:00", "end": "08:00", "tz": TEHRAN},
    "holiday": {"enabled": True, "auto": True, "days": [5, 6], "extra": []},
    # hard auto-stop for a one-off overnight run (ISO 8601 with offset).
    "max_run_end": "",
    # load thresholds (all configurable).
    "guard": {
        "user_request_cap": 5,       # external requests on the model in use
        "sglang_token_cap": 0.7,     # sglang token_usage (0-1)
        "vllm_waiting_cap": 5,       # vllm waiting requests
        "queue_cap": 6,              # vllm waiting + sglang queue
        "dcgm_util_cap": 0.9,        # per-H100 SM utilisation (0-1)
        "prom_timeout": 6,
    },
    # rolling state filled by the controller (for /api/boost + /metrics).
    "last": {"ts": 0, "active": 0, "target": 0, "level": -1,
             "skipping": False, "throttled": False, "reason": "", "load": {}},
    "shards": {},   # shard_index -> pid (for the kill switch / reconciliation)
}

_lock = threading.Lock()
_running = False          # thread guard
_last_snapshot = {"data": None, "ts": 0.0}   # for /metrics (avoid re-query)
_LAST_LEVEL_CHANGE = {}   # shard-index -> monotonic ts, for launch hysteresis


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

def _db_env():
    env = os.environ
    ep = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(ep):
        for line in open(ep, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env.setdefault(k.strip(), v.strip())
    return env


def load_boost():
    """Read the boost state, merging in the per-key defaults (so new keys
    added in code appear without a rewrite)."""
    import logic  # sibling module; uses its own _state_lock for the file
    st = logic.load_state().get("boost") or {}
    merged = _deep_merge(json.loads(json.dumps(DEFAULT_BOOST)), st or {})
    return merged


def _save_boost(boost):
    import logic
    st = logic.load_state()
    st["boost"] = boost
    logic.save_state(st)


def _deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _seed_from_env():
    """One-time convenience: apply IRANSEDA_BOOST_* env vars to state if the
    user set them and state hasn't been explicitly changed. Best-effort."""
    env = os.environ
    patch = {}
    if env.get("IRANSEDA_BOOST_ENABLED") is not None:
        patch["enabled"] = env["IRANSEDA_BOOST_ENABLED"].lower() in ("1", "true", "yes")
    if env.get("IRANSEDA_BOOST_START"):
        patch.setdefault("window", {})["start"] = env["IRANSEDA_BOOST_START"]
    if env.get("IRANSEDA_BOOST_END"):
        patch.setdefault("window", {})["end"] = env["IRANSEDA_BOOST_END"]
    if env.get("IRANSEDA_NORMAL_WORKERS"):
        patch["normal_workers"] = int(env["IRANSEDA_NORMAL_WORKERS"])
    if env.get("IRANSEDA_BOOST_WORKERS"):
        patch["boost_workers"] = int(env["IRANSEDA_BOOST_WORKERS"])
    if env.get("IRANSEDA_HOLIDAY_BOOST") is not None:
        patch.setdefault("holiday", {})["enabled"] = env["IRANSEDA_HOLIDAY_BOOST"].lower() in ("1", "true", "yes")
    if env.get("IRANSEDA_WEEKEND_DAYS"):
        patch.setdefault("holiday", {})["days"] = _parse_days(env["IRANSEDA_WEEKEND_DAYS"])
    if not patch:
        return
    boost = load_boost()
    for k, v in patch.items():
        if isinstance(v, dict):
            boost[k] = _deep_merge(boost.get(k, {}), v)
        else:
            boost[k] = v
    _save_boost(boost)


def _parse_days(s):
    out = set()
    names = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}
    for part in re.split(r"[,\s]+", s.lower()):
        part = part.strip()
        if not part:
            continue
        if part.isdigit():
            out.add(int(part) % 7)
        elif part in names:
            out.add(names[part])
    return sorted(out) if out else [5, 6]


# ---------------------------------------------------------------------------
# time
# ---------------------------------------------------------------------------

def _now(tz):
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz))
    except Exception:  # noqa: BLE001
        return datetime.now()


def _parse_hhmm(s, default):
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:  # noqa: BLE001
        h, m = default.split(":")
        return int(h) * 60 + int(m)


def in_window(window, now):
    """True if `now` is inside a possibly-midnight-wrapping window."""
    if not window.get("enabled"):
        return False
    start = _parse_hhmm(window.get("start", "22:00"), "22:00")
    end = _parse_hhmm(window.get("end", "08:00"), "08:00")
    cur = now.hour * 60 + now.minute
    if start <= end:
        return start <= cur < end
    return cur >= start or cur < end  # wraps midnight


def on_holiday(boost, now):
    h = boost.get("holiday") or {}
    if not h.get("enabled"):
        return False
    if h.get("auto"):
        return now.weekday() in (h.get("days") or [5, 6])
    # auto disabled: only user-added explicit dates (YYYY-MM-DD) count.
    return now.strftime("%Y-%m-%d") in (h.get("extra") or [])


# ---------------------------------------------------------------------------
# load (from Prometheus on 52)
# ---------------------------------------------------------------------------

def _prom(query, timeout):
    u = PROM_URL + "/api/v1/query?query=" + urllib.parse.quote(query)
    with urllib.request.urlopen(u, timeout=timeout) as r:
        return json.load(r).get("data", {}).get("result", [])


def _first_value(res):
    for x in res:
        if x.get("value"):
            try:
                return float(x["value"][1])
            except (TypeError, ValueError):
                return None
    return None


def read_load(boost):
    """Read live model/GPU load from Prometheus. Returns a dict of the signals
    the guard uses. Any failure -> {"error": ...} and the controller treats it
    as CRITICAL (back off) so we never push when we can't see the road."""
    g = boost.get("guard") or {}
    timeout = int(g.get("prom_timeout", 6))
    try:
        q = 'vllm:num_requests_running{model_name="%s"}' % QWEN_MODEL
        vllm_running = _first_value(_prom(q, timeout)) or 0.0
        vllm_waiting = _first_value(_prom('vllm:num_requests_waiting{model_name="%s"}' % QWEN_MODEL, timeout)) or 0.0
        sg_running = _first_value(_prom('sglang_num_running_reqs{model_name="%s"}' % QWEN_MODEL, timeout)) or 0.0
        sg_queue = _first_value(_prom('sglang_num_queue_reqs{model_name="%s"}' % QWEN_MODEL, timeout)) or 0.0
        sg_token = _first_value(_prom('sglang_token_usage{model_name="%s"}' % QWEN_MODEL, timeout)) or 0.0
        g0 = _first_value(_prom('max(DCGM_FI_DEV_GPU_UTIL{gpu="0"})', timeout)) or 0.0
        g1 = _first_value(_prom('max(DCGM_FI_DEV_GPU_UTIL{gpu="1"})', timeout)) or 0.0
        return {
            "ok": True,
            "vllm_running": vllm_running, "vllm_waiting": vllm_waiting,
            "sglang_running": sg_running, "sglang_queue": sg_queue,
            "sglang_token": sg_token,
            "gpu0_util": g0 / 100.0, "gpu1_util": g1 / 100.0,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": repr(e)[:200]}


def load_level(load, boost, our_workers):
    """Map live load -> (level 0..3, max_allowed_workers, reason).

    The user's explicit rule: when more than `user_request_cap` *interactive*
    requests are on the model in use, DO NOT use it (allowed -> 0, log why).
    sglang token / queue pressure taper it down (1..2 workers). We intentionally
    do NOT gate on raw DCGM SM utilisation: the H100s sit ~99% from the serving
    stack itself, so it would be a permanent false-block -- it's surfaced as an
    advisory in the reason only.
    """
    g = boost.get("guard") or {}
    bw = int(boost.get("boost_workers", 4))
    if not load.get("ok"):
        return 3, 0, "prometheus unreachable; holding off (%s)" % load.get("error")
    reasons = []
    level = 0
    # external interactive pressure on the model in use (total running minus ours)
    ext = max(0.0, (load.get("vllm_running", 0) + load.get("sglang_running", 0)) - our_workers)
    cap = int(g.get("user_request_cap", 5))
    if ext > cap:
        # the explicit "don't use it" condition: yield entirely to interactive
        level = 3
        reasons.append("NOT using model: %d interactive requests > cap %d" % (int(ext), cap))
    if load.get("sglang_token", 0) > g.get("sglang_token_cap", 0.7):
        level = max(level, 1)
        reasons.append("sglang token %.2f > cap %s" % (load["sglang_token"], g.get("sglang_token_cap")))
    if (load.get("vllm_waiting", 0) + load.get("sglang_queue", 0)) > g.get("queue_cap", 6):
        level = max(level, 1)
        reasons.append("queue %d > cap %s" % (int(load.get("vllm_waiting", 0) + load.get("sglang_queue", 0)), g.get("queue_cap")))
    if load.get("vllm_waiting", 0) > g.get("vllm_waiting_cap", 5):
        level = max(level, 2)
        reasons.append("vllm waiting %d > cap %s" % (int(load["vllm_waiting"]), g.get("vllm_waiting_cap")))
    # advisory only -- co-located serving keeps the SMs near 100% always
    gutil = max(load.get("gpu0_util", 0), load.get("gpu1_util", 0))
    if gutil > g.get("dcgm_util_cap", 0.9):
        reasons.append("(advisory) GPU util %.0f%% high (serving stack)" % (gutil * 100))
    allowed = {0: bw, 1: min(2, bw), 2: 1, 3: 0}[level]
    return level, allowed, "; ".join(reasons)


# ---------------------------------------------------------------------------
# job backlog
# ---------------------------------------------------------------------------

def job_backlog(job):
    """How many .srt files still lack this job's output (0 => nothing to do)."""
    suffix = JOB_SUFFIX.get(job)
    if not suffix:
        return 0
    if not os.path.isdir(DOWNLOADS):
        return 0
    srt = [f for f in os.listdir(DOWNLOADS)
           if f.endswith(".srt") and not f.endswith(".ffmpeg.failed")]
    if not os.path.isdir(CLEANED):
        return len(srt)
    done = set(os.listdir(CLEANED))
    need = 0
    for stem in srt:
        base = stem[:-len(".srt")]
        if (base + suffix) not in done:
            need += 1
    return need


# ---------------------------------------------------------------------------
# shard workers
# ---------------------------------------------------------------------------

def _shard_pid(i):
    return (load_boost().get("shards") or {}).get(str(i))


def _list_boost_procs():
    """PIDs of llm_jobs run-all procs for OUR job (safety: only our job)."""
    boost = load_boost()
    job = boost.get("job", "correct_subtitles")
    try:
        out = subprocess.run("ps -C python3 -o pid=,args= 2>/dev/null",
                             shell=True, capture_output=True, text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001
        return []
    pids = []
    for line in out.splitlines():
        if "run-all --job %s" % job in line and "llm_jobs.py" in line:
            pid = line.split()
            if pid and pid[0].isdigit():
                pids.append(int(pid[0]))
    return pids


def _launch_shard(i, shards, job, model):
    env = _db_env()
    env["DB_HOST"] = env.get("DB_HOST", "127.0.0.1")
    env["DB_PORT"] = env.get("DB_PORT", "3308")
    env["IRANSEDA_ROOT"] = PROJECT_ROOT
    logf = os.path.join(os.path.dirname(LOG_PATH), "boost_s%d.log" % i)
    # llm_jobs.py lives in the dashboard/ dir; it is invoked from PROJECT_ROOT
    # as "python3 dashboard/llm_jobs.py" (matches the documented CLI).
    cmd = (
        "setsid nohup %s -u dashboard/llm_jobs.py run-all --job %s "
        "--model %s --shard %d --shards %d "
        ">> %s 2>&1 </dev/null & echo $!"
        % (shlex.quote(PYTHON), job, shlex.quote(model), i, shards, shlex.quote(logf))
    )
    cmd = "cd %s && %s" % (shlex.quote(PROJECT_ROOT), cmd)
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=30, env=env, cwd=PROJECT_ROOT)
        pid = int((p.stdout or "").strip().splitlines()[-1]) if p.stdout.strip() else None
        return pid
    except Exception:  # noqa: BLE001
        return None


def _kill(pid):
    if not pid:
        return
    try:
        os.kill(int(pid), signal.SIGTERM)
    except (ProcessLookupError, ValueError, TypeError, OSError):
        pass
    except Exception:  # noqa: BLE001
        pass


def _reconcile(active, shards, job, model, reason):
    """Launch/kill so that shards {0..active-1} are running (of `shards`)."""
    global _LAST_LEVEL_CHANGE
    boost = load_boost()
    known = {str(i): p for i, p in (boost.get("shards") or {}).items()}
    changed = []
    # kill shards beyond `active`, and any stale tracked pids
    for i in list(known.keys()):
        ii = int(i)
        if ii >= active:
            _kill(known[i])
            _LAST_LEVEL_CHANGE[ii] = time.time()   # hysteresis: don't re-launch for 45s
            changed.append("kill shard %d (%s)" % (ii, reason))
    # launch missing shards below `active`
    for i in range(active):
        pid = known.get(str(i))
        # is it still alive?
        alive = False
        if pid:
            try:
                os.kill(int(pid), 0)
                alive = True
            except (ProcessLookupError, OSError):
                alive = False
        if not alive:
            # hysteresis: don't flap re-launch within 45s of a kill on this index
            last = _LAST_LEVEL_CHANGE.get(i, 0)
            if time.time() - last > 45:
                npid = _launch_shard(i, shards, job, model)
                known[str(i)] = npid
                changed.append("launch shard %d (pid %s)" % (i, npid))
    boost["shards"] = {k: v for k, v in known.items() if int(k) < active or v}
    _save_boost(boost)
    for c in changed:
        _log(c)


# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------

def _log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# the decision cycle
# ---------------------------------------------------------------------------

_last_load = {}   # most recent read_load() result, shared with _finalize


def _cycle():
    global _last_load
    _seed_from_env()
    boost = load_boost()
    now = _now((boost.get("window") or {}).get("tz", TEHRAN))
    backlog = job_backlog(boost.get("job"))
    _last_load = read_load(boost)
    load = _last_load

    if boost.get("mode") == "PAUSED":
        target, level, reason, skipping = 0, -1, "PAUSED (kill switch)", False
    elif backlog <= 0:
        target, level, reason, skipping = 0, -1, "job '%s' has no backlog left" % boost.get("job"), False
    else:
        night = in_window(boost.get("window") or {}, now)
        holiday = on_holiday(boost, now)
        boost_window = bool(night or holiday)
        # one-off overnight run hard stop -> auto back to NORMAL at this time
        if boost.get("max_run_end"):
            try:
                if now >= _parse_iso(boost["max_run_end"]):
                    _set_mode(boost, "NORMAL")
                    _log("max_run_end reached -> NORMAL")
                    _finalize(0, -1, "max_run_end passed -> NORMAL", False, boost)
                    return
            except Exception:  # noqa: BLE001
                pass
        # NORMAL = 24/7 baseline burn at `normal_workers`. BOOST = `boost_workers`
        # inside the night/holiday window, falling back to the normal baseline
        # outside it. (set_boost already enforces boost_workers >= normal_workers.)
        bw = int(boost.get("boost_workers", 4))
        if boost.get("mode") == "BOOST" and boost.get("enabled") and boost_window:
            base = bw
        else:
            base = int(boost.get("normal_workers", 2))
        base = max(0, min(base, bw))
        level, allowed, lreason = load_level(load, boost, base)
        if boost.get("auto_throttle"):
            # The auto-throttle protects interactive users at ALL times: it can
            # hold us below the requested count whenever the guard says so (the
            # CRITICAL "don't use it" case forces 0).
            target = min(base, allowed)
            reason = lreason or ("boost window, load LOW" if boost_window else "baseline, load LOW")
        else:
            target, reason = base, lreason or "auto-throttle off, %d workers" % base
        skipping = target < base
        target = max(0, min(target, bw))

    active = _count_active()
    _reconcile(target, int(boost.get("boost_workers", 4)),
               boost.get("job"), boost.get("model"), reason)
    if target > active:
        _log("target %d > running %d; launching (reason: %s)" % (target, active, reason))
    elif target < active:
        _log("target %d < running %d; scaling down (reason: %s)" % (target, active, reason))
    _finalize(target, level, reason, skipping, boost)


def _count_active():
    n = 0
    for pid in (load_boost().get("shards") or {}).values():
        if pid:
            try:
                os.kill(int(pid), 0)
                n += 1
            except (ProcessLookupError, OSError):
                pass
    return n


def _finalize(target, level, reason, skipping, boost):
    global _last_snapshot
    boost["last"] = {
        "ts": time.time(),
        "active": _count_active(),
        "target": target,
        "level": level,
        "skipping": bool(skipping),
        "throttled": bool(skipping),
        "reason": reason,
        "load": _last_load,
    }
    _save_boost(boost)
    _last_snapshot = {"data": boost_snapshot(), "ts": time.time()}


def _set_mode(boost, mode):
    boost["mode"] = mode
    _save_boost(boost)
    _log("mode -> %s" % mode)


def _parse_iso(s):
    return datetime.fromisoformat(s)


def boost_snapshot():
    """Everything /api/boost + /metrics need, in one dict."""
    boost = load_boost()
    last = boost.get("last") or {}
    return {
        "boost": boost,
        "now": datetime.now().isoformat(timespec="seconds"),
        "backlog": job_backlog(boost.get("job")),
        "active": _count_active(),
        "window_active": in_window(boost.get("window") or {},
                                   _now((boost.get("window") or {}).get("tz", TEHRAN))),
        "holiday": on_holiday(boost,
                              _now((boost.get("window") or {}).get("tz", TEHRAN))),
        "last": last,
    }


# ---------------------------------------------------------------------------
# control (called by the API / CLI)
# ---------------------------------------------------------------------------

def set_boost(payload):
    boost = load_boost()
    for k in ("enabled", "mode", "job", "model", "normal_workers", "boost_workers",
              "min_workers", "auto_throttle", "max_run_end"):
        if k in payload:
            boost[k] = payload[k]
    for k in ("window", "holiday", "guard"):
        if k in payload and isinstance(payload[k], dict):
            boost[k] = _deep_merge(json.loads(json.dumps(DEFAULT_BOOST[k])), payload[k])
    if boost.get("mode") not in MODES:
        boost["mode"] = "NORMAL"
    boost["normal_workers"] = max(0, int(boost.get("normal_workers", 2)))
    boost["boost_workers"] = max(boost["normal_workers"], int(boost.get("boost_workers", 4)))
    if boost["mode"] != "PAUSED":
        _LAST_LEVEL_CHANGE.clear()
    _save_boost(boost)
    _log("set: %s" % json.dumps({k: payload[k] for k in payload}, ensure_ascii=False)[:300])
    return boost_snapshot()


def pause():
    return set_boost({"mode": "PAUSED"})


def normal():
    return set_boost({"mode": "NORMAL"})


def start():
    return set_boost({"mode": "NORMAL", "enabled": True})


def boost_mode():
    """Elevated night/holiday burn: `boost_workers` inside the window."""
    return set_boost({"mode": "BOOST", "enabled": True})


def stop_all():
    """Emergency: PAUSE and kill any running shards immediately (best-effort)."""
    pause()
    for pid in _list_boost_procs():
        _kill(pid)
    _log("EMERGENCY STOP: paused + killed boost shards")
    return boost_snapshot()


# ---------------------------------------------------------------------------
# thread
# ---------------------------------------------------------------------------

def _loop():
    global _running, _last_load
    _running = True
    _log("boost controller started (model=%s job=%s)" %
         (load_boost().get("model"), load_boost().get("job")))
    while True:
        try:
            _cycle()
        except Exception as e:  # noqa: BLE001
            _log("cycle error: %r" % e)
        time.sleep(30)


def ensure_started():
    global _running
    if not _running:
        import logic
        logic.run_in_thread(_loop)


def status():
    global _last_snapshot
    if time.time() - _last_snapshot.get("ts", 0) > 10:
        _last_snapshot = {"data": boost_snapshot(), "ts": time.time()}
    return _last_snapshot["data"]
