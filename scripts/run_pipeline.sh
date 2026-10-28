#!/usr/bin/env bash
# run_pipeline.sh — the one simple permanent runner for the DISCOVERY +
# DOWNLOAD half of the iranseda chain, on server 53.
#
# The full chain and who owns each step:
#   [THIS script]      scan.go        discover new episodes -> DB (advances max id)
#   [THIS script]      download_db.go download pending media, set status=pending_transcribe
#   [container]        iranseda-whisper-worker   transcribe pending_transcribe -> SRT
#                     (already running, restart: unless-stopped)
#   [cron 30-min]      refresh_site.sh           regenerate site/.txt/dump + git push
#                     (already on the */30 cron)
#
# So: this script + those two already-persistent pieces = the whole pipeline.
# Downloads are bounded by MAX_DOWNLOADS / DOWNLOAD_DELAY in ./.env (25 / 2s).
#
# Every run is recorded into the radio DB (pipeline_runs table) via
# scripts/record_run.py so /metrics + Grafana can show per-run stats:
# new sessions, no_new_work (ok run with 0 new = expected), downloads,
# SRTs produced, duration. The record call is best-effort and never
# changes the exit status of the pipeline.
set -uo pipefail
R=/home/saber/saberprojects/iranseda-crawler-golang-
export PATH="$PATH:$HOME/go-toolchain/go/bin"
export GOPATH="$HOME/gopath"
export GOBIN="$HOME/gopath/bin"
export IRANSEDA_NO_SSL_VERIFY=$(grep "^IRANSEDA_NO_SSL_VERIFY=" "$R/.env" 2>/dev/null | cut -d= -f2 || echo "0")
LOG_DIR="$R/scripts/logs"
LOG="$LOG_DIR/pipeline.log"
SCAN_OUT="$LOG_DIR/scan_last.out"
DISC_OUT="$LOG_DIR/discover_last.out"
DL_OUT="$LOG_DIR/download_last.out"
LOCK="$R/.pipeline.lock"
PY="$R/dashboard/venv/bin/python3"
REC="$R/scripts/record_run.py"
mkdir -p "$LOG_DIR"

record(){
  # $1=started $2=status $3=scan_new $4=disc_new $5=disc_programs $6=dl_ok $7=dl_fail $8=error
  REC_KIND=pipeline REC_STARTED_AT="$1" REC_STATUS="$2" \
  REC_SCAN_NEW="$3" REC_DISC_NEW="$4" REC_DISC_PROGRAMS="$5" \
  REC_DL_OK="$6" REC_DL_FAIL="$7" REC_ERROR="$8" \
  "$PY" "$REC" >>"$LOG" 2>&1 || echo "record: FAILED (non-fatal)"
}

run(){
  local START_TS; START_TS=$(date '+%Y-%m-%d %H:%M:%S')
  echo "===== $START_TS pipeline START ====="
  cd "$R" || return 1

  local RUN_STATUS="ok" RUN_ERROR="" SCAN_NEW=0

  # 1) Discover new episodes. Idempotent (sessionExists) so safe to run often.
  if go run scan.go > "$SCAN_OUT" 2>&1; then
    SCAN_NEW=$(grep -c 'Inserted:' "$SCAN_OUT" || true)
    echo "scan: OK ($SCAN_NEW new sessions)"
  else
    RUN_STATUS="failed"
    RUN_ERROR="scan failed: $(tail -n 1 "$SCAN_OUT" 2>/dev/null | head -c 200)"
    echo "scan: FAILED -> tail of $SCAN_OUT:"; tail -n 8 "$SCAN_OUT"
    record "$START_TS" "$RUN_STATUS" "$SCAN_NEW" 0 0 0 0 "$RUN_ERROR"
    return 1
  fi

  # 1.5) Periodic discovery (panel-added programs). For every active program
  #      in radio_programs, walk the most-recent archive pages and insert any
  #      episode not yet in radio_program_sessions (pending_download). Bounded
  #      by NEW_SCAN_PAGES (default 14 pages = ~280 episodes). This is what
  #      keeps one-click-added programs current on their own — scan.go only
  #      advances the id cursor of programs it itself registered. Never fatal:
  #      a hiccup here must not block downloads.
  local DISC_NEW=0 DISC_PROGRAMS=0 DISC_LINE
  if "$PY" "$R/scripts/discover_new.py" > "$DISC_OUT" 2>&1; then
    DISC_LINE=$(tail -n 1 "$DISC_OUT")
    DISC_NEW=$(printf '%s' "$DISC_LINE" | grep -oE '[0-9]+ new episodes' | grep -oE '^[0-9]+' || true)
    DISC_PROGRAMS=$(printf '%s' "$DISC_LINE" | grep -oE 'across [0-9]+ programs' | grep -oE '[0-9]+' || true)
    DISC_NEW=${DISC_NEW:-0}; DISC_PROGRAMS=${DISC_PROGRAMS:-0}
    echo "discover: $DISC_LINE"
  else
    RUN_ERROR="${RUN_ERROR:+$RUN_ERROR; }discover failed: $(tail -n 1 "$DISC_OUT" 2>/dev/null | head -c 200)"
    echo "discover: FAILED -> tail of $DISC_OUT:"; tail -n 8 "$DISC_OUT"
  fi

  # 2) Download the newest pending media (bounded by .env MAX_DOWNLOADS).
  #    On success each row flips to status=pending_transcribe so the running
  #    whisper worker picks it up automatically.
  local DL_OK=0 DL_FAIL=0
  if go run download_db.go > "$DL_OUT" 2>&1; then
    DL_OK=$(grep -c 'marked as downloaded' "$DL_OUT" || true)
    DL_FAIL=$(grep -cE 'Download failed|Error while downloading|failed to download file' "$DL_OUT" || true)
    echo "download: OK ($DL_OK this run)"
  else
    DL_FAIL=$(grep -cE 'Download failed|Error while downloading|failed to download file' "$DL_OUT" || true)
    RUN_ERROR="${RUN_ERROR:+$RUN_ERROR; }download failed: $(tail -n 1 "$DL_OUT" 2>/dev/null | head -c 200)"
    echo "download: FAILED -> tail of $DL_OUT:"; tail -n 8 "$DL_OUT"
  fi

  echo "===== $(date '+%Y-%m-%d %H:%M:%S') pipeline END ====="
  record "$START_TS" "$RUN_STATUS" "$SCAN_NEW" "$DISC_NEW" "$DISC_PROGRAMS" "$DL_OK" "$DL_FAIL" "$RUN_ERROR"
}

# skip if a previous run is still going (downloads take a few minutes)
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') previous run active -> SKIP =====" | tee -a "$LOG"
  exit 0
fi

run 2>&1 | tee -a "$LOG"
tail -n 4000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
