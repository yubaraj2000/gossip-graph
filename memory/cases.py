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

from memory import db, ingest, llm, recall
from memory.models import CaseIn, CharacterIn, ConversationIn

# Claims closer than this (cosine distance) to the case's title + question are what interviewees talk about.
# Measured on the live village: the true theft 0.283, its garbled retellings 0.32, competing theft rumors
# 0.33-0.38; unrelated chatter from about 0.42 up.
CASE_RELEVANCE = 0.40
TESTIMONY_MAX = 4

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


CASE_TEXT = "MATCH (k:Case {id: $case}) RETURN k.title, k.question, k.embedding, k.status"
SAVE_CASE_EMBEDDING = "MATCH (k:Case {id: $case}) SET k.embedding = $embedding"
ACTIVE_INVESTIGATOR = """
MATCH (i:Character)-[:INVESTIGATES {active: true}]->(:Case {id: $case})
RETURN i.id, i.name, i.kind, i.identity
"""
CHARACTER = "MATCH (c:Character {id: $id}) RETURN c.id, c.name, c.kind"

# What the interviewee believes about the case, and only their *direct* sources: a villager knows who told
# them, not who told the teller. That's what makes the investigator follow the trail interview by interview.
TESTIMONY = """
CALL db.idx.vector.queryNodes('Claim', 'embedding', 100, vecf32($q)) YIELD node, score
WITH node, score WHERE score < $max_distance
MATCH (node)<-[:OF]-(b:Belief {holder: $who, status: 'active'})
OPTIONAL MATCH (b)-[:HEARD_FROM]->(:Belief)-[:HELD_BY]->(src:Character)
RETURN node.id, node.text, b.origin, collect(DISTINCT src.id), collect(DISTINCT src.name), score
ORDER BY score
LIMIT $limit
"""

START_INTERVIEW = """
MERGE (cv:Conversation {id: $id})
ON CREATE SET cv.status = 'new', cv.kind = 'interview'
WITH cv, cv.status AS before
SET cv.status = CASE WHEN before = 'ingested' THEN before ELSE 'ingesting' END
RETURN before
"""

CLOSE_INTERVIEW = """
MATCH (cv:Conversation {id: $conv}), (k:Case {id: $case})
SET cv.status = 'ingested', cv.summary = $summary
MERGE (cv)-[:PART_OF]->(k)
WITH cv, k
MATCH (k)-[:HAS_LEAD]->(ld:Lead {target: $target})
SET ld.status = 'done', ld.done_at = $ts
MERGE (ld)-[:RESOLVED_BY]->(cv)
"""

ADD_FINDING = """
MATCH (k:Case {id: $case}), (c:Claim {id: $claim}), (cv:Conversation {id: $conv})
MERGE (k)-[:HAS_FINDING]->(f:Finding {case: $case, claim: $claim, said_by: $said_by})
ON CREATE SET f.testimony = $testimony, f.sources = $sources, f.line = $line, f.at = $ts
MERGE (f)-[:ABOUT_CLAIM]->(c)
MERGE (f)-[:FROM_INTERVIEW]->(cv)
"""

# A named source becomes the next lead (or jumps the queue if already an open lead).
ADD_SOURCE_LEAD = """
MATCH (k:Case {id: $case}), (t:Character {id: $target})
MERGE (k)-[:HAS_LEAD]->(ld:Lead {case: $case, target: $target})
ON CREATE SET ld.kind = 'source', ld.reason = $reason, ld.priority = 0, ld.status = 'open', ld.created_at = $ts
ON MATCH SET ld.priority = CASE WHEN ld.status = 'open' THEN 0 ELSE ld.priority END,
             ld.reason = CASE WHEN ld.status = 'open' AND NOT ld.reason CONTAINS $reason
                              THEN ld.reason + ' ' + $reason ELSE ld.reason END
MERGE (ld)-[:TARGET]->(t)
RETURN ld.status
"""

# An interview the investigator chose directly still gets a lead, so the case file records why it happened.
CHOSEN_LEAD = """
MATCH (k:Case {id: $case}), (t:Character {id: $target})
MERGE (k)-[:HAS_LEAD]->(ld:Lead {case: $case, target: $target})
ON CREATE SET ld.kind = 'chosen', ld.reason = 'Chosen directly by the investigator.', ld.priority = 0,
              ld.status = 'open', ld.created_at = $ts
MERGE (ld)-[:TARGET]->(t)
"""

FINDINGS = """
MATCH (:Case {id: $case})-[:HAS_FINDING]->(f:Finding)-[:ABOUT_CLAIM]->(c:Claim)
MATCH (s:Character) WHERE s.id = f.said_by
RETURN c.id, c.text, s.name, f.testimony, f.sources, f.line, f.at
ORDER BY f.at
"""

INTERVIEWS = """
MATCH (cv:Conversation {kind: 'interview'})-[:PART_OF]->(:Case {id: $case})
MATCH (p:Character)-[:PARTICIPATED_IN]->(cv)
RETURN cv.id, cv.ended_at, cv.summary, collect(p.name)
ORDER BY cv.ended_at
"""


class CaseClosed(RuntimeError):
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
    g = db.world_graph(world_id)
    order = {"open": 0, "done": 1, "dropped": 2}
    return {
        "case": cid, "title": title, "question": question, "status": status, "opened_at": opened_at,
        "investigators": sorted((i for i in investigators if i["id"]), key=lambda i: i["since"]),
        "leads": sorted((ld for ld in leads if ld["target"]),
                        key=lambda ld: (order.get(ld["status"], 9), ld["priority"], ld["created_at"])),
        "interviews": [{"conversation": c, "at": at, "summary": summ, "participants": who}
                       for c, at, summ, who in g.ro_query(INTERVIEWS, {"case": case_id}).result_set],
        "findings": [{"claim": c, "text": text, "said_by": by, "testimony": t, "sources": src, "line": line, "at": at}
                     for c, text, by, t, src, line, at in g.ro_query(FINDINGS, {"case": case_id}).result_set],
        "briefing": json.loads(report) if report else None,
    }


def interview(world_id: str, case_id: str, target: str | None = None) -> dict:
    """The active investigator interviews the next lead (or `target`), writes everything to the case file, and
    turns every named source into a new lead. Interviewees answer from their own beliefs, word for word."""
    g = db.world_graph(world_id)
    file = case_file(world_id, case_id)
    if file["status"] != "open":
        raise CaseClosed(f"case {case_id} is {file['status']}")
    inv_rows = g.ro_query(ACTIVE_INVESTIGATOR, {"case": case_id}).result_set
    if not inv_rows:
        raise CaseClosed(f"case {case_id} has no active investigator")
    inv_id, inv_name, inv_kind, inv_identity = inv_rows[0]
    if target is None:
        open_leads = [ld for ld in file["leads"] if ld["status"] == "open"]
        if not open_leads:
            return {"case": case_id, "status": "no_open_leads"}
        target = open_leads[0]["target"]
    who = g.ro_query(CHARACTER, {"id": target}).result_set
    if not who:
        raise ValueError(f"unknown character {target!r}")
    _, who_name, who_kind = who[0]

    conv_id = f"interview:{case_id}:{target}"
    if g.query(START_INTERVIEW, {"id": conv_id}).result_set[0][0] == "ingested":
        return {"case": case_id, "status": "already_interviewed", "interviewee": who_name}
    g.query(CHOSEN_LEAD, {"case": case_id, "target": target, "ts": time.time() * 1000})

    testimony = g.ro_query(TESTIMONY, {"q": _case_embedding(g, case_id), "who": target, "max_distance": CASE_RELEVANCE,
                                       "limit": TESTIMONY_MAX}).result_set
    ts = time.time() * 1000
    lines = [(inv_id, f"Namaste, {who_name}. I'm {inv_name}, looking into {file['title'][0].lower() + file['title'][1:]}. "
                      "What have you heard about it, and who told you?")]
    for claim_id, text, origin, src_ids, src_names, _ in testimony:
        lines.append((target, _testify(text, origin, src_names, who_name)))
    if not testimony:
        lines.append((target, "I haven't heard anything about that."))
    conv = ConversationIn(
        id=conv_id,
        participants=[CharacterIn(id=inv_id, name=inv_name, kind=inv_kind or "npc", identity=inv_identity or ""),
                      CharacterIn(id=target, name=who_name, kind=who_kind or "npc")],
        messages=[{"author": a, "text": t, "ts": ts + i} for i, (a, t) in enumerate(lines)])
    msgs, _, _ = ingest.record_transcript(g, conv)

    findings, new_leads = [], []
    for n, (claim_id, text, origin, src_ids, src_names, _) in enumerate(testimony, start=1):
        msg = msgs[n]
        ingest.hear(g, inv_id, target, claim_id, msg["id"], msg["ts"])  # the investigator now believes it too
        g.query(ADD_FINDING, {"case": case_id, "claim": claim_id, "conv": conv_id, "said_by": target,
                              "testimony": origin, "sources": src_names, "line": msg["text"], "ts": msg["ts"]})
        findings.append({"claim": claim_id, "text": text, "testimony": origin, "sources": src_names})
        if origin == "heard":
            for sid, sname in zip(src_ids, src_names):
                if sid in (inv_id, target):
                    continue
                status = g.query(ADD_SOURCE_LEAD, {"case": case_id, "target": sid, "ts": msg["ts"],
                                                   "reason": f'{who_name} heard "{text}" from {sname}.'}).result_set
                if status and status[0][0] == "open" and sname not in new_leads:
                    new_leads.append(sname)

    g.query(CLOSE_INTERVIEW, {"conv": conv_id, "case": case_id, "target": target, "ts": msgs[-1]["ts"],
                              "summary": f"{inv_name} interviewed {who_name}: {len(testimony)} relevant claim(s)."})
    return {"case": case_id, "status": "interviewed", "investigator": inv_name, "interviewee": who_name,
            "transcript": [{"speaker": inv_name if a == inv_id else who_name, "text": t} for a, t in lines],
            "findings": findings, "new_leads": new_leads}


def _testify(text: str, origin: str, sources: list[str], my_name: str) -> str:
    """The interviewee's answer about one belief: the claim plus *how they know it*, straight from the graph."""
    text = recall.as_me(text, my_name).rstrip(".")
    if origin == "witnessed":
        return f"I saw it with my own eyes: {text}."
    if origin == "heard":
        return f"{recall.and_names(sources)} told me that {recall.lower_first(text)}."
    return f"{text}. Nobody told me; that's what I've been saying."


def _case_embedding(g: Graph, case_id: str) -> list[float]:
    title, question, embedding, _ = g.ro_query(CASE_TEXT, {"case": case_id}).result_set[0]
    if embedding is None:
        embedding = llm.embed([f"{title}. {question}"])[0]
        g.query(SAVE_CASE_EMBEDDING, {"case": case_id, "embedding": embedding})
    return list(embedding)


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
