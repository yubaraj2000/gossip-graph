"""Step 2.6: the prototype story end to end, through the HTTP API only, reproducing the prototype's numbers.

Prototype (Oct 16, RESEARCH_LOG): Bram witnesses Kai's theft; trust Pip 0.9, Mara 0.8, Tom 0.6;
gossip spreads Bram -> Pip 0.90 -> Mara 0.72 -> Tom 0.43; "who told you?" = Tom <- Mara <- Pip <- Bram.
"""
import os

import pytest
from fastapi.testclient import TestClient

from memory.app import app
from tests.helpers import THEFT, seed_witnessed_theft

client = TestClient(app)

# Same personalities as the prototype's trust values.
CHARACTERS = [
    {"id": "p:1", "name": "Bram", "identity": "the village blacksmith"},
    {"id": "p:2", "name": "Pip", "identity": "Bram's chatty apprentice", "gullibility": 0.9},
    {"id": "p:3", "name": "Mara", "identity": "the gossipy innkeeper", "gullibility": 0.8},
    {"id": "p:4", "name": "Tom", "identity": "the town guard", "gullibility": 0.6},
    {"id": "p:9", "name": "Kai", "kind": "human", "identity": "a traveler"},
]
NAMES = {c["id"]: c["name"] for c in CHARACTERS}

# The real dialogue from the live gossip preview (run 2).
STORY = [
    ("c:1", [("p:1", "Pip, I've got a problem with Kai - that scamp stole a silver hammer right out of my forge, "
                     "and I saw him do it with my own two eyes."),
             ("p:2", "Oh no, Master! Can we go get the hammer back from Kai, he's always been a bit of a troublemaker!")]),
    ("c:2", [("p:2", "Oh, Mara! Guess what? I was talking to Bram, and he told me something crazy - Kai swiped his "
                     "silver hammer! Can you imagine?"),
             ("p:3", "That's quite the surprise! I've seen Kai in here a few times already this week...")]),
    ("c:3", [("p:3", "Tom, I've got some gossip that might interest you - Kai was spotted trying to fence a stolen "
                     "silver hammer, supposedly taken from Bram."),
             ("p:4", "I'm intrigued, where did you hear this and what's the source?")]),
]


def body(cid, lines, t0):
    ids = sorted({a for a, _ in lines})
    return {"id": cid, "participants": [{"id": i, "name": NAMES[i]} for i in ids],
            "messages": [{"author": a, "text": text, "ts": t0 + i} for i, (a, text) in enumerate(lines)]}


def tell_the_story(world_id):
    assert client.post(f"/worlds/{world_id}/characters", json=CHARACTERS).status_code == 200
    seed_witnessed_theft(world_id)  # stand-in for the step 3.3 narrator endpoint
    beliefs = {}
    for n, (cid, lines) in enumerate(STORY):
        r = client.post(f"/worlds/{world_id}/conversations", json=body(cid, lines, 1000 * (n + 1)))
        assert r.status_code == 200 and r.json()["status"] == "ingested", r.text
        for b in r.json()["beliefs"]:
            if b["claim"] == "k_seed":
                beliefs[b["holder"]] = b["confidence"]
    return beliefs


def reputation_of_kai(world_id, holder):
    r = client.get(f"/worlds/{world_id}/recall", params={"me": holder, "other": "p:9"}).json()
    theft = next(b for b in r["beliefs"] if b["claim"] == "k_seed")
    return theft["confidence"] * -1.0


def check_story(world_id, beliefs):
    # The chain reproduces the prototype: 0.90 -> 0.72 -> 0.43
    assert beliefs == {"p:2": 0.9, "p:3": 0.72, "p:4": 0.432}

    # Grudge against Kai from the theft (prototype: confidence x severity; here confidence x valence)
    assert {h: round(reputation_of_kai(world_id, h), 3) for h in ("p:1", "p:2", "p:3", "p:4")} == {
        "p:1": -1.0, "p:2": -0.9, "p:3": -0.72, "p:4": -0.432}

    # "Who told you?" reproduces the prototype's path, now grounded in the witnessed event
    r = client.get(f"/worlds/{world_id}/explain", params={"holder": "p:4", "claim": "k_seed"}).json()
    theft = r["beliefs"][0]
    assert [s["name"] for s in theft["paths"][0]["steps"]] == ["Tom", "Mara", "Pip", "Bram"]
    assert theft["sentence"] == "Mara told me. Mara heard it from Pip, who heard it from Bram. Bram saw it happen."
    assert theft["verdict"] == "witnessed"

    # Re-sending a conversation (AI Town does, once per NPC) changes nothing
    cid, lines = STORY[2]
    assert client.post(f"/worlds/{world_id}/conversations", json=body(cid, lines, 3000)).json()["status"] == "skipped"
    assert round(reputation_of_kai(world_id, "p:4"), 3) == -0.432


def test_prototype_story_through_the_api(village):
    world_id, scripted, _ = village
    for cid, _ in STORY:
        scripted[cid] = [{"message_index": 0, **THEFT}]
    check_story(world_id, tell_the_story(world_id))

    # A second, independent source: Bram tells Tom directly -> 1 - (1 - 0.432)(1 - 1.0 x 0.6)
    scripted["c:4"] = [{"message_index": 0, **THEFT}]
    r = client.post(f"/worlds/{world_id}/conversations",
                    json=body("c:4", [("p:1", "Tom, Kai stole a silver hammer from my forge."), ("p:4", "Noted.")], 4000))
    assert {b["holder"]: b["confidence"] for b in r.json()["beliefs"]} == {"p:4": round(1 - 0.568 * 0.4, 3)}
    sentence = client.get(f"/worlds/{world_id}/explain", params={"holder": "p:4", "claim": "k_seed"}).json()
    assert sentence["beliefs"][0]["sentence"] == "Bram told me. Bram saw it happen. I also heard it from Mara."


@pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="set RUN_LIVE=1 to call the real LLM")
def test_live_prototype_story_with_the_real_model(world_id):
    """Same story and numbers, with llama3.1:8b doing the claim extraction on the real dialogue."""
    check_story(world_id, tell_the_story(world_id))
