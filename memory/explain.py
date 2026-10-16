"""Explain: "who told you that?" — every provenance path behind a belief (docs/DATA_MODEL.md, Q4).

The answer sentence is built from the graph path itself, never paraphrased by the LLM: the gossip preview
showed the 3B model garbling the chain when it retold it.
"""
from memory import db

MAX_PATHS_PER_BELIEF = 5

# Q4: each path follows HEARD_FROM from the holder's belief back to a root (witnessed, or said first).
PATHS = """
MATCH (:Character {id: $holder})<-[:HELD_BY]-(b:Belief {status: 'active'})-[:OF]->(c:Claim)-[:ABOUT]->(s:Character)
WHERE ($claim IS NULL OR c.id = $claim) AND ($subject IS NULL OR s.id = $subject)
MATCH p = (b)-[:HEARD_FROM*0..8]->(root:Belief)
WHERE NOT (root)-[:HEARD_FROM]->()
OPTIONAL MATCH (root)-[:SAW]->(e:Event)
OPTIONAL MATCH (c)-[:REFERS_TO]->(ev:Event)
RETURN c.id, c.text, s.id, c.valence, b.confidence, b.origin,
       [x IN nodes(p) | x.holder] AS chain, [x IN nodes(p) | x.confidence] AS confidences,
       root.origin, e.description, count(ev) > 0 AS grounded
ORDER BY b.confidence DESC, c.id, length(p)
"""

# The line each listener heard: the listener's EVIDENCE message, said by the next person in the chain.
EVIDENCE = """
UNWIND $hops AS hop
MATCH (:Belief {holder: hop[0], claim: hop[1]})-[:EVIDENCE]->(m:Message)<-[:SAID]-(:Character {id: hop[2]})
RETURN hop[0], hop[1], hop[2], m.text ORDER BY m.ts
"""

NAMES = "MATCH (c:Character) RETURN c.id, c.name"


def explain(world_id: str, holder: str, claim: str | None = None, subject: str | None = None) -> dict:
    if db.graph_name(world_id) not in db.client().list_graphs():
        return {"holder": holder, "known": False, "beliefs": []}
    g = db.world_graph(world_id)
    names = dict(g.ro_query(NAMES).result_set)
    if holder not in names:
        return {"holder": holder, "known": False, "beliefs": []}

    beliefs: dict[str, dict] = {}
    for (cid, text, sid, valence, conf, origin, chain, confs, root_origin, event, grounded) in g.ro_query(
            PATHS, {"holder": holder, "claim": claim, "subject": subject}).result_set:
        b = beliefs.setdefault(cid, {
            "claim": cid, "text": text, "subject": sid, "subject_name": names.get(sid, sid), "valence": valence,
            "confidence": round(conf, 3), "origin": origin, "grounded": grounded, "paths": []})
        if len(b["paths"]) < MAX_PATHS_PER_BELIEF:
            b["paths"].append({"chain": chain, "confidences": [round(c, 3) for c in confs],
                               "root_origin": root_origin, "event": event})

    hops = sorted({(p["chain"][i], cid, p["chain"][i + 1])
                   for cid, b in beliefs.items() for p in b["paths"] for i in range(len(p["chain"]) - 1)})
    heard = {(h, c, spk): text for h, c, spk, text in g.ro_query(EVIDENCE, {"hops": [list(x) for x in hops]}).result_set}

    for b in beliefs.values():
        for p in b["paths"]:
            p["steps"] = [
                {"holder": h, "name": names.get(h, h), "confidence": p["confidences"][i],
                 "heard_from": p["chain"][i + 1] if i + 1 < len(p["chain"]) else None,
                 "heard_from_name": names.get(p["chain"][i + 1]) if i + 1 < len(p["chain"]) else None,
                 "heard_line": heard.get((h, b["claim"], p["chain"][i + 1])) if i + 1 < len(p["chain"]) else None}
                for i, h in enumerate(p["chain"])]
            del p["confidences"]
        b["verdict"] = "witnessed" if any(p["root_origin"] == "witnessed" for p in b["paths"]) else "unverified"
        b["sentence"] = sentence(b["paths"], names)
    return {"holder": holder, "holder_name": names[holder], "known": True, "beliefs": list(beliefs.values())}


def sentence(paths: list[dict], names: dict[str, str]) -> str:
    """The holder's own answer, word for word from the strongest path, plus any other direct sources.

    Names are repeated instead of pronouns: characters have no recorded pronouns."""
    if not paths:
        return "I don't know where I heard that."
    best = paths[0]
    chain = [names.get(h, h) for h in best["chain"]]
    witnessed = best["root_origin"] == "witnessed"
    if len(chain) == 1:
        return "I saw it myself." if witnessed else "Nobody told me; I said it first."
    out = f"{chain[1]} told me."
    if len(chain) > 2:
        out += f" {chain[1]} heard it from " + ", who heard it from ".join(chain[2:]) + "."
    out += f" {chain[-1]} saw it happen." if witnessed else f" {chain[-1]} started it, and nobody saw it happen."
    others = []
    for p in paths[1:]:
        first = names.get(p["chain"][1], p["chain"][1]) if len(p["chain"]) > 1 else None
        if first and first != chain[1] and first not in others:
            others.append(first)
    if others:
        out += " I also heard it from " + " and ".join(others) + "."
    return out
