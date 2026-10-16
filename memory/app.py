"""HTTP API of the graph-memory service. AI Town's Convex backend calls it via host.docker.internal.

Run: uv run uvicorn memory.app:app --host 127.0.0.1 --port 8100
"""
import httpx
from fastapi import FastAPI, HTTPException

from memory import db
from memory.config import settings

app = FastAPI(title="gossip-graph memory service")


@app.get("/health")
def health() -> dict:
    try:
        falkordb_ok = bool(db.client().connection.ping())
    except Exception:
        falkordb_ok = False
    try:
        ollama = httpx.get(f"{settings.ollama_url}/api/version", timeout=3).json()["version"]
    except Exception:
        ollama = None
    return {"falkordb": falkordb_ok, "ollama": ollama}


@app.get("/worlds")
def list_worlds() -> dict:
    return {"worlds": db.list_worlds()}


@app.post("/worlds/{world_id}")
def create_world(world_id: str) -> dict:
    """Create (or repair) a world's graph schema. Idempotent."""
    try:
        created = db.ensure_schema(world_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"world": world_id, "graph": db.graph_name(world_id), "indexes_created": created}
