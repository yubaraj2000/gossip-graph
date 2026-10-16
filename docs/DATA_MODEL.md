# Graph Data Model — gossip-graph

Every NPC's memory lives in FalkorDB. An NPC knows something only if there is a `Belief` node that links it to a `Claim`. It knows *why* it believes it by following the belief's `HEARD_FROM` chain back to a witness, or to the character who made it up.

> **Status:** design for Phase 2. All queries below were run against FalkorDB on 2026-10-16 using a 5-character test village.

## Decisions (Oct 16)

| Topic | Chosen | Possible later additions |
|---|---|---|
| Claim types | Fixed predicate vocabulary, plus a free-text fallback with vector dedup | — |
| Trust | Fixed confidence rules, plus a per-character `gullibility` trait | Trust that learns from false rumors (Phase 4, optional) |
| Conversation storage | Every message is kept | Condensing old conversations into summaries (Phase 4, optional) |

## Principles

1. **One graph per world.** The graph is named `world_<convexWorldId>`. Worlds are fully isolated (separate memory per tenant), and writes to different worlds run in parallel.
2. **The graph is the brain, and the LLM is the mouth.** Recall, provenance, reputation and gossip ranking are deterministic Cypher. The LLM only does two things:
   - extracts claims from finished conversations
   - turns recalled context into dialogue

   The LLM never writes Cypher.
3. **Nothing is deleted.** Old beliefs are marked `superseded` with a `valid_to` time, so the history of what an NPC used to believe stays queryable.
4. **Truth and belief are separate.** An `Event` is what really happened, and a `Claim` is what someone says. A claim linked to an event is grounded. A claim with no witness at the root of its chain is an unverified rumor.

## Diagram

```mermaid
graph LR
  Ch1((Character)) -- "KNOWS {trust}" --> Ch2((Character))
  Ch1 -- "LEARNED_FROM {count}" --> Ch2
  Ch1 -- PARTICIPATED_IN --> Cv[Conversation]
  Ch1 -- SAID --> M[Message] -- IN --> Cv
  Ch1 -- DID --> E[Event] -- AGAINST --> Ch2
  Ch2 -- WITNESSED --> E
  C[Claim] -- ABOUT --> Ch1
  C -- REFERS_TO --> E
  B[Belief] -- HELD_BY --> Ch2
  B -- OF --> C
  B -- "HEARD_FROM {at}" --> B2[Belief]
  B -- SAW --> E
  B -- EVIDENCE --> M
```

## Nodes

| Label | Key properties | Memory type | Created by |
|---|---|---|---|
| `Character` | `id` (AI Town player id, e.g. `p:3`), `name`, `kind` (`npc` or `human`), `identity`, `gullibility` (0–1, personality) | — | world seed, or a human joining |
| `Conversation` | `id` (e.g. `c:29`), `started_at`, `ended_at`, `summary`, `ingested` | **episodic** | ingest |
| `Message` | `id`, `idx`, `text`, `ts` | **episodic** | ingest |
| `Event` | `id`, `kind`, `description`, `ts`, `severity` (0–1) | **episodic** (ground truth) | narrator endpoint |
| `Claim` | `id`, `key` (`subject\|predicate\|object`), `predicate`, `text`, `valence` (−1 to +1), `embedding` (1024-d) | **semantic** (the proposition) | ingest or narrator |
| `Belief` | `holder` (character id), `claim` (claim id), `confidence` (0–1), `origin` (`witnessed`, `heard` or `self`), `status` (`active` or `superseded`), `created_at`, `valid_to` | **semantic** (one character's stance) | ingest or narrator |
| `Task` *(Phase 4.4)* | `id`, `description`, `status` | **shared state / handoff** | NPC coordination |
| `Rule` *(Phase 4.5, stretch)* | `id`, `condition`, `action`, `strength` | **procedural** | learned from events |

`Belief.holder` and `Belief.claim` repeat information that the relationships already hold. This makes `MERGE` idempotent and lookups indexed: there is exactly one belief per (holder, claim).

## Relationships

| Type | From → To | Meaning |
|---|---|---|
| `KNOWS {trust, interactions}` | Character → Character | Social graph, directed: A's trust in B. Seeded, then updated after each conversation. |
| `LEARNED_FROM {count}` | Character → Character | Rolled-up "who learned things from whom". Used for influence ranking. |
| `PARTICIPATED_IN` | Character → Conversation | Who was in the conversation |
| `SAID` / `IN` | Character → Message → Conversation | The transcript |
| `DID` / `AGAINST` / `WITNESSED` | Character → Event → Character | Who did what to whom, and who saw it |
| `ABOUT` | Claim → Character | Who the claim is about |
| `REFERS_TO` | Claim → Event | The claim is grounded in a real event |
| `HELD_BY` / `OF` | Belief → Character / Claim | Who believes what |
| `HEARD_FROM {at}` | Belief → Belief | **Provenance.** The listener's belief came from the speaker's belief. Can have several sources. |
| `SAW` | Belief → Event | A root belief: the holder witnessed the event |
| `EVIDENCE` | Belief → Message | The exact line where the holder heard it |
| `SUPERSEDED_BY` *(4.1)* | Belief → Belief | Belief revision without deleting |

## Rules

- **Witnessing:** each witness of an event gets a root belief with `confidence = 1.0`, `origin = 'witnessed'` and a `SAW` edge.
  - Events come from the **narrator**, `POST /worlds/{id}/events` (`memory/narrate.py`). The event's claim uses the same key NPC gossip produces (`actor|kind|target`), so rumors before or after attach to it (by key, or by meaning for paraphrases), and the claim gets `REFERS_TO` the event.
  - A witness who had only *heard* the rumor is upgraded to `witnessed`.
  - Sending the same event again is harmless, because the id is a hash of the event.
- **Hearing:** when A tells B a claim, B's incoming confidence is `confidence(A's belief) × trust(B→A)`. If B has no `KNOWS` edge to A, the trust is **B's `gullibility`**, the personality trait: suspicious Tom has 0.3, gossipy Mara has 0.7. If that isn't set either, the trust is `0.5`.
- **Hearing again from another source:** the beliefs combine as `1 − (1 − old)(1 − incoming)`, and a second `HEARD_FROM` edge is added. More independent sources make a belief more certain.
- **Inventing:** if a speaker asserts a claim it has no belief for, the speaker gets a belief with `origin = 'self'` and confidence 0.6. This is how rumors and lies are born, and `explain` shows that they have no witness.
- **Idempotency:** AI Town calls "remember conversation" **once per NPC participant**. A single query atomically moves `Conversation.status` from `new` (or `failed`) to `ingesting`. Queries on one graph run one at a time, so exactly one caller wins and the other gets `skipped`.
- **Echo guard:** hearing your own rumor back adds nothing. If the speaker's belief is downstream of the listener's (`(sb)-[:HEARD_FROM*1..8]->(listener's belief)`), it's skipped.
- **Repeat guard:** hearing the same claim again from the *same* speaker belief doesn't raise confidence. Only independent sources do.
- **No self-adoption:** a character never adopts a claim about themselves.
- **Acquaintance:** talking creates `KNOWS` edges in both directions. On first contact, trust is the truster's `gullibility`.
- **Failure handling:**
  - The transcript is stored *before* the LLM step, so the episode is never lost.
  - A model failure returns HTTP 502 and leaves status `failed`.
  - Claims are parsed one at a time, so a malformed claim is dropped without losing the others.
  - At service start, leftover `ingesting` conversations (from a crash) are marked `failed`.
  - A retry loop (every `RETRY_INTERVAL_S`, default 60 s, only while Ollama is reachable) rebuilds failed conversations from the stored transcript and ingests them again. `POST /worlds/{id}/retry` does the same on demand.
  - A lock older than 10 minutes can also be retaken by a resend.
- **Validation in code** (the 8b model doesn't reliably follow the prompt):
  - the subject must be a known character
  - the claim text must name the subject
  - for person predicates, a non-person object is replaced by the other person named in the text; if there is none, the predicate becomes `did`
  - valence is clamped to −1…1
- **Claim dedup:**
  - First an exact `key` match.
  - Then vector similarity on `Claim.embedding`, **only among claims about the same subject**, with distance < **0.10**. FalkorDB's vector `score` is a cosine **distance** (lower means closer).
  - mxbai-embed-large distances from "Kai stole a silver hammer from Bram":

    | Compared text | Distance |
    |---|---|
    | "Kai swiped Bram's silver hammer" (paraphrase) | 0.089 → merged |
    | looser paraphrase | 0.177 |
    | the "fence" rumor mutation | 0.181 |
    | "Tom stole a silver hammer from Bram" (different subject!) | 0.138 |

  - So embeddings alone cannot be trusted: the key comes first, and the vector check is always filtered by subject.

## Core queries (all verified)

**Q1 — Ingest "listener heard claim from speaker"**
```cypher
MATCH (lis:Character {id:$listener}), (c:Claim {id:$claim}), (spk:Character {id:$speaker})
OPTIONAL MATCH (lis)-[k:KNOWS]->(spk)
WITH lis, c, coalesce(k.trust, lis.gullibility, 0.5) AS trust
MATCH (sb:Belief {holder:$speaker, claim:$claim, status:'active'})
WITH lis, c, sb, sb.confidence * trust AS incoming
MERGE (b:Belief {holder:$listener, claim:$claim})
  ON CREATE SET b.confidence = incoming, b.origin = 'heard', b.status = 'active', b.created_at = $ts
  ON MATCH SET b.confidence = 1 - (1 - b.confidence) * (1 - incoming)
MERGE (b)-[:HELD_BY]->(lis)
MERGE (b)-[:OF]->(c)
MERGE (b)-[:HEARD_FROM {at:$ts}]->(sb)
WITH b MATCH (m:Message {id:$msg}) MERGE (b)-[:EVIDENCE]->(m)
WITH b MATCH (lis:Character {id:$listener}), (spk:Character {id:$speaker})
MERGE (lis)-[l:LEARNED_FROM]->(spk) ON CREATE SET l.count = 1 ON MATCH SET l.count = l.count + 1
```
Test result: Bram → Pip gave 0.90, Pip → Mara 0.72, Mara → Tom 0.43. A second source, Bram → Tom directly, raised Tom's belief to **0.60**.

**Q2 — Recall: what I bring up when talking to someone.** This replaces AI Town's vector `searchMemories`. Served by `GET /worlds/{id}/recall?me=&other=&k=`.
```cypher
MATCH (me:Character {id:$me})<-[:HELD_BY]-(b:Belief {status:'active'})-[:OF]->(c:Claim)-[:ABOUT]->(s:Character)
OPTIONAL MATCH (b)-[sh:HEARD_FROM]-(:Belief {holder:$other})        // we already exchanged this one
OPTIONAL MATCH (:Character {id:$other})-[kk:KNOWS]->(s)              // they know the subject
OPTIONAL MATCH (b)-[:HEARD_FROM]->(:Belief)-[:HELD_BY]->(t:Character)  // who told me
WITH b, c, s, count(DISTINCT sh) > 0 AS already_shared, count(DISTINCT kk) > 0 AS other_knows,
     collect(DISTINCT t.name) AS told_by
WITH b, c, s, told_by, already_shared,
     CASE WHEN s.id = $other THEN 2.0 WHEN other_knows THEN 1.5 ELSE 1.0 END AS relevance
RETURN c.text, b.confidence, b.origin, told_by, already_shared,
       b.confidence * abs(c.valence) * relevance * CASE WHEN already_shared THEN 0.2 ELSE 1.0 END AS score
ORDER BY score DESC LIMIT $k
```
- **Ranking:** `confidence × |valence| × relevance`. Relevance is 2 if the claim is about the person I'm talking to, 1.5 if it's about someone they know, and 1 otherwise. A claim we **already exchanged** (either direction of `HEARD_FROM`) is damped ×0.2, so NPCs don't repeat themselves.
- The endpoint also returns:
  - Q5 reputation
  - my `KNOWS` trust
  - Q3 recent episodes
  - ready-to-use **first-person memory lines** for the NPC prompt. They use words instead of numbers ("I believe it", "it's only a rumor to me"), and my own name becomes "me" / "my".
- ⚠️ **Keep every `OPTIONAL MATCH` before the aggregating `WITH`.** On FalkorDB 6.0.2, `OPTIONAL MATCH … WITH <aggregation> OPTIONAL MATCH (b)-…` silently matched nothing.

**Q3 — Shared episodes:** past conversations between the two characters.
```cypher
MATCH (:Character {id:$me})-[:PARTICIPATED_IN]->(cv:Conversation)<-[:PARTICIPATED_IN]-(:Character {id:$other})
RETURN cv.id, cv.summary ORDER BY cv.ended_at DESC LIMIT 3
```

**Q4 — Explain: "who told you that?"** Returns every provenance path. Served by `GET /worlds/{id}/explain?holder=&claim=&subject=`. It adds the line heard at each hop (the listener's `EVIDENCE` message, said by the next person in the chain), plus an answer sentence built **from the path, not by the LLM**, e.g. *"Mara told me. Mara heard it from Pip, who heard it from Bram. Bram saw it happen."* The verdict is `witnessed` if any path's root `SAW` an event; otherwise `unverified`.
```cypher
MATCH (:Character {id:$holder})<-[:HELD_BY]-(b:Belief)-[:OF]->(:Claim {id:$claim})
MATCH p = (b)-[:HEARD_FROM*0..8]->(root:Belief)
WHERE NOT (root)-[:HEARD_FROM]->()
OPTIONAL MATCH (root)-[:SAW]->(e:Event)
RETURN [x IN nodes(p) | x.holder] AS chain, root.origin, e.description
```
Test results:
- Tom's belief came back with two paths: `Tom ← Bram` and `Tom ← Mara ← Pip ← Bram`. Both trace to Bram's witnessed event.
- The rumor "Tom is a smuggler" came back as `Mara ← Pip` with origin `self`: Pip made it up.

**Q5 — Reputation:** how one character sees another.
```cypher
MATCH (:Character {id:$holder})<-[:HELD_BY]-(b:Belief {status:'active'})-[:OF]->(c:Claim)-[:ABOUT]->(:Character {id:$subject})
RETURN sum(b.confidence * c.valence) AS reputation, count(b) AS evidence
```

**Q6 — Graph algorithms as gameplay**
```cypher
// Bridges: whose silence stops a rumor crossing groups
CALL algo.betweenness({nodeLabels:['Character'], relationshipTypes:['KNOWS']}) YIELD node, score
// Influencers: who others learn from. LEARNED_FROM points listener → speaker,
// so PageRank flows to the sources.
CALL algo.pageRank('Character', 'LEARNED_FROM') YIELD node, score
// Cliques
CALL algo.labelPropagation({nodeLabels:['Character'], relationshipTypes:['KNOWS']}) YIELD node, communityId
```
Test results:
- Betweenness: Mara 1.0, Pip 0.5, Tom 0.5.
- PageRank: Bram 0.37 (the original witness), then Pip 0.25.
- Label propagation: ⚠️ noisy on a 5-character graph. It needs the real 8–10 NPC village to be meaningful.

## Indexes

```cypher
CREATE INDEX FOR (n:Character) ON (n.id)
CREATE INDEX FOR (n:Conversation) ON (n.id)
CREATE INDEX FOR (n:Message) ON (n.id)
CREATE INDEX FOR (n:Event) ON (n.id)
CREATE INDEX FOR (n:Claim) ON (n.id)
CREATE INDEX FOR (n:Claim) ON (n.key)
CREATE INDEX FOR (n:Belief) ON (n.holder)
CREATE INDEX FOR (n:Belief) ON (n.claim)
CREATE VECTOR INDEX FOR (c:Claim) ON (c.embedding) OPTIONS {dimension:1024, similarityFunction:'cosine'}
```

## LLM extraction contract (step 2.3)

There is one call per finished conversation, using `llama3.1:8b` with Ollama's JSON-schema output. It returns:
```json
{
  "summary": "Pip told Mara that Kai stole Bram's hammer.",
  "claims": [
    {"message_index": 0, "speaker": "Pip", "subject": "Kai", "predicate": "stole_from",
     "object": "Bram", "text": "Kai stole a hammer from Bram", "valence": -0.8}
  ]
}
```
- **`predicate` vocabulary:** `stole_from`, `attacked`, `helped`, `lied_to`, `gave_to`, `owes`, `likes`, `dislikes`, `is` (a trait), `did` (any other action), `plans_to`.
- **Validation:** claims whose `subject` isn't a known character are dropped, as is small talk with no claim.

## Track 2 coverage

| Track 2 focus | Where it lives in the graph |
|---|---|
| Episodic memory | `Conversation`, `Message`, `Event` |
| Semantic memory | `Claim` plus `Belief` (confidence, origin, validity) |
| Procedural memory | `Rule` (Phase 4.5, stretch) |
| Persistent conversation history | `Conversation`/`Message`, recalled with Q3 |
| Shared state and handoffs | Beliefs flowing along `HEARD_FROM`; `Task` (4.4) |
| High-concurrency reads and writes | Writes to different world graphs run in parallel; idempotent `MERGE` ingest |
| Separate memory per user/tenant | One graph per world (`world_<id>`), cloned from a template with `GRAPH.COPY` |

## FalkorDB gotchas found while validating

- Pattern predicates such as `(a)-[:R]->(b)` work in `WHERE`, but **not** inside `CASE` or `RETURN` expressions. Use `OPTIONAL MATCH` plus `count(x) > 0` instead.
- Vector `score` is a distance. Sort ascending.
