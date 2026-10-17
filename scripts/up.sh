#!/usr/bin/env bash
# Bring up the whole gossip-graph stack, checking each part and starting only what isn't already running.
#
#   scripts/up.sh          start everything (safe to re-run)
#   scripts/up.sh status   check each part, start nothing
#   scripts/up.sh down     stop what up.sh started in the background (containers keep running)
#
# Ollama: set OLLAMA_URL to your server (default http://127.0.0.1:11435). If nothing answers on :11435, up.sh opens
# scripts/ollama-tunnel.sh (set OLLAMA_SSH_HOST). Convex reaches Ollama through OLLAMA_HOST in its own env.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT=$PWD
RUN=$ROOT/.run  # logs and pids of the background processes (gitignored)
export OLLAMA_URL=${OLLAMA_URL:-http://127.0.0.1:11435}
MEMORY=http://127.0.0.1:8100
CONVEX=http://127.0.0.1:3210
TOWN_PORT=5173
FAILED=0

ok() { printf '  ✅ %s\n' "$*"; }
bad() { printf '  ❌ %s\n' "$*"; FAILED=1; }
up() { curl -sf -m 3 "$1" >/dev/null; }
wait_for() {  # url, seconds
  for _ in $(seq 1 "$2"); do up "$1" && return 0; sleep 1; done
  return 1
}
listening() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
start_bg() {  # name, command...
  local name=$1
  shift
  nohup "$@" >"$RUN/$name.log" 2>&1 &
  echo $! >"$RUN/$name.pid"
}
convex() { (cd world && npx convex "$@" 2>/dev/null); }

check_falkordb() {
  if [ "$(docker exec falkordb redis-cli ping 2>/dev/null)" = "PONG" ]; then ok "FalkorDB on :6379 (browser UI http://127.0.0.1:3000)"
  else bad "FalkorDB is not answering (docker compose up -d)"; fi
}

check_ollama() {
  local v
  v=$(curl -sf -m 3 "$OLLAMA_URL/api/version" | sed 's/.*"version":"\([^"]*\)".*/\1/')
  if [ -n "$v" ]; then ok "Ollama $v at $OLLAMA_URL"; else bad "Ollama not reachable at $OLLAMA_URL"; fi
}

check_memory() {
  local h
  h=$(curl -sf -m 3 "$MEMORY/health")
  if [[ $h == *'"falkordb":true'* && $h != *'"ollama":null'* ]]; then ok "memory service on :8100 ($h)"
  else bad "memory service on :8100: ${h:-not running}"; fi
}

check_town() {
  local w
  if ! up "$CONVEX/version"; then bad "Convex backend on :3210 is not answering"; return; fi
  w=$(convex run world:defaultWorldStatus | sed -n 's/.*"worldId": "\([^"]*\)".*/\1/p')
  if [ -n "$w" ]; then ok "AI Town world $w (Convex on :3210, dashboard http://127.0.0.1:6791)"
  else bad "AI Town has no world yet"; fi
  if listening "$TOWN_PORT"; then ok "town page http://127.0.0.1:$TOWN_PORT/ai-town"
  else bad "Vite is not serving the town on :$TOWN_PORT"; fi
}

status() {
  echo "gossip-graph status"
  check_falkordb
  check_ollama
  check_memory
  check_town
  if up "$MEMORY/ui"; then ok "memory page http://127.0.0.1:8100/ui"; fi
}

start() {
  mkdir -p "$RUN"
  echo "1/6 FalkorDB"
  docker compose up -d >/dev/null 2>&1
  for _ in $(seq 1 30); do [ "$(docker exec falkordb redis-cli ping 2>/dev/null)" = "PONG" ] && break; sleep 1; done
  check_falkordb

  echo "2/6 Ollama"
  if ! up "$OLLAMA_URL/api/version" && [[ $OLLAMA_URL == *:11435 ]]; then
    start_bg tunnel scripts/ollama-tunnel.sh watch  # reopens the tunnel by itself if it drops
    wait_for "$OLLAMA_URL/api/version" 30
  fi
  check_ollama

  echo "3/6 Memory service"
  if ! up "$MEMORY/health"; then
    start_bg memory scripts/run_memory.sh
    wait_for "$MEMORY/health" 60
  fi
  check_memory

  echo "4/6 Convex (AI Town's backend)"
  if [ ! -f world/.env.local ]; then
    bad "world/.env.local is missing: see the README's setup section (admin key, URLs, INVESTIGATOR_SECRET)"
    return
  fi
  (cd world && docker compose up -d backend >/dev/null 2>&1)
  wait_for "$CONVEX/version" 90 || { bad "Convex backend did not become healthy"; return; }
  (cd world && docker compose up -d dashboard >/dev/null 2>&1)  # waits on the backend's healthcheck
  for var in OLLAMA_HOST OLLAMA_MODEL MEMORY_SERVICE_URL INVESTIGATOR_SECRET; do
    convex env get "$var" >/dev/null || bad "Convex env $var is not set (npx convex env set $var …, see README)"
  done

  echo "5/6 Deploy the town's code, and create the village if there is no world"
  if convex dev --once --typecheck enable >"$RUN/deploy.log" 2>&1; then ok "functions deployed"
  else bad "deploy failed, see $RUN/deploy.log"; return; fi
  if ! convex run world:defaultWorldStatus | grep -q worldId; then
    convex run init >/dev/null && uv run python scripts/seed_village.py | head -1
  fi

  echo "6/6 The town page"
  if ! listening "$TOWN_PORT"; then
    start_bg vite bash -c "cd world && exec npx vite --host 127.0.0.1 --port $TOWN_PORT"
    for _ in $(seq 1 30); do listening "$TOWN_PORT" && break; sleep 1; done
  fi
  # macOS sleeps after a minute on battery and kills the stack; hold it awake while this runs.
  if command -v caffeinate >/dev/null && ! pgrep -x caffeinate >/dev/null; then start_bg caffeinate caffeinate -dimsu; fi
  check_town

  echo
  if [ "$FAILED" = 0 ]; then
    echo "Ready. Open the town (keep the tab open: it keeps the world running) and press Memory for the graph:"
    echo "  http://127.0.0.1:$TOWN_PORT/ai-town    http://127.0.0.1:8100/ui"
  else
    echo "Some parts failed (❌ above). Logs: $RUN/"
  fi
}

down() {
  for f in "$RUN"/*.pid; do
    [ -e "$f" ] || continue
    pid=$(cat "$f")
    if kill "$pid" 2>/dev/null; then echo "stopped $(basename "$f" .pid) ($pid)"; fi
    rm -f "$f"
  done
  # uvicorn's server process outlives its parent; stop whatever still listens on the memory service's port.
  if [ -e "$RUN/memory.log" ] && listening 8100; then kill "$(lsof -tiTCP:8100 -sTCP:LISTEN)" 2>/dev/null; fi
  echo "Containers keep running: docker compose stop  (and in world/: docker compose stop)"
}

case "${1:-up}" in
  up) start ;;
  status) status ;;
  down) down ;;
  *) echo "usage: $0 [up|status|down]" >&2; exit 2 ;;
esac
exit $FAILED
