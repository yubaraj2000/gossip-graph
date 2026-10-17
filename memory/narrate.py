"""Narrator: record something that really happened (docs/DATA_MODEL.md: Event = ground truth).

The event's claim gets the same key NPC gossip would produce ("kabir|stole_from|p:0"), so rumors about it,
before or after, attach to the same grounded claim. Witnesses hold it as 'witnessed' at full confidence.
"""
import hashlib
import time

from falkordb import Graph

from memory import db, extract, ingest, llm
from memory.models import EventIn

CREATE_EVENT = """
MATCH (a:Character {id: $actor})
MERGE (e:Event {id: $id})
ON CREATE SET e.kind = $kind, e.description = $description, e.ts = $ts, e.severity = $severity
MERGE (a)-[:DID]->(e)
RETURN e.id
"""

LINK_TARGET = """
MATCH (e:Event {id: $id}), (t:Character {id: $target})
MERGE (e)-[:AGAINST]->(t)
"""

GROUND_CLAIM = "MATCH (c:Claim {id: $claim}), (e:Event {id: $event}) MERGE (c)-[:REFERS_TO]->(e)"

# A witness's belief becomes 'witnessed' at full confidence, even if they had only heard the rumor before.
# Their old HEARD_FROM edges stay as corroboration; explain stops at a witnessed belief.
WITNESS = """
UNWIND $witnesses AS wid
MATCH (w:Character {id: wid}), (c:Claim {id: $claim}), (e:Event {id: $event})
MERGE (w)-[:WITNESSED]->(e)
MERGE (b:Belief {holder: wid, claim: $claim})
ON CREATE SET b.created_at = $ts, b.status = 'active', b.recorded_at = timestamp()
SET b.confidence = 1.0, b.origin = 'witnessed'
MERGE (b)-[:HELD_BY]->(w)
MERGE (b)-[:OF]->(c)
MERGE (b)-[:SAW]->(e)
RETURN wid
"""


class UnknownCharacters(ValueError):
    pass


def narrate(world_id: str, event: EventIn) -> dict:
    if event.kind not in extract.PREDICATES:
        raise ValueError(f"kind must be one of {extract.PREDICATES}, got {event.kind!r}")
    db.ensure_world(world_id)
    g = db.world_graph(world_id)
    actor, target, witnesses = _resolve_all(g, event)
    ts = event.ts if event.ts is not None else time.time() * 1000
    event_id = event.id or "e_" + hashlib.sha1(
        f"{event.kind}|{actor}|{target}|{event.description}".encode()).hexdigest()[:12]

    g.query(CREATE_EVENT, {"id": event_id, "actor": actor, "kind": event.kind, "description": event.description,
                           "ts": ts, "severity": event.severity})
    if target:
        g.query(LINK_TARGET, {"id": event_id, "target": target})

    text = event.claim or event.description
    claim = {"key": f"{actor}|{event.kind}|{target or ''}", "subject": actor, "predicate": event.kind,
             "object": target or "", "text": text, "valence": event.valence}
    claim_id = ingest.resolve_claim(g, claim, llm.embed([text])[0], ts)
    g.query(GROUND_CLAIM, {"claim": claim_id, "event": event_id})
    seen = [w for w in witnesses if w != actor]  # the actor knows what they did; we don't model self-belief
    g.query(WITNESS, {"witnesses": seen, "claim": claim_id, "event": event_id, "ts": ts})
    return {"world": world_id, "event": event_id, "claim": claim_id, "claim_text": _claim_text(g, claim_id),
            "witnesses": seen}


def _resolve_all(g: Graph, event: EventIn) -> tuple[str, str | None, list[str]]:
    rows = g.ro_query("MATCH (c:Character) RETURN c.id, c.name").result_set
    ids = {cid for cid, _ in rows}
    people = {name.lower(): cid for cid, name in rows}

    def resolve(ref: str) -> str | None:
        return ref if ref in ids else ingest.resolve_person(ref, people)

    refs = [event.actor, *([event.target] if event.target else []), *event.witnesses]
    unknown = [r for r in refs if resolve(r) is None]
    if unknown:
        raise UnknownCharacters(f"unknown characters: {unknown}")
    return resolve(event.actor), resolve(event.target) if event.target else None, [resolve(w) for w in event.witnesses]


def _claim_text(g: Graph, claim_id: str) -> str:
    return g.ro_query("MATCH (c:Claim {id: $id}) RETURN c.text", {"id": claim_id}).result_set[0][0]
