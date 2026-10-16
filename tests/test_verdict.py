"""Verdict and debunking (Phase 4.5): judge the case file, then correct the village's memory without deleting it."""
import pytest
from fastapi.testclient import TestClient

from memory import cases, db, ingest, recall
from tests.helpers import FENCE, two_way
from tests.test_interviews import THEFT_TEXT, case  # noqa: F401  (fixture)

client = None
LOST = {"subject": "Kai", "predicate": "did", "object": "", "text": "Kai lost Bram's hammer somewhere", "valence": -0.5}
FENCE_TEXT = FENCE["text"]


@pytest.fixture
def solved(case, monkeypatch):  # noqa: F811
    """Pip also garbles the story to Tom; then the whole trail is investigated and the verdict published."""
    from memory import extract
    world_id = case
    monkeypatch.setattr(extract, "extract", lambda conv, known_people: {
        "summary": "s", "claims": [{"message_index": 0, **LOST}]})
    ingest.ingest_conversation(world_id, two_way("c:4", "p:2", "p:4", "Kai lost Bram's hammer somewhere, I think."))
    cases.interview(world_id, "case_hammer", target="p:4")
    while cases.interview(world_id, "case_hammer")["status"] == "interviewed":
        pass
    return world_id, cases.verdict(world_id, "case_hammer")


def texts(items):
    return [c["text"] for c in items]


def test_verdict_separates_truth_lies_and_garbling(solved):
    _, v = solved
    assert [(c["text"], c["witnesses"]) for c in v["confirmed"]] == [(THEFT_TEXT, ["Bram"])]
    assert [(c["text"], c["started_by"]) for c in v["unfounded"]] == [(FENCE_TEXT, ["Mara"])]
    assert [(c["text"], c["started_by"], c["retelling_of"]) for c in v["distorted"]] == [
        ("Kai lost Bram's hammer somewhere", ["Pip"], THEFT_TEXT)]
    assert f"✅ Confirmed: {THEFT_TEXT}. Bram saw it happen." in v["summary"]
    assert f"❌ Unfounded: {FENCE_TEXT}. Mara started it; nobody saw it." in v["summary"]


def test_publishing_corrects_memory_without_deleting_it(solved):
    world_id, v = solved
    g = db.world_graph(world_id)
    statuses = g.ro_query("""MATCH (b:Belief)-[:OF]->(c:Claim) WHERE c.text IN $t
                             RETURN DISTINCT b.status""", {"t": [FENCE_TEXT, LOST["text"]]}).result_set
    assert statuses == [["superseded"]]  # every copy of the debunked claims is kept, marked outdated
    theft = g.ro_query("MATCH (b:Belief)-[:OF]->(:Claim {text:$t}) RETURN DISTINCT b.status", {"t": THEFT_TEXT})
    assert theft.result_set == [["active"]]  # the truth is untouched
    assert v["published"]["beliefs_superseded"] >= 4


def test_only_the_liar_loses_trust_not_the_honest_garbler(solved):
    world_id, v = solved
    assert v["published"]["trust_lowered"] == [{"villager": "Tom", "trusts_less": "Mara", "trust": 0.15}]  # 0.3 x 0.5
    assert recall.recall(world_id, "p:4", "p:2")["trust"]["trust"] == 0.3  # Tom's trust in Pip unchanged


def test_villagers_remember_the_correction(solved):
    world_id, _ = solved
    r = recall.recall(world_id, "p:4", "p:3")  # Tom about to talk to Mara
    assert FENCE_TEXT not in texts(r["beliefs"]) and LOST["text"] not in texts(r["beliefs"])
    assert ("I used to believe that Kai was spotted trying to fence a stolen hammer, but Inspector Vikram's inquiry "
            "found Mara started it and nobody saw it.") in r["memories"]
    assert ("I had heard that Kai lost Bram's hammer somewhere, but Inspector Vikram's inquiry showed it was a "
            "garbled version of what really happened.") in r["memories"]


def test_a_debunked_rumor_cannot_spread_again(solved, monkeypatch):
    from memory import extract
    world_id, _ = solved
    monkeypatch.setattr(extract, "extract", lambda conv, known_people: {
        "summary": "s", "claims": [{"message_index": 0, **FENCE}]})
    ingest.ingest_conversation(world_id, two_way("c:9", "p:3", "p:2", "Pip! Kai tried to fence a stolen hammer!"))
    pip = db.world_graph(world_id).ro_query(
        "MATCH (b:Belief {holder:'p:2'})-[:OF]->(:Claim {text:$t}) RETURN b.status", {"t": FENCE_TEXT}).result_set
    assert pip == []  # Mara's copy is superseded, so nobody can adopt it from her


def test_verdict_is_final(solved):
    world_id, v = solved
    assert cases.verdict(world_id, "case_hammer") == v  # stored, not re-published
    with pytest.raises(cases.CaseClosed):
        cases.interview(world_id, "case_hammer", target="p:5")
    assert cases.case_file(world_id, "case_hammer")["status"] == "solved"


def test_verdict_endpoint(solved):
    from memory.app import app
    world_id, _ = solved
    http = TestClient(app)
    assert http.post(f"/worlds/{world_id}/cases/case_hammer/verdict").json()["status"] == "solved"
    assert http.post(f"/worlds/{world_id}/cases/case_hammer/interview").status_code == 409
    assert http.post(f"/worlds/{world_id}/cases/nope/verdict").status_code == 404
