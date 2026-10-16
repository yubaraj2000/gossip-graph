"""Recall: what an NPC remembers when it is about to talk to someone (docs/DATA_MODEL.md, Q2/Q3/Q5).

Pure Cypher, no LLM: this sits on the conversation hot path. It replaces AI Town's vector `searchMemories`.
"""
import re

from memory import db

# Gossip ranking: confidence x |valence| x relevance, damped when the two already exchanged this claim.
ALREADY_SHARED_DAMPING = 0.2
# The topic goes into the NPC's prompt; it comes from NPC-made claims, so keep it short and plain.
TOPIC_MAX_CHARS = 200
# Topic choice looks further than the k memories shown, and favours first-hand news.
TOPIC_CANDIDATES = 10
WITNESSED_TOPIC_BOOST = 1.5

CHARACTERS = "MATCH (c:Character) WHERE c.id IN [$me, $other] RETURN c.id, c.name"

# Q2 plus "already shared": the other's belief came from mine, or mine came from theirs.
# All OPTIONAL MATCHes come before the aggregating WITH: on FalkorDB 6.0.2 an OPTIONAL MATCH placed after
# "OPTIONAL MATCH ... WITH <aggregation>" silently matched nothing (see RESEARCH_LOG, step 2.4).
BELIEFS = """
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
"""

# Q5: my overall view of the other, from everything I believe about them.
REPUTATION = """
MATCH (:Character {id: $me})<-[:HELD_BY]-(b:Belief {status: 'active'})-[:OF]->(c:Claim)-[:ABOUT]->(:Character {id: $other})
RETURN coalesce(sum(b.confidence * c.valence), 0.0), count(b)
"""

TRUST = """
MATCH (:Character {id: $me})-[k:KNOWS]->(:Character {id: $other})
RETURN k.trust, k.interactions
"""

# Beliefs a published verdict corrected: kept as 'superseded' (memory updates without deleting history).
DEBUNKED = """
MATCH (:Character {id: $me})<-[:HELD_BY]-(b:Belief {status: 'superseded'})-[:OF]->(c:Claim),
      (b)-[d:DEBUNKED_BY]->(:Case)
RETURN c.text, d.kind, d.started_by, d.by
ORDER BY b.valid_to DESC
LIMIT 2
"""

# Q3: our most recent conversations.
EPISODES = """
MATCH (:Character {id: $me})-[:PARTICIPATED_IN]->(cv:Conversation {status: 'ingested'})<-[:PARTICIPATED_IN]-(:Character {id: $other})
RETURN cv.id, cv.summary, cv.ended_at
ORDER BY cv.ended_at DESC
LIMIT $n
"""


def recall(world_id: str, me: str, other: str, k: int = 5, episodes: int = 3) -> dict:
    g = db.world_graph(world_id)
    if db.graph_name(world_id) not in db.client().list_graphs():
        return _empty(me, other)
    names = dict(g.ro_query(CHARACTERS, {"me": me, "other": other}).result_set)
    if me not in names:
        return _empty(me, other)
    other_name = names.get(other, "them")

    candidates = [
        {"claim": cid, "subject": sid, "subject_name": sname, "text": text, "valence": valence,
         "confidence": round(conf, 3), "origin": origin, "told_by": told_by,
         "about_other": sid == other, "already_shared": shared, "score": round(score, 3)}
        for cid, sid, sname, text, valence, conf, origin, told_by, shared, score in g.ro_query(
            BELIEFS, {"me": me, "other": other, "k": max(k, TOPIC_CANDIDATES),
                      "damping": ALREADY_SHARED_DAMPING}).result_set
    ]
    beliefs = candidates[:k]
    rep_score, evidence = g.ro_query(REPUTATION, {"me": me, "other": other}).result_set[0]
    trust_rows = g.ro_query(TRUST, {"me": me, "other": other}).result_set
    eps = [{"conversation": cid, "summary": summary, "ended_at": ended}
           for cid, summary, ended in g.ro_query(EPISODES, {"me": me, "other": other, "n": episodes}).result_set]

    debunked = [{"text": text, "kind": kind, "started_by": started_by, "by": by}
                for text, kind, started_by, by in g.ro_query(DEBUNKED, {"me": me}).result_set]
    result = {
        "me": me, "other": other, "known": True,
        "beliefs": beliefs,
        "debunked": debunked,
        "reputation": {"score": round(rep_score, 3), "evidence": evidence},
        "trust": {"trust": trust_rows[0][0], "interactions": trust_rows[0][1]} if trust_rows else None,
        "episodes": eps,
    }
    result["memories"] = describe(result, names[me], other_name)
    result["topic"] = topic(candidates, names[me])
    return result


def topic(candidates: list[dict], my_name: str) -> str | None:
    """The one piece of news the graph wants this NPC to open with, in its own words. The small dialogue model
    only has to voice it (step 3.4: with memories alone it never passed on the theft; with a topic it mostly did).

    Gossip is news about third parties: claims about the listener are used only if there's nothing else
    (telling Chotu a rumor about Chotu is a confrontation, not gossip). First-hand news ranks higher."""
    fresh = [b for b in candidates if not b["already_shared"] and b["score"] > 0]
    pool = [b for b in fresh if not b["about_other"]] or fresh
    if not pool:
        return None
    b = max(pool, key=lambda b: b["confidence"] * abs(b["valence"])
            * (WITNESSED_TOPIC_BOOST if b["origin"] == "witnessed" else 1.0))
    text = as_me(b["text"], my_name).rstrip(".")
    if b["origin"] == "witnessed":
        line = f"I saw it with my own eyes: {text}."
    elif b["origin"] == "heard":
        line = f"{and_names(b['told_by'])} told me that {lower_first(text)}."
    else:
        line = f"{text}."
    return " ".join(line.replace('"', "'").split())[:TOPIC_MAX_CHARS]


def describe(r: dict, my_name: str, other_name: str) -> list[str]:
    """First-person memory lines for the NPC's prompt. Words instead of numbers, so dialogue stays natural."""
    lines = []
    trust = r["trust"]
    if trust is None:
        lines.append(f"I don't really know {other_name} yet.")
    else:
        talks = trust["interactions"] or 0
        lines.append(f"I {_trust_words(trust['trust'])} {other_name}; "
                     + (f"we've talked {talks} time(s)." if talks else "we haven't really talked yet."))
    if r["reputation"]["evidence"]:
        lines.append(f"My impression of {other_name} is {_reputation_words(r['reputation']['score'])}.")
    if r["episodes"]:
        lines.append(f"Last time {other_name} and I talked: {r['episodes'][0]['summary']}")
    for d in r.get("debunked", []):
        text = lower_first(as_me(d["text"], my_name).rstrip("."))
        if d["kind"] == "distorted":
            lines.append(f"I had heard that {text}, but {d['by']}'s inquiry showed it was a garbled version of "
                         "what really happened.")
        else:
            lines.append(f"I used to believe that {text}, but {d['by']}'s inquiry found {and_names(d['started_by'])} "
                         "started it and nobody saw it.")
    for b in r["beliefs"]:
        sure = _confidence_words(b["confidence"])
        b = {**b, "text": as_me(b["text"], my_name)}
        if b["origin"] == "witnessed":
            line = f"I saw it myself: {b['text']}."
        elif b["origin"] == "self":
            line = f"I've been saying that {lower_first(b['text'])} ({sure})."
        else:
            line = f"{and_names(b['told_by'])} told me that {lower_first(b['text'])} ({sure})."
        if b["already_shared"]:
            line += f" {other_name} and I already talked about this."
        lines.append(line)
    return lines


def _empty(me: str, other: str) -> dict:
    return {"me": me, "other": other, "known": False, "beliefs": [], "debunked": [],
            "reputation": {"score": 0.0, "evidence": 0}, "trust": None, "episodes": [], "memories": [], "topic": None}


def _confidence_words(c: float) -> str:
    if c >= 0.8:
        return "I'm sure of it"
    if c >= 0.5:
        return "I believe it"
    if c >= 0.25:
        return "I'm not certain"
    return "it's only a rumor to me"


def _trust_words(t: float) -> str:
    if t >= 0.75:
        return "trust"
    if t >= 0.45:
        return "somewhat trust"
    return "don't fully trust"


def _reputation_words(score: float) -> str:
    if score <= -0.5:
        return "very bad"
    if score < -0.15:
        return "bad"
    if score <= 0.15:
        return "mixed"
    if score < 0.5:
        return "good"
    return "very good"


def and_names(names: list[str]) -> str:
    if not names:
        return "Someone"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def as_me(text: str, my_name: str) -> str:
    """'Kai stole a silver hammer from Bram' -> '... from me' in Bram's own memory (not when Bram is the subject)."""
    first, sep, rest = text.partition(" ")
    name = re.escape(my_name)
    rest = re.sub(rf"\b{name}['’]s\b", "my", rest)
    return first + sep + re.sub(rf"\b{name}\b", "me", rest)


def lower_first(text: str) -> str:
    """'The merchant ...' -> 'the merchant ...' mid-sentence; names like 'Kai stole ...' stay as they are."""
    first, sep, rest = text.partition(" ")
    return first.lower() + sep + rest if first.lower() in {"the", "a", "an"} else text
