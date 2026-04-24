#!/usr/bin/env bash
# Start the content dashboard + Cloudflare tunnel for remote access.
# Usage: ./scripts/start-dashboard.sh [--port 8765] [--local-only]

set -euo pipefail

PORT=8765
LOCAL_ONLY=0

while [[ $# -gt 0 ]]; do
  case $1 in
    --port) PORT=$2; shift 2 ;;
    --local-only) LOCAL_ONLY=1; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Kill any existing dashboard / tunnel on this port
pkill -f "pipeline dashboard.*--port $PORT" 2>/dev/null || true
pkill -f "cloudflared tunnel.*$PORT"         2>/dev/null || true
sleep 1

# Start dashboard
echo "Starting dashboard on port $PORT..."
uv run pipeline dashboard --no-browser --port "$PORT" > /tmp/dashboard-${PORT}.log 2>&1 &
DASH_PID=$!
echo "Dashboard PID: $DASH_PID (log: /tmp/dashboard-${PORT}.log)"

# Wait for it to be ready
for i in $(seq 1 10); do
  sleep 1
  if curl -s "http://localhost:$PORT/api/projects" > /dev/null 2>&1; then
    echo "Dashboard ready → http://localhost:$PORT"
    break
  fi
  if [[ $i -eq 10 ]]; then
    echo "ERROR: dashboard didn't start. Check /tmp/dashboard-${PORT}.log"
    exit 1
  fi
done

if [[ $LOCAL_ONLY -eq 1 ]]; then
  echo ""
  echo "Local access only: http://localhost:$PORT"
  exit 0
fi

# Start Cloudflare tunnel
echo ""
echo "Starting Cloudflare tunnel..."
TUNNEL_LOG=/tmp/cloudflared-${PORT}.log
~/.local/bin/cloudflared tunnel --url "http://localhost:$PORT" > "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

# Wait for tunnel URL
TUNNEL_URL=""
for i in $(seq 1 15); do
  sleep 1
  TUNNEL_URL=$(grep -o 'https://[a-zA-Z0-9.-]*trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1 || true)
  if [[ -n "$TUNNEL_URL" ]]; then
    break
  fi
done

if [[ -z "$TUNNEL_URL" ]]; then
  echo "WARNING: tunnel URL not found after 15s. Check $TUNNEL_LOG"
  echo "Dashboard still accessible locally: http://localhost:$PORT"
  exit 1
fi

echo ""
echo "============================================"
echo "  Dashboard ready"
echo "  Local:   http://localhost:$PORT"
echo "  Remote:  $TUNNEL_URL"
echo "============================================"
echo ""
echo "PIDs: dashboard=$DASH_PID  tunnel=$TUNNEL_PID"
echo "Stop: kill $DASH_PID $TUNNEL_PID"
