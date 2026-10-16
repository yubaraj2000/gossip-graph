#!/usr/bin/env bash
# Forward the Ubuntu box's Ollama (127.0.0.1:11434 there) to this Mac on 127.0.0.1:11435.
# Usage: scripts/ollama-tunnel.sh [start|stop|status]
set -euo pipefail

HOST="${OLLAMA_SSH_HOST:-oditek@192.168.29.235}"
LOCAL_PORT="${OLLAMA_LOCAL_PORT:-11435}"
FORWARD="127.0.0.1:${LOCAL_PORT}:127.0.0.1:11434"

case "${1:-start}" in
  start)
    if pgrep -f "ssh .*${FORWARD}" >/dev/null; then
      echo "tunnel already running"
    else
      ssh -f -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -L "${FORWARD}" "${HOST}"
      echo "tunnel started: http://127.0.0.1:${LOCAL_PORT} -> ${HOST}:11434"
    fi
    ;;
  stop)
    pkill -f "ssh .*${FORWARD}" && echo "tunnel stopped" || echo "tunnel not running"
    ;;
  status)
    if curl -sf --max-time 5 "http://127.0.0.1:${LOCAL_PORT}/api/version"; then
      echo " <- Ollama reachable"
    else
      echo "Ollama NOT reachable on ${LOCAL_PORT}"
      exit 1
    fi
    ;;
  *)
    echo "usage: $0 [start|stop|status]" >&2
    exit 2
    ;;
esac
