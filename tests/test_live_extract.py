"""End-to-end ingest with the real LLM (Ollama via the tunnel). Slow, so opt-in: RUN_LIVE=1 uv run pytest -k live"""
import os

import pytest

from memory import db, ingest
from memory.models import CharacterIn, ConversationIn

pytestmark = pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to call the real LLM")


def test_live_theft_gossip_is_extracted_and_spread(world_id):
    db.ensure_world(world_id)
    ingest.upsert_characters(db.world_graph(world_id), [
        CharacterIn(id="p:1", name="Bram"), CharacterIn(id="p:2", name="Pip", gullibility=0.9),
        CharacterIn(id="p:9", name="Kai", kind="human"),
    ])
    conv = ConversationIn(id="c:1", participants=[{"id": "p:1", "name": "Bram"}, {"id": "p:2", "name": "Pip"}],
                          messages=[
        {"author": "p:1", "ts": 1, "text": "Pip, I've got a problem with Kai - that scamp stole a silver hammer "
                                           "right out of my forge, and I saw him do it with my own two eyes."},
        {"author": "p:2", "ts": 2, "text": "Oh no, Master! Can we go get the hammer back from Kai, he's always "
                                           "been a bit of a troublemaker!"},
    ])
    out = ingest.ingest_conversation(world_id, conv)
    keys = [c["key"] for c in out["claims"]]
    assert "p:9|stole_from|p:1" in keys, out
    assert any(b["holder"] == "p:2" and b["from"] == "p:1" for b in out["beliefs"]), out
