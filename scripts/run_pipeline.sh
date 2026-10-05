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
set -uo pipefail
R=/home/saber/saberprojects/iranseda-crawler-golang-
export PATH="$PATH:$HOME/go-toolchain/go/bin"
export GOPATH="$HOME/gopath"
export GOBIN="$HOME/gopath/bin"
LOG_DIR="$R/scripts/logs"
LOG="$LOG_DIR/pipeline.log"
SCAN_OUT="$LOG_DIR/scan_last.out"
DL_OUT="$LOG_DIR/download_last.out"
LOCK="$R/.pipeline.lock"
mkdir -p "$LOG_DIR"

run(){
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') pipeline START ====="
  cd "$R" || return 1

  # 1) Discover new episodes. Idempotent (sessionExists) so safe to run often.
  if go run scan.go > "$SCAN_OUT" 2>&1; then
    echo "scan: OK ($(grep -c 'Inserted:' "$SCAN_OUT") new sessions)"
  else
    echo "scan: FAILED -> tail of $SCAN_OUT:"; tail -n 8 "$SCAN_OUT"; return 1
  fi

  # 2) Download the newest pending media (bounded by .env MAX_DOWNLOADS).
  #    On success each row flips to status=pending_transcribe so the running
  #    whisper worker picks it up automatically.
  if go run download_db.go > "$DL_OUT" 2>&1; then
    echo "download: OK ($(grep -c 'marked as downloaded' "$DL_OUT") this run)"
  else
    echo "download: FAILED -> tail of $DL_OUT:"; tail -n 8 "$DL_OUT"
  fi

  echo "===== $(date '+%Y-%m-%d %H:%M:%S') pipeline END ====="
}

# skip if a previous run is still going (downloads take a few minutes)
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') previous run active -> SKIP =====" | tee -a "$LOG"
  exit 0
fi

run 2>&1 | tee -a "$LOG"
tail -n 4000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
