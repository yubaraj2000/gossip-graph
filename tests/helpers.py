"""Shared test village, scripted-LLM helpers and assertions."""
import hashlib
import random

from memory import db
from memory.models import CharacterIn, ConversationIn

VILLAGE = [
    CharacterIn(id="p:1", name="Bram", gullibility=0.5),
    CharacterIn(id="p:2", name="Pip", gullibility=0.9),
    CharacterIn(id="p:3", name="Mara", gullibility=0.8),
    CharacterIn(id="p:4", name="Tom", gullibility=0.3),
    CharacterIn(id="p:9", name="Kai", kind="human"),
]
NAMES = {c.id: c.name for c in VILLAGE}
THEFT = {"subject": "Kai", "predicate": "stole_from", "object": "Bram",
         "text": "Kai stole a silver hammer from Bram", "valence": -1}
TROUBLEMAKER = {"subject": "Kai", "predicate": "is", "object": "",
                "text": "Kai has always been a troublemaker", "valence": -0.2}
FENCE = {"subject": "Kai", "predicate": "did", "object": "",
         "text": "Kai was spotted trying to fence a stolen hammer", "valence": -1}
# Texts the fake embedder treats as near-duplicates of another text (like a real close paraphrase).
ALIASES = {"Kai swiped Bram's silver hammer": "Kai stole a silver hammer from Bram"}


# Texts the fake embedder puts at about 0.18 cosine distance from another text: a garbled retelling, not the
# same claim (dedup merges below 0.10) but close enough to count as a distortion (below 0.27).
DISTORTIONS = {"Kai lost Bram's hammer somewhere": "Kai stole a silver hammer from Bram",
               "Tom concluded Kai took Bram's hammer": "Kai stole a silver hammer from Bram"}


def fake_embed(texts):
    out = []
    for t in texts:
        rng = random.Random(hashlib.md5(ALIASES.get(t, DISTORTIONS.get(t, t)).encode()).hexdigest())
        v = [rng.gauss(0, 1) for _ in range(1024)]
        if t in ALIASES:
            v[0] += 0.5  # close, but not identical
        if t in DISTORTIONS:
            noise = random.Random(t)
            v = [x + 0.7 * noise.gauss(0, 1) for x in v]
        out.append(v)
    return out


def conv(cid, *lines):
    authors = {a for a, _ in lines}
    return ConversationIn(
        id=cid,
        participants=[c for c in VILLAGE if c.id in authors],
        messages=[{"author": a, "text": t, "ts": 1000 + i} for i, (a, t) in enumerate(lines)],
    )


def two_way(cid, speaker, listener, text):
    """A two-message conversation: speaker says `text`, listener reacts."""
    return conv(cid, (speaker, text), (listener, "Really? I can't believe it!"))


def belief(world_id, holder, claim_text="Kai stole a silver hammer from Bram"):
    rows = db.world_graph(world_id).ro_query(
        "MATCH (b:Belief {holder:$h})-[:OF]->(c:Claim {text:$t}) RETURN b.confidence, b.origin",
        {"h": holder, "t": claim_text}).result_set
    return (round(rows[0][0], 3), rows[0][1]) if rows else None


def seed_witnessed_theft(world_id):
    """What the step 3.3 narrator will do: a real event, a grounded claim, and Bram's eyewitness belief."""
    db.world_graph(world_id).query("""
        MATCH (kai:Character {id:'p:9'}), (bram:Character {id:'p:1'})
        CREATE (e:Event {id:'e1', kind:'stole_from', description:'Kai stole a silver hammer from Bram', ts:0}),
               (kai)-[:DID]->(e), (e)-[:AGAINST]->(bram), (bram)-[:WITNESSED]->(e),
               (c:Claim {id:'k_seed', key:'p:9|stole_from|p:1', predicate:'stole_from', object:'p:1',
                         text:'Kai stole a silver hammer from Bram', valence:-1.0, embedding: vecf32($emb)}),
               (c)-[:ABOUT]->(kai), (c)-[:REFERS_TO]->(e),
               (b:Belief {holder:'p:1', claim:'k_seed', confidence:1.0, origin:'witnessed', status:'active'}),
               (b)-[:HELD_BY]->(bram), (b)-[:OF]->(c), (b)-[:SAW]->(e)""",
        {"emb": fake_embed(["Kai stole a silver hammer from Bram"])[0]})  # real claims always have an embedding
