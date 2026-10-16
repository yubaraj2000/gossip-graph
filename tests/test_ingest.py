"""Ingest pipeline against real FalkorDB, with the LLM replaced by scripted extractions and fake embeddings."""
from fastapi.testclient import TestClient

from memory import db, ingest
from memory.app import app
from tests.helpers import NAMES, THEFT, belief, two_way


def test_gossip_chain_and_provenance(village):
    world_id, scripted, _ = village
    scripted["c:1"] = [{"message_index": 0, **THEFT}]
    scripted["c:2"] = [{"message_index": 0, **THEFT}]
    ingest.ingest_conversation(world_id, two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!"))
    ingest.ingest_conversation(world_id, two_way("c:2", "p:2", "p:3", "Kai stole Bram's hammer!"))

    assert belief(world_id, "p:1") == (0.6, "self")    # Bram asserted it with no recorded source
    assert belief(world_id, "p:2") == (0.54, "heard")  # 0.6 x Pip's gullibility 0.9
    assert belief(world_id, "p:3") == (0.432, "heard") # 0.54 x Mara's gullibility 0.8
    chain = db.world_graph(world_id).ro_query("""
        MATCH (:Character {id:'p:3'})<-[:HELD_BY]-(b:Belief)
        MATCH p = (b)-[:HEARD_FROM*0..8]->(root:Belief) WHERE NOT (root)-[:HEARD_FROM]->()
        RETURN [x IN nodes(p) | x.holder], root.origin""").result_set
    assert chain == [[["p:3", "p:2", "p:1"], "self"]]


def test_same_conversation_twice_is_ingested_once(village):
    world_id, scripted, calls = village
    scripted["c:1"] = [{"message_index": 0, **THEFT}]
    c = two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!")
    assert ingest.ingest_conversation(world_id, c)["status"] == "ingested"
    assert ingest.ingest_conversation(world_id, c)["status"] == "skipped"
    assert calls == ["c:1"]
    assert belief(world_id, "p:2") == (0.54, "heard")


def test_hearing_your_own_rumor_back_does_not_reinforce_it(village):
    world_id, scripted, _ = village
    scripted["c:1"] = [{"message_index": 0, **THEFT}, {"message_index": 1, **THEFT}]  # Pip repeats it back
    ingest.ingest_conversation(world_id, two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!"))
    assert belief(world_id, "p:1") == (0.6, "self")
    echoes = db.world_graph(world_id).ro_query(
        "MATCH (:Belief {holder:'p:1'})-[:HEARD_FROM]->(:Belief {holder:'p:2'}) RETURN count(*)").result_set
    assert echoes == [[0]]


def test_second_independent_source_raises_confidence(village):
    world_id, scripted, _ = village
    for cid in ("c:1", "c:2", "c:3"):
        scripted[cid] = [{"message_index": 0, **THEFT}]
    ingest.ingest_conversation(world_id, two_way("c:1", "p:1", "p:2", "Kai stole from me!"))   # Pip 0.54
    ingest.ingest_conversation(world_id, two_way("c:2", "p:2", "p:4", "Kai stole from Bram!")) # Tom 0.54 x 0.3
    ingest.ingest_conversation(world_id, two_way("c:3", "p:1", "p:4", "Kai stole from me!"))   # + 0.6 x 0.3
    assert belief(world_id, "p:4") == (round(1 - (1 - 0.162) * (1 - 0.18), 3), "heard")


def test_nobody_adopts_a_claim_about_themselves(village):
    world_id, scripted, _ = village
    scripted["c:1"] = [{"message_index": 0, **THEFT}]
    ingest.ingest_conversation(world_id, two_way("c:1", "p:2", "p:9", "Kai, they say you stole Bram's hammer!"))
    assert belief(world_id, "p:9") is None
    assert belief(world_id, "p:2") == (0.6, "self")


def test_near_duplicate_claim_text_reuses_the_claim(village):
    world_id, scripted, _ = village
    scripted["c:1"] = [{"message_index": 0, **THEFT}]
    scripted["c:2"] = [{"message_index": 0, "subject": "Kai", "predicate": "did", "object": "",
                        "text": "Kai swiped Bram's silver hammer", "valence": -1}]
    ingest.ingest_conversation(world_id, two_way("c:1", "p:1", "p:2", "Kai stole from me!"))
    ingest.ingest_conversation(world_id, two_way("c:2", "p:3", "p:4", "Kai swiped Bram's hammer"))
    claims = db.world_graph(world_id).ro_query("MATCH (c:Claim) RETURN count(c)").result_set
    assert claims == [[1]]


def test_validation_fixes_or_drops_bad_claims():
    people = {n.lower(): i for i, n in NAMES.items()}
    msgs = [{"author": "p:1"}, {"author": "p:2"}]
    ok, dropped = ingest._validate([
        {"message_index": 0, "subject": "Kai", "predicate": "stole_from", "object": "a silver hammer",
         "text": "Kai stole a silver hammer from Bram", "valence": -3},
        {"message_index": 1, "subject": "Kai", "predicate": "helped", "object": "the miller",
         "text": "Kai helped the miller", "valence": 0.5},
        {"message_index": 0, "subject": "the merchant", "predicate": "is", "object": "", "text": "x", "valence": -0.5},
        {"message_index": 1, "subject": "Tom", "predicate": "likes", "object": "rare spices",
         "text": "I've had my eye on that merchant", "valence": 0.5},
        {"message_index": 7, "subject": "Kai", "predicate": "is", "object": "", "text": "Kai is rude", "valence": -0.5},
        {"message_index": 0, "subject": "Kai", "predicate": "did", "object": "",
         "text": "Kai heard fascinating tales lately", "valence": 0.0},
    ], msgs, people)
    assert [(c["key"], c["valence"], c["speaker"]) for c in ok] == [
        ("p:9|stole_from|p:1", -1.0, "p:1"),  # object fixed from the text, valence clamped
        ("p:9|did|miller", 0.5, "p:2"),        # no person to help -> downgraded to "did"
    ]
    assert sorted(d["reason"] for d in dropped) == [
        "message_index out of range", "neutral, not gossip", "text does not name the subject", "unknown subject"]


def test_api_ingest_endpoint(village):
    world_id, scripted, _ = village
    scripted["c:1"] = [{"message_index": 0, **THEFT}]
    client = TestClient(app)
    body = two_way("c:1", "p:1", "p:2", "Kai stole from me!").model_dump()
    first = client.post(f"/worlds/{world_id}/conversations", json=body)
    assert first.status_code == 200 and first.json()["status"] == "ingested"
    assert first.json()["beliefs"] == [{"holder": "p:2", "claim": first.json()["claims"][0]["id"],
                                        "confidence": 0.54, "from": "p:1"}]
    assert client.post(f"/worlds/{world_id}/conversations", json=body).json()["status"] == "skipped"
    body["messages"][0]["author"] = "p:4"  # not a participant
    assert client.post(f"/worlds/{world_id}/conversations", json=body).status_code == 422


def test_names_with_forms_of_address_resolve_unambiguously():
    people = {"bram": "p:1", "pandit shastri": "p:5", "balwant": "p:6", "gopal": "p:7"}
    resolve = ingest._resolve_person
    assert resolve("Balwant Singh", people) == "p:6"
    assert resolve("Shastri ji", people) == "p:5"
    assert resolve("Pandit ji", people) == "p:5"
    assert resolve("Gopal bhai", people) == "p:7"
    assert resolve("Ramu Patel", people) is None  # invented outsider
    assert resolve("", people) is None
    assert resolve("Pandit Gopal", {"pandit shastri": "p:5", "gopal": "p:7"}) is None  # ambiguous -> no guess
    assert ingest._names_person("Shastri ji is wary of gossip", "Pandit Shastri")
    assert not ingest._names_person("The priest is wary of gossip", "Pandit Shastri")
