"""Start a background village from the village template, then check that the villages' memories stay separate.

Step 4.6. The template holds the village's starting state (people, personalities, trust, friendships), mapped to the
live AI Town world's player ids, so the same person has the same id in every village. A background village is a
GRAPH.COPY of the template: same people, none of the live village's history.

    uv run python -m scripts.background_village [--world chandanpur_b] [--fresh] [--good-deed]

--fresh       delete the background village and start it again from the template
--good-deed   narrate something that happens only in the background village: Kabir helps Pandit Shastri
"""
import argparse
import sys
from pathlib import Path

import httpx

from scripts.seed_village import MEMORY_SERVICE, ROOT, village_payload

OUTSIDER = "kabir"
GOOD_DEED = {"kind": "helped", "actor": "Kabir", "target": "Pandit Shastri", "valence": 0.7,
             "description": "Kabir helped Pandit Shastri carry the new temple bell up the hill",
             "witnesses": ["Pandit Shastri"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--village", type=Path, default=ROOT / "village" / "chandanpur.json")
    ap.add_argument("--world", default="chandanpur_b")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--good-deed", action="store_true")
    a = ap.parse_args()

    live, village, players, characters, relationships = village_payload(a.village)
    template = a.village.stem
    with httpx.Client(base_url=MEMORY_SERVICE, timeout=60) as http:
        t = http.post(f"/templates/{template}",
                      json={"characters": characters, "relationships": relationships}).raise_for_status().json()
        print(f"template {t['graph']}: {t['characters']} characters, {t['trust_links']} trust links, "
              f"{t['friendships']} friendships")

        if a.fresh:
            http.delete(f"/worlds/{a.world}").raise_for_status()
        r = http.post(f"/worlds/{a.world}/from-template/{template}")
        if r.status_code == 409:
            print(f"world {a.world} already exists, reusing it (--fresh starts it again from the template)")
        else:
            w = r.raise_for_status().json()
            print(f"world {w['graph']}: copied from {template} in {w['copy_ms']} ms")
        if a.good_deed:
            e = http.post(f"/worlds/{a.world}/events", json=GOOD_DEED).raise_for_status().json()
            print(f"narrated in {a.world} only: {e['claim_text']}")

        print(f"\nWhat each villager thinks of Kabir:\n{'':18}{'live ' + live[:8] + '…':<44}{a.world}")
        shared = set()
        for c in village["characters"]:
            pid = players[c["name"]]
            views = [http.get(f"/worlds/{w}/recall", params={"me": pid, "other": OUTSIDER}).raise_for_status().json()
                     for w in (live, a.world)]
            print(f"  {c['name']:<16}" + "".join(f"{_summary(v):<44}" for v in views).rstrip())
            shared |= {b["text"] for b in views[0]["beliefs"]} & {b["text"] for b in views[1]["beliefs"]}

    if shared:
        sys.exit(f"\n❌ not isolated: both villages hold {sorted(shared)}")
    print(f"\n✅ isolated: nothing anyone believes about Kabir in the live village exists in {a.world}")


def _summary(view: dict) -> str:
    rep = view["reputation"]
    if not rep["evidence"]:
        return "never heard of him"
    top = max(view["beliefs"], key=lambda b: b["score"])["text"] if view["beliefs"] else ""
    return f"{rep['score']:+.1f} ({rep['evidence']}) {top[:28]}"


if __name__ == "__main__":
    main()
