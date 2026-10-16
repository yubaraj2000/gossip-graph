"""An investigator agent: opens or joins a case, then interviews until the trail runs out.

    uv run python -m scripts.investigate "Inspector Vikram" [--case ID] [--crash-after N] [--pause SECONDS]

The agent keeps nothing between runs: everything it learns is written to the case file in the graph.
--crash-after N kills the process abruptly after N interviews (the Phase 4.4 demo). Run it again with another
investigator and they resume from the case file without repeating an interview. When the leads run out, the
investigator publishes the verdict, which corrects the village's memory.
"""
import argparse
import os
import re
import sys
import time

import httpx

from scripts.seed_village import MEMORY_SERVICE, convex

TITLE = "The missing silver hammer"
QUESTION = "Rumors about a theft are spreading in Chandanpur. What really happened, and where did each story start?"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("name", help='e.g. "Inspector Vikram"')
    p.add_argument("--case", default="case_hammer")
    p.add_argument("--world", help="defaults to AI Town's current default world")
    p.add_argument("--crash-after", type=int, help="die abruptly after this many interviews")
    p.add_argument("--pause", type=float, default=0, help="seconds between interviews (for recording)")
    args = p.parse_args()

    world = args.world or convex("world:defaultWorldStatus")["worldId"]
    me = {"id": "inv:" + re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-"), "name": args.name,
          "identity": f"{args.name}, an investigator sent to Chandanpur. Knows nobody in the village."}
    http = httpx.Client(base_url=f"{MEMORY_SERVICE}/worlds/{world}", timeout=120)

    if http.get(f"/cases/{args.case}").status_code == 404:
        file = http.post("/cases", json={"id": args.case, "title": TITLE, "question": QUESTION, "investigator": me})
        file = file.raise_for_status().json()
        print(f"🕵  {args.name} opens the case: {file['title']}\n\n📋 Briefing (from the village's social graph):")
        for line in file["briefing"]["summary"]:
            print(f"   • {line}")
    else:
        file = http.post(f"/cases/{args.case}/assign", json=me).raise_for_status().json()
        print(f"🕵  {args.name} takes over the case, knowing only what the case file says:\n")
        for line in file["handoff"]:
            print(f"   📂 {line}")

    done = 0
    while True:
        r = http.post(f"/cases/{args.case}/interview").raise_for_status().json()
        if r["status"] == "no_open_leads":
            print("\n✅ No open leads left. Publishing the verdict:\n")
            for line in http.post(f"/cases/{args.case}/verdict").raise_for_status().json()["summary"]:
                print(f"   {line}")
            break
        done += 1
        print(f"\n🎙  Interview {done}: {r['interviewee']}")
        for t in r["transcript"]:
            print(f"   {t['speaker']}: {t['text']}")
        if r["new_leads"]:
            print(f"   → new leads: {', '.join(r['new_leads'])}")
        if args.crash_after and done >= args.crash_after:
            print(f"\n💥 {args.name}'s process crashed. Everything learned so far is in the case file.")
            sys.stdout.flush()  # os._exit skips Python's cleanup, including flushing piped output
            os._exit(1)
        time.sleep(args.pause)


if __name__ == "__main__":
    main()
