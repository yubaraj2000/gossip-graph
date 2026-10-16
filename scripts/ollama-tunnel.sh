#!/usr/bin/env bash
# Forward the Ubuntu box's Ollama (127.0.0.1:11434 there) to this Mac on 127.0.0.1:11435.
# Usage: scripts/ollama-tunnel.sh [start|stop|status|watch]
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
  watch)
    # Keep the tunnel alive across Mac sleep/wake: check every 20 s, reopen when Ollama is unreachable.
    echo "watching tunnel (Ctrl+C to stop)"
    while true; do
      if ! curl -sf --max-time 5 "http://127.0.0.1:${LOCAL_PORT}/api/version" >/dev/null; then
        echo "$(date +%H:%M:%S) tunnel down, reopening"
        pkill -f "ssh .*${FORWARD}" || true
        "$0" start || true
      fi
      sleep 20
    done
    ;;
  *)
    echo "usage: $0 [start|stop|status|watch]" >&2
    exit 2
    ;;
esac
