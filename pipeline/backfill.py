#!/usr/bin/env python3
"""Ask questions added after a run (questions.LATE_QUESTIONS) of the already-scored words where they can matter.

    python backfill.py --mock
    python backfill.py

Re-asking every scored word costs a full request each (the per-request overhead dominates), so only two groups
get the late questions:
- words that clear any bucket at --near (they could become candidates, and candidates need a category)
- words with sounds_funny >= --near (where misleading words live)

Reads out/full/scored.jsonl and writes answers to the score cache only. Afterwards, regenerate scored.jsonl for free:
    python run_full.py --limit N --no-backfill
"""
import argparse
import asyncio
import json
import os
import sys

from pilot import HERE, PRICE_PER_MTOK, Limiter, make_client
from questions import LATE_QUESTIONS, POSITIVE_BUCKETS, QUESTIONS
from score_cache import ScoreCache, ask, default_path, state_for


def wanted(rec, near):
    s = rec["scores"]
    if all(n in s for n in LATE_QUESTIONS if n in QUESTIONS and QUESTIONS[n].type == "noul") and rec.get("category"):
        return False  # already has them
    return s["sounds_funny"] >= near or any(s.get(b, 0) >= near for b in POSITIVE_BUCKETS)


async def run(args, recs):
    cache = ScoreCache(default_path(args.mock))
    sem, limiter = asyncio.Semaphore(args.concurrency), Limiter(args.rps)
    qs = {n: QUESTIONS[n] for n in LATE_QUESTIONS}
    tokens = done = 0
    async with make_client(args.mock) as client:
        for start in range(0, len(recs), 256):
            batch = recs[start:start + 256]
            res = await asyncio.gather(*(ask(client, limiter, sem, cache, state_for(r), qs, args.model,
                                             (r["word"], r["pos"]), args.mock) for r in batch), return_exceptions=True)
            for r in res:
                if isinstance(r, Exception):
                    print(f"\nfailed: {r!r}", file=sys.stderr)
                    continue
                tokens += r[1]
                done += 1
            print(f"\r{done:,}/{len(recs):,}  {tokens / 1e6:.2f}M tok  ${tokens / 1e6 * PRICE_PER_MTOK:.3f}", end="",
                  file=sys.stderr, flush=True)
    cache.close()
    print(f"\ndone: {done:,} words, {tokens:,} tokens (${tokens / 1e6 * PRICE_PER_MTOK:.2f})", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--near", type=float, default=0.5)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--rps", type=float, default=15)
    ap.add_argument("--model", default="jev-1.13.0")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()
    if not args.mock and not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("Set TYPESAFE_API_KEY first (or pass --mock for a dry run).")
    scored = HERE / "out" / ("full-mock" if args.mock else "full") / "scored.jsonl"
    recs = [json.loads(l) for l in open(scored, encoding="utf-8")]
    recs = [r for r in recs if not any(r["scores"].get(k, 0) >= 0.5 for k in ("offensive", "familiar", "sad"))]
    todo = [r for r in recs if wanted(r, args.near)]
    print(f"{len(todo):,} of {len(recs):,} unrejected words need the late questions", file=sys.stderr)
    asyncio.run(run(args, todo))


if __name__ == "__main__":
    main()
