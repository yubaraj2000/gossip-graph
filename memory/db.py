"""FalkorDB access: one graph per world (plus village templates to start worlds from), and idempotent schema setup."""
import re
import threading
from functools import lru_cache

from falkordb import FalkorDB, Graph
from redis.exceptions import ResponseError

from memory.config import settings

WORLD_PREFIX = "world_"
TEMPLATE_PREFIX = "template_"
_WORLD_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

# Mirrors the "Indexes" section of docs/DATA_MODEL.md.
RANGE_INDEXES = [
    ("Character", "id"),
    ("Conversation", "id"),
    ("Message", "id"),
    ("Event", "id"),
    ("Claim", "id"),
    ("Claim", "key"),
    ("Belief", "holder"),
    ("Belief", "claim"),
]
VECTOR_INDEXES = [("Claim", "embedding")]


@lru_cache(maxsize=1)
def client() -> FalkorDB:
    return FalkorDB(host=settings.falkordb_host, port=settings.falkordb_port)


def graph_name(world_id: str) -> str:
    """World ids come from AI Town (Convex ids); anything else is rejected before it reaches FalkorDB."""
    if not _WORLD_ID.fullmatch(world_id):
        raise ValueError(f"invalid world id: {world_id!r}")
    return WORLD_PREFIX + world_id


def world_graph(world_id: str) -> Graph:
    return client().select_graph(graph_name(world_id))


def template_graph_name(name: str) -> str:
    if not _WORLD_ID.fullmatch(name):
        raise ValueError(f"invalid template name: {name!r}")
    return TEMPLATE_PREFIX + name


def template_graph(name: str) -> Graph:
    return client().select_graph(template_graph_name(name))


def list_worlds() -> list[str]:
    return sorted(n.removeprefix(WORLD_PREFIX) for n in client().list_graphs() if n.startswith(WORLD_PREFIX))


def list_templates() -> list[str]:
    return sorted(n.removeprefix(TEMPLATE_PREFIX) for n in client().list_graphs() if n.startswith(TEMPLATE_PREFIX))


def exists(graph: str) -> bool:
    return graph in client().list_graphs()


def existing_indexes(world_id: str) -> set[tuple[str, str, str]]:
    """(label, property, kind) for every index in the world's graph."""
    return _indexes(graph_name(world_id))


def _indexes(graph: str) -> set[tuple[str, str, str]]:
    # Querying a graph that was never written to fails with "empty key", so check first.
    if not exists(graph):
        return set()
    rows = client().select_graph(graph).ro_query("CALL db.indexes() YIELD label, types RETURN label, types").result_set
    return {(label, prop, kind) for label, types in rows for prop, kinds in types.items() for kind in kinds}


_ready: set[str] = set()
_ready_lock = threading.Lock()


def ensure_world(world_id: str) -> None:
    """ensure_schema, but only once per world per process (it is on every ingest's hot path).

    AI Town reports each conversation once per NPC, at the same moment, so a brand-new world gets
    concurrent first calls: the lock makes one of them set the schema up while the others wait."""
    if world_id in _ready:
        return
    with _ready_lock:
        if world_id not in _ready:
            ensure_schema(world_id)
            _ready.add(world_id)


def delete_world(world_id: str) -> bool:
    """Delete a world's graph. True if it existed. The next write to this world id sets its schema up again."""
    name = graph_name(world_id)
    with _ready_lock:
        _ready.discard(world_id)
        if not exists(name):
            return False
        client().select_graph(name).delete()
        return True


def ensure_schema(world_id: str) -> list[str]:
    """Create any missing indexes for a world. Safe to call repeatedly; returns what it created."""
    return ensure_graph_schema(graph_name(world_id))


def ensure_graph_schema(graph: str) -> list[str]:
    """ensure_schema for any graph name (worlds and templates share one schema)."""
    g = client().select_graph(graph)
    have = _indexes(graph)
    created = []
    for label, prop in RANGE_INDEXES:
        if (label, prop, "RANGE") not in have and _create_index(g, f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"):
            created.append(f"{label}.{prop}")
    for label, prop in VECTOR_INDEXES:
        if (label, prop, "VECTOR") not in have and _create_index(
                g, f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.{prop}) "
                   f"OPTIONS {{dimension:{settings.embedding_dim}, similarityFunction:'cosine'}}"):
            created.append(f"{label}.{prop} (vector)")
    return created


def _create_index(g: Graph, cypher: str) -> bool:
    """True if this call created the index; False if someone else (another thread or process) got there first."""
    try:
        g.query(cypher)
        return True
    except ResponseError as e:
        if "already indexed" in str(e):
            return False
        raise
