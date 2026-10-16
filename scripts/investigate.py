"""An investigator agent: opens or joins a case, then interviews until the trail runs out.

    uv run python -m scripts.investigate "Inspector Vikram" [--case ID] [--in-town] [--crash-after N] [--pause S]

The agent keeps nothing between runs: everything it learns is written to the case file in the graph.
--in-town   the investigator appears in AI Town as a player, walks to each villager, and the interview shows up
            as a real conversation (both sides posted from the graph, word for word).
--crash-after N kills the process abruptly after N interviews (the Phase 4.4 demo). Run it again with another
investigator and they resume from the case file without repeating an interview. When the leads run out, the
investigator publishes the verdict, which corrects the village's memory.
"""
import argparse
import math
import os
import re
import sys
import time
from pathlib import Path

import httpx

from scripts.seed_village import MEMORY_SERVICE, convex

ROOT = Path(__file__).resolve().parent.parent
TITLE = "The missing silver hammer"
QUESTION = "Rumors about a theft are spreading in Chandanpur. What really happened, and where did each story start?"


class Town:
    """The investigator as a visible player in AI Town, through the gossipGraph mutations (Convex HTTP API)."""

    def __init__(self, world: str):
        lines = (ROOT / "world" / ".env.local").read_text().splitlines()
        env = {k.strip(): v.strip().strip('"')
               for k, v in (line.split("=", 1) for line in lines if "=" in line and not line.lstrip().startswith("#"))}
        self.world, self.secret = world, env["INVESTIGATOR_SECRET"]
        self.http = httpx.Client(base_url=env.get("CONVEX_SELF_HOSTED_URL", "http://127.0.0.1:3210"), timeout=30)

    def _call(self, kind: str, path: str, args: dict):
        body = self.http.post(f"/api/{kind}", json={"path": path, "args": args, "format": "json"}) \
            .raise_for_status().json()
        if body.get("status") != "success":
            raise RuntimeError(body.get("errorMessage", body))
        return body["value"]

    def _act(self, fn: str, **args):
        """Run a gossipGraph mutation and wait for the game engine to process the input."""
        input_id = self._call("mutation", f"gossipGraph:{fn}", {"secret": self.secret, "worldId": self.world, **args})
        for _ in range(60):
            status = self._call("query", "aiTown/main:inputStatus", {"inputId": input_id})
            if status is not None:
                if status["kind"] == "error":
                    raise RuntimeError(status["message"])
                return status["value"]
            time.sleep(0.5)
        raise TimeoutError(f"{fn} was not processed")

    def world_state(self) -> dict:
        return self._call("query", "world:worldState", {"worldId": self.world})["world"]

    def players(self) -> dict[str, dict]:
        return {p["id"]: p for p in self.world_state()["players"]}

    def join(self, name: str, character: str) -> str:
        token = "investigator:" + name
        found = [pid for pid, p in self.players().items() if p.get("human") == token]
        if not found:
            self._act("join", name=name, character=character, description=f"{name}, an investigator.")
            found = [pid for pid, p in self.players().items() if p.get("human") == token]
        return found[0]

    def meet(self, me: str, them: str, timeout: float = 90) -> str:
        """Walk up to `them`, invite them, and wait until both are talking. Returns the conversation id."""
        deadline, conv = time.time() + timeout, None
        while time.time() < deadline:
            world = self.world_state()
            players = {p["id"]: p for p in world["players"]}
            if them not in players:
                raise RuntimeError(f"{them} is not in town")
            if conv is None:
                busy = any(them in [m["playerId"] for m in c["participants"]] for c in world["conversations"])
                if busy or math.dist(_xy(players[me]), _xy(players[them])) > 3:
                    tx, ty = _xy(players[them])
                    self._act("moveTo", playerId=me, destination={"x": math.floor(tx) + 1, "y": math.floor(ty)})
                else:
                    try:
                        conv = self._act("invite", playerId=me, invitee=them)
                    except RuntimeError:
                        conv = None  # they just got busy; try again
            else:
                c = next((c for c in world["conversations"] if c["id"] == conv), None)
                if c is None:
                    conv = None  # the invite expired or was declined
                elif all(m["status"]["kind"] == "participating" for m in c["participants"]):
                    return conv
            time.sleep(2)
        raise TimeoutError(f"could not meet {them}")

    def say(self, conv: str, author: str, text: str) -> None:
        self._act("say", conversationId=conv, playerId=author, text=text)

    def leave(self, me: str, conv: str) -> None:
        self._act("leaveConversation", playerId=me, conversationId=conv)


def _xy(player: dict) -> tuple[float, float]:
    return player["position"]["x"], player["position"]["y"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("name", help='e.g. "Inspector Vikram"')
    p.add_argument("--case", default="case_hammer")
    p.add_argument("--world", help="defaults to AI Town's current default world")
    p.add_argument("--in-town", action="store_true", help="appear in AI Town and hold the interviews there")
    p.add_argument("--character", default="f5", help="AI Town sprite for --in-town (f1-f8)")
    p.add_argument("--crash-after", type=int, help="die abruptly after this many interviews")
    p.add_argument("--pause", type=float, default=0, help="seconds between interviews (for recording)")
    p.add_argument("--line-pause", type=float, default=2.5, help="seconds between interview lines in town")
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

    town = Town(world) if args.in_town else None
    me_in_town = town.join(args.name, args.character) if town else None
    if town:
        print(f"\n🚶 {args.name} arrives in Chandanpur (player {me_in_town}).")

    done, postponed = 0, {}  # target -> how many times they couldn't be reached in town
    while True:
        leads = [ld for ld in http.get(f"/cases/{args.case}").raise_for_status().json()["leads"]
                 if ld["status"] == "open"]
        if not leads:
            print("\n✅ No open leads left. Publishing the verdict:\n")
            for line in http.post(f"/cases/{args.case}/verdict").raise_for_status().json()["summary"]:
                print(f"   {line}")
            break
        # Villagers busy in long conversations are postponed: try the others first.
        lead = min(leads, key=lambda ld: postponed.get(ld["target"], 0))
        conv = None
        if town and lead["target"] in town.players() and postponed.get(lead["target"], 0) < 2:
            print(f"\n🚶 Walking to {lead['name']}: {lead['reason']}")
            try:
                conv = town.meet(me_in_town, lead["target"])
            except TimeoutError:
                postponed[lead["target"]] = postponed.get(lead["target"], 0) + 1
                print(f"   ⏳ {lead['name']} is busy; coming back later.")
                continue
        elif town and postponed.get(lead["target"]):
            print(f"\n🗒  {lead['name']} stayed busy, so {args.name} leaves them a note instead of walking over.")
        r = http.post(f"/cases/{args.case}/interview", params={"target": lead["target"]}).raise_for_status().json()
        done += 1
        print(f"\n🎙  Interview {done}: {r['interviewee']}")
        for t in r["transcript"]:
            print(f"   {t['speaker']}: {t['text']}")
            if conv:
                town.say(conv, me_in_town if t["speaker"] == args.name else lead["target"], t["text"])
                time.sleep(args.line_pause)
        if conv:
            town.leave(me_in_town, conv)
        if r["new_leads"]:
            print(f"   → new leads: {', '.join(r['new_leads'])}")
        if args.crash_after and done >= args.crash_after:
            print(f"\n💥 {args.name}'s process crashed. Everything learned so far is in the case file.")
            sys.stdout.flush()  # os._exit skips Python's cleanup, including flushing piped output
            os._exit(1)
        time.sleep(args.pause)


if __name__ == "__main__":
    main()
