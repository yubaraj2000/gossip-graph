"""Seeding a village's social graph: characters with personality, and who-trusts-whom."""
from fastapi.testclient import TestClient

from memory import db, recall
from memory.app import app

client = TestClient(app)


def test_relationships_seed_trust_and_feed_recall(village):
    world_id, _, _ = village
    r = client.post(f"/worlds/{world_id}/relationships", json=[
        {"source": "p:4", "target": "p:3", "trust": 0.6},
        {"source": "p:4", "target": "p:404", "trust": 0.9},  # unknown character: skipped, not an error
    ])
    assert r.json() == {"world": world_id, "set": 1, "skipped_unknown_characters": 1}
    assert recall.recall(world_id, "p:4", "p:3")["trust"] == {"trust": 0.6, "interactions": 0}


def test_reseeding_updates_trust_but_keeps_history(village):
    world_id, _, _ = village
    client.post(f"/worlds/{world_id}/relationships", json=[{"source": "p:1", "target": "p:2", "trust": 0.6}])
    db.world_graph(world_id).query(
        "MATCH (:Character {id:'p:1'})-[k:KNOWS]->(:Character {id:'p:2'}) SET k.interactions = 5")
    client.post(f"/worlds/{world_id}/relationships", json=[{"source": "p:1", "target": "p:2", "trust": 0.8}])
    assert recall.recall(world_id, "p:1", "p:2")["trust"] == {"trust": 0.8, "interactions": 5}


def test_trust_must_be_between_0_and_1(village):
    world_id, _, _ = village
    r = client.post(f"/worlds/{world_id}/relationships", json=[{"source": "p:1", "target": "p:2", "trust": 1.5}])
    assert r.status_code == 422
