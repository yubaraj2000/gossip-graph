"""Village templates (step 4.6): start separate worlds from one seeded village, and prove they stay separate."""
import uuid

import pytest
from fastapi.testclient import TestClient

from memory import db, llm, recall
from memory.app import app
from tests.helpers import VILLAGE, fake_embed

client = TestClient(app)
TRUST = [{"source": "p:2", "target": "p:1", "trust": 0.8}, {"source": "p:3", "target": "p:2", "trust": 0.7},
         {"source": "p:4", "target": "p:3", "trust": 0.4}]
THEFT_EVENT = {"kind": "stole_from", "actor": "Kai", "target": "Bram", "valence": -1.0,
               "description": "Kai stole a silver hammer from Bram", "witnesses": ["Bram"]}


@pytest.fixture
def names(monkeypatch):
    """A template name and two world ids, all deleted afterwards."""
    monkeypatch.setattr(llm, "embed", fake_embed)
    suffix = uuid.uuid4().hex[:8]
    template, worlds = "test_" + suffix, ["test_" + suffix + "_a", "test_" + suffix + "_b"]
    yield template, worlds
    for graph in [db.template_graph_name(template), *map(db.graph_name, worlds)]:
        if db.exists(graph):
            db.client().select_graph(graph).delete()


def make_template(name):
    r = client.post(f"/templates/{name}",
                    json={"characters": [c.model_dump() for c in VILLAGE], "relationships": TRUST})
    assert r.status_code == 200, r.text
    return r.json()


def start(world_id, template):
    return client.post(f"/worlds/{world_id}/from-template/{template}")


def test_a_template_holds_the_village_and_its_schema(names):
    template, _ = names
    out = make_template(template)
    assert (out["characters"], out["trust_links"], out["friendships"]) == (5, 3, 3)
    assert ("Claim", "embedding", "VECTOR") in db._indexes(db.template_graph_name(template))
    assert template in client.get("/templates").json()["templates"]
    assert template not in db.list_worlds()  # templates are never treated as live worlds


def test_a_world_started_from_a_template_is_an_exact_copy(names):
    template, (a, _) = names
    make_template(template)
    r = start(a, template)
    assert r.status_code == 200, r.text
    assert (r.json()["characters"], r.json()["trust_links"], r.json()["friendships"]) == (5, 3, 3)
    assert db.existing_indexes(a) == db._indexes(db.template_graph_name(template))
    pip = db.world_graph(a).ro_query(
        "MATCH (p:Character {id:'p:2'})-[k:KNOWS]->(:Character {id:'p:1'}) RETURN p.gullibility, k.trust").result_set
    assert pip == [[0.9, 0.8]]


def test_what_happens_in_one_world_stays_there(names):
    template, (a, b) = names
    make_template(template)
    start(a, template), start(b, template)
    assert client.post(f"/worlds/{a}/events", json=THEFT_EVENT).status_code == 200

    in_a, in_b = recall.recall(a, "p:1", "p:9"), recall.recall(b, "p:1", "p:9")
    assert in_a["reputation"]["evidence"] == 1 and in_a["reputation"]["score"] < 0  # Bram saw Kai steal
    assert in_b["reputation"] == {"score": 0.0, "evidence": 0}  # same Bram, same Kai, never happened here
    assert in_b["beliefs"] == []
    for graph in (db.graph_name(b), db.template_graph_name(template)):
        assert db.client().select_graph(graph).ro_query(
            "MATCH (n) WHERE n:Event OR n:Claim OR n:Belief RETURN count(n)").result_set == [[0]]


def test_starting_a_world_never_overwrites_one(names):
    template, (a, _) = names
    make_template(template)
    start(a, template)
    client.post(f"/worlds/{a}/events", json=THEFT_EVENT)
    assert start(a, template).status_code == 409
    assert db.world_graph(a).ro_query("MATCH (e:Event) RETURN count(e)").result_set == [[1]]


def test_a_deleted_world_can_start_again_from_the_template(names):
    template, (a, _) = names
    make_template(template)
    start(a, template)
    client.post(f"/worlds/{a}/events", json=THEFT_EVENT)
    assert client.delete(f"/worlds/{a}").json()["deleted"] is True
    assert start(a, template).status_code == 200
    assert db.world_graph(a).ro_query("MATCH (e:Event) RETURN count(e)").result_set == [[0]]


def test_bad_requests(names):
    template, (a, _) = names
    assert start(a, template).status_code == 404  # no such template
    assert start(a, "bad name!").status_code == 422
    assert client.post("/templates/bad name!", json={"characters": [VILLAGE[0].model_dump()]}).status_code == 422
    assert client.post(f"/templates/{template}", json={"characters": []}).status_code == 422
