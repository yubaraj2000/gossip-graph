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
| Oct 16 | **GO on AI Town** as the base world | Phase 1 test: every part works; about 8 s per NPC reply; the Mac has memory headroom | Plan B (Python village from scratch) |
| Oct 16 | Data model: **fixed claim vocabulary** with a free-text and vector-dedup fallback | Reliable dedup, and reputation can be counted by claim type | Free text only; open triples |
| Oct 16 | Trust: **fixed confidence rules plus a per-character `gullibility`**, used as the default trust for strangers | Nearly free to add, and NPCs feel different (suspicious guard, gossipy innkeeper) | Learned trust, forgetting and LLM-judged wording, all deferred |
| Oct 16 | Store **every message** | Keeps 'the exact line where you heard it'; storage is trivial (see the scale test) | Summaries only; claim lines only |
| Oct 16 | Multi-village plan: **1 live AI Town village plus 2–3 background villages** fed by replayed conversations, plus a concurrency load test | The DB cost is negligible, but CPU LLM throughput is shared, so a second live village would halve the chatter | Two live AI Town worlds |

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

### Oct 16 — Phase 2: Graph data model and memory service

**✅ 2.1 Data model designed and validated: `docs/DATA_MODEL.md`** [AI]
- **Nodes:**
  - `Character`
  - `Conversation`, `Message` (episodic)
  - `Event` (ground truth)
  - `Claim` (the proposition)
  - `Belief` (one per holder and claim: confidence, origin, status)
  - later: `Task`, `Rule`
- **Key idea:** `Belief -[:HEARD_FROM]-> Belief` is provenance. A root belief either `SAW` an `Event` (witnessed) or has `origin='self'` (invented rumor).
- **Validated on the temp graph `__dm_check` (5 characters, deleted afterwards):**
  - **Ingest:** chained confidence Bram → Pip 0.90 → Mara 0.72 → Tom 0.43. A second source (Bram → Tom) raised Tom's belief to 0.60 via noisy-OR ✅
  - **Explain:** Tom's belief returns both paths, `Tom←Bram` and `Tom←Mara←Pip←Bram`. The invented rumor returns `Mara←Pip` with origin `self` ✅
  - **Reputation:** Tom's view of Kai is −0.48 ✅
  - **Vector dedup:** score 0.001 for a near-duplicate vs 0.947 for an unrelated claim, which **confirms score is a distance** ✅
  - **PageRank on `LEARNED_FROM`** (listener→speaker) ranks the sources: Bram 0.37 first. This fixes the earlier direction catch ✅
  - ⚠️ Label propagation is noisy on 5 nodes; re-check with the real village.
- **❌ → ✅ Recall:**
  - **First version:** hard-filtered to claims about the listener or people the listener knows. Mara therefore wouldn't gossip to Tom about the stranger Kai ❌
  - **Fix:** relevance weighting instead of a filter (2 if about the listener, 1.5 if about someone the listener knows, 1 otherwise), giving `score = confidence × |valence| × relevance`.
- **❌ FalkorDB gotcha:** `CASE WHEN (s)<-[:KNOWS]-(...)` fails with `Invalid input Colon`. Pattern predicates only work in `WHERE`. **Fix:** `OPTIONAL MATCH ... count(kk) > 0`. After the fix, recall returns both the Kai theft (score 0.58) and the rumor about Tom (0.58) ✅
- **AI Town detail:** `rememberConversation` is called **once per NPC participant**, so ingest is made idempotent with `Conversation.ingested`.

**🔬 Live gossip preview: real LLM dialogue plus graph memory** [AI]

Throwaway script in Claude's scratchpad, not project code. It left the graph `preview_gossip` in FalkorDB for browsing.

**Setup:**
- 4 NPCs (Bram, Pip, Mara, Tom) plus Kai, using `llama3.2:3b` on Ubuntu.
- Each NPC's prompt includes its recall (Q2) from the graph.
- After each line, a stand-in for step 2.3 extraction: if the speaker mentions Kai, the listener gets the belief via Q1.

**Findings:**
- **❌ Run 1:** with a generic prompt ("share your most interesting news"), Mara **ignored her memory and invented a different rumor** (spices at the port). The chain stopped at Mara.
  - **Lesson:** small models drift from the provided context, and NPCs invent gossip on their own.
  - Step 2.3 extraction must capture invented claims as `origin='self'`, so made-up rumors also become traceable.
- **✅ Run 2:** with a grounded prompt ("tell the most interesting item from the list above … do not invent other news"), the full chain spread: Bram → Pip 90% → Mara 72% → Tom 43%.
  - Q4 explain returned **`Tom ← Mara ← Pip ← Bram`**, rooted in Bram's witnessed event ✅
- **⚠️ The LLM garbles provenance when it paraphrases.** Given the exact chain, Tom (3B) still said "It was Bram I spoke to first".
  - **Lesson:** show "who told you" from the graph path verbatim (UI or template), and let the LLM add flavor only. Or use 8b for that answer.
- **💡 Rumors mutate.** Mara embellished it to "Kai was spotted trying to fence a stolen silver hammer".
  - Extraction should store this as a **new related claim** that is `HEARD_FROM` the original: "rumor mutation" as a demo feature.
- **❌ → ✅ FalkorDB gotcha:** `'Bram''s forge'` ('' quote-escaping) fails with `Encountered unhandled type in inlined properties`. Use double quotes or (better) query parameters.
- **Speed:** 3–19 s per two-line exchange, and 42 s for the first one (cold model load).

**✅ Scale and cost test for multiple villages** [AI]

Simulated "busy day" village on the temp graph `__scale_day`, deleted afterwards: 10 NPCs, 300 conversations, 3,000 messages, 400 claims, 3,000 beliefs, 4,110 nodes in total.

| Measurement | Result |
|---|---|
| FalkorDB memory (`GRAPH.MEMORY USAGE`) | about **1 MB** per busy-day village; the 15-node preview graph reports 0 MB |
| Recall (Q2) latency, 50 random runs | **0.4 ms median**, 0.5 ms p95 |
| `GRAPH.COPY` of the whole village | **12 ms** |
| Money | $0 (everything is local) |

- **The bottleneck is LLM throughput, not the database.** Ollama on the Ubuntu CPU takes about 8 s per NPC line and serves requests one at a time. Extraction calls share the same capacity.
- **Implication:** extra villages are free in FalkorDB. Running them *live* would divide the chatter rate.

**✅ Gullibility trait verified** [AI]
- Q1 now uses `coalesce(k.trust, lis.gullibility, 0.5)`.
- A stranger's news (confidence 1.0) lands at 0.7 for Mara (gullibility 0.7), 0.3 for Tom (0.3), and 0.5 when the trait is unset.

**✅ 2.2 Memory service skeleton (`memory/`, FastAPI)** [AI]

**Files:**
- `memory/config.py`: settings from environment variables (FalkorDB host and port, `OLLAMA_URL`, embedding dimension 1024).
- `memory/db.py`:
  - one graph per world (`world_<id>`)
  - world ids validated against `[A-Za-z0-9_-]{1,64}` before reaching Cypher
  - `ensure_schema()` creates only the missing indexes: 8 range indexes plus the `Claim.embedding` 1024-d cosine vector index
- `memory/app.py`: `GET /health`, `GET /worlds`, `POST /worlds/{id}` (idempotent).

**FalkorDB behaviors found:**
- Creating an existing index fails with `Attribute 'id' is already indexed`, so we check `CALL db.indexes()` first.
- `db.indexes()` on a graph that was never written fails with `Invalid graph operation on empty key`, so we check `list_graphs()` first.

**Tests:** 12 of 12 pass (`uv run pytest`), against the real FalkorDB with throwaway graphs. They cover:
- unsafe ids rejected, including a Cypher-injection-shaped id
- idempotent schema creation
- vector index present
- world isolation (same `p:1` id, different worlds)
- the API endpoints

Harmless warning: Starlette's test client says `httpx` is deprecated in favor of `httpx2`.

**Running:**
- `uv run uvicorn memory.app:app --host 127.0.0.1 --port 8100`
- `/health` returns `{"falkordb":true,"ollama":"0.30.10"}` **from the Mac and from inside the Convex container** (`host.docker.internal:8100`) ✅
- Created the live AI Town world's graph `world_m177e3zakbq26txfhjmd8mtb0s8ga9ef` with 9 indexes. A second call created nothing ✅

**Tunnel:** `scripts/ollama-tunnel.sh watch` reopens the tunnel every 20 s if Ollama is unreachable, which fixes the drop after the Mac sleeps.

**Data model doc:** added the `Claim.id` index, which the code uses.

**✅ 2.3 Ingest: conversation → claims → beliefs** [AI]

**Files:**
- `memory/extract.py`: prompt plus a JSON-schema answer format, with an enum of 11 predicates.
- `memory/llm.py`: Ollama `/api/chat` with `format` (structured output, temperature 0), and `/api/embed`.
- `memory/ingest.py`: the pipeline.
- `memory/models.py`: request bodies.
- **Endpoints:** `POST /worlds/{id}/characters` and `POST /worlds/{id}/conversations`.

**Embedding distances measured first** (mxbai-embed-large, against "Kai stole a silver hammer from Bram"):

| Compared text | Distance |
|---|---|
| paraphrase | 0.089 |
| looser paraphrase | 0.177 |
| rumor mutation | 0.181 |
| "Kai is a thief" | 0.172 |
| **"Tom stole a silver hammer from Bram"** | **0.138** |
| unrelated | 0.497 |
| small talk | 0.679 |

- **❌ Embeddings alone can't dedup:** a different *subject* scored closer than a real paraphrase.
- **Decision:** structured key first; the vector fallback only for the same subject at < 0.10.

**Extraction prompt, iteration 1 (live, `llama3.1:8b`):**
- ✅ Got the theft, a trait, and the "fence" mutation as a separate `did` claim.
- ❌ Object was "a silver hammer" instead of "Bram".
- ❌ Junk claims ("Tom is looking stern", "the merchant …").
- ❌ Valence −1 for everything.

**Iteration 2:** added rules for person objects, skipping momentary looks and moods, and a valence scale.
- ✅ Valence calibrated (troublemaker −0.2).
- ❌ Still wrong objects, and a nonsense claim ("Tom likes rare spices" with copied first-person text).

**Decision: enforce rules in code, not the prompt.** See `_validate`:
- the subject must be known
- the text must name the subject (kills copied-speech junk)
- a person predicate with a non-person object takes the person named in the text, or else becomes `did`
- valence is clamped

**Rules added:**
- **Atomic take:** `TAKE_CONVERSATION` moves status `new|failed → ingesting` in one query. AI Town sends each conversation once per NPC participant, so exactly one call ingests it.
- **Echo guard:** no reinforcement from your own rumor coming back.
- **Repeat guard:** the same speaker belief only counts once.
- **No self-adoption:** a character never adopts a claim about themselves.
- **KNOWS on first talk:** trust starts at the truster's gullibility.

**Tests:** 20 pass, plus 1 opt-in live test that passes in 14 s (`RUN_LIVE=1 uv run pytest -k live`). The suite uses a scripted fake LLM and covers:
- chain plus provenance: 0.6 → 0.54 → 0.432
- idempotency (the extractor is called once)
- echo guard
- a second independent source: Tom 0.162 ⊕ 0.18 = 0.313
- self-adoption
- near-duplicate dedup
- validation
- the API

**✅ End to end over HTTP with the real LLM** (world `demo`, kept for browsing):

| Conversation | Result |
|---|---|
| Bram→Pip | Pip 54%. Pip's "troublemaker" trait went back to Bram at 30% (0.6 × Bram's gullibility 0.5). |
| Pip→Mara | "Kai swiped his silver hammer" **merged into the same claim** via its key. Mara 43%. |
| Mara→Tom | Tom only **13%** (gullibility 0.3), plus the separate "fence" mutation claim at 18%. |

- Re-sending Mara→Tom returned `skipped` ✅
- **Provenance:** `Tom ← Mara ← Pip ← Bram` ✅
- **Speed:** 9–14 s per conversation (8b on CPU).
- **Note:** the root origin is `self` because there was no narrator event. With step 3.3's narrator event it becomes `witnessed`.
- 💡 **Idea:** an extraction flag for "speaker claims to have seen it first-hand" ("I saw him do it with my own two eyes"). It could be a lie, so keep it distinct from `witnessed`.

### Oct 16 — "Does the pipeline break?" Robustness check of ingest (participant's request)

**Probe:** a scratch script hitting the API with failures, concurrency and odd input. Results before the fixes:

| Scenario | Before | After fix |
|---|---|---|
| Model gives `valence: "very bad"` | ❌ HTTP **422**, whole conversation lost | ✅ that claim dropped, others kept |
| Model gives `message_index: "0"` or `"one"` | ❌ HTTP **500** crash | ✅ numeric strings accepted, junk dropped |
| Model gives a claim as a plain string or `null` | ❌ HTTP **500** crash | ✅ dropped as "malformed claim" |
| Model returns non-JSON | ❌ HTTP **422** (blames the caller) | ✅ **502** `LLMError`; transcript kept; status `failed` |
| `claims` is not a list / embedding count mismatch | — | ✅ 502 |
| Ollama down, then a resend | ✅ 502, then ingested | ✅ unchanged |
| Same conversation ×8 at once | ✅ 1 ingested, 7 skipped, extractor called once | ✅ unchanged |
| 30 conversations at once across 3 worlds | ✅ all ingested, 10 per world | ✅ unchanged |
| Injection-shaped conversation id, emoji, quotes | ✅ stored as plain data | ✅ unchanged |
| **Crash mid-ingest** | ❌ stuck in `ingesting` **forever**; resends say `skipped`; memory silently lost | ✅ see below |
| Silent participant (never speaks) | ❌ not linked to the conversation (found while writing tests) | ✅ participants linked independently of messages |

**Fixes:**
- `memory/llm.py`: new `LLMError`, which wraps HTTP, JSON and shape errors plus embedding count checks.
- `_validate`: parses one claim at a time (`_as_number`, `_text`).
- **Stale lock:** `taken_at` is recorded, and a lock older than 10 minutes can be retaken.
- **Startup recovery:** `ingesting` → `failed`.
- **Retry loop** (FastAPI lifespan): rebuilds failed conversations from the stored transcript. It stops at the first model failure so it doesn't hammer a down model.
- `POST /worlds/{id}/retry` for on-demand retries.

**Tests:** 45 pass (+1 live, opt-in). `tests/test_robustness.py` has 25 cases. Shared fixtures moved to `tests/helpers.py` and `conftest.py`.

**Live chaos test on the real service, tunnel and LLM** (world `chaos`, deleted afterwards):
- ✅ **Tunnel cut mid-request:** HTTP 502 `chat failed: [Errno 61] Connection refused`; status `failed` with the reason saved. Tunnel back plus a resend: ingested, Pip 54%.
- ⚠️ **First crash attempt was invalid:** `pkill -f "uvicorn memory.app:app"` only killed the `--reload` *parent*. The worker (a child process with a different command line) finished the request (HTTP 200), then held port 8100, so the restart failed with exit code 3. **To really stop the service, kill the port's listener:** `lsof -ti tcp:8100 | xargs kill`.
- ✅ **Real crash:** `kill -9` of a single-process service mid-ingest. The client got an empty reply (curl exit 52), and the conversation was stuck at `ingesting`.
  - After restart, the log said `1 interrupted conversation(s) marked failed for retry`.
  - About 20 s later: `retried c:3 -> ingested`, **with no resend by anyone**.
- **FalkorDB gotcha:** `count{(c)<-[:IN]-(:Message)}` (a COUNT subquery) is not supported (`Invalid input '('`). Use `OPTIONAL MATCH` + `count()`.
- **Assumption, documented in `app.py`:** a single service process, because startup recovery treats every `ingesting` as interrupted.

---

## Open questions

- 🔬 Build on an existing open-source game or world, or build from scratch? Candidates so far:
  - `a16z-infra/ai-town` (MIT, TypeScript)
  - `google-deepmind/concordia` (Apache-2.0, Python)
- ✅ ~~LLM provider~~ → Ollama on the Ubuntu box (see Decisions). Groq's free tier is an optional upgrade for the demo recording.
