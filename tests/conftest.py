"""Tests run against the local FalkorDB (docker compose up -d) using throwaway world graphs."""
import uuid

import pytest

from memory import db, extract, ingest, llm
from tests.helpers import VILLAGE, fake_embed


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
