"""Read-only views of a world's graph for the memory page (Phase 5). Each panel is a few small Cypher queries."""
import time

from memory import db

CHARACTERS = """
MATCH (c:Character)
OPTIONAL MATCH (c)<-[:HELD_BY]-(b:Belief {status: 'active'})
OPTIONAL MATCH (c)<-[:ABOUT]-(k:Claim)
RETURN c.id, c.name, c.kind, c.gullibility, count(DISTINCT b), count(DISTINCT k)
"""
INVESTIGATORS = "MATCH (c:Character)-[:INVESTIGATES]->(:Case) RETURN DISTINCT c.id"
FRIENDSHIPS = "MATCH (a:Character)-[:FRIEND]->(b:Character) RETURN a.id, b.id"
# LEARNED_FROM points listener -> speaker; the page draws news flowing speaker -> listener.
NEWS_FLOW = "MATCH (lis:Character)-[l:LEARNED_FROM]->(spk:Character) RETURN spk.id, lis.id, l.count"
TOTALS = {
    "beliefs": "MATCH (b:Belief {status: 'active'}) RETURN count(b)",
    "outdated": "MATCH (b:Belief {status: 'superseded'}) RETURN count(b)",
    "claims": "MATCH (c:Claim) RETURN count(c)",
    "conversations": "MATCH (c:Conversation {status: 'ingested'}) RETURN count(c)",
}
# Same shape as scripts/live_feed.py: every belief as it forms, with who it came from and the line they heard.
NEW_BELIEFS = """
MATCH (h:Character)<-[:HELD_BY]-(b:Belief)-[:OF]->(c:Claim)
WHERE b.created_at > $since
OPTIONAL MATCH (b)-[:HEARD_FROM]->(:Belief)-[:HELD_BY]->(src:Character)
OPTIONAL MATCH (b)-[:EVIDENCE]->(m:Message)<-[:SAID]-(src)
RETURN b.created_at, h.id, h.name, b.origin, b.confidence, b.status, c.id, c.text, c.valence,
       src.id, src.name, m.text
ORDER BY b.created_at DESC LIMIT $limit
"""


def graph(world_id: str, since: float | None = None, limit: int = 40) -> dict:
    """Characters, friendships and news flow, plus the beliefs formed since `since` (ms; default: last 30 min)."""
    if not db.exists(db.graph_name(world_id)):
        raise LookupError(f"no world {world_id!r}")
    g = db.world_graph(world_id)
    now = time.time() * 1000
    investigators = {r[0] for r in g.ro_query(INVESTIGATORS).result_set}
    characters = [{"id": cid, "name": name, "kind": kind, "gullibility": gull, "beliefs": n, "talked_about": k,
                   "role": "investigator" if cid in investigators else "outsider" if kind == "human" else "villager"}
                  for cid, name, kind, gull, n, k in g.ro_query(CHARACTERS).result_set]
    # Humans who neither believe anything nor are talked about (e.g. a visitor's town avatar) are noise on the map.
    characters = [c for c in characters if c["role"] != "outsider" or c["beliefs"] or c["talked_about"]]
    feed = [{"at": at, "holder": hid, "holder_name": hname, "origin": origin, "confidence": round(conf, 3),
             "status": status, "claim": cid, "text": text, "valence": valence, "from": sid, "from_name": sname,
             "line": line}
            for at, hid, hname, origin, conf, status, cid, text, valence, sid, sname, line
            in g.ro_query(NEW_BELIEFS, {"since": now - 30 * 60 * 1000 if since is None else since,
                                        "limit": limit}).result_set]
    return {
        "world": world_id,
        "now": now,
        "characters": characters,
        "friendships": g.ro_query(FRIENDSHIPS).result_set,
        "news_flow": [{"from": s, "to": t, "count": n} for s, t, n in g.ro_query(NEWS_FLOW).result_set],
        "totals": {name: g.ro_query(q).result_set[0][0] for name, q in TOTALS.items()},
        "feed": feed,
    }
