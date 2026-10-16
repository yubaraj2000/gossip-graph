"""Explain ("who told you that?") against real FalkorDB: paths, the line heard at each hop, answer sentences."""
from fastapi.testclient import TestClient

from memory import explain, ingest
from memory.app import app
from tests.helpers import THEFT, seed_witnessed_theft, two_way

THEFT_TEXT = "Kai stole a silver hammer from Bram"


def belief(r, text):
    return next(b for b in r["beliefs"] if b["text"] == text)


def test_full_chain_with_the_line_heard_at_each_hop(gossip):
    r = explain.explain(gossip, "p:4", subject="p:9")
    theft = belief(r, THEFT_TEXT)
    assert theft["sentence"] == ("Mara told me. Mara heard it from Pip, who heard it from Bram. "
                                 "Bram started it, and nobody saw it happen.")
    assert theft["verdict"] == "unverified" and theft["grounded"] is False
    steps = theft["paths"][0]["steps"]
    assert [s["name"] for s in steps] == ["Tom", "Mara", "Pip", "Bram"]
    assert [s["heard_line"] for s in steps] == [
        "Kai stole it and tried to fence it!", "Kai stole Bram's hammer!", "Kai stole a silver hammer from me!", None]
    assert [s["confidence"] for s in steps] == [round(0.432 * 0.3, 3), 0.432, 0.54, 0.6]


def test_a_mutated_rumor_traces_to_whoever_changed_it(gossip):
    fence = belief(explain.explain(gossip, "p:4"), "Kai was spotted trying to fence a stolen hammer")
    assert fence["sentence"] == "Mara told me. Mara started it, and nobody saw it happen."


def test_a_second_source_shows_up_as_another_path(gossip, monkeypatch):
    from memory import extract
    monkeypatch.setattr(extract, "extract", lambda conv, known_people: {
        "summary": "s", "claims": [{"message_index": 0, **THEFT}]})
    ingest.ingest_conversation(gossip, two_way("c:4", "p:1", "p:4", "Kai stole from me, Tom."))
    theft = belief(explain.explain(gossip, "p:4"), THEFT_TEXT)
    assert [p["chain"] for p in theft["paths"]] == [["p:4", "p:1"], ["p:4", "p:3", "p:2", "p:1"]]
    assert theft["sentence"] == ("Bram told me. Bram started it, and nobody saw it happen. "
                                 "I also heard it from Mara.")


def test_a_witnessed_event_grounds_the_whole_chain(village):
    world_id, scripted, _ = village
    seed_witnessed_theft(world_id)
    scripted["c:1"] = scripted["c:2"] = [{"message_index": 0, **THEFT}]
    ingest.ingest_conversation(world_id, two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!"))
    ingest.ingest_conversation(world_id, two_way("c:2", "p:2", "p:3", "Kai stole Bram's hammer!"))
    theft = belief(explain.explain(world_id, "p:3"), THEFT_TEXT)
    assert theft["sentence"] == "Pip told me. Pip heard it from Bram. Bram saw it happen."
    assert theft["verdict"] == "witnessed" and theft["grounded"] is True
    assert theft["paths"][0]["event"] == "Kai stole a silver hammer from Bram"
    assert theft["confidence"] == round(1.0 * 0.9 * 0.8, 3)  # an eyewitness starts at 1.0, not 0.6
    assert belief(explain.explain(world_id, "p:1"), THEFT_TEXT)["sentence"] == "I saw it myself."


def test_the_originator_says_so(gossip):
    theft = belief(explain.explain(gossip, "p:1"), THEFT_TEXT)
    assert theft["sentence"] == "Nobody told me; I said it first."


def test_filters_and_unknowns(gossip, world_id):
    everything = explain.explain(gossip, "p:4")
    one = everything["beliefs"][0]["claim"]
    assert [b["claim"] for b in explain.explain(gossip, "p:4", claim=one)["beliefs"]] == [one]
    assert explain.explain(gossip, "p:4", subject="p:1")["beliefs"] == []
    assert explain.explain(gossip, "p:404")["known"] is False
    assert explain.explain(world_id + "_missing", "p:4")["known"] is False


def test_explain_endpoint(gossip):
    client = TestClient(app)
    r = client.get(f"/worlds/{gossip}/explain", params={"holder": "p:4", "subject": "p:9"})
    assert r.status_code == 200 and len(r.json()["beliefs"]) == 2
    assert client.get(f"/worlds/{gossip}/explain").status_code == 422
    assert client.get("/worlds/bad id/explain", params={"holder": "p:4"}).status_code == 422
