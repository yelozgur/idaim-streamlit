#!/bin/bash
# retrain-weekly.sh — IDAIM weekly retraining (local path)
#
# Production: Pzt 09:00 cron → train_local.py + export_cron_artifacts.py
# Models:     data/07_models/model_<species>.joblib  (Streamlit Cloud reads)
# Watch list: appended to Sheets 'watch_list' tab (via gspread)
# Metrics:    data/07_models/metrics_local.json
# Export:     data/exports/cron_run_<timestamp>.xlsx
#
# Logs: data/logs/cron_<timestamp>.log (one per run)
#
# To install: mavis cron self idaim-weekly-retrain --every 7d --prompt "..."
# (or use OS cron / launchd — see deployment notes)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV=".venv/bin/python"
if [ ! -x "$VENV" ]; then
  echo "FATAL: $VENV not found or not executable" >&2
  exit 1
fi

LOG_DIR="data/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/cron_$(date +%Y%m%d_%H%M%S).log"

log() { echo "$@" | tee -a "$LOG"; }

log "=== IDAIM retrain-weekly $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
log "PWD: $SCRIPT_DIR"
log "Log: $LOG"
log ""

# Step 1: train + write watch list
log "[1/2] train_local.py --species both --write-watchlist"
if "$VENV" train_local.py --species both --write-watchlist 2>&1 | tee -a "$LOG"; then
  log "  train: OK"
else
  log "  train: FAILED (exit=$?) — continuing to export so we have artifacts"
fi
log ""

# Step 2: export artifacts to Excel (always runs, so we have a record even on partial failure)
log "[2/2] export_cron_artifacts.py"
if "$VENV" export_cron_artifacts.py 2>&1 | tee -a "$LOG"; then
  log "  export: OK"
else
  log "  export: FAILED (exit=$?)"
fi
log ""

log "=== DONE $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
