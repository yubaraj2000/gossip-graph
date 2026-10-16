"""HTTP API of the graph-memory service. AI Town's Convex backend calls it via host.docker.internal.

Run: uv run uvicorn memory.app:app --host 127.0.0.1 --port 8100
Assumes a single service process: at startup, any 'ingesting' conversation is treated as interrupted.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query

from memory import db, explain, ingest, llm, narrate, recall
from memory.config import settings
from memory.models import CharacterIn, ConversationIn, EventIn, RelationshipIn

log = logging.getLogger("memory")


@asynccontextmanager
async def lifespan(_: FastAPI):
    for world_id in db.list_worlds():
        if n := ingest.recover_interrupted(world_id):
            log.warning("world %s: %d interrupted conversation(s) marked failed for retry", world_id, n)
    task = asyncio.create_task(_retry_loop())
    yield
    task.cancel()


async def _retry_loop() -> None:
    """Failed conversations (model outage, crash) are re-ingested from their stored transcript."""
    while True:
        await asyncio.sleep(settings.retry_interval_s)
        if not _ollama_version():
            continue
        for world_id in db.list_worlds():
            try:
                for r in await asyncio.to_thread(ingest.retry_failed, world_id):
                    log.warning("world %s: retried %s -> %s", world_id, r["conversation"], r["status"])
            except Exception:
                log.exception("world %s: retry pass failed", world_id)


def _ollama_version() -> str | None:
    try:
        return httpx.get(f"{settings.ollama_url}/api/version", timeout=3).json()["version"]
    except Exception:
        return None


app = FastAPI(title="gossip-graph memory service", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    try:
        falkordb_ok = bool(db.client().connection.ping())
    except Exception:
        falkordb_ok = False
    return {"falkordb": falkordb_ok, "ollama": _ollama_version()}


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


@app.post("/worlds/{world_id}/characters")
def upsert_characters(world_id: str, characters: list[CharacterIn]) -> dict:
    """Seed or update the village's characters (names, identities, gullibility)."""
    try:
        db.ensure_world(world_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    ingest.upsert_characters(db.world_graph(world_id), characters)
    return {"world": world_id, "characters": len(characters)}


@app.post("/worlds/{world_id}/relationships")
def set_relationships(world_id: str, relationships: list[RelationshipIn]) -> dict:
    """Seed who-trusts-whom (directed KNOWS edges). Both characters must already exist."""
    _check_world_id(world_id)
    db.ensure_world(world_id)
    done = ingest.set_relationships(db.world_graph(world_id), relationships)
    return {"world": world_id, "set": done, "skipped_unknown_characters": len(relationships) - done}


@app.post("/worlds/{world_id}/events")
def narrate_event(world_id: str, event: EventIn) -> dict:
    """Narrator: record something that really happened, ground the matching claim and give witnesses a
    'witnessed' belief. Idempotent for the same event."""
    _check_world_id(world_id)
    try:
        return narrate.narrate(world_id, event)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except llm.LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/worlds/{world_id}/conversations")
def ingest_conversation(world_id: str, conv: ConversationIn) -> dict:
    """Store a finished conversation and spread its claims as beliefs. Safe to call more than once."""
    _check_world_id(world_id)
    try:
        return ingest.ingest_conversation(world_id, conv)
    except llm.LLMError as e:
        # The transcript is stored and the conversation marked 'failed'; the retry loop will pick it up.
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/worlds/{world_id}/retry")
def retry_failed(world_id: str) -> dict:
    """Re-ingest this world's failed conversations now instead of waiting for the retry loop."""
    _check_world_id(world_id)
    return {"world": world_id, "results": ingest.retry_failed(world_id)}


@app.get("/worlds/{world_id}/recall")
def recall_memories(world_id: str, me: str, other: str, k: int = Query(5, ge=1, le=20),
                    episodes: int = Query(3, ge=0, le=10)) -> dict:
    """What `me` remembers when about to talk to `other`: ranked gossip, reputation, trust, past talks.

    Graph-only (no LLM), so it is fast enough to call before every line of dialogue."""
    _check_world_id(world_id)
    return recall.recall(world_id, me, other, k=k, episodes=episodes)


@app.get("/worlds/{world_id}/explain")
def explain_beliefs(world_id: str, holder: str, claim: str | None = None, subject: str | None = None) -> dict:
    """"Who told you that?": every provenance path behind `holder`'s beliefs (optionally one claim, or one subject),
    with the line heard at each hop and an answer sentence built straight from the graph."""
    _check_world_id(world_id)
    return explain.explain(world_id, holder, claim=claim, subject=subject)


def _check_world_id(world_id: str) -> None:
    try:
        db.graph_name(world_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
