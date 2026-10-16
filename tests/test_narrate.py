"""Narrator events: ground truth, witnessed beliefs, and how gossip attaches to them."""
from fastapi.testclient import TestClient

from memory import db, explain, ingest
from memory.app import app
from tests.helpers import THEFT, two_way

client = TestClient(app)
THEFT_EVENT = {"kind": "stole_from", "actor": "Kai", "target": "Bram", "valence": -1.0,
               "description": "Kai stole a silver hammer from Bram", "witnesses": ["Bram"]}


def narrate(world_id, **overrides):
    r = client.post(f"/worlds/{world_id}/events", json={**THEFT_EVENT, **overrides})
    assert r.status_code == 200, r.text
    return r.json()


def theft(world_id, holder):
    r = explain.explain(world_id, holder)
    return next(b for b in r["beliefs"] if b["text"] == "Kai stole a silver hammer from Bram")


def test_an_event_grounds_its_claim_and_its_witnesses_know(village):
    world_id, _, _ = village
    out = narrate(world_id)
    assert out["witnesses"] == ["p:1"]
    bram = theft(world_id, "p:1")
    assert (bram["origin"], bram["confidence"], bram["grounded"]) == ("witnessed", 1.0, True)
    assert bram["sentence"] == "I saw it myself."


def test_gossip_about_the_event_traces_back_to_the_witness(village):
    world_id, scripted, _ = village
    narrate(world_id)
    scripted["c:1"] = [{"message_index": 0, **THEFT}]  # same key as the event: kai|stole_from|bram
    ingest.ingest_conversation(world_id, two_way("c:1", "p:1", "p:2", "Kai stole my silver hammer!"))
    pip = theft(world_id, "p:2")
    assert pip["confidence"] == 0.9  # 1.0 (eyewitness) x Pip's gullibility 0.9
    assert (pip["sentence"], pip["verdict"]) == ("Bram told me. Bram saw it happen.", "witnessed")


def test_an_event_recorded_after_the_gossip_upgrades_it(village):
    world_id, scripted, _ = village
    scripted["c:1"] = [{"message_index": 0, **THEFT}]
    ingest.ingest_conversation(world_id, two_way("c:1", "p:1", "p:2", "Kai stole my silver hammer!"))
    assert theft(world_id, "p:2")["sentence"] == "Bram told me. Bram started it, and nobody saw it happen."
    narrate(world_id)  # the narrator confirms it really happened, and Bram saw it
    assert theft(world_id, "p:1")["origin"] == "witnessed"
    assert theft(world_id, "p:2")["sentence"] == "Bram told me. Bram saw it happen."
    assert db.world_graph(world_id).ro_query("MATCH (c:Claim) RETURN count(c)").result_set == [[1]]


def test_the_event_grounds_a_paraphrased_rumor_too(village):
    world_id, scripted, _ = village
    scripted["c:1"] = [{"message_index": 0, "subject": "Kai", "predicate": "did", "object": "",
                        "text": "Kai swiped Bram's silver hammer", "valence": -1}]  # different key, same meaning
    ingest.ingest_conversation(world_id, two_way("c:1", "p:3", "p:4", "Kai swiped Bram's silver hammer"))
    out = narrate(world_id)
    assert out["claim_text"] == "Kai swiped Bram's silver hammer"  # grounded the existing rumor, no duplicate
    assert db.world_graph(world_id).ro_query("MATCH (c:Claim) RETURN count(c)").result_set == [[1]]


def test_the_same_event_twice_changes_nothing(village):
    world_id, _, _ = village
    first, second = narrate(world_id), narrate(world_id)
    assert first["event"] == second["event"]
    g = db.world_graph(world_id)
    assert g.ro_query("MATCH (e:Event) RETURN count(e)").result_set == [[1]]
    assert g.ro_query("MATCH (b:Belief) RETURN count(b)").result_set == [[1]]


def test_names_ids_and_honorifics_resolve(village):
    world_id, _, _ = village
    out = narrate(world_id, actor="p:9", target="Bram ji", witnesses=["Mara", "p:4", "Kai"])
    assert out["witnesses"] == ["p:3", "p:4"]  # the actor isn't given a belief about themselves


def test_bad_events_are_rejected(village):
    world_id, _, _ = village
    unknown = client.post(f"/worlds/{world_id}/events", json={**THEFT_EVENT, "witnesses": ["Ghost"]})
    assert unknown.status_code == 422 and "Ghost" in unknown.text
    bad_kind = client.post(f"/worlds/{world_id}/events", json={**THEFT_EVENT, "kind": "teleported"})
    assert bad_kind.status_code == 422
