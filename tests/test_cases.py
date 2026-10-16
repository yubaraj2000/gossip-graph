"""Cases (Phase 4.1): the case file and the structure-only briefing, on the real Chandanpur social graph."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memory import cases, db, ingest
from memory.app import app
from memory.models import CharacterIn, RelationshipIn

client = TestClient(app)
VILLAGE = json.loads((Path(__file__).parent.parent / "village" / "chandanpur.json").read_text())
VIKRAM = {"id": "inv:vikram", "name": "Inspector Vikram", "identity": "A district police inspector."}
CASE = {"title": "The missing silver hammer", "question": "What really happened, and where did each story start?",
        "investigator": VIKRAM}


@pytest.fixture
def chandanpur(world_id):
    """The real village file, with ids v:0..v:7, plus the outsider Kabir."""
    ids = {c["name"]: f"v:{n}" for n, c in enumerate(VILLAGE["characters"])}
    g = db.world_graph(world_id)
    db.ensure_world(world_id)
    ingest.upsert_characters(g, [CharacterIn(id=ids[c["name"]], name=c["name"], gullibility=c["gullibility"])
                                 for c in VILLAGE["characters"]]
                             + [CharacterIn(id="kabir", name="Kabir", kind="human")])
    ingest.set_relationships(g, [RelationshipIn(source=ids[r["from"]], target=ids[r["to"]], trust=r["trust"])
                                 for r in VILLAGE["relationships"]])
    return world_id, ids


def names(items):
    return [i["name"] for i in items]


def test_briefing_finds_the_bridge_the_circles_and_suggests_leads(chandanpur):
    world_id, _ = chandanpur
    r = client.post(f"/worlds/{world_id}/cases", json=CASE)
    assert r.status_code == 200
    brief = r.json()["briefing"]
    assert brief["bridges"][0]["name"] == "Gopal"
    assert sorted(sorted(names(c)) for c in brief["circles"]) == [
        ["Balwant", "Meera", "Pandit Shastri"], ["Chotu", "Lakshmi", "Ramesh", "Sarla"]]
    assert brief["hubs_based_on"] == "who trusts whom"  # nobody has learned anything from anyone yet
    leads = r.json()["leads"]
    assert [ld["kind"] for ld in leads][:2] == ["hub", "bridge"]
    assert "Gopal" in [ld["name"] for ld in leads]
    assert len({ld["target"] for ld in leads}) == len(leads)  # one lead per person
    assert "Kabir" not in json.dumps(brief) and "Inspector" not in json.dumps(brief)  # villagers only


def test_hubs_follow_who_others_learn_from_once_gossip_exists(chandanpur):
    world_id, ids = chandanpur
    g = db.world_graph(world_id)
    for listener in ("Chotu", "Sarla", "Gopal", "Ramesh"):  # everyone has learned things from Lakshmi
        g.query("MATCH (a:Character {id:$a}), (b:Character {id:$b}) CREATE (a)-[:LEARNED_FROM {count: 2}]->(b)",
                {"a": ids[listener], "b": ids["Lakshmi"]})
    brief = cases.briefing(g)
    assert brief["hubs_based_on"] == "who learned from whom"
    assert brief["hubs"][0]["name"] == "Lakshmi"


def test_the_case_file_is_written_once_and_shared_by_every_investigator(chandanpur):
    world_id, _ = chandanpur
    first = client.post(f"/worlds/{world_id}/cases", json=CASE).json()
    anjali = {**VIKRAM, "id": "inv:anjali", "name": "Inspector Anjali"}
    second = client.post(f"/worlds/{world_id}/cases", json={**CASE, "investigator": anjali}).json()
    assert second["case"] == first["case"]
    assert second["briefing"] == first["briefing"] and second["leads"] == first["leads"]
    assert [(i["name"], i["active"]) for i in second["investigators"]] == [
        ("Inspector Vikram", False), ("Inspector Anjali", True)]


def test_investigators_are_not_part_of_the_village_structure(chandanpur):
    world_id, ids = chandanpur
    client.post(f"/worlds/{world_id}/cases", json=CASE)
    g = db.world_graph(world_id)
    for name in ("Lakshmi", "Meera", "Gopal"):  # interviews make the investigator acquainted with villagers
        g.query("MATCH (a:Character {id:'inv:vikram'}), (b:Character {id:$b}) "
                "CREATE (a)-[:KNOWS {trust: 0.5}]->(b), (b)-[:KNOWS {trust: 0.5}]->(a)", {"b": ids[name]})
    brief = cases.briefing(g)
    assert "Inspector Vikram" not in json.dumps(brief)
    assert brief["bridges"][0]["name"] == "Gopal"


def test_unknown_case_is_404(chandanpur):
    world_id, _ = chandanpur
    assert client.get(f"/worlds/{world_id}/cases/nope").status_code == 404


def test_circles_come_from_friendships_even_when_everyone_has_met(chandanpur):
    """Seen live: after hours of talk, KNOWS linked nearly everyone and the circles dissolved into one."""
    world_id, ids = chandanpur
    db.world_graph(world_id).query("""
        MATCH (a:Character {kind:'npc'}), (b:Character {kind:'npc'}) WHERE a <> b
        MERGE (a)-[k:KNOWS]->(b) ON CREATE SET k.trust = 0.5""")
    brief = cases.briefing(db.world_graph(world_id))
    assert brief["circles_based_on"] == "friendships"
    assert brief["bridges"][0]["name"] == "Gopal"
    assert len(brief["circles"]) == 2
