"""Interviews (Phase 4.2-4.3): the investigator follows the trail upstream, one interview at a time."""
import pytest
from fastapi.testclient import TestClient

from memory import cases, db, explain, ingest
from memory.app import app
from memory.models import CaseIn, CharacterIn
from tests.helpers import FENCE, THEFT, seed_witnessed_theft, two_way

client = TestClient(app)
VIKRAM = CharacterIn(id="inv:vikram", name="Inspector Vikram", identity="A district police inspector.")
THEFT_TEXT = "Kai stole a silver hammer from Bram"


@pytest.fixture
def case(village, monkeypatch):
    """Bram saw Kai steal his hammer; Bram -> Pip -> Mara -> Tom, and Mara added the 'fence' twist."""
    world_id, scripted, _ = village
    monkeypatch.setattr(cases, "CASE_RELEVANCE", 2.1)  # fake embeddings are random: treat every claim as relevant
    seed_witnessed_theft(world_id)
    scripted["c:1"] = scripted["c:2"] = [{"message_index": 0, **THEFT}]
    scripted["c:3"] = [{"message_index": 0, **THEFT}, {"message_index": 0, **FENCE}]
    ingest.ingest_conversation(world_id, two_way("c:1", "p:1", "p:2", "Kai stole my silver hammer!"))
    ingest.ingest_conversation(world_id, two_way("c:2", "p:2", "p:3", "Kai stole Bram's hammer!"))
    ingest.ingest_conversation(world_id, two_way("c:3", "p:3", "p:4", "Kai stole it and tried to fence it!"))
    cases.open_case(world_id, CaseIn(id="case_hammer", title="The missing silver hammer",
                                     question="What really happened?", investigator=VIKRAM))
    return world_id


def test_interviews_follow_the_trail_to_the_eyewitness(case):
    tom = cases.interview(case, "case_hammer", target="p:4")
    assert tom["transcript"][0]["text"].startswith("Namaste, Tom. I'm Inspector Vikram, looking into the missing silver hammer.")
    assert {f["text"]: f["sources"] for f in tom["findings"]} == {
        THEFT_TEXT: ["Mara"], "Kai was spotted trying to fence a stolen hammer": ["Mara"]}  # direct source only
    assert "Mara told me that Kai stole a silver hammer from Bram." in [t["text"] for t in tom["transcript"]]
    assert tom["new_leads"] == ["Mara"]

    mara = cases.interview(case, "case_hammer")  # no target: the planner picks the named source first
    assert mara["interviewee"] == "Mara" and mara["new_leads"] == ["Pip"]
    assert "Kai was spotted trying to fence a stolen hammer. Nobody told me; that's what I've been saying." in \
        [t["text"] for t in mara["transcript"]]

    pip = cases.interview(case, "case_hammer")
    assert pip["interviewee"] == "Pip" and pip["new_leads"] == ["Bram"]
    bram = cases.interview(case, "case_hammer")
    assert bram["interviewee"] == "Bram" and bram["new_leads"] == []
    assert bram["transcript"][1]["text"] == "I saw it with my own eyes: Kai stole a silver hammer from me."

    file = cases.case_file(case, "case_hammer")
    assert [(f["said_by"], f["testimony"]) for f in file["findings"] if f["text"] == THEFT_TEXT] == [
        ("Tom", "heard"), ("Mara", "heard"), ("Pip", "heard"), ("Bram", "witnessed")]
    assert [ld["status"] for ld in file["leads"] if ld["name"] in ("Tom", "Mara", "Pip", "Bram")] == ["done"] * 4
    assert len(file["interviews"]) == 4


def test_the_investigator_only_knows_what_interviews_told_them(case):
    assert explain.explain(case, "inv:vikram")["beliefs"] == []  # minds are private: nothing before interviews
    cases.interview(case, "case_hammer", target="p:4")
    cases.interview(case, "case_hammer", target="p:1")
    theft = next(b for b in explain.explain(case, "inv:vikram")["beliefs"] if b["text"] == THEFT_TEXT)
    assert theft["verdict"] == "witnessed"
    assert theft["sentence"].startswith("Bram told me. Bram saw it happen.")  # the eyewitness is the best path


def test_an_interview_is_never_repeated(case):
    cases.interview(case, "case_hammer", target="p:4")
    again = cases.interview(case, "case_hammer", target="p:4")
    assert again["status"] == "already_interviewed"
    assert len(cases.case_file(case, "case_hammer")["findings"]) == 2


def test_someone_with_nothing_relevant_says_so(case, monkeypatch):
    monkeypatch.setattr(cases, "CASE_RELEVANCE", 0.0)
    r = cases.interview(case, "case_hammer", target="p:4")
    assert r["transcript"][1]["text"] == "I haven't heard anything about that."
    assert r["findings"] == [] and r["new_leads"] == []


def test_running_out_of_leads(case):
    for _ in range(20):
        if cases.interview(case, "case_hammer")["status"] == "no_open_leads":
            break
    assert cases.interview(case, "case_hammer") == {"case": "case_hammer", "status": "no_open_leads"}


def test_interview_endpoint(case):
    r = client.post(f"/worlds/{case}/cases/case_hammer/interview", params={"target": "p:4"})
    assert r.status_code == 200 and r.json()["new_leads"] == ["Mara"]
    assert client.post(f"/worlds/{case}/cases/nope/interview").status_code == 404
    assert client.post(f"/worlds/{case}/cases/case_hammer/interview", params={"target": "p:404"}).status_code == 422
