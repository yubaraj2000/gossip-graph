"""Live feed of the village's memory: new conversations and every belief as it forms, with who said what.

    uv run python -m scripts.live_feed [world_id] [--once]      (from the repository root)

With no world id, uses AI Town's current default world. Polls the graph every 3 seconds; Ctrl+C to stop.
"""
import sys
import time

from memory import db
from scripts.seed_village import convex

NEW_CONVERSATIONS = """
MATCH (p:Character)-[:PARTICIPATED_IN]->(c:Conversation {status: 'ingested'})
WHERE c.ended_at > $since
RETURN c.id, c.ended_at, c.summary, collect(p.name) ORDER BY c.ended_at
"""

NEW_BELIEFS = """
MATCH (h:Character)<-[:HELD_BY]-(b:Belief)-[:OF]->(c:Claim)
WHERE b.created_at > $since
OPTIONAL MATCH (b)-[:HEARD_FROM]->(:Belief)-[:HELD_BY]->(src:Character)
OPTIONAL MATCH (b)-[:EVIDENCE]->(m:Message)<-[:SAID]-(src)
RETURN b.created_at, h.name, b.origin, b.confidence, c.text, src.name, m.text
ORDER BY b.created_at
"""


def main(world_id: str, once: bool) -> None:
    g = db.world_graph(world_id)
    print(f"live feed for world {world_id} (graph world_{world_id})\n")
    since = 0 if once else time.time() * 1000 - 10 * 60 * 1000  # start with the last 10 minutes
    while True:
        events = []
        for cid, ended, summary, who in g.ro_query(NEW_CONVERSATIONS, {"since": since}).result_set:
            events.append((ended, f"💬 {' & '.join(who)} talked ({cid}): {summary}"))
        for ts, holder, origin, conf, claim, src, line in g.ro_query(NEW_BELIEFS, {"since": since}).result_set:
            pct = f"{round(conf * 100)}%"
            if origin == "witnessed":
                events.append((ts, f"👁  {holder} SAW it: \"{claim}\" ({pct})"))
            elif origin == "heard":
                said = f'  ← {src} said: "{line[:140]}"' if line else ""
                events.append((ts, f"👂 {holder} now believes \"{claim}\" ({pct}, from {src}){said}"))
            else:
                events.append((ts, f"🗣  {holder} started saying \"{claim}\" ({pct})"))
        for ts, text in sorted(events):
            print(f"{time.strftime('%H:%M:%S', time.localtime(ts / 1000))}  {text}")
            since = max(since, ts)
        if once:
            return
        time.sleep(3)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--once"]
    world = args[0] if args else convex("world:defaultWorldStatus")["worldId"]
    try:
        main(world, once="--once" in sys.argv)
    except KeyboardInterrupt:
        pass
