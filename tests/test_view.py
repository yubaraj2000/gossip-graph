"""The memory page's data (Phase 5.1): the village map, news flow, totals and the live belief feed."""
from fastapi.testclient import TestClient

from memory import db, ingest
from memory.app import app
from memory.models import CharacterIn

client = TestClient(app)


def graph(world_id, **params):
    r = client.get(f"/worlds/{world_id}/graph", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_map_shows_who_learned_from_whom(gossip):
    out = graph(gossip, since=0)
    roles = {c["name"]: c["role"] for c in out["characters"]}
    assert roles == {"Bram": "villager", "Pip": "villager", "Mara": "villager", "Tom": "villager", "Kai": "outsider"}
    flow = {(f["from"], f["to"]) for f in out["news_flow"]}
    assert {("p:1", "p:2"), ("p:2", "p:3"), ("p:3", "p:4")} <= flow  # Bram -> Pip -> Mara -> Tom
    assert out["totals"]["conversations"] == 3


def test_the_feed_says_who_heard_what_from_whom(gossip):
    feed = graph(gossip, since=0)["feed"]
    tom = next(b for b in feed if b["holder_name"] == "Tom" and b["text"] == "Kai stole a silver hammer from Bram")
    assert (tom["origin"], tom["from_name"]) == ("heard", "Mara")
    assert tom["line"] == "Kai stole it and tried to fence it!"
    assert feed == sorted(feed, key=lambda b: -b["at"])  # newest first
    assert graph(gossip, since=max(b["at"] for b in feed))["feed"] == []  # only what's new since the last poll


def test_silent_strangers_are_left_off_the_map(gossip):
    ingest.upsert_characters(db.world_graph(gossip), [CharacterIn(id="p:99", name="Visitor", kind="human")])
    names = {c["name"] for c in graph(gossip)["characters"]}
    assert "Visitor" not in names and "Kai" in names  # Kai is talked about, the visitor isn't


def test_missing_world_and_the_page(world_id):
    assert client.get(f"/worlds/{world_id}/graph").status_code == 404
    page = client.get("/ui")
    assert page.status_code == 200 and "Village memory" in page.text
    assert page.headers["cache-control"] == "no-store"


def insights(world_id):
    r = client.get(f"/worlds/{world_id}/insights")
    assert r.status_code == 200, r.text
    return r.json()


def test_insights_show_the_village_structure(gossip):
    out = insights(gossip)
    assert out["hubs_based_on"] == "who learned from whom"  # gossip has flowed, so hubs come from news flow
    assert {h["name"] for h in out["hubs"]} <= {"Bram", "Pip", "Mara", "Tom"}
    assert not any(line.startswith("Suggested") for line in out["summary"])  # that line is for investigators


def test_reputation_is_what_the_village_believes(gossip):
    kai = next(r for r in insights(gossip)["reputation"] if r["name"] == "Kai")
    assert kai["top_claim"] == "Kai stole a silver hammer from Bram"
    assert kai["villagers_with_opinion"] == kai["think_badly"] == 4  # Bram, Pip, Mara and Tom
    assert -1 <= kai["opinion"] < -0.15 and kai["words"] in ("bad", "very bad")


def test_an_investigators_notes_are_not_village_opinion(gossip):
    db.world_graph(gossip).query("MATCH (t:Character {id: 'p:4'}) CREATE (t)-[:INVESTIGATES]->(:Case {id: 'k1'})")
    kai = next(r for r in insights(gossip)["reputation"] if r["name"] == "Kai")
    assert kai["villagers_with_opinion"] == 3  # Tom now counts as an investigator


def test_insights_for_a_missing_world(world_id):
    assert client.get(f"/worlds/{world_id}/insights").status_code == 404


def test_the_case_board_lists_cases_and_who_interviewed_whom(gossip):
    case = {"id": "k_board", "title": "The missing silver hammer", "question": "Who took Bram's hammer?",
            "investigator": {"id": "inv:vikram", "name": "Inspector Vikram", "kind": "human"}}
    assert client.post(f"/worlds/{gossip}/cases", json=case).status_code == 200
    assert client.post(f"/worlds/{gossip}/cases/k_board/interview", params={"target": "p:4"}).status_code == 200
    listed = client.get(f"/worlds/{gossip}/cases").json()["cases"]
    assert [(c["case"], c["status"], c["investigator"]) for c in listed] == [("k_board", "open", "Inspector Vikram")]
    interview = client.get(f"/worlds/{gossip}/cases/k_board").json()["interviews"][0]
    assert sorted(interview["participant_ids"]) == ["inv:vikram", "p:4"]  # the map draws Vikram -> Tom


def test_no_cases_in_a_new_world(world_id):
    assert client.get(f"/worlds/{world_id}/cases").json()["cases"] == []
