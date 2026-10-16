"""Tests run against the local FalkorDB (docker compose up -d) using throwaway world graphs."""
import uuid

import pytest

from memory import db, extract, ingest, llm
from tests.helpers import FENCE, THEFT, TROUBLEMAKER, VILLAGE, fake_embed, two_way


@pytest.fixture
def world_id():
    wid = "test_" + uuid.uuid4().hex[:8]
    yield wid
    if db.graph_name(wid) in db.client().list_graphs():
        db.world_graph(wid).delete()


@pytest.fixture
def village(world_id, monkeypatch):
    """A seeded world whose extractor returns `scripted[conversation_id]`."""
    scripted, calls = {}, []

    def fake_extract(conv, known_people):
        calls.append(conv.id)
        return {"summary": f"summary of {conv.id}", "claims": scripted.get(conv.id, [])}

    monkeypatch.setattr(extract, "extract", fake_extract)
    monkeypatch.setattr(llm, "embed", fake_embed)
    db.ensure_world(world_id)
    ingest.upsert_characters(db.world_graph(world_id), VILLAGE)
    return world_id, scripted, calls


@pytest.fixture
def gossip(village):
    """Bram -> Pip (theft; Pip adds 'troublemaker'), Pip -> Mara (theft), Mara -> Tom (theft + fence mutation)."""
    world_id, scripted, _ = village
    scripted["c:1"] = [{"message_index": 0, **THEFT}, {"message_index": 1, **TROUBLEMAKER}]
    scripted["c:2"] = [{"message_index": 0, **THEFT}]
    scripted["c:3"] = [{"message_index": 0, **THEFT}, {"message_index": 0, **FENCE}]
    ingest.ingest_conversation(world_id, two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!"))
    ingest.ingest_conversation(world_id, two_way("c:2", "p:2", "p:3", "Kai stole Bram's hammer!"))
    ingest.ingest_conversation(world_id, two_way("c:3", "p:3", "p:4", "Kai stole it and tried to fence it!"))
    return world_id
