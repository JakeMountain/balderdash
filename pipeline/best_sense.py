#!/usr/bin/env python3
"""Pick each candidate's definition to show by asking its bucket's question of every definition separately.

    python best_sense.py --mock
    python best_sense.py

The best_definition Choice asks which sense is funniest, without knowing why the word was selected, so an insult
can end up showing its fish sense (bludger). Here a candidate with several definitions gets one request with one Noul
per definition, phrased as its bucket's question about that definition alone. The highest wins if it clears
--min; otherwise the Choice's pick stands. sounds_funny doesn't depend on the sense, so it keeps the Choice's pick.

Writes out/selection/best_sense.json: {word: {"index": i, "by": "bucket" | "choice", "scores": [...]}}.
All definitions stay in the record; this only picks the one to highlight.
"""
import argparse
import asyncio
import json
import os
import sys

from typesafe_sdk import Noul

from pilot import HERE, PRICE_PER_MTOK, Limiter, make_client
from score_cache import ScoreCache, ask, default_path

PER_SENSE = {
    "oddly_specific": "Does `definitions[{i}]` describe something so narrow or oddly particular that a listener might "
                      "assume it was a made-up joke definition?",
    "gross": "Would most people find the thing described by `definitions[{i}]` gross or icky, the kind of thing that "
             "makes someone say 'ew'?",
    "insult": "Is `definitions[{i}]` a colorful name for a kind of person, especially a mocking or insulting one?",
    "misleading": "Does the word in `word` sound or look like it means something quite different from "
                  "`definitions[{i}]`?",
}


async def run(args, cands):
    cache = ScoreCache(default_path(args.mock))
    sem, limiter = asyncio.Semaphore(args.concurrency), Limiter(args.rps)
    out, tokens = {}, 0

    async def one(r):
        nonlocal tokens
        b, defs = r["bucket"], r["definitions"]
        if b not in PER_SENSE or len(defs) < 2:
            return r["word"], {"index": r["best_definition"], "by": "choice", "scores": None}
        state = {"word": r["word"], "part_of_speech": r["pos"], "definitions": defs}
        qs = {f"sense_{b}_{i}": Noul(instructions=PER_SENSE[b].format(i=i)) for i in range(len(defs))}
        ans, t = await ask(client, limiter, sem, cache, state, qs, args.model, (r["word"], r["pos"]), args.mock)
        tokens += t
        scores = [round(ans[f"sense_{b}_{i}"], 3) for i in range(len(defs))]
        top = max(range(len(defs)), key=lambda i: scores[i])
        if scores[top] >= args.min:
            return r["word"], {"index": top, "by": "bucket", "scores": scores}
        return r["word"], {"index": r["best_definition"], "by": "choice", "scores": scores}

    async with make_client(args.mock) as client:
        for word, pick in await asyncio.gather(*(one(r) for r in cands)):
            out[word] = pick
    cache.close()
    return out, tokens


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min", type=float, default=0.5, help="a sense must score this to override the Choice")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--rps", type=float, default=15)
    ap.add_argument("--model", default="jev-1.13.0")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()
    if not args.mock and not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("Set TYPESAFE_API_KEY first (or pass --mock for a dry run).")
    path = HERE / "out" / "selection" / "candidates.jsonl"
    cands = [json.loads(l) for l in open(path, encoding="utf-8")]
    picks, tokens = asyncio.run(run(args, cands))
    changed = sum(p["index"] != c["best_definition"] for p, c in zip((picks[c["word"]] for c in cands), cands))
    (HERE / "out" / "selection" / "best_sense.json").write_text(json.dumps(picks, ensure_ascii=False), encoding="utf-8")
    print(f"{len(cands):,} candidates, {sum(len(c['definitions']) > 1 for c in cands):,} with several definitions; "
          f"{changed:,} now show a different one. {tokens:,} tokens (${tokens / 1e6 * PRICE_PER_MTOK:.3f})")


if __name__ == "__main__":
    main()
