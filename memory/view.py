"""Read-only views of a world's graph for the memory page (Phase 5). Each panel is a few small Cypher queries."""
import time

from memory import cases, db, recall

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
# Polled by when the belief entered the graph (recorded_at), not when it was said (created_at): conversations finish
# extraction out of order, so a later-recorded belief can carry an earlier time and would otherwise be skipped.
NEW_BELIEFS = """
MATCH (h:Character)<-[:HELD_BY]-(b:Belief)-[:OF]->(c:Claim)
WHERE coalesce(b.recorded_at, b.created_at) > $since
OPTIONAL MATCH (b)-[:HEARD_FROM]->(:Belief)-[:HELD_BY]->(src:Character)
OPTIONAL MATCH (b)-[:EVIDENCE]->(m:Message)<-[:SAID]-(src)
RETURN b.created_at, h.id, h.name, b.origin, b.confidence, b.status, c.id, c.text, c.valence,
       src.id, src.name, m.text, coalesce(b.recorded_at, b.created_at)
ORDER BY coalesce(b.recorded_at, b.created_at) DESC LIMIT $limit
"""


def graph(world_id: str, since: float | None = None, limit: int = 40) -> dict:
    """Characters, friendships and news flow, plus the beliefs recorded since `since` (ms; default: last 30 min).
    Pass back the returned `now` as the next `since`: it is read before the feed query, so nothing falls in between."""
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
    feed = [{"at": at, "recorded_at": rec, "holder": hid, "holder_name": hname, "origin": origin,
             "confidence": round(conf, 3), "status": status, "claim": cid, "text": text, "valence": valence,
             "from": sid, "from_name": sname, "line": line}
            for at, hid, hname, origin, conf, status, cid, text, valence, sid, sname, line, rec
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


# What the village thinks of each person: each villager's opinion is the average of confidence x valence over their
# active beliefs about that person (-1 to +1), and the village's view averages the villagers who have one.
# Averages, not sums: a sum grows with how much someone is talked about, so the most gossiped-about person would
# always look worst. Investigators' notes don't count.
REPUTATION = """
MATCH (h:Character)<-[:HELD_BY]-(b:Belief {status: 'active'})-[:OF]->(c:Claim)-[:ABOUT]->(x:Character)
WHERE h <> x AND NOT (h)-[:INVESTIGATES]->()
WITH x, h, avg(b.confidence * c.valence) AS opinion
RETURN x.id, x.name, avg(opinion), count(h),
       sum(CASE WHEN opinion < -0.15 THEN 1 ELSE 0 END), sum(CASE WHEN opinion > 0.15 THEN 1 ELSE 0 END)
"""
# The most widely believed claim about each person.
TOP_CLAIM = """
MATCH (b:Belief {status: 'active'})-[:OF]->(c:Claim)-[:ABOUT]->(x:Character)
WITH x, c, count(b) AS believers ORDER BY believers DESC
RETURN x.id, collect(c.text)[0], collect(believers)[0]
"""


def insights(world_id: str) -> dict:
    """The village as a whole: bridges, news hubs and circles (the investigator's briefing, computed live) and
    what the village thinks of each person."""
    if not db.exists(db.graph_name(world_id)):
        raise LookupError(f"no world {world_id!r}")
    g = db.world_graph(world_id)
    structure = cases.briefing(g)
    top = {x: (text, n) for x, text, n in g.ro_query(TOP_CLAIM).result_set}
    reputation = [{"id": x, "name": name, "opinion": round(avg, 3), "words": recall.reputation_words(avg),
                   "villagers_with_opinion": holders, "think_badly": int(bad), "think_well": int(good),
                   "top_claim": top.get(x, (None, 0))[0], "top_claim_believers": top.get(x, (None, 0))[1]}
                  for x, name, avg, holders, bad, good in g.ro_query(REPUTATION).result_set]
    return {
        "world": world_id,
        "summary": [line for line in structure["summary"] if not line.startswith("Suggested")],
        **{k: structure[k] for k in ("hubs", "bridges", "circles", "hubs_based_on", "circles_based_on")},
        "reputation": sorted(reputation, key=lambda r: r["opinion"]),
    }
