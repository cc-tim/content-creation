#!/usr/bin/env bash
# Restart content dashboard when an AI agent session ends with src/pipeline/ changes.
# Called by Claude Code and Codex Stop hooks. Always exits 0 (non-blocking).

PROJECT_DIR="/home/tim-huang/content-creation"

CHANGED=$(git -C "$PROJECT_DIR" status --porcelain src/pipeline/ 2>/dev/null || true)

if [[ -n "$CHANGED" ]]; then
  systemctl --user restart --no-block content-dashboard 2>/dev/null || true
fi

exit 0
