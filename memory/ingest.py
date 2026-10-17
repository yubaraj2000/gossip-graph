"""Ingest a finished conversation: transcript -> claims -> beliefs with provenance (docs/DATA_MODEL.md, Q1)."""
import hashlib
import re
import time

from falkordb import Graph

from memory import db, extract, llm
from memory.models import CharacterIn, ConversationIn, RelationshipIn

# Confidence of a belief the speaker asserts without any traceable source (invented, or first-hand but unrecorded).
INVENTED_CONFIDENCE = 0.6
# Claims about the same subject closer than this (cosine distance) are the same claim. Measured on mxbai-embed-large:
# paraphrase 0.089 (same), looser paraphrase 0.177 / rumor mutation 0.181 (kept separate).
DEDUP_MAX_DISTANCE = 0.10
# An 'ingesting' conversation older than this is assumed to belong to a crashed run and may be taken again.
STALE_INGEST_MS = 10 * 60 * 1000
# Claims this close to neutral are not gossip ("Lakshmi heard fascinating tales lately", valence 0.0). Recall ranks
# by |valence|, so they would never surface anyway; dropping them keeps the graph readable.
MIN_ABS_VALENCE = 0.15
# Instructions, plans and speculation aren't claims ("Ask Meera about...", "I'll ask Sarla...", "Perhaps Balwant...").
NOT_A_STATEMENT = re.compile(
    r"^(ask|tell|let'?s|let|go|find|check|look|see|please|don'?t|i'?ll|i will|i'm going|we should|we need"
    r"|perhaps|maybe|possibly|might)\b",
    re.IGNORECASE)
# Forms of address dropped when matching names ("Pandit ji", "Gopal bhai", "Balwant Singh").
HONORIFICS = {"ji", "bhai", "didi", "sahib", "saab", "baba", "kaka", "chacha", "singh", "mr", "mrs", "the"}
# Predicates whose object must be a person; otherwise the claim is downgraded to "did".
PERSON_PREDICATES = {"stole_from", "attacked", "helped", "lied_to", "gave_to", "owes", "likes", "dislikes"}

UPSERT_CHARACTERS = """
UNWIND $chars AS ch
MERGE (c:Character {id: ch.id})
SET c.name = ch.name, c.kind = ch.kind,
    c.identity = CASE WHEN ch.identity = '' THEN c.identity ELSE ch.identity END,
    c.gullibility = coalesce(ch.gullibility, c.gullibility)
"""

# Seeded social graph (village file). KNOWS carries trust for gossip and is also created by talking, so it
# densifies over time; FRIEND marks only the village's lasting friendships (the structure the investigator's
# briefing reads). Re-seeding updates trust but keeps the interaction count.
SET_RELATIONSHIPS = """
UNWIND $rels AS r
MATCH (a:Character {id: r.source}), (b:Character {id: r.target})
MERGE (a)-[k:KNOWS]->(b)
ON CREATE SET k.interactions = 0
SET k.trust = r.trust
MERGE (a)-[:FRIEND]->(b)
RETURN count(k)
"""

# Atomically claim the conversation for ingestion. Queries on one graph run one at a time, so when AI Town
# sends the same conversation twice (once per NPC participant), exactly one caller gets `mine = true`.
# A run that crashed mid-ingest leaves 'ingesting' behind; after STALE_INGEST_MS it can be taken again.
TAKE_CONVERSATION = """
MERGE (cv:Conversation {id: $id})
ON CREATE SET cv.status = 'new'
WITH cv, (cv.status IN ['new', 'failed']
          OR (cv.status = 'ingesting' AND coalesce(cv.taken_at, 0) < $stale_before)) AS mine
SET cv.status = CASE WHEN mine THEN 'ingesting' ELSE cv.status END,
    cv.taken_at = CASE WHEN mine THEN $now ELSE cv.taken_at END
RETURN mine
"""

# Participants are linked even if they never spoke (e.g. a silent human player).
LINK_PARTICIPANTS = """
MATCH (cv:Conversation {id: $id})
SET cv.started_at = $started_at, cv.ended_at = $ended_at
WITH cv
UNWIND $participants AS pid
MATCH (p:Character {id: pid})
MERGE (p)-[:PARTICIPATED_IN]->(cv)
"""

WRITE_MESSAGES = """
MATCH (cv:Conversation {id: $id})
UNWIND $msgs AS m
MATCH (a:Character {id: m.author})
MERGE (msg:Message {id: m.id})
ON CREATE SET msg.idx = m.idx, msg.text = m.text, msg.ts = m.ts
MERGE (a)-[:SAID]->(msg)
MERGE (msg)-[:IN]->(cv)
"""

# Talking makes people acquainted: first contact trusts at the listener's gullibility.
TOUCH_KNOWS = """
UNWIND $pairs AS p
MATCH (a:Character {id: p[0]}), (b:Character {id: p[1]})
MERGE (a)-[k:KNOWS]->(b)
ON CREATE SET k.trust = coalesce(a.gullibility, 0.5), k.interactions = 0
SET k.interactions = k.interactions + 1, k.last_talked = $ts
"""

FIND_SIMILAR_CLAIM = """
CALL db.idx.vector.queryNodes('Claim', 'embedding', 10, vecf32($embedding)) YIELD node, score
MATCH (node)-[:ABOUT]->(:Character {id: $subject})
WHERE score < $max_distance
RETURN node.id ORDER BY score LIMIT 1
"""

CREATE_CLAIM = """
MATCH (s:Character {id: $subject})
MERGE (c:Claim {key: $key})
ON CREATE SET c.id = $id, c.predicate = $predicate, c.object = $object, c.text = $text,
              c.valence = $valence, c.embedding = vecf32($embedding), c.created_at = $ts
MERGE (c)-[:ABOUT]->(s)
RETURN c.id
"""

# A speaker asserting a claim they hold no belief in becomes its origin ('self').
ENSURE_SPEAKER_BELIEF = """
MATCH (spk:Character {id: $speaker}), (c:Claim {id: $claim})
MERGE (b:Belief {holder: $speaker, claim: $claim})
ON CREATE SET b.confidence = $confidence, b.origin = 'self', b.status = 'active', b.created_at = $ts
MERGE (b)-[:HELD_BY]->(spk)
MERGE (b)-[:OF]->(c)
WITH b
MATCH (m:Message {id: $msg})
MERGE (b)-[:EVIDENCE]->(m)
RETURN b.origin
"""

# Q1 from DATA_MODEL.md, with two guards:
#  - echo: the listener's own belief is upstream of the speaker's, so hearing it back adds nothing
#  - repeat: the listener already heard this claim from this speaker's belief
HEAR = """
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
"""

FINISH = "MATCH (cv:Conversation {id: $id}) SET cv.status = $status, cv.summary = $summary, cv.error = $error"

# Run at service start: an 'ingesting' conversation can only be left over from a run that died.
RECOVER_INTERRUPTED = """
MATCH (cv:Conversation {status: 'ingesting'})
SET cv.status = 'failed', cv.error = 'interrupted: the memory service stopped mid-ingest'
RETURN count(cv)
"""

FAILED_CONVERSATIONS = """
MATCH (cv:Conversation {status: 'failed'})
RETURN cv.id ORDER BY coalesce(cv.ended_at, 0) LIMIT $limit
"""

LOAD_PARTICIPANTS = """
MATCH (p:Character)-[:PARTICIPATED_IN]->(:Conversation {id: $id})
RETURN p.id, p.name, coalesce(p.kind, 'npc')
"""

LOAD_MESSAGES = """
MATCH (a:Character)-[:SAID]->(m:Message)-[:IN]->(:Conversation {id: $id})
RETURN a.id, m.text, m.ts ORDER BY m.idx
"""


def upsert_characters(g: Graph, chars: list[CharacterIn]) -> None:
    g.query(UPSERT_CHARACTERS, {"chars": [c.model_dump() for c in chars]})


def set_relationships(g: Graph, rels: list[RelationshipIn]) -> int:
    """Create or update KNOWS trust edges; returns how many were set (pairs with unknown ids are skipped)."""
    return g.query(SET_RELATIONSHIPS, {"rels": [r.model_dump() for r in rels]}).result_set[0][0]


def ingest_conversation(world_id: str, conv: ConversationIn) -> dict:
    """Store a finished conversation and turn its claims into beliefs. Idempotent per conversation id."""
    db.ensure_world(world_id)
    g = db.world_graph(world_id)
    upsert_characters(g, conv.participants)
    now = time.time() * 1000
    if not g.query(TAKE_CONVERSATION, {"id": conv.id, "now": now,
                                       "stale_before": now - STALE_INGEST_MS}).result_set[0][0]:
        return {"conversation": conv.id, "status": "skipped"}
    try:
        result = _ingest(g, conv)
    except Exception as e:
        g.query(FINISH, {"id": conv.id, "status": "failed", "summary": None, "error": str(e)[:500]})
        raise
    g.query(FINISH, {"id": conv.id, "status": "ingested", "summary": result["summary"], "error": None})
    return {"conversation": conv.id, "status": "ingested", **result}


def recover_interrupted(world_id: str) -> int:
    """Mark conversations a crashed run left in 'ingesting' as 'failed', so retry_failed picks them up."""
    return db.world_graph(world_id).query(RECOVER_INTERRUPTED).result_set[0][0]


def retry_failed(world_id: str, limit: int = 10) -> list[dict]:
    """Re-ingest failed conversations from the transcript already stored in the graph."""
    g = db.world_graph(world_id)
    results = []
    for (cid,) in g.ro_query(FAILED_CONVERSATIONS, {"limit": limit}).result_set:
        conv = load_conversation(g, cid)
        if conv is None:
            results.append({"conversation": cid, "status": "failed", "error": "transcript incomplete, cannot rebuild"})
            continue
        try:
            results.append(ingest_conversation(world_id, conv))
        except llm.LLMError as e:
            results.append({"conversation": cid, "status": "failed", "error": str(e)})
            break  # the model is down; the remaining ones would fail the same way
    return results


def load_conversation(g: Graph, cid: str) -> ConversationIn | None:
    participants = [{"id": pid, "name": name, "kind": kind}
                    for pid, name, kind in g.ro_query(LOAD_PARTICIPANTS, {"id": cid}).result_set]
    messages = [{"author": a, "text": t, "ts": ts} for a, t, ts in g.ro_query(LOAD_MESSAGES, {"id": cid}).result_set]
    try:
        return ConversationIn(id=cid, participants=participants, messages=messages)
    except ValueError:
        return None


def record_transcript(g: Graph, conv: ConversationIn) -> tuple[list[dict], list[str], float]:
    """Store participants, messages and acquaintance for a conversation whose node already exists."""
    msgs = [{"id": f"{conv.id}:{i}", "idx": i, "author": m.author, "text": m.text, "ts": m.ts}
            for i, m in enumerate(conv.messages)]
    ts = msgs[-1]["ts"] if msgs else 0
    ids = [p.id for p in conv.participants]
    g.query(LINK_PARTICIPANTS, {"id": conv.id, "participants": ids,
                                "started_at": msgs[0]["ts"] if msgs else None, "ended_at": ts})
    g.query(WRITE_MESSAGES, {"id": conv.id, "msgs": msgs})
    g.query(TOUCH_KNOWS, {"pairs": [[a, b] for a in ids for b in ids if a != b], "ts": ts})
    return msgs, ids, ts


def hear(g: Graph, listener: str, speaker: str, claim: str, msg_id: str, ts: float) -> float | None:
    """Q1: the listener heard the claim from the speaker in message msg_id. Returns the listener's new
    confidence, or None when a guard (echo / repeat) or a missing speaker belief stopped it."""
    row = g.query(HEAR, {"listener": listener, "speaker": speaker, "claim": claim, "msg": msg_id,
                         "ts": ts}).result_set
    return row[0][0] if row else None


def _ingest(g: Graph, conv: ConversationIn) -> dict:
    msgs, ids, ts = record_transcript(g, conv)
    if not msgs:
        return {"summary": "", "claims": [], "beliefs": [], "dropped": []}

    rows = g.ro_query("MATCH (c:Character) RETURN c.id, c.name").result_set
    people = {name.lower(): cid for cid, name in rows}
    raw = extract.extract(conv, known_people=sorted(name for _, name in rows))
    raw_claims = raw.get("claims") or []
    if not isinstance(raw_claims, list):
        raise llm.LLMError(f"claims is {type(raw_claims).__name__}, expected a list")
    claims, dropped = _validate(raw_claims, msgs, people)
    embeddings = llm.embed([c["text"] for c in claims])
    if len(embeddings) != len(claims):
        raise llm.LLMError(f"got {len(embeddings)} embeddings for {len(claims)} claims")

    beliefs = []
    for c, emb in zip(claims, embeddings):
        c["id"] = resolve_claim(g, c, emb, ts)
        msg = msgs[c["message_index"]]
        g.query(ENSURE_SPEAKER_BELIEF, {"speaker": c["speaker"], "claim": c["id"], "confidence": INVENTED_CONFIDENCE,
                                        "msg": msg["id"], "ts": msg["ts"]})
        for listener in ids:
            if listener in (c["speaker"], c["subject"]):  # nobody adopts a claim about themselves
                continue
            conf = hear(g, listener, c["speaker"], c["id"], msg["id"], msg["ts"])
            if conf is not None:
                beliefs.append({"holder": listener, "claim": c["id"], "confidence": round(conf, 3),
                                "from": c["speaker"]})
    return {"summary": str(raw.get("summary") or ""), "claims": claims, "beliefs": beliefs, "dropped": dropped}


def _validate(raw_claims: list[dict], msgs: list[dict], people: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Enforce in code what the small model doesn't reliably follow in the prompt."""
    ok, dropped = [], []
    id_to_name = {cid: name for name, cid in people.items()}
    parsed = []
    for rc in raw_claims:  # one malformed claim must not sink the others
        if not isinstance(rc, dict):
            dropped.append({"claim": rc, "reason": "malformed claim"})
            continue
        idx, valence = _as_number(rc.get("message_index"), int), _as_number(rc.get("valence"), float)
        if valence is None:
            dropped.append({**rc, "reason": "malformed claim"})
            continue
        if abs(valence) < MIN_ABS_VALENCE:
            dropped.append({**rc, "reason": "neutral, not gossip"})
            continue
        parsed.append((idx, valence, rc))
    for idx, valence, rc in sorted(parsed, key=lambda p: -1 if p[0] is None else p[0]):
        subject = resolve_person(_text(rc.get("subject")), people)
        text = _text(rc.get("text"))
        if idx is None or not 0 <= idx < len(msgs):
            dropped.append({**rc, "reason": "message_index out of range"})
            continue
        if subject is None:
            dropped.append({**rc, "reason": "unknown subject"})
            continue
        if subject == msgs[idx]["author"]:
            # People don't spread gossip about themselves. When the model makes the speaker the subject, it has
            # misread reported speech or chatter ("Ramesh stole something from his own forge", said by Ramesh), and a
            # verdict would then wrongly blame the speaker as the rumor's starter (seen in the Oct 17 rehearsal).
            dropped.append({**rc, "reason": "speaker is the subject"})
            continue
        if NOT_A_STATEMENT.match(text) or text.endswith("?") or text[:1].islower():
            # instructions/plans, questions, and lowercase fragments ("does that mean you've got it fixed…")
            dropped.append({**rc, "reason": "not a statement"})
            continue
        if not names_person(text, id_to_name[subject]):
            dropped.append({**rc, "reason": "text does not name the subject"})
            continue
        predicate = rc.get("predicate") if rc.get("predicate") in extract.PREDICATES else "did"
        obj = resolve_person(_text(rc.get("object")), people)
        if predicate in PERSON_PREDICATES and obj is None:
            # e.g. object "a silver hammer" for stole_from: take the other person named in the text instead
            obj = next((cid for name, cid in people.items() if cid != subject and names_person(text, name)), None)
            if obj is None:
                predicate = "did"
        # A structured key only identifies a claim when it names two people ("kabir|stole_from|p:0": "stole" and
        # "swiped" merge). Generic claims ("Kai did …", "Kai is …") would all collapse into "p:9|did|", so their
        # key is their own normalized text, and paraphrases of them merge by meaning (resolve_claim's vector step).
        object_key = obj if predicate in PERSON_PREDICATES and obj else _normalize_text(text)
        ok.append({
            "message_index": idx,
            "speaker": msgs[idx]["author"],
            "subject": subject,
            "predicate": predicate,
            "object": obj or _text(rc.get("object")),
            "key": f"{subject}|{predicate}|{object_key}",
            "text": text,
            "valence": max(-1.0, min(1.0, valence)),
        })
    return ok, dropped


def resolve_claim(g: Graph, c: dict, embedding: list[float], ts: float) -> str:
    """Same structured key -> same claim; else a near-identical claim about the same subject; else a new claim."""
    existing = g.ro_query("MATCH (k:Claim {key: $key}) RETURN k.id", {"key": c["key"]}).result_set
    if existing:
        return existing[0][0]
    similar = g.ro_query(FIND_SIMILAR_CLAIM, {"embedding": embedding, "subject": c["subject"],
                                              "max_distance": DEDUP_MAX_DISTANCE}).result_set
    if similar:
        return similar[0][0]
    claim_id = "k_" + hashlib.sha1(c["key"].encode()).hexdigest()[:12]
    return g.query(CREATE_CLAIM, {**{k: c[k] for k in ("key", "subject", "predicate", "object", "text", "valence")},
                                  "id": claim_id, "embedding": embedding, "ts": ts}).result_set[0][0]


def _as_number(value, kind):
    """int/float from model output that may be a number, a numeric string, or junk ("very bad")."""
    if isinstance(value, bool):
        return None
    try:
        return kind(value)
    except (TypeError, ValueError):
        return None


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def resolve_person(raw: str, people: dict[str, str]) -> str | None:
    """Character id for a name as the model wrote it: exact, or an unambiguous match ignoring forms of address
    ("Balwant Singh" -> Balwant, "Shastri ji" / "Pandit ji" -> Pandit Shastri). Unknown people -> None."""
    exact = people.get(raw.lower())
    if exact or not raw:
        return exact
    words = {w for w in re.findall(r"[a-z]+", raw.lower()) if w not in HONORIFICS}
    matches = {cid for name, cid in people.items() if words & set(re.findall(r"[a-z]+", name.lower()))}
    return matches.pop() if len(matches) == 1 else None


def names_person(text: str, name: str) -> bool:
    """The text refers to this person by any word of their name ("Shastri ji" names Pandit Shastri)."""
    return any(_mentions(text, w) for w in name.split() if w.lower() not in HONORIFICS)


def _mentions(text: str, name: str) -> bool:
    return re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE) is not None


def _normalize_text(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", text.lower()).split())


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^(a|an|the)\s+", "", s.strip().lower()))
