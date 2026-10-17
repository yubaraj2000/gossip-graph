#!/usr/bin/env bash
# Start the village over: a fresh AI Town world (all town tables wiped), seeded from village/chandanpur.json, plus
# the village template and the background copy (chandanpur_b). Old worlds' graphs in FalkorDB are kept.
#
#   scripts/reset_village.sh --yes
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

if [ "${1:-}" != "--yes" ]; then
  echo "This wipes every AI Town table (the current town, its players and messages) and creates a new world."
  echo "FalkorDB graphs of old worlds are kept. Run again with --yes to do it."
  exit 1
fi

cvx() { (cd world && npx convex "$@"); }

echo "1/5 stopping the engine and wiping AI Town's tables"
cvx run testing:stop >/dev/null 2>&1 || true  # nothing to stop if there's no world
cvx run testing:wipeAllTables >/dev/null
for _ in $(seq 1 60); do  # the wipe runs as scheduled batches
  [ "$( (cd world && npx convex data worlds --limit 1 2>/dev/null) | grep -c '"_id"\|^"')" = 0 ] &&
    [ "$( (cd world && npx convex data messages --limit 1 2>/dev/null) | grep -c conversationId)" = 0 ] && break
  sleep 2
done

echo "2/5 deploying and creating a new world"
cvx dev --once --typecheck enable >/dev/null
cvx run init >/dev/null
world=$(cvx run world:defaultWorldStatus 2>/dev/null | sed -n 's/.*"worldId": "\([^"]*\)".*/\1/p')
echo "    world $world"

echo "3/5 seeding personalities, trust and friendships"
uv run python scripts/seed_village.py | head -1

echo "4/5 template and background village (with its own good deed)"
uv run python -m scripts.background_village --fresh --good-deed | tail -1

echo "5/5 done. Open http://127.0.0.1:5173/ai-town (reload the tab) and the memory page:"
echo "    http://127.0.0.1:8100/ui?world=$world"
