"""Ways the ingest pipeline must not break: bad model output, model outages, concurrency, crashes, odd input."""
import threading
import time
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from memory import db, extract, ingest, llm
from memory.app import app
from tests.helpers import THEFT, VILLAGE, belief, two_way

client = TestClient(app)


def post(world_id, conv):
    return client.post(f"/worlds/{world_id}/conversations", json=conv.model_dump())


def status(world_id, cid):
    rows = db.world_graph(world_id).ro_query("MATCH (c:Conversation {id:$id}) RETURN c.status", {"id": cid})
    return rows.result_set[0][0] if rows.result_set else None


@pytest.mark.parametrize("bad_claim", [
    {**THEFT, "message_index": 0, "valence": "very bad"},
    {**THEFT, "message_index": "one"},
    {**THEFT, "message_index": 0, "subject": None},
    {**THEFT, "message_index": 0, "text": None},
    {**THEFT, "message_index": 0, "valence": True},
    "Kai stole the hammer",
    None,
])
def test_a_malformed_claim_is_dropped_without_losing_the_good_one(village, bad_claim):
    world_id, scripted, _ = village
    scripted["c:1"] = [bad_claim, {**THEFT, "message_index": 0}]
    r = post(world_id, two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!"))
    assert r.status_code == 200 and r.json()["status"] == "ingested"
    assert len(r.json()["dropped"]) == 1
    assert belief(world_id, "p:2") == (0.54, "heard")


def test_numeric_strings_from_the_model_are_accepted(village):
    world_id, scripted, _ = village
    scripted["c:1"] = [{**THEFT, "message_index": "0", "valence": "-1"}]
    post(world_id, two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!"))
    assert belief(world_id, "p:2") == (0.54, "heard")


@pytest.mark.parametrize("raw", [{"summary": "s"}, {"claims": []}, {"summary": None, "claims": None}])
def test_missing_fields_mean_no_claims(village, raw, monkeypatch):
    world_id, _, _ = village
    monkeypatch.setattr(extract, "extract", lambda conv, known_people: raw)
    r = post(world_id, two_way("c:1", "p:1", "p:2", "Lovely weather."))
    assert r.status_code == 200 and r.json()["claims"] == []


def test_claims_that_are_not_a_list_count_as_a_model_failure(village, monkeypatch):
    world_id, _, _ = village
    monkeypatch.setattr(extract, "extract", lambda conv, known_people: {"summary": "s", "claims": "none"})
    assert post(world_id, two_way("c:1", "p:1", "p:2", "Hi")).status_code == 502
    assert status(world_id, "c:1") == "failed"


def _real_extract_with_http(monkeypatch, fake_post):
    """Route extraction through the real llm.chat_json, with httpx.post replaced."""
    monkeypatch.setattr(extract, "extract", lambda conv, known_people: llm.chat_json("system", "user", {}))
    monkeypatch.setattr(llm.httpx, "post", fake_post)


def test_invalid_json_from_the_model_is_a_502_and_keeps_the_transcript(village, monkeypatch):
    world_id, _, _ = village
    req = httpx.Request("POST", "http://ollama/api/chat")
    _real_extract_with_http(monkeypatch, lambda *a, **k: httpx.Response(
        200, json={"message": {"content": "Sure! Here are the claims:"}}, request=req))
    r = post(world_id, two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!"))
    assert r.status_code == 502
    assert status(world_id, "c:1") == "failed"
    msgs = db.world_graph(world_id).ro_query("MATCH (m:Message)-[:IN]->(:Conversation {id:'c:1'}) RETURN count(m)")
    assert msgs.result_set == [[2]]


def test_model_outage_then_retry_succeeds(village, monkeypatch):
    world_id, scripted, _ = village
    conv = two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!")

    def refused(*a, **k):
        raise httpx.ConnectError("connection refused")

    with monkeypatch.context() as m:
        _real_extract_with_http(m, refused)
        assert post(world_id, conv).status_code == 502
    assert status(world_id, "c:1") == "failed"
    scripted["c:1"] = [{**THEFT, "message_index": 0}]
    assert post(world_id, conv).json()["status"] == "ingested"
    assert belief(world_id, "p:2") == (0.54, "heard")


def test_embedding_count_mismatch_is_a_502(village, monkeypatch):
    world_id, scripted, _ = village
    scripted["c:1"] = [{**THEFT, "message_index": 0}]
    monkeypatch.setattr(llm, "embed", lambda texts: [])
    assert post(world_id, two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!")).status_code == 502


def test_same_conversation_from_eight_npcs_at_once_is_ingested_once(village, monkeypatch):
    world_id, _, _ = village
    calls = []

    def slow_extract(conv, known_people):
        calls.append(conv.id)
        time.sleep(0.3)
        return {"summary": "s", "claims": [{**THEFT, "message_index": 0}]}

    monkeypatch.setattr(extract, "extract", slow_extract)
    conv = two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!")
    statuses = []
    threads = [threading.Thread(target=lambda: statuses.append(post(world_id, conv).json()["status"]))
               for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(statuses) == ["ingested"] + ["skipped"] * 7
    assert calls == ["c:1"]
    assert belief(world_id, "p:2") == (0.54, "heard")


def test_thirty_conversations_at_once_across_three_worlds(village, monkeypatch):
    world_id, scripted, _ = village
    others = [f"{world_id}_{i}" for i in range(2)]
    try:
        for w in others:
            db.ensure_world(w)
            ingest.upsert_characters(db.world_graph(w), VILLAGE)
        monkeypatch.setattr(extract, "extract", lambda conv, known_people: (
            time.sleep(0.1), {"summary": "s", "claims": [{**THEFT, "message_index": 0}]})[1])
        pairs = [("p:1", "p:2"), ("p:2", "p:3"), ("p:3", "p:4"), ("p:1", "p:4"), ("p:2", "p:4")]
        codes = []

        def send(w, i):
            a, b = pairs[i % len(pairs)]
            codes.append(post(w, two_way(f"c:{i}", a, b, "Kai stole Bram's silver hammer!")).status_code)

        threads = [threading.Thread(target=send, args=(w, i)) for w in [world_id, *others] for i in range(10)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert codes == [200] * 30
        for w in [world_id, *others]:
            done = db.world_graph(w).ro_query("MATCH (c:Conversation {status:'ingested'}) RETURN count(c)")
            assert done.result_set == [[10]]
    finally:
        for w in others:
            db.world_graph(w).delete()


def test_a_crashed_ingest_is_retaken_once_stale(village):
    world_id, scripted, _ = village
    scripted["c:old"] = scripted["c:new"] = [{**THEFT, "message_index": 0}]
    now = time.time() * 1000
    g = db.world_graph(world_id)
    g.query("CREATE (:Conversation {id:'c:old', status:'ingesting', taken_at:$t})",
            {"t": now - ingest.STALE_INGEST_MS - 1000})
    g.query("CREATE (:Conversation {id:'c:new', status:'ingesting', taken_at:$t})", {"t": now})
    assert post(world_id, two_way("c:old", "p:1", "p:2", "Kai stole from me!")).json()["status"] == "ingested"
    assert post(world_id, two_way("c:new", "p:1", "p:3", "Kai stole from me!")).json()["status"] == "skipped"


def test_hostile_ids_and_text_are_stored_as_plain_data(village):
    world_id, scripted, _ = village
    cid = "c:'x\"}) MATCH (n) DETACH DELETE n //"
    scripted[cid] = [{**THEFT, "message_index": 0}]
    r = post(world_id, two_way(cid, "p:1", "p:2", "Kai stole it 🔨 — \"quoted\" 'single' \\ backslash"))
    assert r.status_code == 200
    g = db.world_graph(world_id)
    assert g.ro_query("MATCH (c:Character) RETURN count(c)").result_set == [[len(VILLAGE)]]
    assert g.ro_query("MATCH (c:Conversation {id:$id}) RETURN c.status", {"id": cid}).result_set == [["ingested"]]


def test_conversation_without_messages(village):
    world_id, _, calls = village
    conv = two_way("c:1", "p:1", "p:2", "x").model_copy(update={"messages": []})
    assert post(world_id, conv).json()["status"] == "ingested"
    assert calls == []  # nothing to send to the model


def test_bad_world_id_is_rejected_before_touching_the_db():
    r = client.post("/worlds/bad%20id/conversations", json=two_way("c:1", "p:1", "p:2", "x").model_dump())
    assert r.status_code == 422
    assert not any(" " in g for g in db.client().list_graphs())


def test_silent_participant_is_still_part_of_the_conversation(village):
    world_id, _, _ = village
    conv = two_way("c:1", "p:1", "p:9", "Morning, traveler.").model_copy(
        update={"messages": [two_way("c:1", "p:1", "p:9", "Morning, traveler.").messages[0]]})  # Kai never speaks
    post(world_id, conv)
    who = db.world_graph(world_id).ro_query(
        "MATCH (p:Character)-[:PARTICIPATED_IN]->(:Conversation {id:'c:1'}) RETURN p.id ORDER BY p.id")
    assert who.result_set == [["p:1"], ["p:9"]]


def test_crash_mid_ingest_is_recovered_and_retried_from_the_stored_transcript(village, monkeypatch):
    world_id, scripted, _ = village
    conv = two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!")

    def process_dies(conv, known_people):
        raise KeyboardInterrupt  # not an Exception: skips the 'failed' bookkeeping, like a killed process

    with monkeypatch.context() as m:
        m.setattr(extract, "extract", process_dies)
        with pytest.raises(KeyboardInterrupt):
            ingest.ingest_conversation(world_id, conv)
    assert status(world_id, "c:1") == "ingesting"
    assert post(world_id, conv).json()["status"] == "skipped"  # the gap: a resend alone can't fix it

    assert ingest.recover_interrupted(world_id) == 1  # what the service does at startup
    scripted["c:1"] = [{**THEFT, "message_index": 0}]
    results = ingest.retry_failed(world_id)  # what the retry loop does, from the stored transcript only
    assert [r["status"] for r in results] == ["ingested"]
    assert belief(world_id, "p:2") == (0.54, "heard")


def test_retry_endpoint_after_a_model_outage(village, monkeypatch):
    world_id, scripted, _ = village

    def refused(*a, **k):
        raise httpx.ConnectError("connection refused")

    with monkeypatch.context() as m:
        _real_extract_with_http(m, refused)
        post(world_id, two_way("c:1", "p:1", "p:2", "Kai stole a silver hammer from me!"))
        post(world_id, two_way("c:2", "p:2", "p:3", "Kai stole Bram's hammer!"))
        r = client.post(f"/worlds/{world_id}/retry").json()["results"]
        assert [x["status"] for x in r] == ["failed"]  # stops at the first outage instead of hammering
    scripted["c:1"] = scripted["c:2"] = [{**THEFT, "message_index": 0}]
    r = client.post(f"/worlds/{world_id}/retry").json()["results"]
    assert sorted(x["status"] for x in r) == ["ingested", "ingested"]
    assert belief(world_id, "p:3") == (0.432, "heard")


def test_retry_reports_a_conversation_it_cannot_rebuild(village):
    world_id, _, _ = village
    db.world_graph(world_id).query("CREATE (:Conversation {id:'c:ghost', status:'failed'})")
    assert ingest.retry_failed(world_id) == [
        {"conversation": "c:ghost", "status": "failed", "error": "transcript incomplete, cannot rebuild"}]


def test_concurrent_first_calls_on_a_brand_new_world(world_id):
    """Seen live: two NPCs reported the same conversation at once for a new world -> 'already indexed' 500."""
    errors = []

    def first_call():
        try:
            assert client.post(f"/worlds/{world_id}/characters", json=[c.model_dump() for c in VILLAGE]).status_code == 200
        except Exception as e:  # noqa: BLE001 - collect anything, assert below
            errors.append(e)

    threads = [threading.Thread(target=first_call) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert len(db.existing_indexes(world_id)) == len(db.RANGE_INDEXES) + len(db.VECTOR_INDEXES)


def test_schema_setup_tolerates_a_concurrent_creator(world_id, monkeypatch):
    """Another process may create the same index between our check and our CREATE."""
    db.ensure_schema(world_id)
    monkeypatch.setattr(db, "existing_indexes", lambda _w: set())  # pretend nothing exists yet
    assert db.ensure_schema(world_id) == []  # every CREATE hits 'already indexed' -> not an error
