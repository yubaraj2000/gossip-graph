"""Investigation cases: a case file in the graph that any investigator can pick up (PLAN.md Phase 4).

Minds are private: the briefing uses only the social structure (who knows whom, who learned from whom, who
talks), never anyone's beliefs. Everything an investigator does is written to the case file, so a replacement
investigator can resume after a crash. The briefing borrows Graphify's idea: orient a newcomer from a graph
report (hubs, bridges, communities, suggested questions) instead of re-reading everything.
"""
import hashlib
import json
import time
from collections import defaultdict

from falkordb import Graph

from memory import db, ingest
from memory.models import CaseIn

OPEN_CASE = """
MERGE (k:Case {id: $id})
ON CREATE SET k.title = $title, k.question = $question, k.status = 'open', k.opened_at = $ts
RETURN k.status
"""

ASSIGN = """
MATCH (k:Case {id: $case}), (i:Character {id: $investigator})
OPTIONAL MATCH (other:Character)-[old:INVESTIGATES]->(k) WHERE other.id <> $investigator
SET old.active = false
MERGE (i)-[r:INVESTIGATES]->(k)
ON CREATE SET r.since = $ts
SET r.active = true
"""

# The social structure only: villagers are NPCs that aren't investigators.
VILLAGERS = """
MATCH (c:Character {kind: 'npc'}) WHERE NOT (c)-[:INVESTIGATES]->()
RETURN c.id, c.name
"""
# Friendships (seeded) are the village's lasting structure; KNOWS also grows with every first conversation and
# soon links almost everyone (seen live: the two circles dissolved into one), so it's only a fallback.
TIES = """
MATCH (a:Character)-[:{rel}]->(b:Character)
WHERE a.id IN $ids AND b.id IN $ids
RETURN a.id, b.id
"""
BETWEENNESS = """
CALL algo.betweenness({{nodeLabels: ['Character'], relationshipTypes: ['{rel}']}}) YIELD node, score
RETURN node.id, score
"""
HAS_FRIENDS = "MATCH ()-[f:FRIEND]->() RETURN count(f) > 0"
# LEARNED_FROM points listener -> speaker, so PageRank flows to the people others learn from.
NEWS_HUBS = "CALL algo.pageRank('Character', 'LEARNED_FROM') YIELD node, score RETURN node.id, score"
TRUST_HUBS = "CALL algo.pageRank('Character', 'KNOWS') YIELD node, score RETURN node.id, score"
HAS_LEARNED_FROM = "MATCH ()-[l:LEARNED_FROM]->() RETURN count(l) > 0"

SAVE_BRIEFING = "MATCH (k:Case {id: $case}) SET k.briefing = $briefing"

ADD_LEADS = """
UNWIND $leads AS l
MATCH (k:Case {id: $case}), (t:Character {id: l.target})
MERGE (k)-[:HAS_LEAD]->(ld:Lead {case: $case, target: l.target})
ON CREATE SET ld.kind = l.kind, ld.reason = l.reason, ld.priority = l.priority, ld.status = 'open',
              ld.created_at = $ts
MERGE (ld)-[:TARGET]->(t)
"""

CASE_FILE = """
MATCH (k:Case {id: $case})
OPTIONAL MATCH (i:Character)-[r:INVESTIGATES]->(k)
WITH k, collect({id: i.id, name: i.name, active: r.active, since: r.since}) AS investigators
OPTIONAL MATCH (k)-[:HAS_LEAD]->(ld:Lead)-[:TARGET]->(t:Character)
WITH k, investigators,
     collect({target: t.id, name: t.name, kind: ld.kind, reason: ld.reason, priority: ld.priority,
              status: ld.status, created_at: ld.created_at, done_at: ld.done_at}) AS leads
RETURN k.id, k.title, k.question, k.status, k.opened_at, k.briefing, investigators, leads
"""


class CaseNotFound(LookupError):
    pass


def open_case(world_id: str, case: CaseIn) -> dict:
    """Open (or re-open) a case, assign its investigator, and write the briefing and first leads to the graph."""
    db.ensure_world(world_id)
    g = db.world_graph(world_id)
    case_id = case.id or "case_" + hashlib.sha1(case.title.encode()).hexdigest()[:10]
    ts = time.time() * 1000
    ingest.upsert_characters(g, [case.investigator])
    g.query(OPEN_CASE, {"id": case_id, "title": case.title, "question": case.question, "ts": ts})
    g.query(ASSIGN, {"case": case_id, "investigator": case.investigator.id, "ts": ts})
    existing = case_file(world_id, case_id)
    if existing["briefing"] is None:  # computed once: every investigator on the case reads the same briefing
        report = briefing(g)
        g.query(SAVE_BRIEFING, {"case": case_id, "briefing": json.dumps(report)})
        g.query(ADD_LEADS, {"case": case_id, "leads": report["suggested_leads"], "ts": ts})
    return case_file(world_id, case_id)


def case_file(world_id: str, case_id: str) -> dict:
    rows = db.world_graph(world_id).ro_query(CASE_FILE, {"case": case_id}).result_set
    if not rows:
        raise CaseNotFound(case_id)
    cid, title, question, status, opened_at, report, investigators, leads = rows[0]
    order = {"open": 0, "done": 1, "dropped": 2}
    return {
        "case": cid, "title": title, "question": question, "status": status, "opened_at": opened_at,
        "investigators": sorted((i for i in investigators if i["id"]), key=lambda i: i["since"]),
        "leads": sorted((ld for ld in leads if ld["target"]),
                        key=lambda ld: (order.get(ld["status"], 9), ld["priority"], ld["created_at"])),
        "briefing": json.loads(report) if report else None,
    }


def briefing(g: Graph) -> dict:
    """A Graphify-style orientation report from the social structure only (no beliefs)."""
    names = dict(g.ro_query(VILLAGERS).result_set)
    ids = list(names)
    ties = "FRIEND" if g.ro_query(HAS_FRIENDS).result_set[0][0] else "KNOWS"
    edges = g.ro_query(TIES.format(rel=ties), {"ids": ids}).result_set

    between = {i: s for i, s in g.ro_query(BETWEENNESS.format(rel=ties)).result_set if i in names}
    bridges = sorted((i for i in between if between[i] > 0), key=lambda i: -between[i])[:3]
    learned = g.ro_query(HAS_LEARNED_FROM).result_set[0][0]
    rank = {i: s for i, s in g.ro_query(NEWS_HUBS if learned else TRUST_HUBS).result_set if i in names}
    hubs = sorted(rank, key=lambda i: -rank[i])[:3]
    # FalkorDB's labelPropagation paired up unconnected villagers on this graph (RESEARCH_LOG 3.2), so circles are
    # the groups left when the top bridge is taken out.
    circles = _components([i for i in ids if not bridges or i != bridges[0]], edges)

    leads, seen = [], set()

    def lead(target, kind, reason):
        if target not in seen:
            seen.add(target)
            leads.append({"target": target, "kind": kind, "reason": reason, "priority": len(leads) + 1})

    if hubs:
        lead(hubs[0], "hub", f"{names[hubs[0]]} is where news collects: "
             + ("others learn the most from them." if learned else "the most trusted person in the village."))
    if bridges:
        lead(bridges[0], "bridge", f"{names[bridges[0]]} is the main bridge between the circles; "
             "news crossing the village passes through them.")
    for circle in circles:
        voice = max(circle, key=lambda i: rank.get(i, 0))
        lead(voice, "circle", f"{names[voice]} speaks for the circle of " + ", ".join(names[i] for i in circle) + ".")

    summary = []
    if hubs:
        summary.append("Most news comes from " + _and([names[i] for i in hubs[:2]])
                       + (" (others learn from them most)." if learned else " (the most trusted villagers)."))
    if bridges:
        summary.append(f"{names[bridges[0]]} bridges the village's circles"
                       + (f"; {names[bridges[1]]} is the next-strongest link." if len(bridges) > 1 else "."))
    for n, circle in enumerate(circles, 1):
        summary.append(f"Circle {n}: " + _and([names[i] for i in circle]) + ".")
    summary.append("Suggested first interviews: " + _and([names[ld["target"]] for ld in leads]) + ".")

    return {
        "hubs": [{"id": i, "name": names[i], "score": round(rank[i], 3)} for i in hubs],
        "bridges": [{"id": i, "name": names[i], "score": round(between[i], 2)} for i in bridges],
        "circles": [[{"id": i, "name": names[i]} for i in c] for c in circles],
        "suggested_leads": leads,
        "summary": summary,
        "hubs_based_on": "who learned from whom" if learned else "who trusts whom",
        "circles_based_on": "friendships" if ties == "FRIEND" else "acquaintances",
    }


def _components(ids: list[str], edges: list[list[str]]) -> list[list[str]]:
    """Connected groups among `ids`, treating KNOWS as undirected; largest first, singletons dropped."""
    keep = set(ids)
    adj = defaultdict(set)
    for a, b in edges:
        if a in keep and b in keep:
            adj[a].add(b)
            adj[b].add(a)
    seen, groups = set(), []
    for start in ids:
        if start in seen or not adj[start]:
            continue
        stack, group = [start], []
        seen.add(start)
        while stack:
            node = stack.pop()
            group.append(node)
            for nxt in adj[node] - seen:
                seen.add(nxt)
                stack.append(nxt)
        groups.append(sorted(group))
    return sorted(groups, key=lambda grp: (-len(grp), grp))


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
