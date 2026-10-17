"""Village templates: seed a village once, then start any number of separate worlds from it with GRAPH.COPY.

A template holds only the starting state: characters, personalities, trust (KNOWS) and friendships (FRIEND), plus
the schema and indexes. It has no memories. Each copy is an independent graph, so what happens in one world never
reaches another world or the template (FalkorDB has no cross-graph queries).
"""
import time

from memory import db, ingest
from memory.models import CharacterIn, RelationshipIn


class TemplateNotFound(LookupError):
    pass


class WorldExists(FileExistsError):
    pass


# Separate queries on purpose: an OPTIONAL MATCH after an aggregating WITH can silently match nothing (step 2.4).
COUNTS = {
    "characters": "MATCH (c:Character) RETURN count(c)",
    "trust_links": "MATCH ()-[k:KNOWS]->() RETURN count(k)",
    "friendships": "MATCH ()-[f:FRIEND]->() RETURN count(f)",
}


def create(name: str, characters: list[CharacterIn], relationships: list[RelationshipIn]) -> dict:
    """Create the template, replacing any older version. Worlds already started from it are separate and unaffected."""
    graph = db.template_graph_name(name)
    if db.exists(graph):
        db.client().select_graph(graph).delete()
    db.ensure_graph_schema(graph)
    g = db.client().select_graph(graph)
    ingest.upsert_characters(g, characters)
    ingest.set_relationships(g, relationships)
    return {"template": name, "graph": graph, **_counts(graph)}


def start_world(name: str, world_id: str) -> dict:
    """Start a new world as an exact copy of the template."""
    source, target = db.template_graph_name(name), db.graph_name(world_id)
    if not db.exists(source):
        raise TemplateNotFound(f"no template {name!r}")
    if db.exists(target):
        raise WorldExists(f"world {world_id!r} already exists")
    t = time.perf_counter()
    db.client().select_graph(source).copy(target)
    ms = (time.perf_counter() - t) * 1000
    return {"world": world_id, "graph": target, "template": name, "copy_ms": round(ms, 1), **_counts(target)}


def _counts(graph: str) -> dict:
    g = db.client().select_graph(graph)
    return {name: g.ro_query(q).result_set[0][0] for name, q in COUNTS.items()}
