#!/usr/bin/env bash
# Run the graph-memory service on 127.0.0.1:8100. Extra args go to uvicorn (e.g. --reload --reload-dir memory).
# --timeout-graceful-shutdown: without it, a reload or stop waits forever for AI Town's kept-alive connections.
cd "$(dirname "$0")/.." || exit 1
exec uv run uvicorn memory.app:app --host 127.0.0.1 --port 8100 --timeout-graceful-shutdown 5 "$@"
