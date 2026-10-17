#!/usr/bin/env bash
# Create the dialogue model variant on the Ollama box (through the tunnel). Idempotent.
# llama3.2:3b-t24 = llama3.2:3b with 24 CPU threads. On the i9-13900K (32 logical CPUs) that is ~28% faster than
# Ollama's default 8, and it leaves 8 threads for extraction (llama3.1:8b, see EXTRACT_THREADS in memory/config.py).
# Giving both models 24 threads oversubscribes the CPU: a dialogue line took 135 s instead of 9 s (RESEARCH_LOG, Oct 17).
set -euo pipefail

OLLAMA="${OLLAMA_URL:-http://127.0.0.1:11435}"
curl -sf "${OLLAMA}/api/create" \
  -d '{"model": "llama3.2:3b-t24", "from": "llama3.2:3b", "parameters": {"num_thread": 24}, "stream": false}'
echo
echo "now: cd world && npx convex env set OLLAMA_MODEL llama3.2:3b-t24"
