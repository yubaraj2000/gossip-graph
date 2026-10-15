# Project Plan — NPC Graph Memory (Graph Hacks, Track 2)

**Goal:** NPCs whose memories, gossip, trust and reputation live in a FalkorDB graph. NPCs remember across sessions, share what they know with each other, and can explain where every belief came from.

**Principle:** the graph is the brain, and the LLM is the mouth. Every NPC belief is a node in FalkorDB. The LLM only turns graph results into dialogue and extracts facts from conversations. If FalkorDB is removed, the NPCs know nothing (rule 3).

**Deadline:** Oct 18, 23:59 IST. **Target submission:** Oct 18, 21:00 IST, which leaves a 3-hour buffer.

**Working agreement:**
- Each phase needs your approval before it starts.
- Inside a phase, Claude does one step at a time and reports back before the next one.
- Every step's result goes into `RESEARCH_LOG.md`.
- At the end of each phase there is a **review checkpoint**: Claude walks you through the code and queries, so you can explain them to the judges (rule 12).
- **Git is yours [me].** Claude never runs git commands. After each step Claude gives you the exact commands and the commit message, and you run them.

**Architecture (if AI Town passes the Phase 1 test):**

```
Browser ──► AI Town (pixel world: NPCs walk and talk)      [open-source base, MIT, credited]
               │  3 hooks: 2× read memory, 1× save memory
               ▼
            Graph-memory service (Python, FastAPI)       [our original work]
               │  Cypher
               ▼
            FalkorDB on the Mac (Docker, persistent)        one graph per world
            Ollama on the Ubuntu box (via SSH tunnel)       llama3.2:3b chatter, llama3.1:8b extraction
```

---

## Phase 0 — Foundations (mostly done)

- [x] Read the hackathon rules and FAQ, and pick Track 2
- [x] FalkorDB in Docker with persistence and sane timeouts (`docker-compose.yml`)
- [x] Python 3.12 environment with `uv`
- [x] Study the FalkorDB repos, Graphify and AI Town (`reference/`)
- [x] Prove the gossip, provenance and reputation queries work (NPC prototype)
- [x] Ollama on the Ubuntu box: benchmarked and reachable through an SSH tunnel
- [x] Record book (`RESEARCH_LOG.md`)
- [ ] **0.1** [me] Set your git identity, run `git init`, and make the first commits (Claude provides the commands and messages). Commit timestamps prove the work was done during the event (rule 8).
- [ ] **0.2** [me] Create an empty **public** GitHub repo, add the Mac's SSH key to your GitHub account, and push.

**Done when:** the repo is on GitHub with the current files.

---

## Phase 1 — Feasibility test: AI Town (timebox: 2 hours)

- [ ] **1.1** Copy AI Town into the project as `world/`, with credit and its MIT license kept.
- [ ] **1.2** Start AI Town's self-hosted Convex backend in Docker on the Mac, and generate its admin key.
- [ ] **1.3** Open a persistent SSH tunnel to Ubuntu's Ollama on port 11435, and check that Convex can reach it from inside Docker.
- [ ] **1.4** Run the town with `llama3.2:3b` and `nomic-embed-text`, and watch NPCs talk to each other.
- [ ] **1.5** Measure how fast the NPCs chat, and how much memory the Mac uses.

**Go/no-go decision (you decide):**
- ✅ **Go** if the town runs in the browser and NPCs hold conversations within the 2 hours. Continue to Phase 2.
- ❌ **No-go** if it doesn't. Switch to **Plan B**: a small Python village from scratch, with a simple web UI and the FalkorDB Browser for the graph view. Phases 2, 4, 5 and 6 stay the same; Phase 3 becomes "build the village".

---

## Phase 2 — Graph data model and memory service (core original work)

- [ ] **2.1** Design the graph model and write it up in `docs/DATA_MODEL.md`. It is needed for the README.
  - Nodes: `NPC`, `Player`, `Location`, `Event`, `Conversation`, `Message`, `Belief`, `Task`
  - Relationships: `KNOWS {trust}`, `HELD_BY`, `ABOUT`, `FROM`, `WITNESSED`, `PARTICIPATED_IN`
  - Time fields on beliefs so they can be marked outdated instead of deleted
- [ ] **2.2** Create the Python service (`memory/`, FastAPI): config, FalkorDB client, one graph per world (`world_<id>`).
- [ ] **2.3** **Ingest**: take a finished conversation and use `llama3.1:8b` with a JSON schema to extract claims ("who said what about whom"). Turn them into `Belief` nodes that record their source and trust.
- [ ] **2.4** **Recall**: given an NPC and the person they're talking to, return the beliefs about that person with confidence and source, shared past episodes, and a reputation score.
- [ ] **2.5** **Explain**: return the provenance path for any belief ("who told you that?").
- [ ] **2.6** Tests: a scripted scenario must reproduce the prototype results (the Bram → Pip → Mara chain, grudge scores).

**Done when:** the tests pass and every endpoint works with `curl`. **Review checkpoint.**

---

## Phase 3 — Connect the world to the graph

- [ ] **3.1** Replace AI Town's memory (`convex/agent/memory.ts` plus its 3 call sites) with calls to our service, and **delete its vector memory** so FalkorDB is essential.
- [ ] **3.2** Replace the default characters with our village: 8–10 NPCs with roles, a who-knows-whom network, and trust values.
- [ ] **3.3** A "narrator" endpoint to inject an event (e.g. "Kai stole from Bram", witnessed by Bram).
- [ ] **3.4** End-to-end check: inject the theft, let NPCs talk, ask Mara "who told you?", and confirm the chain is correct.

**Done when:** a rumor spreads through real NPC conversations and the explanation is correct. **Review checkpoint.**

---

## Phase 4 — Track 2 depth (ordered by value; cut from the bottom if behind)

- [ ] **4.1 Memory updates:** a new event ("Kai returned the item") marks old beliefs outdated instead of deleting them, and NPCs say "I heard you stole, but also that you made it right."
- [ ] **4.2 Graph algorithms as gameplay:**
  - betweenness finds the "bridge" gossips
  - PageRank on `HEARS_FROM` finds the influencers
  - label propagation finds the cliques

  These go in an Insights endpoint, plus the "bribe the bridge and the rumor stops" demo.
- [ ] **4.3 Separate worlds and concurrency:** create a world by cloning a template village with `GRAPH.COPY`, run 2 worlds at once, and use a load script to show parallel writes.
- [ ] **4.4 Agent coordination and handoff:** the guard captain creates a `Task` ("investigate the theft") in the graph, and a guard NPC picks it up and reports back.
- [ ] **4.5 Procedural memory (stretch):** NPCs learn behavior rules from events (e.g. the merchant raises prices above a grudge threshold).

**Done when:** at least 4.1–4.3 work. **Review checkpoint.**

---

## Phase 5 — Make the graph visible (for the demo)

- [ ] **5.1** A graph panel next to the town showing beliefs appearing as gossip spreads (or the FalkorDB Browser if time is short).
- [ ] **5.2** "Why do you think that?" highlights the provenance path.
- [ ] **5.3** An Insights panel: bridges, influencers, cliques, reputation per NPC.

---

## Phase 6 — Submission (feature freeze: Oct 18, 14:00 IST)

- [ ] **6.1** One-command local setup (`docker compose`), plus instructions for Ollama.
- [ ] **6.2** README:
  - what it is and the architecture diagram
  - **graph data model**
  - **every Cypher query and algorithm used**
  - setup steps
  - credit to AI Town
  - **AI-assistant disclosure**
  - track: Agent Memory and Coordination
- [ ] **6.3** Demo video (about 3 minutes, script first): theft, then gossip spreading on the graph, "who told you?", bribing the bridge, two worlds side by side.
- [ ] **6.4** [me] Submit on WeMakeDevs with the repo link, video and track.
- [ ] **6.5** Optional: blog post for the AirPods side prize, drafted from `RESEARCH_LOG.md`.

**Live deployment:** the FAQ says a live deployment is preferred, but a working video plus complete local setup steps is acceptable. Ollama runs on a home LAN machine, so we plan for local setup plus video.

---

## Timeline

| When (IST) | Phases |
|---|---|
| Oct 16 morning | Phase 0 wrap-up, then Phase 1 test and the go/no-go decision |
| Oct 16 afternoon and evening | Phase 2 |
| Oct 17 | Phase 3, then Phase 4.1–4.3 |
| Oct 18 until 14:00 | Phase 4 leftovers, Phase 5 → **feature freeze** |
| Oct 18 14:00–21:00 | Phase 6 → **submit** |

## Scope cuts if we fall behind (in this order)

1. Procedural memory (4.5)
2. Agent handoff (4.4)
3. Custom graph panel (5.1–5.3). Use the FalkorDB Browser instead.
4. The two-worlds concurrency demo (4.3). Keep separate worlds, drop the load test.

## Risks

| Risk | Mitigation |
|---|---|
| AI Town or Convex won't run | Hard 2-hour timebox, then Plan B (Python village) |
| CPU-only Ollama is slow | `llama3.2:3b` for chatter, fewer NPCs, slower simulation speed |
| The small model extracts claims badly | `llama3.1:8b` with a strict JSON schema, validation, and tests on fixed transcripts |
| The graph looks like decoration (rule 3) | Delete AI Town's vector memory; every recall goes through Cypher |
| Our original work is unclear to judges | README credits; the research log separates AI Town from our code; git history |
| The tunnel to Ubuntu drops | SSH keep-alive options, and a script to reopen it |
