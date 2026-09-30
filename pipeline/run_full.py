#!/usr/bin/env python3
"""Full run: score every word in the pool with Jev, once. Resumable: anything already in the score cache is skipped.

    python run_full.py --mock --limit 2000     # dry run
    python run_full.py --limit 500             # real, first 500 (prints the real token count per word)
    python run_full.py                         # real, everything; Ctrl-C any time and rerun to resume

The pool is shuffled with the pilot's seed and scored one entry per word, so the pilot's words come from the cache.
Output: out/full/scored.jsonl, every scored word (cached or new), which selection.py reads.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from typesafe_sdk import TypeSafeAuthenticationError, TypeSafePermissionDeniedError

from pilot import HERE, PRICE_PER_MTOK, Limiter, load_dictionaries, make_client, unique_pool
from score_cache import ScoreCache, default_path, score_word

REPORT_AFTER = 500  # new requests before printing the real tokens-per-word figure


async def run(args, pool):
    cache = ScoreCache(default_path(args.mock))
    sem, limiter = asyncio.Semaphore(args.concurrency), Limiter(args.rps)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "scored.jsonl.part"
    done = new = tokens = errors = consecutive = 0
    reported = False
    t0 = time.monotonic()
    async with make_client(args.mock) as client:
        with open(tmp, "w", encoding="utf-8") as f:
            for start in range(0, len(pool), args.wave):
                wave = pool[start:start + args.wave]
                results = await asyncio.gather(
                    *(score_word(client, limiter, sem, cache, e, args.model, args.mock, not args.no_backfill)
                      for e in wave),
                    return_exceptions=True)
                for res in results:
                    if isinstance(res, (TypeSafeAuthenticationError, TypeSafePermissionDeniedError)):
                        raise SystemExit(f"TypeSafe rejected the API key: {res}")
                    if isinstance(res, Exception):
                        errors += 1
                        consecutive += 1
                        if consecutive >= 25:
                            raise SystemExit(f"25 requests in a row failed; last error: {res!r}. "
                                             f"Everything scored so far is cached; rerun to resume.")
                        continue
                    consecutive = 0
                    done += 1
                    if res["input_tokens"]:
                        new += 1
                        tokens += res["input_tokens"]
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
                if new >= REPORT_AFTER and not reported:
                    reported = True
                    per = tokens / new
                    left = len(pool) - done
                    print(f"\nreal cost after {new} requests: {per:,.0f} input tokens per word; the rest "
                          f"({left:,} words) projects to {per * left / 1e6:.1f}M tokens, "
                          f"${per * left / 1e6 * PRICE_PER_MTOK:.2f}", file=sys.stderr)
                el = time.monotonic() - t0
                rate = new / el if el else 0
                eta = (len(pool) - done) / rate / 60 if rate else 0
                print(f"\r{done:,}/{len(pool):,} scored ({new:,} new, {done - new:,} cached)  {tokens / 1e6:.2f}M tok "
                      f"${tokens / 1e6 * PRICE_PER_MTOK:.3f}  {rate:.1f}/s  ~{eta:.0f} min left  {errors} errors",
                      end="", file=sys.stderr)
    tmp.replace(out / "scored.jsonl")
    cache.close()
    print(f"\ndone: {done:,} words, {new:,} new requests, {tokens:,} input tokens "
          f"(${tokens / 1e6 * PRICE_PER_MTOK:.2f}), {errors} failed. wrote {out / 'scored.jsonl'}", file=sys.stderr)
    if errors:
        print("some requests failed; rerun to fill them in (cached words are free)", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0, help="only the first N words of the shuffled pool")
    ap.add_argument("--zipf-max", type=float, default=2.5)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--rps", type=float, default=15)
    ap.add_argument("--wave", type=int, default=256)
    ap.add_argument("--model", default="jev-1.13.0")
    ap.add_argument("--seed", type=int, default=1, help="keep equal to the pilot's so its words are cache hits")
    ap.add_argument("--data", default=str(HERE / "cache"))
    ap.add_argument("--out", default=None, help="default out/full/ (out/full-mock/ with --mock)")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--no-wiktionary", action="store_true")
    ap.add_argument("--no-backfill", action="store_true",
                    help="don't ask newly added questions of already-scored words (see backfill.py)")
    args = ap.parse_args()
    args.out = args.out or str(HERE / "out" / ("full-mock" if args.mock else "full"))
    if not args.mock and not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("Set TYPESAFE_API_KEY first (or pass --mock for a dry run).")
    pool = unique_pool(load_dictionaries(args.data, not args.no_wiktionary), args.zipf_max, args.seed)
    if args.limit:
        pool = pool[:args.limit]
    print(f"pool: {len(pool):,} words", file=sys.stderr)
    asyncio.run(run(args, pool))


if __name__ == "__main__":
    main()
