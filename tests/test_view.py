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
