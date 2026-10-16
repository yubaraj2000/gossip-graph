"""FalkorDB access: one graph per world, plus idempotent schema setup."""
import re
from functools import lru_cache

from falkordb import FalkorDB, Graph

from memory.config import settings

WORLD_PREFIX = "world_"
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


def list_worlds() -> list[str]:
    return sorted(n.removeprefix(WORLD_PREFIX) for n in client().list_graphs() if n.startswith(WORLD_PREFIX))


def existing_indexes(world_id: str) -> set[tuple[str, str, str]]:
    """(label, property, kind) for every index in the world's graph."""
    # Querying a graph that was never written to fails with "empty key", so check first.
    if graph_name(world_id) not in client().list_graphs():
        return set()
    rows = world_graph(world_id).ro_query("CALL db.indexes() YIELD label, types RETURN label, types").result_set
    return {(label, prop, kind) for label, types in rows for prop, kinds in types.items() for kind in kinds}


def ensure_schema(world_id: str) -> list[str]:
    """Create any missing indexes for a world. Safe to call repeatedly; returns what it created."""
    g = world_graph(world_id)
    have = existing_indexes(world_id)
    created = []
    for label, prop in RANGE_INDEXES:
        if (label, prop, "RANGE") not in have:
            g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
            created.append(f"{label}.{prop}")
    for label, prop in VECTOR_INDEXES:
        if (label, prop, "VECTOR") not in have:
            g.query(
                f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.{prop}) "
                f"OPTIONS {{dimension:{settings.embedding_dim}, similarityFunction:'cosine'}}"
            )
            created.append(f"{label}.{prop} (vector)")
    return created
