"""Recall against real FalkorDB: ranking, already-shared damping, reputation, trust, episodes, memory lines."""
from fastapi.testclient import TestClient

from memory import recall
from memory.app import app

def by_text(r):
    return {b["text"]: b for b in r["beliefs"]}


def test_rumors_already_exchanged_with_the_listener_are_damped(gossip):
    r = recall.recall(gossip, "p:2", "p:1")  # Pip about to talk to Bram, who told him about the theft
    beliefs = by_text(r)
    theft = beliefs["Kai stole a silver hammer from Bram"]
    assert theft["already_shared"] and theft["told_by"] == ["Bram"]
    assert theft["score"] == round(0.54 * 1.0 * 1.0 * recall.ALREADY_SHARED_DAMPING, 3)
    assert beliefs["Kai has always been a troublemaker"]["already_shared"]  # Bram heard that one from Pip


def test_fresh_gossip_is_not_marked_shared(gossip):
    r = recall.recall(gossip, "p:3", "p:1")  # Mara has never talked to Bram
    assert not any(b["already_shared"] for b in r["beliefs"])
    assert r["trust"] is None and r["episodes"] == []


def test_claims_about_the_listener_rank_first_and_shape_reputation(gossip):
    r = recall.recall(gossip, "p:4", "p:9")  # suspicious Tom about to talk to Kai himself
    assert all(b["about_other"] for b in r["beliefs"])
    theft = by_text(r)["Kai stole a silver hammer from Bram"]
    assert theft["confidence"] == round(0.432 * 0.3, 3)       # heard via Mara, Tom's gullibility 0.3
    assert theft["score"] == round(0.432 * 0.3 * 1.0 * 2.0, 3)  # x2: it's about the listener
    assert r["reputation"]["evidence"] == 2 and r["reputation"]["score"] < 0
    assert "My impression of Kai is bad." in r["memories"]


def test_k_limits_and_orders_by_score(gossip):
    r = recall.recall(gossip, "p:4", "p:9", k=1)
    assert len(r["beliefs"]) == 1
    full = recall.recall(gossip, "p:4", "p:9", k=10)["beliefs"]
    assert [b["score"] for b in full] == sorted((b["score"] for b in full), reverse=True)


def test_episodes_and_trust_come_from_past_conversations(gossip):
    r = recall.recall(gossip, "p:3", "p:4")  # Mara -> Tom: they talked in c:3
    assert [e["conversation"] for e in r["episodes"]] == ["c:3"]
    assert r["trust"] == {"trust": 0.8, "interactions": 1}  # Mara's gullibility 0.8 on first contact
    assert r["memories"][0] == "I trust Tom; we've talked 1 time(s)."
    assert r["memories"][1] == "Last time Tom and I talked: summary of c:3"


def test_memory_lines_are_first_person(gossip):
    lines = recall.recall(gossip, "p:1", "p:2")["memories"]  # Bram's own view
    assert "I've been saying that Kai stole a silver hammer from me (I believe it). " \
           "Pip and I already talked about this." in lines
    lines = recall.recall(gossip, "p:3", "p:4")["memories"]
    assert "Pip told me that Kai stole a silver hammer from Bram (I'm not certain). " \
           "Tom and I already talked about this." in lines


def test_unknown_characters_and_worlds_recall_nothing(gossip, world_id):
    assert recall.recall(gossip, "p:404", "p:1")["known"] is False
    assert recall.recall(world_id + "_missing", "p:1", "p:2") == recall._empty("p:1", "p:2")


def test_recall_endpoint(gossip):
    client = TestClient(app)
    r = client.get(f"/worlds/{gossip}/recall", params={"me": "p:4", "other": "p:9", "k": 2})
    assert r.status_code == 200 and len(r.json()["beliefs"]) == 2
    assert client.get(f"/worlds/{gossip}/recall", params={"me": "p:4"}).status_code == 422
    assert client.get(f"/worlds/{gossip}/recall", params={"me": "p:4", "other": "p:9", "k": 99}).status_code == 422
    assert client.get("/worlds/bad id/recall", params={"me": "p:1", "other": "p:2"}).status_code == 422
