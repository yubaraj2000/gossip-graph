"""Crash and resume (Phase 4.4): a replacement investigator picks up from the case file alone."""
from fastapi.testclient import TestClient

from memory import cases, db, explain
from memory.app import app
from memory.models import CharacterIn
from tests.test_interviews import case  # noqa: F401  (fixture)

client = TestClient(app)
ANJALI = CharacterIn(id="inv:anjali", name="Inspector Anjali", identity="A sharp inspector from the district.")


def test_replacement_resumes_without_repeating_interviews(case):  # noqa: F811
    cases.interview(case, "case_hammer", target="p:4")  # Vikram: Tom -> names Mara
    cases.interview(case, "case_hammer")                # Vikram: Mara -> names Pip
    # 💥 Vikram crashes. Anjali joins with nothing but the case id.
    handoff = cases.assign(case, "case_hammer", ANJALI)
    assert [(i["name"], i["active"]) for i in handoff["investigators"]] == [
        ("Inspector Vikram", False), ("Inspector Anjali", True)]
    assert "Inspector Vikram interviewed Tom and Mara." in handoff["handoff"]
    assert 'Finding: "Kai stole a silver hammer from Bram": Tom heard it from Mara; Mara heard it from Pip.' \
        in handoff["handoff"]
    assert handoff["handoff"][-1] == "Next: interview Pip."

    pip = cases.interview(case, "case_hammer")
    assert (pip["investigator"], pip["interviewee"]) == ("Inspector Anjali", "Pip")
    bram = cases.interview(case, "case_hammer")
    assert bram["interviewee"] == "Bram" and bram["findings"][0]["testimony"] == "witnessed"

    interviews = cases.case_file(case, "case_hammer")["interviews"]
    interviewed = [next(p for p in iv["participants"] if not p.startswith("Inspector")) for iv in interviews]
    assert sorted(interviewed) == ["Bram", "Mara", "Pip", "Tom"]  # each exactly once
    assert [next(p for p in iv["participants"] if p.startswith("Inspector")) for iv in interviews] == [
        "Inspector Vikram", "Inspector Vikram", "Inspector Anjali", "Inspector Anjali"]


def test_the_replacement_does_not_inherit_the_old_investigators_mind(case):  # noqa: F811
    cases.interview(case, "case_hammer", target="p:4")
    cases.assign(case, "case_hammer", ANJALI)
    assert explain.explain(case, "inv:anjali")["beliefs"] == []  # she read the file; she heard nothing yet
    assert explain.explain(case, "inv:vikram")["beliefs"] != []


def test_assigning_twice_is_harmless(case):  # noqa: F811
    cases.assign(case, "case_hammer", ANJALI)
    again = cases.assign(case, "case_hammer", ANJALI)
    assert [(i["name"], i["active"]) for i in again["investigators"]] == [
        ("Inspector Vikram", False), ("Inspector Anjali", True)]
    assert db.world_graph(case).ro_query(
        "MATCH (:Character {id:'inv:anjali'})-[r:INVESTIGATES]->() RETURN count(r)").result_set == [[1]]


def test_assign_endpoint(case):  # noqa: F811
    r = client.post(f"/worlds/{case}/cases/case_hammer/assign", json=ANJALI.model_dump())
    assert r.status_code == 200 and r.json()["handoff"][0].startswith("Case: The missing silver hammer.")
    assert client.post(f"/worlds/{case}/cases/nope/assign", json=ANJALI.model_dump()).status_code == 404
