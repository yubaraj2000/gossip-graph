"""Measure where the town's LLM time goes.

`proxy` sits on the port the apps already use (127.0.0.1:11435) and forwards to the SSH tunnel on another port,
logging one JSON line per Ollama call: model, endpoint, wall time, Ollama's own compute time (so wall - compute =
time spent queued behind other calls), tokens, and how many calls were already in flight.

`report` summarises that log, plus the gaps between chat lines in AI Town (what a viewer experiences as lag).

    scripts/ollama-tunnel.sh stop && OLLAMA_LOCAL_PORT=11437 scripts/ollama-tunnel.sh start
    uv run python -m scripts.llm_timing proxy --log llm_timing.jsonl
    uv run python -m scripts.llm_timing report --log llm_timing.jsonl [--messages messages.jsonl]
"""
import argparse
import json
import statistics
import time
from collections import Counter, defaultdict

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

in_flight: Counter = Counter()


def build_app(upstream: str, log_path: str) -> Starlette:
    client = httpx.AsyncClient(base_url=upstream, timeout=600)

    async def forward(request: Request) -> Response:
        body = await request.body()
        try:
            req = json.loads(body) if body else {}
        except json.JSONDecodeError:
            req = {}
        model = req.get("model", "?")
        busy_before = sum(in_flight.values())
        in_flight[model] += 1
        start = time.time()
        try:
            r = await client.request(request.method, request.url.path, content=body,
                                     params=request.query_params,
                                     headers={"content-type": request.headers.get("content-type", "application/json")})
        finally:
            in_flight[model] -= 1
        wall = time.time() - start
        rec = {"t": round(start, 3), "path": request.url.path, "model": model, "status": r.status_code,
               "wall_s": round(wall, 3), "busy_before": busy_before}
        try:
            out = r.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            out = {}
        if "total_duration" in out:  # native /api/chat, /api/embed: Ollama reports its own compute time
            rec["compute_s"] = round(out["total_duration"] / 1e9, 3)
            rec["load_s"] = round(out.get("load_duration", 0) / 1e9, 3)
            rec["out_tokens"] = out.get("eval_count")
            rec["in_tokens"] = out.get("prompt_eval_count")
        elif "usage" in out:  # OpenAI-compatible /v1/chat/completions (AI Town dialogue)
            rec["out_tokens"] = out["usage"].get("completion_tokens")
            rec["in_tokens"] = out["usage"].get("prompt_tokens")
        with open(log_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return Response(r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type"))

    return Starlette(routes=[Route("/{path:path}", forward, methods=["GET", "POST", "DELETE", "HEAD"])])


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def report(log_path: str, messages_path: str | None) -> None:
    recs = [json.loads(line) for line in open(log_path)]
    print(f"{len(recs)} Ollama calls over {(recs[-1]['t'] - recs[0]['t']) / 60:.1f} min\n")
    print(f"{'model / endpoint':40} {'n':>4} {'median s':>9} {'p90 s':>7} {'max s':>7} {'queued med s':>13} {'out tok med':>11}")
    groups = defaultdict(list)
    for r in recs:
        groups[f"{r['model']} {r['path']}"].append(r)
    for key, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        walls = [r["wall_s"] for r in rs]
        queued = [r["wall_s"] - r["compute_s"] for r in rs if "compute_s" in r]
        toks = [r["out_tokens"] for r in rs if r.get("out_tokens") is not None]
        print(f"{key[:40]:40} {len(rs):>4} {statistics.median(walls):>9.1f} {pct(walls, 0.9):>7.1f} {max(walls):>7.1f}"
              f" {statistics.median(queued) if queued else float('nan'):>13.1f}"
              f" {statistics.median(toks) if toks else float('nan'):>11.0f}")

    # Dialogue latency split by whether the bigger extraction model was running at the same time.
    dialogue = [r for r in recs if r["path"] == "/v1/chat/completions"]
    extract = [(r["t"], r["t"] + r["wall_s"]) for r in recs if r["path"] == "/api/chat"]
    if dialogue:
        overlap = [r["wall_s"] for r in dialogue
                   if any(s < r["t"] + r["wall_s"] and r["t"] < e for s, e in extract)]
        alone = [r["wall_s"] for r in dialogue
                 if not any(s < r["t"] + r["wall_s"] and r["t"] < e for s, e in extract)]
        print("\nDialogue line latency:")
        for name, xs in (("while extraction ran", overlap), ("with no extraction", alone)):
            if xs:
                print(f"  {name:22} n={len(xs):>3}  median {statistics.median(xs):5.1f}s  p90 {pct(xs, 0.9):5.1f}s")
        print("  by calls already in flight: " + ", ".join(
            f"{b}→{statistics.median([r['wall_s'] for r in dialogue if r['busy_before'] == b]):.1f}s"
            f" (n={sum(r['busy_before'] == b for r in dialogue)})"
            for b in sorted({r["busy_before"] for r in dialogue})))

    if messages_path:
        # `npx convex data messages --format jsonLines`: gap between consecutive lines in one conversation.
        msgs = [json.loads(line) for line in open(messages_path) if line.strip()]
        msgs = [m for m in msgs if m.get("_creationTime", 0) / 1000 >= recs[0]["t"]]
        by_conv = defaultdict(list)
        for m in msgs:
            by_conv[m["conversationId"]].append(m["_creationTime"] / 1000)
        gaps = [b - a for ts in by_conv.values() for a, b in zip(sorted(ts), sorted(ts)[1:])]
        if gaps:
            print(f"\nAI Town: {len(msgs)} chat lines in {len(by_conv)} conversations;"
                  f" gap between lines median {statistics.median(gaps):.1f}s, p90 {pct(gaps, 0.9):.1f}s,"
                  f" max {max(gaps):.1f}s")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("proxy")
    p.add_argument("--port", type=int, default=11435)
    p.add_argument("--upstream", default="http://127.0.0.1:11437")
    p.add_argument("--log", default="llm_timing.jsonl")
    r = sub.add_parser("report")
    r.add_argument("--log", default="llm_timing.jsonl")
    r.add_argument("--messages")
    a = ap.parse_args()
    if a.cmd == "proxy":
        uvicorn.run(build_app(a.upstream, a.log), host="127.0.0.1", port=a.port, log_level="warning")
    else:
        report(a.log, a.messages)


if __name__ == "__main__":
    main()
