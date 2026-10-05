#!/usr/bin/env bash
# Auto-refresh the IranSeda GitHub Pages site + push new subtitles.
# Regenerates docs/ from the radio DB, builds full-text (.txt) for each .srt,
# commits docs/ + downloads/, pushes to origin/download-db.
# Then prunes audio media that was subtitled longer than AUDIO_RETENTION_DAYS ago (default 10).
set -uo pipefail
export GIT_TERMINAL_PROMPT=0
R=/home/saber/saberprojects/iranseda-crawler-golang-
PY="$R/crawler/venv/bin/python3"
LOG_DIR="$R/scripts/logs"
LOG="$LOG_DIR/refresh_site.log"
GEN_OUT="$LOG_DIR/generate_last.out"
LOCK="$R/.refresh_site.lock"
BRANCH=download-db
mkdir -p "$LOG_DIR"

run(){
  echo "===== $(date "+%Y-%m-%d %H:%M:%S") refresh START ====="
  cd "$R" || return 1
  export ENVIRONMENT=server
  export DB_HOST=172.20.1.53 DB_PORT=3308
  export DOWNLOADS_PATH="$R/downloads" DOCS_PATH="$R/docs" PROGRAMS_PATH="$R/docs/programs"
  # AUDIO_RETENTION_DAYS configurable (default 10): keep audio N days after subtitled.
  if "$PY" generate_site.py > "$GEN_OUT" 2>&1; then
    echo "generate: OK"
  else
    echo "generate: FAILED -> tail of $GEN_OUT:"
    tail -n 8 "$GEN_OUT"
    echo "===== refresh END (generate failed) ====="; return 1
  fi
  # Build full-text (.txt) for every .srt that doesn't have one yet (before git add so it's pushed).
  if "$PY" convert_srt_to_txt.py >> "$GEN_OUT" 2>&1; then
    echo "txt convert: OK"
  else
    echo "txt convert: FAILED (non-fatal) -> tail of $GEN_OUT:"
    tail -n 5 "$GEN_OUT"
  fi
  git add -- docs downloads
  if git diff --cached --quiet; then
    echo "nothing changed -> no commit/push"
  else
    local n; n=$(git diff --cached --numstat | wc -l)
    git commit -q -m "auto: refresh site + subtitles ($(date +%Y-%m-%d_%H:%M))"
    echo "committed ($n changed paths)"
    # Rebase onto remote before pushing: an external push (manual, or from
    # another machine) must not wedge us. --autostash protects uncommitted
    # tracked changes (venv/.pyc) through the rebase.
    if git pull --rebase --autostash origin "$BRANCH" >/dev/null 2>&1; then
      echo "rebase: OK"
    else
      echo "rebase: FAILED (aborting to keep tree clean; retry next run)"
      git rebase --abort 2>/dev/null
    fi
    if git push origin "$BRANCH" 2>&1 | tail -n 3; then
      echo "push: OK"
    else
      echo "push: FAILED"
    fi
  fi
  # Prune audio for sessions subtitled more than AUDIO_RETENTION_DAYS ago.
  # Safe: only deletes media whose session is already status='subtitled' (SRT delivered).
  if "$PY" scripts/cleanup_audio.py --apply >> "$GEN_OUT" 2>&1; then
    echo "audio cleanup: OK"
  else
    echo "audio cleanup: FAILED (non-fatal) -> tail of $GEN_OUT:"
    tail -n 5 "$GEN_OUT"
  fi
  echo "===== $(date "+%Y-%m-%d %H:%M:%S") refresh END ====="
}

# skip if a previous run is still going (long first run)
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "===== $(date "+%Y-%m-%d %H:%M:%S") previous run active -> SKIP =====" | tee -a "$LOG"
  exit 0
fi

run 2>&1 | tee -a "$LOG"
tail -n 4000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
