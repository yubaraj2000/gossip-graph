# Research Log — Graph Hacks (Track 2: Agent Memory and Coordination)

This log records every change, experiment, and decision: what we tried, whether it worked, and why.
Newest entries go at the bottom of each section.

**Status legend:**
- ✅ worked
- ❌ didn't work
- ⚠️ partial or has a catch
- 🔬 in progress
- 💡 idea, not tried yet

**AI assistance disclosure (rule 11):** this project is built with help from Claude Code, an AI coding assistant. Each log entry notes who did the work: **[me]** for the participant and **[AI]** for Claude Code. The participant reviews and understands everything that gets merged.

---

## Decisions

| Date | Decision | Why | Alternatives rejected |
|---|---|---|---|
| Oct 15 | Enter **Track 2: Agent Memory and Coordination** | FalkorDB's one-graph-per-tenant and parallel writes across graphs match the track; Graphiti already supports FalkorDB | Track 1, Track 3 |
| Oct 15 | Python 3.12 via `uv`, not the system Python 3.15 | 3.15 is too new: falkordblite, code-graph and torch don't support it yet | System Python |
| Oct 15 | FalkorDB via `docker-compose.yml` with a volume and AOF | The old container used `--rm` and no volume, so data was lost on restart | Plain `docker run` |
| Oct 16 | Build solo | — | — |
| Oct 16 | Project direction: **NPCs with graph memory and gossip** | Most original of the four ideas, great demo, and the graph is the game logic itself (passes rule 3) | Support-desk "Relay", on-call incidents, study tutor |
| Oct 16 | Principle: **"graph is the brain, LLM is the mouth"** | All NPC knowledge, gossip and reputation live in FalkorDB and are computed with Cypher. The LLM only renders dialogue. This keeps LLM cost low and the graph essential. | LLM-driven NPC-to-NPC conversations |
| Oct 16 | LLM: **Ollama on the Ubuntu box** (CPU), reached from the Mac via an SSH tunnel on port 11435 | Free and unlimited, and the models are already installed; free API tiers are too small for constant NPC chatter. Keeps the Mac's 16 GB free for Docker. | Free API tiers (Groq, Gemini, OpenRouter); Ollama on the Mac |
| Oct 16 | **Git is done by the participant**: Claude provides the commands and commit messages, and never runs git | The participant owns the repo history, which is the evidence for rule 8 | Claude running git |

---

## Experiments and changes

### Oct 15 — Environment

**✅ FalkorDB persistence fix** [AI]
- **Problem:** the container was started with `--rm` and no volume, so the tutorial `social` graph was gone after a restart.
- **Change:** added `docker-compose.yml` with:
  - the `falkordb_data` volume mounted at `/var/lib/falkordb/data`
  - `--appendonly yes`
  - ports bound to `127.0.0.1`
- **Evidence:** seeded the `social` graph, ran `docker compose restart`, and `query.py` still returned Alice's friends and Bob's posts.

**✅ Query timeouts** [AI]
- **Problem:** the image default `TIMEOUT 1000` (deprecated) aborted read queries after 1s, and there was no limit on writes.
- **Change:** `FALKORDB_ARGS=TIMEOUT_DEFAULT 10000 TIMEOUT_MAX 60000 RESULTSET_SIZE 10000 MAX_QUEUED_QUERIES 500`.
- **Evidence:** `GRAPH.CONFIG GET` shows the new values.

**✅ Python env** [AI]
- `brew install uv`, then `uv` with Python 3.12.15 and `falkordb==1.8.0`.
- Run scripts with `uv run python <file>`.

### Oct 15 — Research

**✅ Studied 12 FalkorDB repos and Graphify** [AI]
- Summaries are in `reference/FALKORDB_REFERENCE.md` and `reference/GRAPHIFY_NOTES.md`. The `reference/` folder is gitignored.
- **Vector search:** the `score` is a distance, so lower is closer. The docs cheat-sheet says the opposite.
- **Results:** silently capped at 10,000 rows.
- **Tenants:** one graph per tenant is native. Writes are serialized per graph, but different graphs write in parallel.
- **Graphiti:** each `group_id` becomes its own FalkorDB graph.
- **Graphify:** its MCP tools query NetworkX, not FalkorDB, so using them as-is would break rule 3.

**✅ Verified local FalkorDB** [AI]
- Module version 60002 (≈ v6.0.2), native arm64.
- **Algorithms available:**
  - `algo.BFS`, `algo.SPpaths`, `algo.SSpaths`
  - `algo.pageRank`, `algo.betweenness`, `algo.HarmonicCentrality`
  - `algo.WCC`, `algo.labelPropagation`
  - `algo.MSF`, `algo.maxFlow`
- **Not available:** `algo.AStar`.

### Oct 16 — NPC prototype

**✅ Gossip, provenance and reputation in pure Cypher** [AI]

Ran on the temp graph `__npc_sketch`, deleted afterwards.

**Model:**
- `(:NPC)-[:KNOWS {trust}]->(:NPC)`
- `(:Player)-[:DID]->(:Event)-[:AGAINST]->(:NPC)`
- `(:Belief {holder, confidence, tick})`, linked by `HELD_BY` to the NPC, `ABOUT` to the event, and `FROM` to the source belief

**Results:**
- **Gossip tick query:** the rumor spread Bram → Pip 0.9 and Tom 0.3, then Pip → Mara 0.72, then stopped on its own.
- **Provenance:** `(b)-[:FROM*0..6]->(root)` returned `Mara ← Pip ← Bram`.
- **Grudge** (sum of confidence × severity): Bram 0.8, Pip 0.72, Mara 0.58, Tom 0.24.
- **Betweenness:** Pip and Mara score 1.0, as expected for bridges.

**⚠️ Catch: PageRank direction** [AI]
- `algo.pageRank('NPC','KNOWS')` over teller→listener edges ranks who *hears* the most (Tom 0.42), not who *spreads* the most.
- To find spreaders, reverse the edge direction or add a `HEARS_FROM` relationship.

### Oct 16 — Rules check

**✅ Hackathon FAQ, "Can I continue an existing project?"** [AI]
- Official answer: "You may reuse general libraries, templates, and infrastructure. The submission and its main FalkorDB implementation must be new work completed during the event."
- Rule 9 also allows open-source libraries, templates and public assets; the original work is what gets judged.
- **So:** building on an open-source game or world is allowed, if the FalkorDB memory system is ours and written during the event.

### Oct 16 — Open-source base candidates

**🔬 Searched GitHub for an open-source NPC world to build on** [AI]

| Repo | License | Stack | Stars, last push | Notes |
|---|---|---|---|---|
| `a16z-infra/ai-town` | MIT | TypeScript, Convex, Pixi.js | 10.6k, Aug 2026 | Calls itself a "deployable starter kit" (a template, so allowed by the FAQ). Pixel-art town with 16 characters. NPCs talk to each other through an LLM, and a human can join. Ollama (default), OpenAI, Together or any OpenAI-compatible API. |
| `google-deepmind/concordia` | Apache-2.0 | Python | 1.8k, Oct 15 2026 | Social simulation library. Text only, no visual world. Memory is `associative_memory/basic_associative_memory.py`. |
| `joonspk-research/generative_agents` | Apache-2.0 | Python | 22k, Aug 2024 | The original "Smallville". Stale, with an old OpenAI API. ❌ Not worth reviving in 3 days. |
| `mindcraft-bots/mindcraft` | MIT | JS, Minecraft | 5.9k | ❌ Needs a paid Minecraft Java account. |

**AI Town memory integration points** (cloned to `reference/ai-town/`):
- All memory lives in `convex/agent/memory.ts`. AI Town's own memory is vector-only:
  - `rememberConversation` summarizes a conversation, then embeds and stores it.
  - `searchMemories` runs a vector search ranked by recency and importance.
  - Reflections are generated on top.
- **Only 3 call sites:**
  - `searchMemories` in `convex/agent/conversation.ts:34` (starting a conversation)
  - `searchMemories` in `convex/agent/conversation.ts:102` (continuing a conversation)
  - `rememberConversation` in `convex/aiTown/agentOperations.ts:27`
- **Integration idea:** replace both with HTTP calls (Convex actions can `fetch`) to our own Python graph-memory service on FalkorDB, and remove the vector memory so FalkorDB is essential (rule 3).
- **Setup cost:** self-hosted Convex means 3 containers (frontend, backend, dashboard) plus an admin key.
- **Port note:** AI Town's backend publishes port 11434, which is Ollama's default.

### Oct 16 — Second machine (Ubuntu, 32 GB RAM)

**❌ Couldn't reach the Ubuntu box at `192.168.29.235`** [AI]
- **Plan:** use it to run the LLM and maybe the heavy services, to take load off the Mac (M5, 16 GB).
- **Result:** no reply to ping, and ARP shows `(incomplete)`, so no device answered at that IP. The Mac is at `192.168.29.115`, on the same subnet.
- **Likely causes:** the box is asleep or off, its IP changed, it's on a different network, or the router isolates clients.
- **Access approach:** SSH key only. Claude doesn't log in with passwords. The user runs `ssh-copy-id` themselves.

**⚠️ Retry: box reachable, key not installed yet** [AI]
- Ping is OK and port 22 is open.
- Key-only SSH returns `Permission denied (publickey,password)`. That's expected, because no key had been installed yet.
- **Change:** generated a Mac key, `~/.ssh/id_ed25519` (ed25519, no passphrase, comment `yubarajdas-mac graph_hack`).
- **Pending [me]:** install it on Ubuntu with `ssh-copy-id oditek@192.168.29.235`.

**✅ Key installed [me], and Claude can now SSH in with the key** [AI]

**Box specs:**
- Ubuntu 24.04.3, i9-13900K (24 cores / 32 threads), 31 GiB RAM (about 21 GiB free)
- Disk: 69 GB free on `/`, 83 GB free on `/home`
- **No discrete GPU** (Intel UHD 770 only), so Ollama runs **100% on CPU**.

**Already installed:**
- **Ollama 0.30.10** with `llama3.2:3b`, `llama3.1:8b` and `nomic-embed-text`. These are AI Town's default chat and embedding models.
- Ollama listens on `127.0.0.1:11434` only, so it isn't exposed on the LAN.
- **Docker 29.1.3 is installed, but `oditek` is not in the `docker` group, and sudo needs a password.**
- **Containers there need [me]:** `sudo usermod -aG docker oditek`, then log in again.

**Not shared by other people.** All 3 "users" are sessions of the same account, `oditek`:
- the GNOME desktop on the machine itself (`seat0` and `tty2`)
- SSH from the Mac (`192.168.29.115`)

The other accounts are system services: squid proxy, postfix, ollama, NoMachine (`nx`) and xrdp.

**✅ Ollama CPU benchmark** [AI]

Prompt: a 3-sentence in-character NPC reply.

| Model | Load (cold) | Prompt processing | Generation |
|---|---|---|---|
| `llama3.2:3b` | 2.2 s | 161 tok/s | **24.4 tok/s** (a 40-token NPC line takes about 2 s) |
| `llama3.1:8b` | 4.2 s | 66 tok/s cold, 482 tok/s warm | **11 tok/s** (a 40-token line takes about 4 s) |
| `nomic-embed-text` | — | — | 2 embeddings (dim 768) in 0.3 s |

**✅ SSH tunnel from the Mac works** [AI]
- `ssh -f -N -L 11435:127.0.0.1:11434 oditek@192.168.29.235` makes `http://127.0.0.1:11435/api/tags` on the Mac list all 3 models.
- ✅ Tested from inside a Docker container in Phase 1.3: `host.docker.internal:11435` works from the Convex backend container.
- ⚠️ AI Town's `docker-compose.yml` publishes host port **11434** on its backend container. That would clash with a tunnel on 11434, so use **11435** for the tunnel.

### Oct 16 — Free LLM API research

**⚠️ Free tiers are too small for AI Town's constant NPC chatter** [AI]

Sources are web articles from Sept–Oct 2026, and they partly conflict.

| Provider | Free limits | Catch |
|---|---|---|
| Groq | About 30 requests/min, 1,000 requests/day and 200k tokens/day per model | Open-weight models only (gpt-oss, Qwen). The daily token cap usually binds first. |
| Gemini | Flash and Flash-Lite only | Google no longer publishes free limits; one developer measured just 20 requests/day. Free-tier prompts may be used for training outside the EU. |
| OpenRouter `:free` | 20 requests/min, 50 requests/day | 1,000/day only after buying $10 of credits |
| Cerebras | Reportedly no permanent free tier since July 2026 | Trial credit needs a card |

- Gemini embeddings are free, but their limits are also unpublished.
- **Conclusion:** use Ollama on the Ubuntu box as the main engine. Groq's free tier is an optional higher-quality option for the player's own conversations in the recorded demo.

### Oct 16 — Planning

**✅ Wrote `PLAN.md`: 7 phases (0–6)** [AI]. Approved by [me], with the change that the participant does all git work.
- Working agreement:
  - you approve each phase before it starts
  - Claude does one step at a time and reports
  - each phase ends with a review checkpoint
- **Feature freeze:** Oct 18, 14:00 IST. **Target submission:** 21:00 IST.

### Oct 16 — Repo published

**✅ Public repo: https://github.com/yubaraj2000/gossip-graph** [me]
- Pushed 2 commits on `main`:
  - `0c821a7` chore: set up FalkorDB and Python
  - `d2927a5` docs: add research log and plan
- Both are dated 2026-10-16, about 01:18 IST, so within the event window (rule 8).
- `reference/` and `.venv/` were correctly left out.
- The commits deliberately have **no** `Co-Authored-By` trailer; that's the participant's choice for all commits. The AI-assistance disclosure (rule 11) lives in this log and the README instead.

### Oct 16 — Phase 1: AI Town feasibility test (timebox started 01:36 IST, ends 03:36 IST)

**✅ 1.1 Imported AI Town into `world/`** [AI]
- Unmodified copy of `a16z-infra/ai-town` at commit `8e05997` (2026-08-25), with the upstream `.git/` left out.
- 16 MB, 209 files. The largest file is `src/editor/tilesets/Modern.png` at 5.4 MB, so nothing near GitHub's limits.
- The MIT `LICENSE` is kept. `world/UPSTREAM.md` records the source, the commit, and how to diff our changes.
- AI Town's own `world/.gitignore` already excludes `node_modules`, `.env*.local` and `.env`.
- **Rule for later changes:** commit the import on its own first, so that `git diff <import> -- world/` shows exactly our modifications.

**✅ 1.2 Convex backend running in Docker on the Mac** [AI]
- `docker compose up -d backend dashboard` in `world/`.
- **Frontend container skipped:** its Dockerfile builds Ubuntu, nvm and Node 18. That's slow and heavy, so we run Vite on the host instead.
- `npm install` on the host (Node 24): 749 packages in 15 s.
  - ⚠️ npm skipped the `esbuild` install scripts (new `allowScripts` policy). Harmless: Vite starts fine.
- Admin key generated with `generate_admin_key.sh` and stored in `world/.env.local` (mode 600, gitignored by `world/.gitignore`), together with `CONVEX_SELF_HOSTED_URL` and `VITE_CONVEX_URL`.
- ⚠️ AI Town's compose file publishes 3210, 3211, 6791 and 11434 on `0.0.0.0`, so they're visible on the LAN. Fine for the test; restrict to `127.0.0.1` when we modify `world/`.

**✅ 1.3 Ollama tunnel, reachable from inside Docker** [AI]
- New `scripts/ollama-tunnel.sh` (`start`, `stop`, `status`): SSH `-L 127.0.0.1:11435 → ubuntu:11434`, with keep-alives.
- From the backend container, `curl http://host.docker.internal:11435/api/version` returns `0.30.10` ✅.
- **Embedding gotcha:** AI Town's Ollama default is `mxbai-embed-large` (1024 dimensions, set in `convex/util/llm.ts`), not `nomic-embed-text` (768). We pulled `mxbai-embed-large` on Ubuntu (669 MB) instead of changing upstream code.
- Convex env:
  - `OLLAMA_HOST=http://host.docker.internal:11435`
  - `OLLAMA_MODEL=llama3.2:3b`
  - `OLLAMA_EMBEDDING_MODEL=mxbai-embed-large`

**✅ 1.4 Town runs, and NPCs talk** [AI]
- `npx convex dev --until-success --run init --codegen disable` deployed the functions and created the default world.
  - `--codegen disable` keeps `convex/_generated/` identical to upstream.
  - `diff -rq world/ reference/ai-town/` shows **no upstream file changed**.
- Vite serves `http://127.0.0.1:5173/ai-town`. It renders in Chrome (`127.0.0.1` is allowed; `localhost:3000` was blocked earlier).
- **Idle worlds:** AI Town stops a world after 5 minutes without a heartbeat (`IDLE_WORLD_TIMEOUT`). An open browser tab sends heartbeats. For headless runs, call `npx convex run world:heartbeatWorld '{"worldId": ...}'` every minute.
- Within about 3 minutes the NPCs (`p:0` Lucky and `p:6`) exchanged 10+ messages via `llama3.2:3b` on Ubuntu. The content is the default characters' whimsy (space cheese), to be replaced in Phase 3.
- ⚠️ `npx convex logs --history N` **streams forever**. Run it in the background and kill it, or use `npx convex data <table>` for snapshots.

**✅ 1.5 Measured (8 minutes of real activity, 01:48–01:56)** [AI]

| Metric | Result |
|---|---|
| NPC reply gap (`llama3.2:3b` on the Ubuntu CPU, about 40 words per message) | **median 8 s** (min 6 s, max 11 s), over 18 replies |
| Conversations | 2, with 10 messages each, about 70–80 s per conversation |
| AI Town memories (summary plus `mxbai-embed-large` embedding) | 3 created within about 20 s of each conversation ending, so the embedding path works |
| Convex backend RAM | about 540–550 MiB |
| FalkorDB RAM | about 71 MiB |
| Mac free memory | 51–52% (M5, 16 GB): plenty of headroom |

**❌ Found: the Mac's idle sleep kills the whole stack** [AI]
- The Mac sleeps after **1 minute** idle on battery (`pmset sleep 1`, display after 2 minutes).
- `pmset -g log` shows `Idle Sleep` at **01:56:05**, the exact second the NPC messages stopped.
- After that it only woke in dark-wake bursts, which explains the heartbeat gaps (01:55 → 02:36 → 02:52 → …).
- The SSH tunnel died during sleep, so `ollama-tunnel.sh status` showed it unreachable at 04:33. Restarted ✅.
- **Fix for working sessions:**
  - run `caffeinate -dimsu` while the stack runs (a temporary hold, no system setting changed)
  - stay on mains power
  - TODO: make `ollama-tunnel.sh` reconnect automatically

**⚠️ Timebox:** 01:36–03:36 by the clock, but the active work for 1.1–1.5 took **about 20 minutes**. The rest was the Mac asleep.

**Feasibility verdict: everything needed works.**
- Self-hosted Convex in Docker ✅
- Vite frontend ✅
- Ollama on Ubuntu via the tunnel, including from inside Docker ✅
- NPC conversations ✅
- AI Town's memory pipeline ✅
- `world/` still identical to upstream ✅

Go/no-go is the participant's call [me].

---

## Open questions

- 🔬 Build on an existing open-source game or world, or build from scratch? Candidates so far:
  - `a16z-infra/ai-town` (MIT, TypeScript)
  - `google-deepmind/concordia` (Apache-2.0, Python)
- ✅ ~~LLM provider~~ → Ollama on the Ubuntu box (see Decisions). Groq's free tier is an optional upgrade for the demo recording.
