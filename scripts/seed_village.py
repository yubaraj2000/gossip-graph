"""Seed the live AI Town world's graph with the village's personalities and who-trusts-whom.

Run after `npx convex run init` in world/, with the memory service up:
    uv run python scripts/seed_village.py [village/chandanpur.json]
Village names are matched to the player ids AI Town assigned in the current default world.
"""
import json
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
MEMORY_SERVICE = "http://127.0.0.1:8100"


def convex(function: str, args: dict | None = None):
    cmd = ["npx", "convex", "run", function] + ([json.dumps(args)] if args else [])
    out = subprocess.run(cmd, cwd=ROOT / "world", capture_output=True, text=True, check=True).stdout
    start = min(i for i in (out.find("{"), out.find("[")) if i >= 0)  # skip any CLI chatter before the JSON
    return json.JSONDecoder().raw_decode(out[start:])[0]


def village_payload(village_file: Path) -> tuple[str, dict, dict, list[dict], list[dict]]:
    """The village file mapped onto the live AI Town world: (world id, village, name -> player id, characters,
    trust links), in the shape the memory service takes."""
    village = json.loads(village_file.read_text())
    world_id = convex("world:defaultWorldStatus")["worldId"]
    players = {d["name"]: d["playerId"]
               for d in convex("world:gameDescriptions", {"worldId": world_id})["playerDescriptions"]}
    missing = sorted({c["name"] for c in village["characters"]} - players.keys())
    if missing:
        sys.exit(f"not in AI Town's world {world_id}: {missing} (did you deploy data/characters.ts and run init?)")

    characters = [{"id": players[c["name"]], "name": c["name"], "kind": "npc", "gullibility": c["gullibility"]}
                  for c in village["characters"]]
    # Outsiders aren't AI Town NPCs: they keep the fixed id from the village file.
    characters += [{"id": o["id"], "name": o["name"], "kind": o["kind"], "identity": o["identity"],
                    "gullibility": o["gullibility"]} for o in village.get("outsiders", [])]
    relationships = [{"source": players[r["from"]], "target": players[r["to"]], "trust": r["trust"]}
                     for r in village["relationships"]]
    return world_id, village, players, characters, relationships


def main(village_file: Path) -> None:
    world_id, village, players, characters, relationships = village_payload(village_file)
    with httpx.Client(base_url=MEMORY_SERVICE, timeout=30) as http:
        http.post(f"/worlds/{world_id}").raise_for_status()
        http.post(f"/worlds/{world_id}/characters", json=characters).raise_for_status()
        result = http.post(f"/worlds/{world_id}/relationships", json=relationships).raise_for_status().json()
    print(f"world {world_id}: seeded {len(characters)} characters and {result['set']} trust links "
          f"({result['skipped_unknown_characters']} skipped) from {village_file.name}")
    for c in village["characters"]:
        print(f"  {players[c['name']]:>5}  {c['name']:<15} {c['role']:<18} gullibility {c['gullibility']}")
    for o in village.get("outsiders", []):
        print(f"  {o['id']:>5}  {o['name']:<15} {o['role']:<18} gullibility {o['gullibility']}  (outsider)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "village" / "chandanpur.json")
