# How gossip-graph's memory works — Phase 2 walkthrough

A plain-language tour of the memory service (`memory/`), so you can explain every part to the judges.
Read one section at a time; each ends with the files to open alongside it.

---

## 1. The big picture: what happens when two NPCs talk

```
            ┌──────────── before speaking ────────────┐
AI Town ──► GET /recall?me=Mara&other=Tom   (2 ms, no AI)
            ◄── "Pip told me Kai stole Bram's hammer (I believe it)…"
            │
            ▼  NPCs talk — llama3.2:3b writes each line, with those memories in its prompt
            │
            ▼  conversation ends
AI Town ──► POST /conversations   (9–14 s, runs after the talk, nobody waits on it)
            1. store the transcript                       (episodic memory)
            2. llama3.1:8b lists the claims made          (the only AI step)
            3. code checks and cleans every claim
            4. claims → beliefs, each remembering who it came from
            │
anyone ───► GET /explain?holder=Tom   (2 ms, no AI)
            ◄── "Mara told me. Mara heard it from Pip, who heard it from Bram. Bram saw it happen."
```

**The AI is used in exactly two places:** writing dialogue (AI Town) and extracting claims from a finished
conversation (`extract.py`). Everything else — who believes what, how sure, who told whom, reputation, the
"who told you?" answer — is Cypher on FalkorDB. That is why removing FalkorDB breaks the game (rule 3): the
NPCs would have no memory at all.

| File | Job |
|---|---|
| `memory/app.py` | The web API (FastAPI): endpoints, crash recovery at startup, retry loop |
| `memory/ingest.py` | Conversation → claims → beliefs (the biggest piece) |
| `memory/extract.py` | The prompt and answer format for claim extraction |
| `memory/llm.py` | Talks to Ollama; turns any AI failure into one error type (`LLMError`) |
| `memory/recall.py` | "What do I remember before talking to X?" |
| `memory/explain.py` | "Who told you that?" |
| `memory/db.py` | One FalkorDB graph per world, plus index setup |
| `memory/models.py`, `config.py` | Request shapes and settings |

---

## 2. The graph model

Think of a newspaper:

| Node | Newspaper analogy | Example |
|---|---|---|
| `Event` | What actually happened | Kai took the hammer (Bram saw it) |
| `Claim` | The headline people repeat | "Kai stole a silver hammer from Bram" |
| `Belief` | One reader's opinion of that headline | Tom: 43% sure, heard it from Mara |
| `Conversation`, `Message` | The interviews where it was said | c:3, "Tom, I've got some gossip…" |
| `Character` | The readers | Tom, gullibility 0.3 (suspicious) |

**Why three separate things (Event / Claim / Belief)?**
- A claim can exist **without** an event — that's a rumor or a lie. The graph can tell the difference.
- Ten people can hold the **same** claim with **different** confidence.
- Each belief has its **own** source, so every person's chain is traceable.

**Provenance** is one relationship: `(Tom's belief)-[:HEARD_FROM]->(Mara's belief)`. Follow those arrows
back and you reach either a belief that `SAW` an event (witnessed) or one nobody told them (`origin: 'self'`,
they started it).

**Confidence math** (all in Cypher, see Q1 below):
- Hearing: `speaker's confidence × my trust in the speaker`.
  Trust = my `KNOWS.trust` for them, or, if we've never met, my `gullibility` (personality).
- Hearing it again from **another** person: `1 − (1 − old)(1 − new)`. Two independent 40% sources ≈ 64%.
- Worked example (the step 2.6 test): Bram saw it (1.0) → Pip 0.9 → Mara 0.72 → Tom 0.432. Then Bram
  tells Tom directly (1.0 × 0.6) → Tom = 1 − (0.568 × 0.4) = **0.773**.

**One graph per world** (`world_<id>`): villages never see each other's memories, and writes to different
villages run in parallel.

Files: `docs/DATA_MODEL.md` (full reference).

---

## 3. Ingest, step by step (`ingest.py → ingest_conversation`)

1. **Lock the conversation.** AI Town sends every conversation once *per NPC in it*. One Cypher query flips
   `status` from `new` to `ingesting`; FalkorDB runs one write at a time per graph, so exactly one caller wins
   and the other gets `skipped`. Tested with 8 simultaneous sends → 1 ingest.
2. **Store the transcript first** (participants, messages, `KNOWS` links). If the AI later fails, the episode
   is still saved and can be retried.
3. **Extract claims** with `llama3.1:8b`, forced into a JSON schema (`extract.py`).
4. **Check every claim in code** (`_validate`) — the small model ignores some prompt rules:
   - the subject must be a known character, and the text must name them;
   - for person-to-person claims, a non-person object is fixed from the text ("…from Bram") or downgraded to `did`;
   - malformed fields drop only that claim, never the conversation.
5. **Merge duplicates** (`_resolve_claim`): same structured key (`subject|predicate|object`) → same claim;
   otherwise near-identical text about the **same** person (vector distance < 0.10); otherwise a new claim.
   Why not vectors alone? "Tom stole the hammer" scored *closer* to "Kai stole the hammer" than a real paraphrase.
6. **Beliefs.** The speaker gets one if they had none (`origin: 'self'`, 0.6 — they started it). Each listener
   *hears* it (Q1), with three guards: no echo (your own rumor coming back), no repeat (same source twice),
   no believing rumors about yourself.
7. **Finish** → `ingested`. Any AI failure → `failed` + HTTP 502; a crash leaves `ingesting`, which startup
   recovery turns into `failed`; the retry loop re-runs failed ones from the stored transcript every 60 s.

Files: `memory/ingest.py`, `memory/extract.py`.

---

## 4. The three key queries, line by line

### Q1 — Hear a claim (`ingest.py`, `HEAR`)
```cypher
MATCH (lis:Character {id: $listener}), (spk:Character {id: $speaker}), (c:Claim {id: $claim})
MATCH (sb:Belief {holder: $speaker, claim: $claim, status: 'active'})          // the speaker's belief
WHERE NOT (sb)-[:HEARD_FROM*1..8]->(:Belief {holder: $listener})              // echo guard
  AND NOT (:Belief {holder: $listener, claim: $claim})-[:HEARD_FROM]->(sb)    // repeat guard
OPTIONAL MATCH (lis)-[k:KNOWS]->(spk)
WITH lis, spk, c, sb, sb.confidence * coalesce(k.trust, lis.gullibility, 0.5) AS incoming
MERGE (b:Belief {holder: $listener, claim: $claim})                          // one belief per person per claim
ON CREATE SET b.confidence = incoming, b.origin = 'heard', b.status = 'active', b.created_at = $ts
ON MATCH  SET b.confidence = 1 - (1 - b.confidence) * (1 - incoming)          // second source: combine
MERGE (b)-[:HELD_BY]->(lis)
MERGE (b)-[:OF]->(c)
MERGE (b)-[:HEARD_FROM {at: $ts}]->(sb)                                       // provenance
MERGE (lis)-[l:LEARNED_FROM]->(spk) ON CREATE SET l.count = 1 ON MATCH SET l.count = l.count + 1
WITH b MATCH (m:Message {id: $msg}) MERGE (b)-[:EVIDENCE]->(m)                // the exact line heard
```

### Q2 — Recall (`recall.py`, `BELIEFS`)
```cypher
MATCH (me:Character {id:$me})<-[:HELD_BY]-(b:Belief {status:'active'})-[:OF]->(c:Claim)-[:ABOUT]->(s:Character)
OPTIONAL MATCH (b)-[sh:HEARD_FROM]-(:Belief {holder:$other})        // did we already exchange this?
OPTIONAL MATCH (:Character {id:$other})-[kk:KNOWS]->(s)              // does the listener know the subject?
OPTIONAL MATCH (b)-[:HEARD_FROM]->(:Belief)-[:HELD_BY]->(t:Character)  // who told me
WITH b, c, s, count(DISTINCT sh) > 0 AS already_shared, count(DISTINCT kk) > 0 AS other_knows,
     collect(DISTINCT t.name) AS told_by
WITH b, c, s, told_by, already_shared,
     CASE WHEN s.id = $other THEN 2.0 WHEN other_knows THEN 1.5 ELSE 1.0 END AS relevance
RETURN c.text, b.confidence, told_by, already_shared,
       b.confidence * abs(c.valence) * relevance * CASE WHEN already_shared THEN 0.2 ELSE 1.0 END AS score
ORDER BY score DESC LIMIT $k
```
Score = how sure × how juicy × how relevant to the listener, and ×0.2 if we already talked about it.
The ordering of the `OPTIONAL MATCH`es matters — see section 5.

### Q4 — Explain (`explain.py`, `PATHS`)
```cypher
MATCH (:Character {id: $holder})<-[:HELD_BY]-(b:Belief {status: 'active'})-[:OF]->(c:Claim)-[:ABOUT]->(s:Character)
MATCH p = (b)-[:HEARD_FROM*0..8]->(root:Belief)        // walk the arrows back, up to 8 hops
WHERE (root.origin <> 'heard' OR NOT (root)-[:HEARD_FROM]->())   // ...stop at whoever saw it or said it first
  AND all(x IN nodes(p)[0..size(nodes(p)) - 1] WHERE x.origin = 'heard')  // only hearsay is passed through
OPTIONAL MATCH (root)-[:SAW]->(e:Event)                // did the root person witness a real event?
RETURN [x IN nodes(p) | x.holder] AS chain, root.origin, e.description
```
Python then turns the chain into a fixed sentence — never the AI, because in the preview the AI garbled it.
(Simplified here; the full query, with the claim/subject filters and the line heard at each hop, is `explain.PATHS` in [QUERIES.md](QUERIES.md). The stopping rule was added in Phase 3: a witness who later also *heard* the rumor is still where it came from.)

---

## 5. Failure handling and the bugs we found

| Found | What went wrong | Fix |
|---|---|---|
| Robustness probe | Model returned `valence: "very bad"` → whole conversation lost | Parse claims one by one; drop only the bad one |
| Robustness probe | Model returned non-JSON → reported as *our caller's* fault (422) | `LLMError` → 502 "AI failed", transcript kept |
| Robustness probe | Crash mid-ingest → stuck forever, memory silently lost | Startup recovery + automatic retry from the stored transcript |
| Writing tests | A silent participant wasn't linked to the conversation | Link participants separately from messages |
| Recall | "Already shared" never fired | FalkorDB 6.0.2 quirk: put all `OPTIONAL MATCH`es before the aggregating `WITH` |
| Data model | `CASE WHEN (pattern)` failed | Pattern checks only in `WHERE`; use `OPTIONAL MATCH` + `count()` |
| Preview | `'Bram''s'` quote-escaping failed | Use query parameters, never string-built values |
| Dedup | Vectors rated a different *person's* claim closer than a paraphrase | Structured key first; vectors only for the same subject |

Tests at the end of Phase 2: 61 automated (against real FalkorDB, with a scripted AI) + 2 live tests with the real model (3/3 passes). Today: 121 + 2.

---

## 6. Practice questions (the kind judges ask)

**Why a graph database and not a vector database?**
The questions we answer are paths, not similarity: "who told you?" is a walk along `HEARD_FROM` arrows;
"how sure are you?" combines trust along a chain; "already shared?" checks a link between two people's beliefs.
We do use FalkorDB's vector index — but only to merge near-identical claims, filtered by person.

**What breaks if you remove FalkorDB?**
Everything that makes NPCs NPCs-with-memory: recall returns nothing, gossip can't spread, nobody can say who
told them. AI Town's own vector memory is removed in Phase 3, so there's no fallback.

**How do you stop the same rumor counting twice?**
Three guards in Q1 (echo, repeat, self) plus the per-conversation lock, because AI Town sends each conversation
once per participant.

**How do you know a rumor is made up?**
Follow its `HEARD_FROM` chain back. If the root belief `SAW` an `Event`, it's witnessed. If the root is
`origin: 'self'` with no event, someone started it — the graph names who.

**Why doesn't the LLM write Cypher?**
Reliability and safety: the 8B model already ignores prompt rules. It only fills a fixed JSON form; our code
validates it and runs fixed, parameterized queries.

**What if the AI returns garbage or the AI server is down?**
Bad claims are dropped individually; outages return 502 and the conversation is retried automatically from its
stored transcript (demonstrated live: tunnel cut, `kill -9` mid-ingest).

**How does separate memory per user work?**
One FalkorDB graph per world. Same character id in two worlds = two different people; tested.

**How fast is it?**
Recall and explain: ~2 ms over HTTP. Ingest: 9–14 s on a CPU-only 8B model, done after the conversation so
nobody waits.

**What did you build vs. reuse?**
AI Town (MIT) provides the pixel world and NPC dialogue. The memory system — graph model, ingest, recall,
explain, failure handling — is ours, written during the event (see git history and `RESEARCH_LOG.md`).

---

# Phase 3 — plugging the memory into the game

**Two connections only.** Before an NPC speaks, AI Town calls `GET /recall` and gets memory lines plus one
**topic** (the best fresh news, in the NPC's own words). After a conversation ends, AI Town sends the transcript
to `POST /conversations`. AI Town's own vector memory (tables, embeddings, reflections) was deleted, so without
FalkorDB the villagers remember nothing.

**The village of Chandanpur.** Eight villagers with a personality (gullibility) and trust links
(`village/chandanpur.json`): a market circle (Ramesh, Chotu, Lakshmi, Sarla) and a temple/school circle
(Pandit Shastri, Meera, Balwant), joined by Gopal the milkman — the top bridge by betweenness (24).

**The narrator** (`POST /events`) records what really happened: "Kabir stole Ramesh's hammer; Ramesh saw it."
Ramesh gets a 100% witnessed belief; rumors about it — before or after — attach to the same claim and become
verifiable.

**The graph picks the topic.** With memories alone, the small model never retold the theft (0/5 replays).
Recall now hands it one fresh piece of news to voice, preferring news about other people and first-hand news.
*The graph decides what to say; the AI only says it.*

**Live result.** Ramesh (saw it, 100%) → Gopal (70%) → Pandit Shastri (42%): from the market circle to the
temple circle through the predicted bridge. Pandit Shastri: *"Gopal told me. Gopal heard it from Ramesh.
Ramesh saw it happen."*

**Fixed along the way:** a setup race when two NPCs report at once; "who told you" crediting a later source
instead of the originator; honorifics ("Shastri ji", "Balwant Singh"); a service freeze on reload.

---

# Phase 4 — the investigator

**The idea.** A new agent, Inspector Vikram, arrives knowing nothing and must find out what happened to Ramesh's
hammer only by questioning villagers. Every mind stays private, including his: nobody, not even the
investigator, reads the whole graph. One scene covers Track 2: memory that survives a crash, a handoff through
shared state, and memory that gets corrected.

**1. A briefing from structure only** (`POST /cases`). Before any interview, the graph says *who matters*, not
*what they believe*: news hubs (PageRank over who-learned-from-whom), the bridge (betweenness: Gopal), and the
circles (friend groups once the bridge is removed). That gives the first leads: Gopal, Lakshmi, Pandit Shastri.

**2. Interviews follow the trail upstream** (`/interview`). A villager testifies only about case-relevant beliefs
(vector distance to the case question < 0.40) and names only who told them *directly*. Each name becomes the next
lead. Live: Gopal said "Ramesh told me", so Ramesh came next: "I saw it with my own eyes." The eyewitness was
reached in interview 3, and every competing rumor was traced to whoever started it.

**3. Crash and resume** (`/assign`). The case file (case, leads, findings) lives in the graph, not in the agent.
Vikram's process dies after 2 interviews; Inspector Anjali starts fresh, reads a handoff summary built from the file,
and continues with the next lead. No interview is repeated, and she doesn't inherit his beliefs (she starts with 0),
only the shared case file.

**4. Verdict and debunking** (`/verdict`), decided from the findings only:
- *confirmed*: someone saw it
- *distorted*: an honest garbling of the truth (distance < 0.27)
- *unfounded*: someone started it and nobody saw it
- *unresolved*: the trail ran out

Debunked beliefs are marked superseded, **never deleted**. Whoever started an unfounded rumor loses half the trust
of the people they misled. Villagers remember the correction, and a debunked rumor can't spread again:
*"I used to believe that Ramesh stole two iron artifacts, but Inspector Anjali's inquiry found Lakshmi started it
and nobody saw it."*

**5. In the town** (4.7). The investigator walks up to villagers in AI Town, and the interview lines on screen are
the case file, word for word.

**6. Separate villages** (4.6). `GRAPH.COPY` of a village template (6 ms) starts a second Chandanpur with the same
people and no history. Kabir is a thief in one village and a stranger (or a helper) in the other; nothing leaks
between graphs.

**Fixed along the way:**
- talk densified the social graph, so lasting friendships became `FRIEND` edges
- two different rumors were merged under one claim key
- a true retelling was judged a lie
- speculation ("perhaps…") was stored as a claim
- the investigator crashed waiting for a busy villager; it now postpones that villager
- upstream AI Town removed idle humans after 5 minutes

**Known limit:** a mis-extracted line can still look like a rumor (one cost Ramesh some trust in the live world).
Reset the village before recording.
