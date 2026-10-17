# Every Cypher query

All **78** queries the memory service runs against FalkorDB, copied from the source by `scripts/export_queries.py` (re-run it after changing a query; don't edit this file by hand). `$name` is a query parameter; `{rel}` in the betweenness query is `FRIEND`, or `KNOWS` before any friendships exist. Besides these, the service uses `GRAPH.COPY` to start a world from a village template (`memory/templates.py`).

For what each query is for, start with the README's "How the graph does the work" and [DATA_MODEL.md](DATA_MODEL.md).

## `memory/db.py`

FalkorDB access: one graph per world (plus village templates to start worlds from), and idempotent schema setup.

### inline in `_indexes()`

```cypher
CALL db.indexes() YIELD label, types RETURN label, types
```

### inline in `ensure_graph_schema()`

```cypher
CREATE INDEX FOR (n:{label}) ON (n.{prop})
```

### inline in `ensure_graph_schema()`

```cypher
CREATE VECTOR INDEX FOR (n:{label}) ON (n.{prop}) OPTIONS {dimension:{settings.embedding_dim}, similarityFunction:'cosine'}
```

## `memory/ingest.py`

Ingest a finished conversation: transcript -> claims -> beliefs with provenance (docs/DATA_MODEL.md, Q1).

### `UPSERT_CHARACTERS`

```cypher
UNWIND $chars AS ch
MERGE (c:Character {id: ch.id})
SET c.name = ch.name, c.kind = ch.kind,
    c.identity = CASE WHEN ch.identity = '' THEN c.identity ELSE ch.identity END,
    c.gullibility = coalesce(ch.gullibility, c.gullibility)
```

### `SET_RELATIONSHIPS`

Seeded social graph (village file). KNOWS carries trust for gossip and is also created by talking, so it densifies over time; FRIEND marks only the village's lasting friendships (the structure the investigator's briefing reads). Re-seeding updates trust but keeps the interaction count.

```cypher
UNWIND $rels AS r
MATCH (a:Character {id: r.source}), (b:Character {id: r.target})
MERGE (a)-[k:KNOWS]->(b)
ON CREATE SET k.interactions = 0
SET k.trust = r.trust
MERGE (a)-[:FRIEND]->(b)
RETURN count(k)
```

### `TAKE_CONVERSATION`

Atomically claim the conversation for ingestion. Queries on one graph run one at a time, so when AI Town sends the same conversation twice (once per NPC participant), exactly one caller gets `mine = true`. A run that crashed mid-ingest leaves 'ingesting' behind; after STALE_INGEST_MS it can be taken again.

```cypher
MERGE (cv:Conversation {id: $id})
ON CREATE SET cv.status = 'new'
WITH cv, (cv.status IN ['new', 'failed']
          OR (cv.status = 'ingesting' AND coalesce(cv.taken_at, 0) < $stale_before)) AS mine
SET cv.status = CASE WHEN mine THEN 'ingesting' ELSE cv.status END,
    cv.taken_at = CASE WHEN mine THEN $now ELSE cv.taken_at END
RETURN mine
```

### `LINK_PARTICIPANTS`

Participants are linked even if they never spoke (e.g. a silent human player).

```cypher
MATCH (cv:Conversation {id: $id})
SET cv.started_at = $started_at, cv.ended_at = $ended_at
WITH cv
UNWIND $participants AS pid
MATCH (p:Character {id: pid})
MERGE (p)-[:PARTICIPATED_IN]->(cv)
```

### `WRITE_MESSAGES`

```cypher
MATCH (cv:Conversation {id: $id})
UNWIND $msgs AS m
MATCH (a:Character {id: m.author})
MERGE (msg:Message {id: m.id})
ON CREATE SET msg.idx = m.idx, msg.text = m.text, msg.ts = m.ts
MERGE (a)-[:SAID]->(msg)
MERGE (msg)-[:IN]->(cv)
```

### `TOUCH_KNOWS`

Talking makes people acquainted: first contact trusts at the listener's gullibility.

```cypher
UNWIND $pairs AS p
MATCH (a:Character {id: p[0]}), (b:Character {id: p[1]})
MERGE (a)-[k:KNOWS]->(b)
ON CREATE SET k.trust = coalesce(a.gullibility, 0.5), k.interactions = 0
SET k.interactions = k.interactions + 1, k.last_talked = $ts
```

### `FIND_SIMILAR_CLAIM`

```cypher
CALL db.idx.vector.queryNodes('Claim', 'embedding', 10, vecf32($embedding)) YIELD node, score
MATCH (node)-[:ABOUT]->(:Character {id: $subject})
WHERE score < $max_distance
RETURN node.id ORDER BY score LIMIT 1
```

### `CREATE_CLAIM`

```cypher
MATCH (s:Character {id: $subject})
MERGE (c:Claim {key: $key})
ON CREATE SET c.id = $id, c.predicate = $predicate, c.object = $object, c.text = $text,
              c.valence = $valence, c.embedding = vecf32($embedding), c.created_at = $ts
MERGE (c)-[:ABOUT]->(s)
RETURN c.id
```

### `ENSURE_SPEAKER_BELIEF`

A speaker asserting a claim they hold no belief in becomes its origin ('self').

```cypher
MATCH (spk:Character {id: $speaker}), (c:Claim {id: $claim})
MERGE (b:Belief {holder: $speaker, claim: $claim})
ON CREATE SET b.confidence = $confidence, b.origin = 'self', b.status = 'active', b.created_at = $ts
MERGE (b)-[:HELD_BY]->(spk)
MERGE (b)-[:OF]->(c)
WITH b
MATCH (m:Message {id: $msg})
MERGE (b)-[:EVIDENCE]->(m)
RETURN b.origin
```

### `HEAR`

Q1 from DATA_MODEL.md, with two guards: - echo: the listener's own belief is upstream of the speaker's, so hearing it back adds nothing - repeat: the listener already heard this claim from this speaker's belief

```cypher
MATCH (lis:Character {id: $listener}), (spk:Character {id: $speaker}), (c:Claim {id: $claim})
MATCH (sb:Belief {holder: $speaker, claim: $claim, status: 'active'})
WHERE NOT (sb)-[:HEARD_FROM*1..8]->(:Belief {holder: $listener})
  AND NOT (:Belief {holder: $listener, claim: $claim})-[:HEARD_FROM]->(sb)
OPTIONAL MATCH (lis)-[k:KNOWS]->(spk)
WITH lis, spk, c, sb, sb.confidence * coalesce(k.trust, lis.gullibility, 0.5) AS incoming
MERGE (b:Belief {holder: $listener, claim: $claim})
ON CREATE SET b.confidence = incoming, b.origin = 'heard', b.status = 'active', b.created_at = $ts
ON MATCH SET b.confidence = 1 - (1 - b.confidence) * (1 - incoming)
MERGE (b)-[:HELD_BY]->(lis)
MERGE (b)-[:OF]->(c)
MERGE (b)-[:HEARD_FROM {at: $ts}]->(sb)
MERGE (lis)-[l:LEARNED_FROM]->(spk)
ON CREATE SET l.count = 1
ON MATCH SET l.count = l.count + 1
WITH b
MATCH (m:Message {id: $msg})
MERGE (b)-[:EVIDENCE]->(m)
RETURN b.confidence, b.origin
```

### `FINISH`

```cypher
MATCH (cv:Conversation {id: $id}) SET cv.status = $status, cv.summary = $summary, cv.error = $error
```

### `RECOVER_INTERRUPTED`

Run at service start: an 'ingesting' conversation can only be left over from a run that died.

```cypher
MATCH (cv:Conversation {status: 'ingesting'})
SET cv.status = 'failed', cv.error = 'interrupted: the memory service stopped mid-ingest'
RETURN count(cv)
```

### `FAILED_CONVERSATIONS`

```cypher
MATCH (cv:Conversation {status: 'failed'})
RETURN cv.id ORDER BY coalesce(cv.ended_at, 0) LIMIT $limit
```

### `LOAD_PARTICIPANTS`

```cypher
MATCH (p:Character)-[:PARTICIPATED_IN]->(:Conversation {id: $id})
RETURN p.id, p.name, coalesce(p.kind, 'npc')
```

### `LOAD_MESSAGES`

```cypher
MATCH (a:Character)-[:SAID]->(m:Message)-[:IN]->(:Conversation {id: $id})
RETURN a.id, m.text, m.ts ORDER BY m.idx
```

### inline in `_ingest()`

```cypher
MATCH (c:Character) RETURN c.id, c.name
```

### inline in `resolve_claim()`

```cypher
MATCH (k:Claim {key: $key}) RETURN k.id
```

## `memory/recall.py`

Recall: what an NPC remembers when it is about to talk to someone (docs/DATA_MODEL.md, Q2/Q3/Q5).

### `CHARACTERS`

```cypher
MATCH (c:Character) WHERE c.id IN [$me, $other] RETURN c.id, c.name
```

### `BELIEFS`

Q2 plus "already shared": the other's belief came from mine, or mine came from theirs. All OPTIONAL MATCHes come before the aggregating WITH: on FalkorDB 6.0.2 an OPTIONAL MATCH placed after "OPTIONAL MATCH ... WITH <aggregation>" silently matched nothing (see RESEARCH_LOG, step 2.4).

```cypher
MATCH (me:Character {id: $me})<-[:HELD_BY]-(b:Belief {status: 'active'})-[:OF]->(c:Claim)-[:ABOUT]->(s:Character)
OPTIONAL MATCH (b)-[sh:HEARD_FROM]-(:Belief {holder: $other})
OPTIONAL MATCH (:Character {id: $other})-[kk:KNOWS]->(s)
OPTIONAL MATCH (b)-[:HEARD_FROM]->(:Belief)-[:HELD_BY]->(t:Character)
WITH b, c, s, count(DISTINCT sh) > 0 AS already_shared, count(DISTINCT kk) > 0 AS other_knows,
     collect(DISTINCT t.name) AS told_by
WITH b, c, s, told_by, already_shared,
     CASE WHEN s.id = $other THEN 2.0 WHEN other_knows THEN 1.5 ELSE 1.0 END AS relevance
RETURN c.id, s.id, s.name, c.text, c.valence, b.confidence, b.origin, told_by, already_shared,
       b.confidence * abs(c.valence) * relevance * CASE WHEN already_shared THEN $damping ELSE 1.0 END AS score
ORDER BY score DESC, b.confidence DESC
LIMIT $k
```

### `REPUTATION`

Q5: my overall view of the other, from everything I believe about them.

```cypher
MATCH (:Character {id: $me})<-[:HELD_BY]-(b:Belief {status: 'active'})-[:OF]->(c:Claim)-[:ABOUT]->(:Character {id: $other})
RETURN coalesce(sum(b.confidence * c.valence), 0.0), count(b)
```

### `TRUST`

```cypher
MATCH (:Character {id: $me})-[k:KNOWS]->(:Character {id: $other})
RETURN k.trust, k.interactions
```

### `DEBUNKED`

Beliefs a published verdict corrected: kept as 'superseded' (memory updates without deleting history).

```cypher
MATCH (:Character {id: $me})<-[:HELD_BY]-(b:Belief {status: 'superseded'})-[:OF]->(c:Claim),
      (b)-[d:DEBUNKED_BY]->(:Case)
RETURN c.text, d.kind, d.started_by, d.by
ORDER BY b.valid_to DESC
LIMIT 2
```

### `EPISODES`

Q3: our most recent conversations.

```cypher
MATCH (:Character {id: $me})-[:PARTICIPATED_IN]->(cv:Conversation {status: 'ingested'})<-[:PARTICIPATED_IN]-(:Character {id: $other})
RETURN cv.id, cv.summary, cv.ended_at
ORDER BY cv.ended_at DESC
LIMIT $n
```

## `memory/explain.py`

Explain: "who told you that?" — every provenance path behind a belief (docs/DATA_MODEL.md, Q4).

### `PATHS`

Q4: each path follows HEARD_FROM from the holder's belief back to its origin. Only 'heard' beliefs relay a rumor: a path stops at the first belief that was witnessed or said first, even if that person later also heard it from someone else (that later edge is corroboration, not where the belief came from).

```cypher
MATCH (:Character {id: $holder})<-[:HELD_BY]-(b:Belief {status: 'active'})-[:OF]->(c:Claim)-[:ABOUT]->(s:Character)
WHERE ($claim IS NULL OR c.id = $claim) AND ($subject IS NULL OR s.id = $subject)
MATCH p = (b)-[:HEARD_FROM*0..8]->(root:Belief)
WHERE (root.origin <> 'heard' OR NOT (root)-[:HEARD_FROM]->())
  AND all(x IN nodes(p)[0..size(nodes(p)) - 1] WHERE x.origin = 'heard')
OPTIONAL MATCH (root)-[:SAW]->(e:Event)
OPTIONAL MATCH (c)-[:REFERS_TO]->(ev:Event)
RETURN c.id, c.text, s.id, c.valence, b.confidence, b.origin,
       [x IN nodes(p) | x.holder] AS chain, [x IN nodes(p) | x.confidence] AS confidences,
       root.origin, e.description, count(ev) > 0 AS grounded
ORDER BY b.confidence DESC, c.id, length(p)
```

### `EVIDENCE`

The line each listener heard: the listener's EVIDENCE message, said by the next person in the chain.

```cypher
UNWIND $hops AS hop
MATCH (:Belief {holder: hop[0], claim: hop[1]})-[:EVIDENCE]->(m:Message)<-[:SAID]-(:Character {id: hop[2]})
RETURN hop[0], hop[1], hop[2], m.text ORDER BY m.ts
```

### `NAMES`

```cypher
MATCH (c:Character) RETURN c.id, c.name
```

## `memory/narrate.py`

Narrator: record something that really happened (docs/DATA_MODEL.md: Event = ground truth).

### `CREATE_EVENT`

```cypher
MATCH (a:Character {id: $actor})
MERGE (e:Event {id: $id})
ON CREATE SET e.kind = $kind, e.description = $description, e.ts = $ts, e.severity = $severity
MERGE (a)-[:DID]->(e)
RETURN e.id
```

### `LINK_TARGET`

```cypher
MATCH (e:Event {id: $id}), (t:Character {id: $target})
MERGE (e)-[:AGAINST]->(t)
```

### `GROUND_CLAIM`

```cypher
MATCH (c:Claim {id: $claim}), (e:Event {id: $event}) MERGE (c)-[:REFERS_TO]->(e)
```

### `WITNESS`

A witness's belief becomes 'witnessed' at full confidence, even if they had only heard the rumor before. Their old HEARD_FROM edges stay as corroboration; explain stops at a witnessed belief.

```cypher
UNWIND $witnesses AS wid
MATCH (w:Character {id: wid}), (c:Claim {id: $claim}), (e:Event {id: $event})
MERGE (w)-[:WITNESSED]->(e)
MERGE (b:Belief {holder: wid, claim: $claim})
ON CREATE SET b.created_at = $ts, b.status = 'active'
SET b.confidence = 1.0, b.origin = 'witnessed'
MERGE (b)-[:HELD_BY]->(w)
MERGE (b)-[:OF]->(c)
MERGE (b)-[:SAW]->(e)
RETURN wid
```

### inline in `_resolve_all()`

```cypher
MATCH (c:Character) RETURN c.id, c.name
```

### inline in `_claim_text()`

```cypher
MATCH (c:Claim {id: $id}) RETURN c.text
```

## `memory/cases.py`

Investigation cases: a case file in the graph that any investigator can pick up (PLAN.md Phase 4).

### `OPEN_CASE`

```cypher
MERGE (k:Case {id: $id})
ON CREATE SET k.title = $title, k.question = $question, k.status = 'open', k.opened_at = $ts
RETURN k.status
```

### `ASSIGN`

```cypher
MATCH (k:Case {id: $case}), (i:Character {id: $investigator})
OPTIONAL MATCH (other:Character)-[old:INVESTIGATES]->(k) WHERE other.id <> $investigator
SET old.active = false
MERGE (i)-[r:INVESTIGATES]->(k)
ON CREATE SET r.since = $ts
SET r.active = true
```

### `VILLAGERS`

The social structure only: villagers are NPCs that aren't investigators.

```cypher
MATCH (c:Character {kind: 'npc'}) WHERE NOT (c)-[:INVESTIGATES]->()
RETURN c.id, c.name
```

### `TIES`

Friendships (seeded) are the village's lasting structure; KNOWS also grows with every first conversation and soon links almost everyone (seen live: the two circles dissolved into one), so it's only a fallback.

```cypher
MATCH (a:Character)-[:{rel}]->(b:Character)
WHERE a.id IN $ids AND b.id IN $ids
RETURN a.id, b.id
```

### `BETWEENNESS`

```cypher
CALL algo.betweenness({{nodeLabels: ['Character'], relationshipTypes: ['{rel}']}}) YIELD node, score
RETURN node.id, score
```

### `HAS_FRIENDS`

```cypher
MATCH ()-[f:FRIEND]->() RETURN count(f) > 0
```

### `NEWS_HUBS`

LEARNED_FROM points listener -> speaker, so PageRank flows to the people others learn from.

```cypher
CALL algo.pageRank('Character', 'LEARNED_FROM') YIELD node, score RETURN node.id, score
```

### `TRUST_HUBS`

```cypher
CALL algo.pageRank('Character', 'KNOWS') YIELD node, score RETURN node.id, score
```

### `HAS_LEARNED_FROM`

```cypher
MATCH ()-[l:LEARNED_FROM]->() RETURN count(l) > 0
```

### `SAVE_BRIEFING`

```cypher
MATCH (k:Case {id: $case}) SET k.briefing = $briefing
```

### `ADD_LEADS`

```cypher
UNWIND $leads AS l
MATCH (k:Case {id: $case}), (t:Character {id: l.target})
MERGE (k)-[:HAS_LEAD]->(ld:Lead {case: $case, target: l.target})
ON CREATE SET ld.kind = l.kind, ld.reason = l.reason, ld.priority = l.priority, ld.status = 'open',
              ld.created_at = $ts
MERGE (ld)-[:TARGET]->(t)
```

### `CASE_FILE`

```cypher
MATCH (k:Case {id: $case})
OPTIONAL MATCH (i:Character)-[r:INVESTIGATES]->(k)
WITH k, collect({id: i.id, name: i.name, active: r.active, since: r.since}) AS investigators
OPTIONAL MATCH (k)-[:HAS_LEAD]->(ld:Lead)-[:TARGET]->(t:Character)
WITH k, investigators,
     collect({target: t.id, name: t.name, kind: ld.kind, reason: ld.reason, priority: ld.priority,
              status: ld.status, created_at: ld.created_at, done_at: ld.done_at}) AS leads
RETURN k.id, k.title, k.question, k.status, k.opened_at, k.briefing, investigators, leads, k.verdict
```

### `CASE_TEXT`

```cypher
MATCH (k:Case {id: $case}) RETURN k.title, k.question, k.embedding, k.status
```

### `SAVE_CASE_EMBEDDING`

```cypher
MATCH (k:Case {id: $case}) SET k.embedding = $embedding
```

### `ACTIVE_INVESTIGATOR`

```cypher
MATCH (i:Character)-[:INVESTIGATES {active: true}]->(:Case {id: $case})
RETURN i.id, i.name, i.kind, i.identity
```

### `CHARACTER`

```cypher
MATCH (c:Character {id: $id}) RETURN c.id, c.name, c.kind
```

### `TESTIMONY`

What the interviewee believes about the case, and only their *direct* sources: a villager knows who told them, not who told the teller. That's what makes the investigator follow the trail interview by interview.

```cypher
CALL db.idx.vector.queryNodes('Claim', 'embedding', 100, vecf32($q)) YIELD node, score
WITH node, score WHERE score < $max_distance
MATCH (node)<-[:OF]-(b:Belief {holder: $who, status: 'active'})
OPTIONAL MATCH (b)-[:HEARD_FROM]->(:Belief)-[:HELD_BY]->(src:Character)
RETURN node.id, node.text, b.origin, collect(DISTINCT src.id), collect(DISTINCT src.name), score
ORDER BY score
LIMIT $limit
```

### `START_INTERVIEW`

```cypher
MERGE (cv:Conversation {id: $id})
ON CREATE SET cv.status = 'new', cv.kind = 'interview'
WITH cv, cv.status AS before
SET cv.status = CASE WHEN before = 'ingested' THEN before ELSE 'ingesting' END
RETURN before
```

### `CLOSE_INTERVIEW`

```cypher
MATCH (cv:Conversation {id: $conv}), (k:Case {id: $case})
SET cv.status = 'ingested', cv.summary = $summary
MERGE (cv)-[:PART_OF]->(k)
WITH cv, k
MATCH (k)-[:HAS_LEAD]->(ld:Lead {target: $target})
SET ld.status = 'done', ld.done_at = $ts
MERGE (ld)-[:RESOLVED_BY]->(cv)
```

### `ADD_FINDING`

```cypher
MATCH (k:Case {id: $case}), (c:Claim {id: $claim}), (cv:Conversation {id: $conv})
MERGE (k)-[:HAS_FINDING]->(f:Finding {case: $case, claim: $claim, said_by: $said_by})
ON CREATE SET f.testimony = $testimony, f.sources = $sources, f.line = $line, f.at = $ts
MERGE (f)-[:ABOUT_CLAIM]->(c)
MERGE (f)-[:FROM_INTERVIEW]->(cv)
```

### `ADD_SOURCE_LEAD`

A named source becomes the next lead (or jumps the queue if already an open lead).

```cypher
MATCH (k:Case {id: $case}), (t:Character {id: $target})
MERGE (k)-[:HAS_LEAD]->(ld:Lead {case: $case, target: $target})
ON CREATE SET ld.kind = 'source', ld.reason = $reason, ld.priority = 0, ld.status = 'open', ld.created_at = $ts
ON MATCH SET ld.priority = CASE WHEN ld.status = 'open' THEN 0 ELSE ld.priority END,
             ld.reason = CASE WHEN ld.status = 'open' AND NOT ld.reason CONTAINS $reason
                              THEN ld.reason + ' ' + $reason ELSE ld.reason END
MERGE (ld)-[:TARGET]->(t)
RETURN ld.status
```

### `CHOSEN_LEAD`

An interview the investigator chose directly still gets a lead, so the case file records why it happened.

```cypher
MATCH (k:Case {id: $case}), (t:Character {id: $target})
MERGE (k)-[:HAS_LEAD]->(ld:Lead {case: $case, target: $target})
ON CREATE SET ld.kind = 'chosen', ld.reason = 'Chosen directly by the investigator.', ld.priority = 0,
              ld.status = 'open', ld.created_at = $ts
MERGE (ld)-[:TARGET]->(t)
```

### `FINDINGS`

```cypher
MATCH (:Case {id: $case})-[:HAS_FINDING]->(f:Finding)-[:ABOUT_CLAIM]->(c:Claim)
MATCH (s:Character) WHERE s.id = f.said_by
RETURN c.id, c.text, s.name, s.id, f.testimony, f.sources, f.line, f.at
ORDER BY f.at
```

### `INTERVIEWS`

```cypher
MATCH (cv:Conversation {kind: 'interview'})-[:PART_OF]->(:Case {id: $case})
MATCH (p:Character)-[:PARTICIPATED_IN]->(cv)
RETURN cv.id, cv.ended_at, cv.summary, collect(p.name), collect(p.id)
ORDER BY cv.ended_at
```

### `CASES`

```cypher
MATCH (k:Case)
OPTIONAL MATCH (i:Character)-[:INVESTIGATES {active: true}]->(k)
RETURN k.id, k.title, k.status, k.opened_at, collect(i.name)
ORDER BY k.opened_at DESC
```

### `NEAREST_CONFIRMED`

The closest confirmed claim, and whether the unfounded one is about the same person.

```cypher
MATCH (u:Claim {id: $claim})-[:ABOUT]->(us:Character)
MATCH (c:Claim)-[:ABOUT]->(cs:Character)
WHERE c.id IN $confirmed AND u.embedding IS NOT NULL AND c.embedding IS NOT NULL
RETURN c.text, vec.cosineDistance(u.embedding, c.embedding) AS d, us.id = cs.id, cs.name
ORDER BY d LIMIT 1
```

### `SUPERSEDE`

Publishing: every active belief in a debunked claim is kept but marked superseded (never deleted).

```cypher
MATCH (b:Belief {claim: $claim, status: 'active'})-[:HELD_BY]->(h:Character), (k:Case {id: $case})
SET b.status = 'superseded', b.valid_to = $ts
MERGE (b)-[d:DEBUNKED_BY]->(k)
SET d.kind = $kind, d.started_by = $started_by, d.by = $by
RETURN h.id
```

### `LOWER_TRUST`

```cypher
UNWIND $pairs AS p
MATCH (a:Character {id: p[0]}), (s:Character {id: p[1]})
MERGE (a)-[k:KNOWS]->(s)
ON CREATE SET k.trust = coalesce(a.gullibility, 0.5) * $penalty, k.interactions = 0
ON MATCH SET k.trust = k.trust * $penalty
RETURN a.name, s.name, k.trust
```

### `SOLVE`

```cypher
MATCH (k:Case {id: $case}) SET k.status = 'solved', k.solved_at = $ts, k.verdict = $verdict
```

## `memory/templates.py`

Village templates: seed a village once, then start any number of separate worlds from it with GRAPH.COPY.

### `COUNTS['characters']`

Separate queries on purpose: an OPTIONAL MATCH after an aggregating WITH can silently match nothing (step 2.4).

```cypher
MATCH (c:Character) RETURN count(c)
```

### `COUNTS['trust_links']`

Separate queries on purpose: an OPTIONAL MATCH after an aggregating WITH can silently match nothing (step 2.4).

```cypher
MATCH ()-[k:KNOWS]->() RETURN count(k)
```

### `COUNTS['friendships']`

Separate queries on purpose: an OPTIONAL MATCH after an aggregating WITH can silently match nothing (step 2.4).

```cypher
MATCH ()-[f:FRIEND]->() RETURN count(f)
```

## `memory/view.py`

Read-only views of a world's graph for the memory page (Phase 5). Each panel is a few small Cypher queries.

### `CHARACTERS`

```cypher
MATCH (c:Character)
OPTIONAL MATCH (c)<-[:HELD_BY]-(b:Belief {status: 'active'})
OPTIONAL MATCH (c)<-[:ABOUT]-(k:Claim)
RETURN c.id, c.name, c.kind, c.gullibility, count(DISTINCT b), count(DISTINCT k)
```

### `INVESTIGATORS`

```cypher
MATCH (c:Character)-[:INVESTIGATES]->(:Case) RETURN DISTINCT c.id
```

### `FRIENDSHIPS`

```cypher
MATCH (a:Character)-[:FRIEND]->(b:Character) RETURN a.id, b.id
```

### `NEWS_FLOW`

LEARNED_FROM points listener -> speaker; the page draws news flowing speaker -> listener.

```cypher
MATCH (lis:Character)-[l:LEARNED_FROM]->(spk:Character) RETURN spk.id, lis.id, l.count
```

### `TOTALS['beliefs']`

```cypher
MATCH (b:Belief {status: 'active'}) RETURN count(b)
```

### `TOTALS['outdated']`

```cypher
MATCH (b:Belief {status: 'superseded'}) RETURN count(b)
```

### `TOTALS['claims']`

```cypher
MATCH (c:Claim) RETURN count(c)
```

### `TOTALS['conversations']`

```cypher
MATCH (c:Conversation {status: 'ingested'}) RETURN count(c)
```

### `NEW_BELIEFS`

Same shape as scripts/live_feed.py: every belief as it forms, with who it came from and the line they heard.

```cypher
MATCH (h:Character)<-[:HELD_BY]-(b:Belief)-[:OF]->(c:Claim)
WHERE b.created_at > $since
OPTIONAL MATCH (b)-[:HEARD_FROM]->(:Belief)-[:HELD_BY]->(src:Character)
OPTIONAL MATCH (b)-[:EVIDENCE]->(m:Message)<-[:SAID]-(src)
RETURN b.created_at, h.id, h.name, b.origin, b.confidence, b.status, c.id, c.text, c.valence,
       src.id, src.name, m.text
ORDER BY b.created_at DESC LIMIT $limit
```

### `REPUTATION`

What the village thinks of each person: each villager's opinion is the average of confidence x valence over their active beliefs about that person (-1 to +1), and the village's view averages the villagers who have one. Averages, not sums: a sum grows with how much someone is talked about, so the most gossiped-about person would always look worst. Investigators' notes don't count.

```cypher
MATCH (h:Character)<-[:HELD_BY]-(b:Belief {status: 'active'})-[:OF]->(c:Claim)-[:ABOUT]->(x:Character)
WHERE h <> x AND NOT (h)-[:INVESTIGATES]->()
WITH x, h, avg(b.confidence * c.valence) AS opinion
RETURN x.id, x.name, avg(opinion), count(h),
       sum(CASE WHEN opinion < -0.15 THEN 1 ELSE 0 END), sum(CASE WHEN opinion > 0.15 THEN 1 ELSE 0 END)
```

### `TOP_CLAIM`

The most widely believed claim about each person.

```cypher
MATCH (b:Belief {status: 'active'})-[:OF]->(c:Claim)-[:ABOUT]->(x:Character)
WITH x, c, count(b) AS believers ORDER BY believers DESC
RETURN x.id, collect(c.text)[0], collect(believers)[0]
```
