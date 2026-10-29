#!/usr/bin/env bash
# Auto-refresh the IranSeda GitHub Pages site + push new subtitles.
# Regenerates docs/ from the radio DB, builds full-text (.txt) for each .srt,
# commits docs/ + downloads/, pushes to the CURRENT branch (no hardcoded
# branch — BRANCH is resolved from git).
# Then prunes audio media that was subtitled longer than AUDIO_RETENTION_DAYS ago (default 10).
# Every run is recorded into the radio DB (pipeline_runs, kind='site') via
# scripts/record_run.py: changed paths, SRT/TXT added, push ok/fail.
set -uo pipefail
export GIT_TERMINAL_PROMPT=0
R=/home/saber/saberprojects/iranseda-crawler-golang-
PY="$R/crawler/venv/bin/python3"
LOG_DIR="$R/scripts/logs"
LOG="$LOG_DIR/refresh_site.log"
GEN_OUT="$LOG_DIR/generate_last.out"
LOCK="$R/.refresh_site.lock"
BRANCH=$(git -C "$R" rev-parse --abbrev-ref HEAD)
REC_PY="$R/dashboard/venv/bin/python3"
mkdir -p "$LOG_DIR"

# Verify the live GitHub Pages site is serving what we just pushed.
# GitHub Pages rebuilds can lag a few minutes, so a STALE verdict shortly
# after a push is expected for ~5 min; PERSISTENT STALE means the Pages
# deployment source (branch/folder) is not the branch this script pushes to.
verify_pages(){
  local url="https://saber13812002.github.io/iranseda-crawler-golang-/index.html"
  local local_sha live_sha lm hdr tmp
  local_sha=$(git hash-object docs/index.html 2>/dev/null || echo "?")
  if ! command -v curl >/dev/null 2>&1; then
    echo "pages-verify: SKIPPED (no curl)"
    return 0
  fi
  tmp=$(mktemp)
  hdr=$(mktemp)
  if curl -fsSL --max-time 30 -D "$hdr" "$url" -o "$tmp" 2>/dev/null; then
    live_sha=$(git hash-object "$tmp" 2>/dev/null || echo "?")
    lm=$(grep -i '^last-modified:' "$hdr" | tr -d '\r' | awk '{print $2" "$3" "$4" "$5}')
    if [ "$live_sha" = "$local_sha" ]; then
      echo "pages-verify: OK live==pushed sha=${live_sha:0:8} last-modified=$lm"
    else
      echo "pages-verify: STALE live=${live_sha:0:8} pushed=${local_sha:0:8} last-modified=$lm -> Pages source likely != branch '$BRANCH'"
    fi
  else
    echo "pages-verify: FETCH-FAILED url=$url"
  fi
  rm -f "$tmp" "$hdr"
}

record(){
  # best-effort per-run record; never fails the refresh
  REC_KIND=site REC_STARTED_AT="$1" REC_STATUS="$2" \
  REC_PUBLISHED="$3" REC_SRT_NEW="$4" REC_TXT_NEW="$5" \
  REC_PUSH_OK="$6" REC_ERROR="$7" \
  "$REC_PY" "$R/scripts/record_run.py" >>"$LOG" 2>&1 || echo "record: FAILED (non-fatal)"
}

run(){
  local START_TS; START_TS=$(date '+%Y-%m-%d %H:%M:%S')
  echo "===== $START_TS refresh START ====="
  cd "$R" || return 1
  export ENVIRONMENT=server
  export DB_HOST=172.20.1.53 DB_PORT=3308
  export DOWNLOADS_PATH="$R/downloads" DOCS_PATH="$R/docs" PROGRAMS_PATH="$R/docs/programs"

  local GEN_OK=1 PUSH_OK=0 CHANGED=0 SRT_NEW=0 TXT_NEW=0 REC_ERROR="" REC_STATUS="ok"
  # AUDIO_RETENTION_DAYS configurable (default 10): keep audio N days after subtitled.
  if "$PY" generate_site.py > "$GEN_OUT" 2>&1; then
    echo "generate: OK"
  else
    GEN_OK=0; REC_STATUS="failed"
    REC_ERROR="generate failed: $(tail -n 1 "$GEN_OUT" 2>/dev/null | head -c 200)"
    echo "generate: FAILED -> tail of $GEN_OUT:"
    tail -n 8 "$GEN_OUT"
    echo "===== refresh END (generate failed) ====="
    record "$START_TS" "$REC_STATUS" "$CHANGED" "$SRT_NEW" "$TXT_NEW" "$PUSH_OK" "$REC_ERROR"
    return 1
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
    CHANGED=$n
    SRT_NEW=$(git diff --cached --name-only | grep -c '\.srt$' || true)
    TXT_NEW=$(git diff --cached --name-only | grep -c '\.txt$' || true)
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
      REC_STATUS="failed"
      REC_ERROR="rebase failed (external push conflict?)"
    fi
    if git push origin "$BRANCH" 2>&1 | tail -n 3; then
      echo "push: OK"
      PUSH_OK=1
      # Pages rebuild lags a few minutes; the first check may be STALE by
      # design. The next cron run's check is the authoritative signal.
      verify_pages
    else
      echo "push: FAILED"
      REC_STATUS="failed"
      REC_ERROR="${REC_ERROR:+$REC_ERROR; }push failed"
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
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') refresh END ====="
  record "$START_TS" "$REC_STATUS" "$CHANGED" "$SRT_NEW" "$TXT_NEW" "$PUSH_OK" "$REC_ERROR"
}

# skip if a previous run is still going (long first run)
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') previous run active -> SKIP =====" | tee -a "$LOG"
  exit 0
fi

run 2>&1 | tee -a "$LOG"
tail -n 4000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
