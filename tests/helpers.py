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
# Texts the fake embedder treats as near-duplicates of another text (like a real close paraphrase).
ALIASES = {"Kai swiped Bram's silver hammer": "Kai stole a silver hammer from Bram"}


def fake_embed(texts):
    out = []
    for t in texts:
        rng = random.Random(hashlib.md5(ALIASES.get(t, t).encode()).hexdigest())
        v = [rng.gauss(0, 1) for _ in range(1024)]
        if t in ALIASES:
            v[0] += 0.5  # close, but not identical
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
