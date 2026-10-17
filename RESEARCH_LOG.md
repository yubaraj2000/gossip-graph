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
| Oct 16 | **Investigator agent becomes the Phase 4 centerpiece** (proposed by [me], shaped with [AI]) | One scene covers every Track 2 focus: memory surviving a crash, handoff and shared state through the case file, episodic interviews, semantic verdicts, and memory updates via debunking. The graph does real work: planning interviews and proving the verdict. | The generic guard-captain task handoff; procedural memory |
| Oct 16 | **Minds are private:** the investigator sees only the social structure and must interview to learn beliefs | Makes "agents really remember" provable instead of an omniscient query | Letting the investigator read all beliefs directly |
| Oct 16 | **Include debunking:** published verdicts mark debunked beliefs `superseded` (never deleted), and trust in the originator drops | The "a new agent can come and fix everything" story | Stopping at the verdict |
| Oct 16 | **Village: Chandanpur, 8 villagers with Indian names** ([me] asked for Indian names) | Two circles (market: Ramesh, Chotu, Lakshmi, Sarla; temple/school: Pandit Shastri, Meera, Balwant) joined by Gopal the milkman, which gives the bridge and hub structure for the investigator's briefing | AI Town's default 5 characters |
| Oct 17 | **Keep 4.7: investigator walks and talks in AI Town** ([me]: "helpful in demo") | Most visual demo moment; both sides of each interview are posted from the graph, so the screen matches the case file word for word | Skipping it for Phase 5 time |

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

**✅ 2.4 Recall: `GET /worlds/{id}/recall?me=&other=&k=&episodes=`** [AI]

**Files and behavior:**
- `memory/recall.py`: pure Cypher, no LLM. It returns:
  - ranked beliefs (Q2)
  - reputation (Q5)
  - `KNOWS` trust
  - recent episodes (Q3)
  - `memories`: first-person lines for the NPC prompt
- **New idea, beyond the data-model doc: "already shared".** If my belief and the listener's are linked by `HEARD_FROM` in either direction, we've already exchanged that rumor, so its score is ×0.2. The NPC knows this because it was in that conversation.
- **Memory lines use words, not numbers:**
  - confidence: "I'm sure of it" / "I believe it" / "I'm not certain" / "it's only a rumor to me"
  - trust: "trust" / "somewhat trust" / "don't fully trust"
  - reputation: "very bad" … "very good"
  - first person: "from Bram" becomes "from me" and "Bram's" becomes "my" in Bram's own memory, but not when Bram is the subject. The word boundary leaves "Brambles" alone.

**❌ → ✅ Bug: `already_shared` was always false.**
- Debugged clause by clause. Each `OPTIONAL MATCH` works on its own, and after a plain `WITH b`.
- The failing shape: `MATCH … OPTIONAL MATCH (kk…) WITH b,c,s, count(kk) … OPTIONAL MATCH (b)-[sh:HEARD_FROM]-(…)` returns `count(sh) = 0`.
- **FalkorDB 6.0.2 quirk:** an OPTIONAL MATCH placed after an earlier OPTIONAL MATCH plus an aggregating WITH silently matches nothing. A minimal single-MATCH repro did **not** trigger it, so it needs the multi-clause shape.
- **Fix:** put all OPTIONAL MATCHes before one aggregating WITH. Verified: Pip→Bram and Mara→Tom are now shared; Tom→Kai is not.
- 💡 Consider reporting this upstream to FalkorDB with the demo graph.

**❌ Test-harness slip:** zsh doesn't word-split `$pair`, so the first curl loop sent malformed URLs. It wasn't a service bug; I redid the checks in Python.

**Tests:** 53 pass. `tests/test_recall.py` has 8 cases:
- damping for already-shared claims
- fresh gossip not marked shared
- about-the-listener first, with reputation
- `k` limit and ordering
- episodes and trust
- first-person lines
- unknown characters and worlds
- the endpoint (422 on bad `k`, a missing param, or a bad world)

One expectation of mine had a rounding error (0.26 vs 0.259). I fixed the test, not the code.

**Live on the `demo` world:**
- **Pip→Bram:** "Bram told me that Kai stole a silver hammer from Bram (I believe it). Bram and I already talked about this."
- **Bram→Pip:** "I've been saying that Kai stole a silver hammer from me …"
- **Tom→Kai:** "I don't really know Kai yet. / My impression of Kai is bad. / Mara told me … (it's only a rumor to me)."
- **Latency:** 200 HTTP calls, **2.2 ms median**, 2.4 ms p95.

**✅ 2.5 Explain: `GET /worlds/{id}/explain?holder=&claim=&subject=`** [AI]

**Files:** `memory/explain.py`. For each of the holder's beliefs it returns:
- every `HEARD_FROM` path to a root (Q4), capped at 5 per belief
- each step's holder, confidence, `heard_from` name, and **the exact line heard** (the `EVIDENCE` message said by the next person)
- the root origin and event
- `grounded` (the claim `REFERS_TO` an event)
- `verdict`: `witnessed` or `unverified`
- an answer `sentence`

**The sentence is built from the graph path, never by the LLM.** The preview showed 3B garbling the chain. Names are repeated instead of using pronouns, since characters have no recorded pronouns.

| Case | Sentence |
|---|---|
| Chain | "Mara told me. Mara heard it from Pip, who heard it from Bram. Bram started it, and nobody saw it happen." |
| Witnessed | "Pip told me. Pip heard it from Bram. Bram saw it happen." |
| Extra direct source | "… I also heard it from Mara." |
| Holder is the root | "I saw it myself." / "Nobody told me; I said it first." |

- First sentence draft: "Mara told me, who said it first." It read badly, so it was reworked before the tests.
- Test fixture `gossip` moved into `conftest.py`, with its constants in `tests/helpers.py`, and shared by the recall and explain tests.

**Tests:** 60 pass, all on the first run. `tests/test_explain.py` has 7 cases:
- the full chain with the lines heard
- the mutated rumor traced to Mara
- a second source as a second path (the shortest path comes first)
- **a witnessed event grounds the chain** (seeded the way the 3.3 narrator will): Bram's belief stays `witnessed` at 1.0 through ingest, so Mara is at 0.72
- the originator
- filters and unknowns
- the endpoint

**Live on `demo`:**
- Tom on the theft: *"Mara told me. Mara heard it from Pip, who heard it from Bram. Bram started it, and nobody saw it happen."*
- Mara on the fence rumor: *"Nobody told me; I said it first."* Correct: Mara invented the "fence" twist.
- **Latency:** 200 HTTP calls, **2.0 ms median**, 2.5 ms p95.

**✅ 2.6 Prototype story end to end through the HTTP API: `tests/test_scenario.py`** [AI]

**Flow:** characters via the API, with the prototype's trust as gullibility (Pip 0.9, Mara 0.8, Tom 0.6). The witnessed theft is seeded (a stand-in for the 3.3 narrator). Then the 3 real preview conversations go through `POST /conversations`.

**Checks, all reproducing the prototype:**

| Check | Result |
|---|---|
| Chain | Pip **0.90**, Mara **0.72**, Tom **0.432** |
| Grudge against Kai (−confidence × valence) | Bram 1.0, Pip 0.9, Mara 0.72, Tom 0.432 (via recall) |
| Explain path | Tom ← Mara ← Pip ← Bram, verdict `witnessed`, sentence "… Bram saw it happen." |
| Resend | `skipped`, numbers unchanged |
| Scripted extra: Bram tells Tom directly | Tom = 1 − (1 − 0.432)(1 − 0.6) = 0.773; sentence "Bram told me. Bram saw it happen. I also heard it from Mara." |

**Live version** (`RUN_LIVE=1`, real `llama3.1:8b` on the real dialogue): **3/3 runs passed**, at 49 s, 41 s and 41 s. Extraction was stable enough that every conversation's theft claim merged into the witnessed claim by key. That includes "Kai swiped his silver hammer", which never names Bram.

- Test helper `seed_witnessed_theft` moved to `tests/helpers.py`.
- **Suite:** 61 pass, plus 2 opt-in live tests.

**Phase 2 build steps (2.1–2.6) are complete.** Next: the Phase 2 review checkpoint with the participant.

### Oct 16 — Investigator concept (from the participant's idea)

**💡 → approved.**

**Idea [me]:**
- A new NPC investigator who knows nothing solves a case by asking other NPCs, to show that agents really remember.
- **Production analogy:** if an agent crashes, a new agent can come in and recover everything by itself from the shared memory.
- Take Graphify as the reference.

**What Graphify does** (from `reference/graphify`: README, `AGENTS.md`, `analyze.py`, `report.py`):
- Builds the graph once, so agents query it instead of re-reading files.
- `GRAPH_REPORT.md` for orientation: "God Nodes (most connected)", communities (Leiden), surprising connections.
- `suggest_questions()`:

  | Graph signal | Question it generates |
  |---|---|
  | AMBIGUOUS edges | "What is the exact relationship between …?" |
  | bridge nodes (betweenness) | "Why does X connect A to B?" |
  | god nodes with many INFERRED edges | "Are these inferred relationships correct?" |
  | isolated nodes | "What connects them?" |

- Edge confidence: EXTRACTED / INFERRED / AMBIGUOUS.
- Agent rule: "use the report for broad orientation, scoped queries for specifics".

**Mapping to the village:**

| Graphify | Village |
|---|---|
| Report | Case briefing (hubs via PageRank on `LEARNED_FROM`, bridges via betweenness, cliques via label propagation) |
| Suggested questions | Leads ("who told you?" points upstream; unverified claims lead to "who started this?") |
| EXTRACTED / INFERRED / AMBIGUOUS | `witnessed` / `heard` / `self` |

**Plan updated (`PLAN.md` Phase 4):**
- 4.1 case file and briefing
- 4.2 lead planner
- 4.3 interview loop
- 4.4 crash and resume
- 4.5 verdict and debunking
- 4.6 light separate villages
- 4.7 stretch: walking in AI Town
- **Dropped:** procedural memory and the load test.
- **New scope cut order:** walking in AI Town → background villages → custom panels → the trust drop.

### Oct 16 — Phase 2 review checkpoint

**✅ Done (sections 1–4 walked through; 5–6 skipped at [me]'s request; they're in the doc). Wrote `docs/WALKTHROUGH.md`** [AI]

A plain-language tour, reviewed section by section with the participant [me]:
1. The big picture (the AI is used in only 2 places)
2. The graph model (Event / Claim / Belief, explained with a newspaper analogy; the confidence math with the step 2.6 numbers)
3. Ingest, step by step
4. Q1, Q2 and Q4 annotated line by line
5. Failure handling and the bugs found
6. Judge-style practice questions with answers

It's reusable for the README and the demo script.

### Oct 16 — Phase 3: Connect the world to the graph

**✅ 3.1 AI Town's memory replaced by the graph-memory service** [AI]

These are the first changes to `world/` since the pristine import (`2ddae25`): 7 files, +115/−591.

- **`convex/agent/memory.ts` rewritten** (488 → ~130 lines):
  - `rememberConversation` (same signature, so `agentOperations.ts` is unchanged) loads every villager plus the participants and messages via the new internal query `loadForMemory`. It then calls `POST /worlds/{worldId}/characters` and `POST /worlds/{worldId}/conversations`.
  - `recallMemories` calls `GET /recall` and returns first-person memory lines plus the last conversation summary.
  - **On service errors, both log and continue:** the agent loop never stalls, and the service retries anything it received.
- **`conversation.ts`:**
  - start and continue now use `recallMemories` (no per-turn embedding call any more)
  - "previous conversation" detection uses the recalled summary
  - added `gossipInstructions`: "If your memories include news about other villagers, bring up the most interesting piece in your own words", the nudge the preview proved necessary
- **Deleted AI Town's vector memory (rule 3):**
  - `memories`, `memoryEmbeddings` (1024-d vector index) and `embeddingsCache` tables
  - `embeddingsCache.ts`, importance scoring and reflections
  - those tables in the daily vacuum cron
  - `grep` finds only comments mentioning them now.
- **Removing tables needed empty data:** set `testing.ts` `excludedTables` to `[]` so the wipe includes the cache, deployed, ran `testing:wipeAllTables`, then deployed the new schema with `--typecheck enable` ✅
- Convex env `MEMORY_SERVICE_URL=http://host.docker.internal:8100`. `npx convex run init` created the new world `m176n4n5ak3hat4abpdtbe6scn8gd6z1` (default AI Town characters until step 3.2).

**Live result** (the town ran about 2 h while the session was paused):

| Measure | Result |
|---|---|
| Recall calls from Convex | **28 `GET /recall` → 200** |
| Conversation posts | 5 `POST /conversations` → 200 |
| Ingested into `world_m176…` | **3 conversations** |
| Graph contents | 30 messages, 2 claims, 3 beliefs |

- Example: Pete said "entropy is the work of the devil", so Alice believes it at 30%, HEARD_FROM Pete.
- The default characters mostly philosophize, so there are few claims about people. Step 3.2's village fixes that.

**❌ → ✅ Race found live:** one `POST /characters` → **500 `Attribute 'id' is already indexed`**.
- **Cause:** a brand-new world gets the same conversation from both NPCs at the same moment. Both requests ran `ensure_schema`, and both tried `CREATE INDEX`.
- Harmless that time (the other NPC's call still ingested the conversation), but real.
- **Fix:** a `threading.Lock` in `ensure_world`, plus `_create_index` treating "already indexed" as success, in case another process got there first.
- **Tests:** 8-thread first-call race on a new world, plus a concurrent-creator tolerance test. 63 pass.

**Note:** Convex logged `engineNotRunning` errors at 16:08 for engine `ks737…`. Those are leftovers from the wiped world's scheduled steps and unrelated.

**✅ 3.2 The village of Chandanpur** [AI]

**The village:**
- **`world/data/characters.ts`:** 8 villagers on sprites f1–f8, each with a role identity and a plan. All identities end with the **village roster** ("When you talk about people, talk about them").

  | Villager | Role | Gullibility |
  |---|---|---|
  | Ramesh | blacksmith | 0.5 |
  | Chotu | apprentice | 0.9 |
  | Lakshmi | chai stall | 0.8 |
  | Sarla | tailor | 0.75 |
  | Gopal | milkman (the bridge) | 0.7 |
  | Pandit Shastri | priest | 0.4 |
  | Meera | teacher | 0.35 |
  | Balwant | constable | 0.3 |

- **`village/chandanpur.json`:** gullibility plus 24 directed trust links. Name-keyed, and the single source of truth for personalities.
- **New `POST /worlds/{id}/relationships`:** directed `KNOWS` trust. Re-seeding updates trust but keeps the interaction count, and unknown ids are skipped and reported. 3 tests.
- **New `scripts/seed_village.py`:** reads Convex `world:defaultWorldStatus` and `world:gameDescriptions`, maps names to AI Town player ids, and posts characters and trust.
- **Reset recipe:** `npx convex run testing:wipeAllTables`, then `npx convex dev --once`, then `npx convex run init`, then `uv run python scripts/seed_village.py`.

**Graph algorithms on the seeded village:**
- **Betweenness:** Gopal **24** (the bridge, as designed), then Lakshmi 13. **PageRank** on `KNOWS`: Lakshmi and Gopal 0.16.
- ❌ **`algo.labelPropagation` is unusable here.** At maxIterations 1–20 it returns the same pairs, including **unconnected** ones (Ramesh+Sarla, Gopal+Meera). That's likely the oscillation of synchronous label propagation, plus tie-breaking.
- **Plan for 4.1 circles:** remove the top bridge, then run `algo.WCC`. Consider reporting upstream.

**Live run 1** (world `m1748…`, no roster):
- In character ("Pandit ji", "Namaste Sarla!"), and Balwant spontaneously investigated a metalwork theft.
- **Problems:**
  1. **Trivial claims** ("Lakshmi heard fascinating tales", valence 0.0).
  2. NPCs **invented outsiders** (Ramu Patel, Deepa ji), and those claims were dropped as unknown subjects.
  3. **❌ Provenance bug:** `Ramesh:self<-Balwant`. Ramesh said it first and later also heard it from Balwant, so explain would credit Balwant.
  4. My reporting query double-counted rows, which looked like duplicate claims. Not a real bug.

**Fixes:**
- **Explain paths relay only through `heard` beliefs and stop at the first `self`/`witnessed` belief.** Later edges are corroboration, not origin. Uses `all(x IN nodes(p)[0..size(nodes(p))-1] WHERE x.origin = 'heard')`. Regression test added.
- **`MIN_ABS_VALENCE = 0.15`:** neutral claims are dropped as "neutral, not gossip". Recall would never surface them anyway.
- **Honorific-aware names:** `_resolve_person` ignores ji / bhai / didi / sahib / singh and so on, and matches only when unambiguous. "Balwant Singh" → Balwant; "Shastri ji" and "Pandit ji" → Pandit Shastri; "Ramu Patel" → none. `_names_person` accepts any word of the name. Test added.
- **Roster** in every identity.

**Service hang:**
- ❌ While AI Town was connected, a code edit triggered `--reload`, and uvicorn waited forever: "Waiting for connections to close" (AI Town's kept-alive connections). The seed script timed out.
- **Fix:** new `scripts/run_memory.sh` with `--timeout-graceful-shutdown 5`.

**Live run 2** (world `m171vdd5drtp1tf26ktcjee3xn8gcs5q`, with the roster):
- 4 conversations ingested, 7 posts, **0 errors**.
- **Gossip is about real villagers now:**
  - "someone spotted lurking near Ramesh's forge late at night": Lakshmi → Balwant
  - "a stranger asking about Gopal's milk delivery routes": Sarla → Ramesh
  - "Ramesh said Chotu's work was broken into"
- **Remaining quality notes:**
  - some claim texts stay first-person ("I also overheard Sarla…")
  - reported speech sometimes makes the reporter the subject
  - valence is occasionally harsh (−1.0 for a scolding)

  Acceptable for now.

**Tests:** 68 pass.

**✅ 3.3 Narrator: `POST /worlds/{id}/events`** [AI]

**Files:**
- `memory/narrate.py` and `EventIn`: kind (a claim predicate), actor, target, description, optional claim text, valence, severity, witnesses. Characters may be ids, names, or names with honorifics.
- **What it does:**
  - creates `Event` with `DID` / `AGAINST` edges
  - **resolves the claim exactly like ingest:** key `actor|kind|target`, then vector-by-subject. It grounds an existing rumor instead of duplicating it, and adds `REFERS_TO`.
  - gives witnesses `witnessed` beliefs at 1.0, upgrading any earlier `heard` belief. The actor is never given a belief about themselves.
  - the event id is a hash of the event, so it's idempotent
  - unknown characters or a bad kind return 422; an embedding failure returns 502
- Renamed `ingest._resolve_claim` / `_resolve_person` → `resolve_claim` / `resolve_person`, since narrate shares them.
- **Kabir the traveler:** added as an **outsider** in `village/chandanpur.json`, with fixed id `kabir` and kind `human` (not an AI Town NPC). `seed_village.py` seeds outsiders. The live world `m171…` now has 9 characters.

**Tests:** 75 pass. `tests/test_narrate.py` has 7 cases, all passing on the first run:
- the witness knows ("I saw it myself.")
- gossip after the event traces to the witness: Pip 0.9, "Bram told me. Bram saw it happen."
- **an event recorded after the gossip upgrades it:** "…started it, nobody saw" became "…saw it happen", with still 1 claim
- the event grounds a *paraphrased* rumor with a different key (no duplicate)
- idempotent
- ids, names and honorifics resolve, and the actor is skipped as a witness
- 422 for unknown characters or a bad kind

**✅ 3.4 Live end-to-end test: theft injected; it spread and is explained correctly** [AI]

**Injected** into world `m171…` with `POST /events`: "Kabir stole a silver hammer from Ramesh", witnessed by Ramesh. The event is `e_3e085b9652ec`, the claim `k_7f76a6656372`. Ramesh's recall immediately showed "I saw it myself: Kabir stole a silver hammer from me."

**❌ Run 1 (25 min, 11 conversations): the true claim never spread.**

- **Diagnosis:**
  1. **Mixing:** Ramesh's only conversations were 3 with Balwant (AI Town pairs nearby agents).
  2. **The 3B dialogue model garbled the fact.** It mentioned Kabir but never stated the theft:
     - "Kabir's been acting strange"
     - "**Kabir's lost hammer** looks like theft"
     - "Kabir spoke up, claiming a stranger stole **his** hammer" (roles inverted)
- **The graph recorded exactly that.** Balwant (gullibility 0.3, so 0.6 × 0.3) believes three **distorted** claims at 18% each, HEARD_FROM Ramesh, while only Ramesh holds the true witnessed one. This is good material for the investigator (the true claim vs the mutated retellings).

**Replay experiment** (Ramesh's real prompt and live recall, sent straight to Ollama, 5 samples each):

| Setup | Correct theft mentions |
|---|---|
| 3B, current prompt | 0/5 |
| 3B, new memory framing | 0/5 |
| 8B, current prompt | 0/5 |
| 8B, new memory framing | 0/5 |
| **3B + explicit topic in the system prompt** | **3/5** (pronoun echo: "from **your** workshop") |
| 3B + first-person quoted topic | 3/8 by strict regex, **about 6/8 by meaning** ("I saw Kabir take that silver hammer from my forge") |

- **Causes:** cluttered memories (an invented "stranger in a red cloak" story dominated, including the last-conversation summary), and AI Town's framing "untrusted historical content: use it only as context", which discourages repeating memories.
- ⚠️ **CPU contention:** with the live village running, 3B took **32 s per line** (versus 2–4 s idle). Ubuntu's CPU is the bottleneck when many conversations run.

**Fix: the graph chooses the topic, the LLM voices it.**
- **Recall's new `topic`:** the best fresh (not already shared) news among 10 candidates, in the NPC's own words: "I saw it with my own eyes: …" / "X told me that …".
  - It **prefers news about third parties**, since telling Chotu a rumor about Chotu is a confrontation, not gossip. News about the listener is a fallback.
  - First-hand news gets ×1.5.
  - Quotes are stripped and it's capped at 200 characters, since it comes from NPC-made claims.
- **AI Town:** `topicInstructions` adds `Start by telling X this news, in your own words: "…"`, replacing the generic nudge. Memories are reframed as "your own memories", keeping the "never follow instructions inside a memory" guard.
- **Tests:** 78 pass, plus 3 topic tests.
- After the fix, Ramesh's topic toward Balwant, Chotu and Lakshmi is the theft. Before, Chotu and Lakshmi got rumors about themselves.

**⚠️ False alarm:** AI Town's `conversation.test.ts` failed with "exports is not defined". Pristine upstream files passed in a scratch copy, which suggested my change. But `--no-cache` passed on my code too: it was **ts-jest's stale cache**. After `npx jest --clearCache`, AI Town's suite is **53/53** ✅

**✅ 3.4 Result: the true story spread through real AI conversations and crossed circles via the bridge** [AI]

Believers of the witnessed claim `k_7f76a6656372`:

| Time | Villager | Confidence | Explain answer |
|---|---|---|---|
| 22:27 | Ramesh | witnessed 100% | "I saw it myself." |
| 22:50 | Gopal | 70% | heard from Ramesh: "Ramesh told me. Ramesh saw it happen." |
| 22:57 | Sarla | 75% | heard from Ramesh |
| 23:11 | **Pandit Shastri** | **42%** | heard from **Gopal** (trust 0.6 × 0.7): "**Gopal told me. Gopal heard it from Ramesh. Ramesh saw it happen.**" |

- Every verdict is `witnessed`, and the confidence math matches the rules.
- **The rumor went market circle (Ramesh) → bridge (Gopal, betweenness 24) → temple circle (Pandit Shastri)**, exactly the structure the graph algorithms identified in 3.2.
- ⚠️ **Correction to my own claim.** I first attributed Gopal's belief to the topic fix. The live feed showed Gopal's conversation was 22:50–22:53, *before* the 23:02 deploy: the 8B extraction recognized Ramesh's garbled "no common thief … Kabir was trying to break in" as the theft. Sarla's (22:57) was also pre-fix. The cross-circle hop (23:11) came after the fix. Evidence that the topic fix helps is therefore 1 live hop plus the replays; not proven at scale.

**New `scripts/live_feed.py`** (`uv run python -m scripts.live_feed [world]`): polls the graph every 3 s and narrates:
- 💬 conversations
- 👁 witnessed
- 👂 heard (from whom, with the exact line)
- 🗣 started a rumor

It's useful for watching live and for the demo video. It must run as a module from the repo root.

**Live noise seen in the feed** (it's in the graph, but doesn't break anything):
- an imperative extracted as a claim ("Ask Meera about …")
- an invented counter-rumor ("Ramesh stole two iron artifacts from Lakshmi's cart")
- the "stranger in red" storyline keeps growing

Possible later extraction filters, and good material for the investigator.

**Phase 3 is complete** (3.1–3.4). Next: the Phase 3 review checkpoint with [me], then Phase 4 (the investigator).

### Oct 16 — Phase 3 review checkpoint

**✅ Done** [AI]+[me]. A plain-language recap was given in chat and added to `docs/WALKTHROUGH.md` as a Phase 3 section:
- the two connections
- the village
- the narrator
- the graph choosing the topic
- the live cross-circle spread
- the bugs found

### Oct 16–17 — Phase 4: the Investigator

**✅ 4.1 Case file and briefing** [AI]

**Files:** `memory/cases.py`, plus `POST /worlds/{id}/cases` and `GET /worlds/{id}/cases/{case}`.
- **Case file in the graph:**
  - `Case {title, question, status, briefing}`
  - `(investigator)-[:INVESTIGATES {since, active}]->(Case)`. Assigning a new investigator deactivates the old one.
  - `(Case)-[:HAS_LEAD]->(Lead {kind, reason, priority, status})-[:TARGET]->(Character)`
  - The briefing is computed **once** and stored, so every investigator on the case reads the same one.
- **Briefing, Graphify-style** (its report covers god nodes, communities and suggested questions), **from structure only, no beliefs:**
  - news hubs: PageRank on `LEARNED_FROM` (falls back to `KNOWS`/trust before any gossip)
  - bridges: betweenness
  - circles: connected groups after removing the top bridge, because label propagation was unusable (3.2)
  - suggested leads: top hub, top bridge, and one voice per circle, each with a plain-English reason and summary lines
  - investigators and outsiders are excluded
- **Tests:** 84 pass. `tests/test_cases.py` has 6 cases on the real `chandanpur.json` structure:
  - bridge = Gopal, two circles
  - hubs switch to news flow once gossip exists
  - the case file is shared and written once across investigators
  - investigators don't distort the structure
  - circles survive a fully dense `KNOWS`
  - 404

**❌ → ✅ Live finding: social structure densifies.** The first live briefing said "Chotu bridges", with one circle of 7.
- **Cause:** after hours of talk, `KNOWS` (created on every first conversation) had 52 edges against 24 seeded, so the designed circles dissolved.
- **Fix:** seeding also writes `FRIEND` edges (the lasting friendships). Circles and bridges are read from `FRIEND`, and hubs from live `LEARNED_FROM` news flow. Reseeded the live world (idempotent) and reopened the case.

**Live briefing** (case `case_hammer`, Inspector Vikram):
- "Most news comes from Gopal and Pandit Shastri"
- "Gopal bridges the village's circles; Lakshmi is the next-strongest link"
- circles: {Ramesh, Sarla, Chotu, Lakshmi} and {Meera, Balwant, Pandit Shastri}
- **leads:** Gopal (hub), Lakshmi (circle voice), Pandit Shastri (circle voice)

**✅ 4.2 + 4.3 Lead planner and interviews: `POST /worlds/{id}/cases/{case}/interview[?target=]`** [AI]

**Design: minds stay private.**
- An interviewee testifies only about **case-relevant** beliefs, chosen with the vector index: claim distance to the case's title and question < **0.40**.
- Measured live, for calibration: the true theft at 0.283, its garbled retellings at 0.32, competing theft rumors at 0.33–0.38, unrelated chatter at ≥ 0.42.
- They name only their **direct** sources ("Gopal told me"), never the whole chain. That forces the trail to be followed interview by interview.

**Each interview:**
- The answer lines are built from the graph (no LLM).
- It's recorded as a `Conversation {kind:'interview'}` via the new shared `ingest.record_transcript`.
- The investigator **hears** each testified claim (`ingest.hear`, Q1), so its own beliefs carry provenance.
- A `Finding` is written per claim.
- **Every named source becomes a new lead with priority 0**, which jumps the queue. An interview chosen directly by the investigator gets a `chosen` lead, so the file records why it happened.
- The lead is closed with `RESOLVED_BY`, and interviews are idempotent ("already_interviewed").

**Fixes:**
- **❌ → ✅ A seeded test claim had no embedding**, so vector testimony couldn't see it. The helper now embeds it, as real claims always are.
- **❌ → ✅** `sed '\b…'` doesn't work on macOS; I did the helper renames with Python regex.
- **❌ → ✅ Directly chosen interviews had no lead,** so the file didn't record them. Fixed.
- **New ingest filter:** drop "not a statement", i.e. instructions and plans like "Ask Meera about…" or "I'll discreetly ask…", seen in live testimony.

**Tests:** 90 pass. `tests/test_interviews.py` has 6 cases:
- the trail Tom → Mara → Pip → Bram (witnessed)
- the investigator knows nothing before interviews, and its theft belief then traces to the eyewitness
- an interview is never repeated
- "I haven't heard anything about that"
- running out of leads
- the endpoint (404 / 422)

**Live (Inspector Vikram, `case_hammer`), 5 interviews:**

| # | Interviewee | Testimony | New leads |
|---|---|---|---|
| 1 | Gopal | "Ramesh told me that Kabir stole…"; "Lakshmi told me that Ramesh stole two iron artifacts from Lakshmi's cart" | Ramesh, Lakshmi |
| 2 | Lakshmi | "Sarla told me" about the theft; she **started** both artifact rumors | Sarla |
| 3 | **Ramesh** | "**I saw it with my own eyes: Kabir stole a silver hammer from me**"; he also started the garbled Kabir versions | — |
| 4 | Sarla | "Ramesh told me" | — |
| 5 | Pandit Shastri | "Gopal told me"; "Lakshmi told me" | — |

Then `no_open_leads`. **The eyewitness was reached in interview 3, and every competing rumor was traced to its originator.**

**✅ 4.4 Crash and resume** [AI]

**New pieces:**
- **`POST /worlds/{id}/cases/{case}/assign`:** hands the case to a new investigator. The old one becomes inactive. The response includes a **handoff summary** built from the case file, with no LLM:
  - the case and briefing
  - "Inspector Vikram interviewed Gopal and Lakshmi."
  - one `Finding:` line per claim (who heard it from whom / saw it / started it)
  - open leads with their reasons
  - "Next: interview …"
- **`scripts/investigate.py "<name>" [--case] [--crash-after N] [--pause S]`:** the investigator agent. It opens or joins a case and interviews until the leads run out. It keeps **nothing** between runs; everything lives in the case file. `--crash-after` simulates a crash with `os._exit(1)`.

**Tests:** 94 pass. `tests/test_handoff.py` has 4 cases:
- Anjali resumes at Pip, the next lead, after Vikram's 2 interviews. Each villager is interviewed exactly once, and interviews are attributed to Vikram, Vikram, Anjali, Anjali.
- **The replacement doesn't inherit the old investigator's mind.** Anjali has 0 beliefs after reading the file.
- Assigning twice is harmless.
- The endpoint (404).

**Live demo** (case `case_hammer_demo`):
1. Vikram opens the case, gets the briefing, and interviews Gopal (new leads: Ramesh, Lakshmi), then Lakshmi (new lead: Sarla).
2. 💥 The process dies (exit 1).
3. Anjali, a fresh process, reads the handoff: what Vikram did, the findings, and open leads Ramesh / Sarla / Pandit Shastri.
4. She **interviews Ramesh first** ("I saw it with my own eyes"), then Sarla and Pandit Shastri. **No repeated interviews.**

**Bugs found while building the demo:**
- **❌ → ✅** `httpx` with base URL `/cases` plus `post("")` added a trailing slash, so FastAPI returned 307. Fixed with explicit paths.
- **❌ → ✅** Vikram's output vanished when piped: `os._exit` skips flushing stdout. Fixed with `sys.stdout.flush()` before the crash.

**Old junk in live data:** the "Ask Meera…" claim was created before the not-a-statement filter, so it still shows up in old findings.

**✅ 4.5 Verdict and debunking: `POST /worlds/{id}/cases/{case}/verdict`** [AI]

**Verdict** (in `memory/cases.py`). It uses **only the case file's findings**, never the hidden events:

| Verdict | Rule |
|---|---|
| **confirmed** | someone testified `witnessed` |
| **distorted** | started by someone, same subject as a confirmed claim, vector distance < **0.27**: honest garbling |
| **unfounded** | started by someone (`self`), nobody saw it, and not a distortion |
| **unresolved** | only heard testimony; the trail ran out |

- **Calibration, measured live:** the eyewitness's own garbled retellings sit at 0.18 and 0.25 from the confirmed theft; unrelated claims about the same person start at 0.31; competing stories are about *other* subjects.

**Publishing** (the memory update, nothing deleted):
- Every active belief in a debunked claim becomes `status: 'superseded'` with `valid_to` and `DEBUNKED_BY {kind, started_by, by}`.
- **Only unfounded rumors cost trust:** each misled believer's `KNOWS` trust in the starter is ×0.5 (created if missing).
- The case becomes `solved`, and the verdict is stored, so it's idempotent. Further interviews return 409.

**Effects:**
- **Recall** excludes superseded beliefs, so they can't be retold, and `HEAR` requires an active speaker belief, so a debunked rumor **can't spread again** even if repeated.
- It adds memory lines: "I used to believe that …, but X's inquiry found Y started it and nobody saw it" / "…showed it was a garbled version of what really happened."
- `scripts/investigate.py` publishes the verdict when its leads run out.

**❌ → ✅ Claim-key bug, found by the verdict tests:**
- "Kai lost Bram's hammer somewhere" and "Kai tried to fence a stolen hammer" both got the key `p:9|did|` and were **merged into one claim**. So Pip appeared as a starter of Mara's rumor and lost trust unfairly.
- **Fix:** generic claims are keyed by their normalized text; paraphrases merge by meaning. Regression test added.
- ⚠️ The live world still contains claims merged under the old keys, so **reset the village before recording**.

**New filter:** questions ("…bicycle?") and lowercase fragments ("does that mean…") are dropped as "not a statement", seen in Gopal's live memories.

**Tests:** 103 pass. `tests/test_verdict.py` has 7 cases:
- truth vs lie vs garbling
- publishing supersedes without deleting, and the truth is untouched
- **only the liar loses trust:** Tom→Mara 0.3 → 0.15; Tom→Pip unchanged
- villagers remember the correction
- a debunked rumor can't spread again
- the verdict is final
- the endpoint

**Live** (`case_hammer_demo`, Anjali):
- ✅ the theft (Ramesh saw it)
- ❌ Lakshmi's two "iron artifacts" stories
- ❌ "Ramesh stole tools from the forge", started by Ramesh. That's a **mis-extraction** from earlier chatter, which unfairly cost Ramesh some trust.
- 〰 Ramesh's two garbled Kabir retellings
- **22 beliefs marked outdated**; trust lowered in Lakshmi and Ramesh.
- Gopal's recall now says "I don't fully trust Lakshmi… I used to believe that Ramesh stole two valuable iron artifacts from Lakshmi's cart, but Inspector Anjali's inquiry found Lakshmi started it and nobody saw it." His topic switched to the true theft.

**✅ 4.7 The investigator in AI Town** [AI]

**Design:**
- The investigator is a **human-type player** steered by `scripts/investigate.py --in-town` through the Convex HTTP API.
- **Both sides of each interview are posted from the case file**, so the screen matches the graph word for word.
- The villager's own LLM stays quiet in investigator conversations (an earlier replay showed it garbling a witness's account).

**AI Town changes** (`world/`):
- New `convex/gossipGraph.ts`: `join`, `moveTo`, `invite` (`startConversation`), `say` (a message plus `finishSendingMessage`, as either participant), `leaveConversation`. All require `INVESTIGATOR_SECRET`, which is set in the Convex env and stored in gitignored `world/.env.local`. Investigators join with token `investigator:<name>` (`INVESTIGATOR_TOKEN_PREFIX` in `constants.ts`).
- `agent.ts`: villagers never invite investigators, and they **stay quiet** while talking with one. They still accept the invite and walk over.
- `memory.ts`: conversations with an investigator are **not** sent for ingest, since the case endpoint already recorded the interview. It checks `players` and `archivedPlayers` tokens.
- **Upstream bug found:** a human's `lastInput` was set at join and **never refreshed**, so every human was removed after 5 minutes (`HUMAN_IDLE_TOO_LONG`) regardless of activity. Now `moveTo`, `startConversation` and `finishSendingMessage` refresh it. Side effect, useful for the demo: a "crashed" investigator stands frozen, then disappears after 5 minutes.
- ❌ → ✅ My regex patch of `agent.ts`'s import produced `, INVESTIGATOR_TOKEN_PREFIX } from` on its own line. esbuild rejected the deploy (nothing broken went live). Fixed by hand.
- Deploy `--typecheck enable` ✅; AI Town tests 53/53 ✅

**Script** (`scripts/investigate.py --in-town [--character fN] [--line-pause S]`):
- `Town` client: join (reusing the player if already joined), `meet`, `say`, `leave`.
- `meet` walks next to the villager (`moveTo`), waits while they're busy, invites, and waits until both are `participating`.
- The planner now picks the lead itself and calls `interview?target=…`, so the walk happens before the interview.
- Chrome was disconnected, so a CLI heartbeat loop kept the world alive.

**Live:**
- **Vikram** joined as `p:2990`, walked to Gopal, and the conversation started. The interview lines were posted (`c:3145`: Vikram's question; Gopal: "Ramesh told me that Kabir stole a silver hammer from Ramesh.") Then 💥 the crash.
- Gopal's earlier belief in Lakshmi's rumor was debunked, so it no longer appears.
- **Verified:** the AI Town messages equal the case transcript; 0 town conversations with the investigator were ingested into the graph; the case recorded the interview once.
**Anjali takes over in town:**
- **Run 1:** she joined as `p:3240`, walked to **Ramesh** ("I saw it with my own eyes…") and to **Lakshmi** (new lead: Sarla).
- ❌ Then she **crashed for real**: `TimeoutError: could not meet p:14`. Sarla was stuck in a long NPC conversation (the CPU LLM makes these last minutes).
- **Fix:** `meet` gives up after 90 s, and the investigator **postpones** that villager and interviews the next lead first. After 2 failed attempts it interviews them without walking over ("leaves them a note"), so a busy villager never stops the case.
- **Run 2, same player, resumed from the case file:**
  1. Sarla busy ⏳, then Pandit Shastri busy ⏳
  2. **Sarla interviewed in town**
  3. Pandit Shastri busy again, so a note instead
  4. ✅ verdict published: theft confirmed (Ramesh saw it), 9 beliefs marked outdated

**❌ → ✅ Two verdict judgement flaws seen in run 2:**
1. "**Balwant concluded Kabir was involved in the theft…**" (started by Lakshmi) was ruled *unfounded* and cost Lakshmi trust, although it **agrees with the truth**. The distortion check required the same subject.
   - **Fix:** a near retelling also counts if its text **names the confirmed claim's subject**. `NEAREST_CONFIRMED` now compares against all confirmed claims and returns subject equality and name. Test added.
2. "**Perhaps Balwant noticed anything unusual…**" (speculation) cost Pandit Shastri trust.
   - **Fix:** the not-a-statement filter now also drops "perhaps / maybe / possibly / might". Test added.
- My first patch script for these aborted halfway: the regex anchor didn't match because of my backslash escaping, which left `cases.py` calling a not-yet-renamed helper. Caught immediately and finished with direct edits.

**Tests:** 104 pass. AI Town: 53/53.

**Note:** pipe or redirect the script's output through `python -u` when following it live (it's buffered otherwise).

---

### Oct 17 — Why the town feels laggy (measurement)

**Question** [me]: the simulation feels laggy. Should we switch to, or borrow from, Stanford's Smallville (`joonspk-research/generative_agents`)?

**Smallville vs AI Town** [AI]:
- Smallville is **turn-based**: each step is 10 game-seconds, and every agent makes several LLM calls per step (perceive, plan, react, reflect, talk) before the page moves on. AI Town walks characters without the LLM and only calls it for dialogue. **On our CPU LLM, Smallville would be slower, not faster.**
- It hasn't changed since Aug 2023, it's built on retired OpenAI models, and its memory is JSON files (it would need ripping out, as AI Town's did).
- **Decision:** stay on AI Town. The idea worth borrowing is Smallville's **replay mode** (compute first, play back smoothly), which fits the planned 4.6 replay village and the demo video.

**🔬 Measurement** [AI]: `scripts/llm_timing.py proxy` sits on 127.0.0.1:11435 (the port the apps already use) and forwards to the SSH tunnel moved to 11437, logging every Ollama call with no config changes. A 15-minute run with the current world (8 villagers):

| Calls | n | Median | p90 | Max |
|---|---|---|---|---|
| Dialogue `llama3.2:3b` (AI Town) | 72 | 18.6 s | 31.2 s | 57.3 s |
| Extraction `llama3.1:8b` (memory service, once per conversation) | 8 | 82.7 s | 135.5 s | 135.5 s |
| Embeddings `mxbai-embed-large` | 8 | 0.4 s | 1.0 s | 1.0 s |

- **What the viewer sees:** 72 chat lines in 11 conversations, with a median **19.1 s** gap between lines (p90 33 s, max 53 s). Almost all of it is LLM time; the engine, recall (~2 ms) and the network are negligible.
- **Dialogue line time vs calls already in flight:** 0 → 9.5 s, 1 → 14.0 s, 2 → 24.8 s, 3 → 25.3 s, 4 → 45.6 s.
- **Dialogue while an extraction ran:** median 22.0 s (p90 48.5 s) vs 15.8 s without one.
- **Prompt sizes:** dialogue prompts median **1,020 tokens** in (max 1,339), 63 tokens out (max 211). Extraction prompts 622–1,233 tokens in, ~360 out.

**🔬 CPU benchmark** (world paused; `llama3.2:3b`, an 866-token prompt, 64 tokens out, native `/api/chat`):

| Threads | Reading the prompt | Writing the reply | Total |
|---|---|---|---|
| default (= 8) | 4.8 s (180 tok/s) | 3.0 s (21.6 tok/s) | 8.0 s |
| 16 | 3.7 s (240 tok/s) | 2.3 s (28 tok/s) | 6.1 s |
| 24 | 3.3 s (262 tok/s) | 2.2 s (29 tok/s) | **5.8 s** |

- **Two requests at once run strictly one after the other** (8 s, then 16.6 s). The Ubuntu Ollama serves one request at a time, so with 3–4 conversations going, each line waits behind the others, and an 83 s extraction blocks every conversation.

**Findings:**
1. **The queue is the main cause:** one model call at a time, with several conversations plus extraction sharing it.
2. **~60% of each dialogue call is reading the ~1,000-token prompt,** not writing the reply.
3. **24 threads is ~28% faster** than Ollama's default 8 on the i9-13900K.

**Decision** [me]: apply the thread and concurrency fixes, but **keep the full prompt**. Less context would make the villagers' lines less grounded in what they remember.

**🔬 Thread split with both models running at once** (world paused; a dialogue line while a 200-token extraction runs):

| Threads (dialogue / extraction) | Dialogue alone | Dialogue during extraction | Extraction |
|---|---|---|---|
| 8 / 8 (default) | 8.7 s | 16.0 s, 10.4 s | 24.3 s |
| **24 / 8** | **6.1 s** | **9.0 s, 8.6 s** | 26.0 s |
| 16 / 16 | 6.6 s | 16.1 s, 7.9 s | 21.8 s |
| 24 / 24 | 6.1 s | ❌ **135.2 s**, 11.0 s | 143.9 s |
| 16 / 8 | 6.8 s | 8.8 s, 8.9 s | 25.7 s |

- The two models run as separate processes on the same CPU. 24 + 24 threads on 32 logical CPUs oversubscribes it, and both crawl.

**✅ Fix A** [AI]:
- **Dialogue model with 24 threads:** `scripts/ollama-models.sh` creates `llama3.2:3b-t24` (`llama3.2:3b` plus `num_thread 24`). AI Town calls the OpenAI-compatible endpoint, which can't pass options, so a model variant is the way to set it. Convex env `OLLAMA_MODEL=llama3.2:3b-t24`.
- **Extraction pinned to 8 threads:** `EXTRACT_THREADS` (default 8) in `memory/config.py`, passed by `memory/llm.py`. This keeps the total at 32.
- **At most 2 villager conversations at once:** `MAX_NPC_CONVERSATIONS = 2` (`world/convex/constants.ts`).
  - Checked inside the engine's `finishDoSomething` input, so it's race-free. At the cap, an agent keeps walking and retries after the usual cooldown.
  - Investigator interviews don't count, since the villager's LLM stays quiet in them (`aiTown/conversationLimit.ts`, plus 3 jest tests).
- **Tests:** pytest 104 pass (+2 opt-in live). AI Town 56/56 with `npm test`.
  - ⚠️ Running bare `npx jest` caches the wrong module format and breaks every suite; clear the cache and use `npm test`.

**Before vs after** (15 minutes each, same world):

| | Before | After |
|---|---|---|
| **Gap between chat lines (what you see)** | median **19.1 s**, p90 33.1 s, max 53.4 s | median **12.0 s**, p90 16.9 s, max 19.3 s |
| Dialogue call | median 18.6 s, p90 31.2 s, max 57.3 s | median 9.8 s, p90 14.6 s, max 24.5 s |
| Chat lines per 15 min | 72 (11 conversations) | 70 (10 conversations) |
| Extraction | median 82.7 s | median 87.3 s (still in the background) |

- **The lag is about 40% shorter, and the worst stalls are gone** (53 s → 19 s).
- **The number of lines per minute is unchanged,** so gossip spreads as fast as before. The CPU did the same amount of work; it was just queued less.

**✅ Whole map viewable** [me asked whether the town showed the full map; AI checked]:
- **It didn't.** The map is 64 × 48 tiles (2,048 × 1,536 px), but upstream's zoom-out limit (`PixiViewport.tsx`: `minScale = 1.04 × screenWidth / (worldWidth / 2)`) showed at most about half its width. The default view showed only the top-left corner (tents and the waterfall).
- **Fix** (page only, no backend change): the zoom-out limit is now "the whole town fits" (`min(screenWidth / worldWidth, screenHeight / worldHeight)`). It's the same map drawn smaller and never stretched. The page still opens at upstream's zoom; scroll or pinch out to see the whole town.
- Checked in Chrome: zoomed fully out, the whole town is visible (both tents, the waterfall and river, the three windmills, the pond). `tsc` is clean.

---

### Oct 17 — 4.6 Separate villages: template copy

**Choice** [me, after AI explained both options]: copy a village template rather than replay recorded conversations into a new village. A template copy gives the same people and relationships with no history, needs no LLM, and is ready instantly. Replay gives the copy a history but costs ~85 s of extraction per conversation on the live town's CPU. Replay can be added on top later.

**🔬 Checked first on a throwaway graph** [AI]:
- `GRAPH.COPY` took 6 ms and kept all 9 indexes, including the 1024-d vector index.
- The copy is independent: a node written to it doesn't appear in the source.
- Copying onto an existing graph fails (`destination key already exists`), so a live village can't be overwritten by accident.

**✅ Built** [AI]:
- **`memory/templates.py`:** `create` (replaces an older template) and `start_world` (`GRAPH.COPY`).
- **`memory/db.py`:** a `template_` prefix, so templates never appear as worlds (the retry loop and `/worlds` ignore them). The schema helpers now work on any graph. `delete_world` also forgets the "schema ready" cache, so a re-created world gets its indexes again.
- **Endpoints:** `POST /templates/{name}`, `GET /templates`, `POST /worlds/{id}/from-template/{name}` (404 if the template is missing, 409 if the world exists), `DELETE /worlds/{id}`.
- **Counts use three separate queries,** avoiding the OPTIONAL-MATCH-after-aggregation quirk (step 2.4).
- **`scripts/background_village.py [--world chandanpur_b] [--fresh] [--good-deed]`:**
  1. Builds `template_chandanpur` from `village/chandanpur.json`, mapped to the live world's player ids, so each person has the same id in every village. `seed_village.py`'s mapping is now the shared `village_payload`.
  2. Copies the template into the background village.
  3. Optionally narrates an event that happens only there.
  4. Asks every villager, in both villages, what they think of Kabir.
- **Tests:** `tests/test_templates.py`, 6 cases:
  - template contents and schema
  - an exact copy
  - a theft in world A is invisible in world B and in the template
  - no overwrite (409)
  - delete and start again
  - bad requests
- **pytest:** 110 pass (+2 opt-in live).

**Live** (template from the live world `m171…`):
- `template_chandanpur`: 9 characters, 24 trust links, 24 friendships. `world_chandanpur_b` was copied in **6.4 ms**.
- **Every villager:** in the live village, Kabir's reputation ranges from −0.9 (Gopal, 2 beliefs) to −6.1 (Chotu, 13 beliefs), and the top belief is "Kabir stole a silver hammer". In `chandanpur_b`, every villager has **never heard of him**.
- **With `--good-deed`** (narrated only in `chandanpur_b`: "Kabir helped Pandit Shastri carry the new temple bell up the hill"):
  - Pandit Shastri: **+0.7** in the copy vs **−1.6** in the live village.
  - Same person, same id, opposite reputations.
- ✅ No belief about Kabir appears in both villages. The template still has 0 events, claims or beliefs.

**❌ → ✅ Tunnel dropped:**
- The first `--good-deed` run got a 502. The SSH tunnel had died at 10:23 IST, although the Mac stayed awake under `caffeinate`, so the town was also silent until it was reopened.
- The Ubuntu box answered pings at ~150 ms, which suggests a flaky Wi-Fi link.
- I had started the tunnel with `start`, not `watch`. It now runs in `watch` mode, which reopens it within 20 s.

---

### Oct 17 — Phase 4 review checkpoint

**✅ Done** [AI]+[me]. A plain-language recap was given in chat and added to `docs/WALKTHROUGH.md` as a Phase 4 section:
- the idea (an investigator who knows nothing; minds stay private)
- the structure-only briefing
- interviews that follow the trail upstream
- crash and resume through the case file
- verdict and debunking (never deleting)
- the investigator in the town
- separate villages
- the bugs fixed
- the known extraction limit

---

### Oct 17 — Phase 5: make the graph visible

**Layout decision** [me chose option A of two offered by AI]: a **separate memory page** served by the memory service, opened next to the town. The alternative was panels inside AI Town's 384 px sidebar (about 6–8 h, deeper React changes, CORS). The separate page took about 4–5 h, leaves the town untouched, and maps each panel to Cypher queries we can show in the README.

**✅ 5.1 Live graph panel** [AI]
- **`GET /worlds/{id}/graph[?since=ms]`** (`memory/view.py`):
  - characters with role (villager / outsider / investigator), active beliefs, and how many claims are about them
  - `FRIEND` edges, and `LEARNED_FROM` news flow (drawn speaker → listener, with a count)
  - totals: active and outdated beliefs, claims, ingested conversations
  - the beliefs formed since `since`, newest first, each with who it came from and the exact line heard (the same query shape as `scripts/live_feed.py`)
- **Filtered out:** humans who hold no beliefs and aren't talked about, such as a visitor's town avatar.
- **`GET /ui`** serves `memory/ui/index.html`: one page with vis-network 9.1.9 from unpkg and no build step. It polls every 3 s.
  - **Map:** circle size = how much a villager believes. Only `FRIEND` edges drive the layout, so the market circle, the temple circle and Gopal the bridge show up as shapes. News arrows show each listener's top 2 sources, because after hours of talk the full `LEARNED_FROM` graph (64 edges among 8 villagers) is a hairball. The layout is fixed with a seed, settles, then holds still.
  - **Live feed:** "👂 Chotu heard it from Gopal: … 54%", with the quoted line, colored by valence; outdated beliefs are struck through.
  - **Each new belief flashes** its speaker → listener link and the listener's circle.
  - **Village dropdown:** AI Town worlds, `chandanpur_b`, and others; `test_` graphs are hidden.
- **AI Town:** a **Memory** button in the footer (`MemoryButton.tsx`, a pixel icon `assets/memory.svg`) opens `/ui?world=<current world>` in a new tab. `Button.tsx` gained an optional `target`.
- **Tests:** `tests/test_view.py`, 4 cases:
  - map roles and news flow
  - the feed says who heard what from whom, with the exact line, and `since` returns only what's new
  - silent strangers stay off the map
  - 404, and the page is served with `no-store`
- **Results:** pytest 114 pass (+2 opt-in live); AI Town 56/56.

**Checked in Chrome:**
- The live world draws 14 characters (including leftover duplicate investigator nodes, to be removed by the reset).
- `chandanpur_b` shows the clean seeded structure and the single "Kabir helped Pandit Shastri" belief.
- Replaying the last 6 beliefs as new showed the flashes and feed animation working. No console errors.

**❌ → ✅ Fixes while building:**
- The browser kept serving the old page after edits, so `/ui` now sends `Cache-Control: no-store`.
- The first layout was a hairball where every edge pulled on the nodes. Now only friendships do, and news arrows are limited to each listener's top 2 sources.
- The view was cut off at the edges, so it's now fitted after layout.
- The dropdown labelled the copied village "(live town)". Labels now come from the id format: Convex ids are 32 lowercase letters and digits.

**✅ 5.2 "Why do you think that?"** [AI]
- **No new backend.** The page calls the existing `GET /explain?holder=` (Q4). It takes 66 ms for Ramesh's 214 beliefs (140 KB) and 6 ms for one claim.
- **Click a villager** on the map (or any line in the live feed) to open their panel: role, number of active beliefs, gullibility, and their beliefs sorted by |valence| × confidence, with a text filter. Each belief shows how they know it (saw it / heard it / said it first) and whether it traces to an eyewitness.
- **Click a belief** to see the villager's answer, word for word from the graph path (`explain.sentence`), for example Gopal: *"Ramesh told me. Ramesh heard it from Pandit Shastri. Pandit Shastri started it, and nobody saw it happen."*
  - A badge: ✓ traced to an eyewitness (and "it really happened" if grounded in an event), or ✗ nobody saw it, X started it.
  - Each hop, with the exact line heard.
  - **On the map:** the trail lights up, with arrows from speaker to listener. The strongest path is bright and others are thinner. Everyone else dims, and the person the claim is about is lit. People on the strongest trail show their confidence next to their name (**Pandit Shastri · 60% → Ramesh · 30% → Gopal · 21%**), so you can see doubt growing with each retelling.
- **❌ → ✅ Fixes:**
  - The confidence labels on the arrows were hidden under circles (vis-network draws nodes over edge labels), so they moved onto the names.
  - The percentage ran into the text in the belief list, because the feed's styles were scoped to the feed only.
  - A belief opened from the feed could fall outside the top 80 shown, or below the visible edge. It's now always listed and scrolled to the centre.
- **Checked in Chrome** with real clicks: on Gopal, on a filtered belief ("bribes"), and on a feed line (Sarla: "Lakshmi told me. Lakshmi started it, and nobody saw it happen."). No console errors. pytest 114 pass.

**✅ 5.3 Insights panel** [AI]
- **`GET /worlds/{id}/insights`** (`memory/view.py`), 10–15 ms on the live world:
  - **Structure:** the investigator's briefing (`cases.briefing`), computed live. Bridges come from `algo.betweenness` on `FRIEND`; news hubs from `algo.pageRank` on `LEARNED_FROM`, or on trust before any gossip; circles are the friend groups once the top bridge is removed. The summary sentences are included, minus "Suggested first interviews".
  - **Reputation:** for each person, what the village believes about them. Each villager's opinion is the **average** of confidence × valence over their active beliefs about that person (−1 to +1). The village's view averages the villagers who have one, with counts of who thinks badly or well, plus the most widely believed claim about them. Investigators' notes are excluded.
- **❌ → ✅ Sum vs average:** the first version summed each villager's beliefs (the same score as recall's personal impression). On the live world everyone came out "very bad", and **Ramesh (−7.5) looked worse than Kabir (−3.6)**, only because people talk about Ramesh more. With averages, **Kabir is the worst real person (−0.30, 7 of 8 villagers think badly)**, and the top-ranked "Me" is a leftover junk character the reset removes. `recall._reputation_words` became the public `reputation_words`.
- **Page:** the side panel now has **tabs (Live feed | Insights)**. The Insights tab refreshes every 10 s while open. **Clicking any row** (a bridge, a hub, a circle, a reputation entry) lights those people up on the map; clicking again clears it. A footnote names the FalkorDB algorithms used.
- **❌ → ✅ Map fixes found while testing:**
  - The map never froze or fitted. vis-network's `stabilizationIterationsDone` only fires for data present at construction, so I now use `stabilized`, which also fits again on resize.
  - After switching village, everyone was piled in the centre: the layout "settled" on the empty map just before the new nodes arrived. Physics now restarts only when a village's first nodes are drawn.
- **Checked in Chrome:**
  - Live world: Gopal is bridge 24, Lakshmi 13. The circles {Ramesh, Sarla, Chotu, Lakshmi} and {Meera, Balwant, Pandit Shastri}. Clicking Circle 2 lights its members.
  - `chandanpur_b`: Kabir "very good · 1 well · most believed: Kabir helped Pandit Shastri carry the new temple bell". Hubs fall back to trust, since no gossip has flowed there.
  - No console errors.
- **Tests:** `tests/test_view.py` gained 4 cases: structure, reputation (Kai: 4 of 4 think badly), investigators excluded, 404. pytest **118 pass** (+2 opt-in live).

**✅ 5.4 Case board** [AI]
- **Backend:**
  - `GET /worlds/{id}/cases` (`cases.list_cases`) lists every case, newest first, with whoever is on it now.
  - Interviews in the case file now carry `participant_ids`, so the map knows who interviewed whom.
  - Everything else comes from the existing case file (`GET /cases/{case}`).
- **Page: a third tab, Case.** It shows the newest case by default, with a picker when there are several. It refreshes every 3 s and only re-renders when the file changed, which keeps the scroll position.
  - title, question, an open/solved badge
  - the team: "Inspector Vikram (left the case) → Inspector Anjali (on the case)"
  - the structure-only briefing
  - leads: ✓ done / ○ open, with kind (news hub, bridge, circle voice, named as a source, chosen) and reason
  - interviews: "2. Inspector Vikram → Ramesh", with each testimony line (👁 / 👂 / 🗣)
  - verdict: ✅ true / ✗ made up / 〰 garbled / ? unresolved, plus beliefs marked outdated and trust lowered
- **Map while the Case tab is open:** dashed blue arrows from each investigator to the villagers they interviewed, with everyone outside the case dimmed. Clicking a lead or interview lights that person up.
- **Live end-to-end check in Chrome** on a throwaway template copy (`ui_check`, deleted afterwards), with the page left open the whole time and **no reload**:
  1. The empty state: "No investigation in this village yet".
  2. A case was opened. Interviews with Gopal ("I haven't heard anything about that") and Ramesh ("I saw it with my own eyes") appeared within one poll.
  3. **Assigned to Anjali:** the team line switched to "left the case → on the case", and her interview was added as #3.
  4. The verdict appeared: "✅ True: Kabir stole a silver hammer from Ramesh. Ramesh saw it."

  No console errors. On the live world's `case_hammer_demo`, the full Vikram → Anjali story and the verdict (1 true, 3 made up, 2 garbled, 22 beliefs outdated, trust lowered in Lakshmi and Ramesh) render correctly.
- **❌ → ✅ Fixes:**
  - An investigator who joined after the layout froze was dropped exactly on top of the previous one. The layout now restarts briefly whenever someone new appears.
  - Claims without a final period ran into the verdict text ("…anvil Started by").
- **Tests:** `tests/test_view.py` gained 2 cases: the case list with its investigator and interview participants, and no cases in a new world. pytest **120 pass** (+2 opt-in live).

**Phase 5 complete:** live map and feed, "why do you think that?", insights, and the case board, all on one memory page next to the town.

---

### Oct 17 — Village reset and demo rehearsal

**✅ Reset** [AI] (16:03–16:06 IST):
1. `testing:stop`, then `testing:wipeAllTables`. Every AI Town table was emptied and checked.
2. `npx convex dev --once --typecheck enable`.
3. `npx convex run init`, which created the new world **`m170ny8390cy9829q4br4bf9vd8gffbm`**.
4. `seed_village.py`: 9 characters, 24 trust links.
- **AI Town assigned the same player ids as before** (`p:0` Ramesh … `p:14` Sarla), so ids are deterministic for the same `characters.ts`.
- The old graph `world_m171…` was **kept, not deleted**: it's a separate, inactive world now.
- `background_village.py --fresh --good-deed` rebuilt `template_chandanpur` from the new world and re-copied `chandanpur_b` (10.1 ms). Isolation check ✅.
- **The new graph starts clean:** 0 beliefs, only the 8 villagers. The duplicate inspector nodes, "Me" and the pre-filter junk are gone.

**Rehearsal:**
- The first 2 conversations were ingested about 9 minutes after init. Villagers wander, invite, walk over, and talk for 8 lines before extraction (~73 s) runs.
- **16:15:03:** the narrator recorded the theft (`e_3e085b9652ec`, claim `k_7f76a6656372`, "Kabir stole a silver hammer from Ramesh"). Ramesh is the only witness.

**🔬 Rehearsal results** (live, new world):

| Time (IST) | What happened |
|---|---|
| 16:15:02 | Ramesh **saw** it (100%) |
| 16:17:08 | Meera heard it from Ramesh (35%, gullibility 0.35): straight into the temple circle |
| 16:19:25 | Gopal heard it from Ramesh (70%) |
| 16:19:30 | Chotu heard it from Meera (32%), two hops |
| 16:35:23 | Balwant heard it from **Gopal** (35%): the bridge carried it into the temple circle, two hops |

- 5 believers 19 minutes after the theft. 15 conversations and 114 beliefs in the graph by 16:38.
- **Investigator in town:**
  - Vikram (`p:1411`): briefing (hubs Ramesh and Chotu, bridge Gopal), then interview 1 **Ramesh** ("I saw it with my own eyes"), interview 2 **Gopal** ("Ramesh told me"), then 💥 crash (exit 1). About 1.5 min.
  - Anjali (`p:1498`, sprite f3): read the handoff (Vikram's 2 interviews, findings, next lead Meera), interviewed **Meera** ("Ramesh told me"), then published the verdict. About 1 min.
  - ✅ The theft was confirmed (Ramesh saw it). No interview was repeated.
- **❌ Problem found: self-gossip junk punished the eyewitness.** Ramesh also "testified" two claims extracted as said by Ramesh about Ramesh: "Ramesh knows everything that goes on in Chandanpur" and "Ramesh stole something from his own forge again". The verdict ruled both *unfounded, started by Ramesh*, so **trust in Ramesh was lowered**, although he is the honest eyewitness. This is the same class of mis-extraction as the old world's "Ramesh stole tools from the forge". Cause: `_validate` has no rule against a speaker being the subject of their own gossip; the 3B/8B extraction misreads reported speech and chatter.
- **Investigation depth:** it took only 3 interviews. Ramesh, the source, was also the top news hub, so the briefing sent Vikram straight to the eyewitness. Believers further downstream (Balwant, Chotu) weren't interviewed, because the investigator follows sources upstream, not listeners downstream.
- **Timing for the recording:** reset 3 min, first gossip 9 min, 5 believers 19 min after the theft, investigation about 2.5 min. **A full demo run takes about 35 minutes.**

**✅ Fix: no self-gossip** [AI, approved by me]
- `ingest._validate` now drops any extracted claim whose subject is the person saying it (reason "speaker is the subject"). This is separate from "no self-adoption": that rule stops a listener adopting a claim about themselves, while this one stops the claim being created at all.
- Regression test `test_nobody_starts_gossip_about_themselves`: the rehearsal's "Bram stole something from his own forge again", said by Bram, is dropped, while the theft claim in the same line is kept. pytest **121 pass**.
- The rehearsal world keeps the claims made before the fix. The recording run starts from a fresh reset anyway.

---

### Oct 17 — Phase 6: submission

**✅ 6.2 README** [AI, reviewed by me]
- **`README.md`**, written for the judges:
  - the story in one minute
  - why the graph is essential (AI Town's vector memory deleted; "graph is the brain, LLM is the mouth")
  - an architecture diagram and table, and the data-model diagram
  - **"How the graph does the work":** 7 mechanisms, with the key Cypher copied from the code: hearing with trust and noisy-OR plus the echo and repeat guards, recall ranking and topic, `HEARD_FROM*0..8` provenance, `algo.betweenness` / `algo.pageRank` with the circles method stated honestly, the vector index for dedup and testimony, the non-deleting verdict, and `GRAPH.COPY`
  - the Track 2 coverage table, the memory page, results with measured numbers, setup and demo commands, limitations
  - **AI disclosure** (Claude Code as pair programmer; [me]/[AI] tags in this log; runtime models), and credits (AI Town MIT, FalkorDB, vis-network, Llama, mxbai)
- **`docs/QUERIES.md`** is generated by the new `scripts/export_queries.py`, which reads the source with `ast`: all **78** Cypher queries from 8 modules (66 named, the rest inline), each with the comment above it, so the "every Cypher query" requirement can't drift from the code.
- **Stale docs fixed** (found by the doc review at the start of the session):
  - **DATA_MODEL:** the status line; the dropped `Rule` node removed; Q1–Q5 replaced by the current code; Q6 no longer claims label propagation, and states the real circles method; the extraction example no longer shows a `speaker` field that the schema doesn't have; the validation list is complete; the Track 2 table now shows the case file for handoffs and adds memory corrections (no `Task`, no procedural memory); 4 more FalkorDB gotchas.
  - **WALKTHROUGH:** the explain query's stopping rule, and the test count now dated.
  - **PLAN:** `nomic-embed-text` corrected to `mxbai-embed-large`; circles no longer attributed to label propagation.
- Both README Mermaid diagrams were checked by rendering them with mermaid 10.9.1 in Chrome: they parse.

---

## Open questions

- ✅ ~~4.6 scope~~ → `GRAPH.COPY` template village (Oct 17). Replay could be added on top.
- ✅ ~~Phase 5 form~~ → a separate memory page (`/ui`) next to the town (Oct 17).
- 💡 **Report upstream to FalkorDB (optional):**
  - (a) An OPTIONAL MATCH after `OPTIONAL MATCH … WITH <aggregation>` silently matched nothing (step 2.4).
  - (b) `algo.labelPropagation` grouped unconnected nodes on the village graph (step 3.2).
- ⚠️ **Extraction quality** is the weakest link: reported speech makes the reporter the subject, and junk slips through. The filters help; the investigator and verdict make the noise visible instead of hiding it.
- ⚠️ **The Ubuntu CPU LLM is the throughput bottleneck** with 8 NPCs (3B lines take 4–32 s depending on load). For recording, consider fewer simultaneous conversations, or Groq's free tier for dialogue.
- ✅ ~~Base world~~ → AI Town (GO on Oct 16). ✅ ~~LLM provider~~ → Ollama on the Ubuntu box.
