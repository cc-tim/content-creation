#!/usr/bin/env bash
# Restart content dashboard when an AI agent session ends with src/pipeline/ changes.
# Called by Claude Code and Codex Stop hooks. Always exits 0 (non-blocking).

PROJECT_DIR="/home/tim-huang/content-creation"
ACTIVE_COMPOSE_DIR="$PROJECT_DIR/output/.dashboard-compose-actions"
PENDING_RESTART_MARKER="$PROJECT_DIR/output/.dashboard-restart-pending"

CHANGED=$(git -C "$PROJECT_DIR" status --porcelain src/pipeline/ 2>/dev/null || true)

if [[ -n "$CHANGED" ]]; then
  if [[ -d "$ACTIVE_COMPOSE_DIR" ]] && find "$ACTIVE_COMPOSE_DIR" -type f -name '*.json' -mmin -360 -print -quit | grep -q .; then
    mkdir -p "$(dirname "$PENDING_RESTART_MARKER")"
    touch "$PENDING_RESTART_MARKER"
    exit 0
  fi
  systemctl --user restart --no-block content-dashboard 2>/dev/null || true
fi

exit 0
