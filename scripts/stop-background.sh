#!/usr/bin/env bash
#
# stop-background.sh — EMERGENCY KILL SWITCH for iranseda background work.
#
# What it DOES stop (and ONLY these):
#   * the boost / LLM "run-all" shard workers  (python3 ... llm_jobs.py run-all)
#   * the boost controller's ability to relaunch them (sets mode -> PAUSED)
#
# What it NEVER touches:
#   * the model servers (qwen38 / qwen38-sglang / vllm / sglang)
#   * the whisper worker + api containers
#   * the LiteLLM proxy (on 52)
#   * the dashboard itself (uvicorn on :8990)
#
# Usage:  ./scripts/stop-background.sh          # pause boost + kill shard procs
#         ./scripts/stop-background.sh --procs   # kill shard procs only (no API)
#
# Safe to run repeatedly. It never kills anything whose command line does not
# contain "llm_jobs.py run-all", so a model server / whisper / dashboard whose
# path merely lives nearby is left alone.
set -u

ROOT="${IRANSEDA_ROOT:-/home/saber/saberprojects/iranseda-crawler-golang-}"
PORT="${IRANSEDA_DASH_PORT:-8990}"
PROCS_ONLY=0
[ "${1:-}" = "--procs" ] && PROCS_ONLY=1

echo "[stop-background] $(date '+%F %T') — iranseda background stop"

# --- 1. Ask the dashboard to PAUSE the boost controller (best-effort). --------
# Pausing first means the 30s controller loop won't relaunch shards we're about
# to kill. If the dashboard is down we just skip it — the procs below still get
# killed and the controller isn't running anyway.
if [ "$PROCS_ONLY" -eq 0 ]; then
  TOKEN=$(grep -Eo '^[A-Z_]*TOKEN[[:space:]]*=[[:space:]]*[^[:space:]]+' \
          "$ROOT/dashboard/dashboard.env" 2>/dev/null | head -1 | cut -d= -f2-)
  if [ -n "${TOKEN:-}" ]; then
    RESP=$(curl -s -m 10 -X POST -H "Authorization: Bearer $TOKEN" \
              "http://127.0.0.1:$PORT/api/boost/pause" 2>/dev/null || true)
    echo "[stop-background] pause boost -> ${RESP:-<dashboard unreachable; skipped>}"
  else
    echo "[stop-background] no dashboard token found; skipping pause (still killing procs)"
  fi
fi

# --- 2. Kill the boost / LLM run-all shard procs. -----------------------------
# pkill -f matches the full command line; our own script's cmdline is
# "bash .../stop-background.sh" (no "llm_jobs.py run-all"), so no self-match.
PIDS=$(pgrep -f "llm_jobs.py run-all" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  echo "[stop-background] killing run-all shard PID(s): $PIDS"
  # shellcheck disable=SC2086
  kill $PIDS 2>/dev/null || true
  sleep 2
  STILL=$(pgrep -f "llm_jobs.py run-all" 2>/dev/null || true)
  if [ -n "$STILL" ]; then
    echo "[stop-background] SIGTERM ignored by: $STILL — sending SIGKILL"
    # shellcheck disable=SC2086
    kill -9 $STILL 2>/dev/null || true
  fi
else
  echo "[stop-background] no iranseda background (run-all) procs running."
fi

echo "[stop-background] done. Model servers / whisper / LiteLLM / dashboard were NOT touched."
