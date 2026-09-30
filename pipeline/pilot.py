#!/usr/bin/env python3
"""Pilot: score random dictionary words with Jev until every bucket has N words, then write a QC sheet.

    pip install -r requirements.txt
    export TYPESAFE_API_KEY=...
    python pilot.py                      # 10 per bucket, threshold 0.6, Zipf <= 2.5
    python pilot.py --mock               # dry run with a fake Jev, no key or network needed for scoring

Outputs (in --out, default pipeline/out/pilot/):
    qc.md       the bucketed words, grouped, for reading
    qc.csv      the same with every score and blank verdict/notes columns for marking
    scored.jsonl every word scored, including rejects and unsure ones (for threshold tuning later)
"""
import argparse
import asyncio
import csv
import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient, TypeSafeAuthenticationError, TypeSafePermissionDeniedError

from pool import build_pool, load_entries
from questions import BUCKETS, POSITIVE_BUCKETS
from score_cache import SCORE_KEYS, ScoreCache, default_path, score_word

WEBSTER_URL = "https://raw.githubusercontent.com/matthewreagan/WebstersEnglishDictionary/master/WebstersEnglishDictionary.txt"
WORDNET_URL = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet2022.zip"
PRICE_PER_MTOK = 0.042  # jev-1.13 input price, USD; output is free
HERE = Path(__file__).resolve().parent


def load_dotenv(path=HERE.parent / ".env"):
    """KEY=VALUE lines from the repo's .env into os.environ; real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():  # -sig: PowerShell 5.1 writes a BOM
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv()  # runs on import, so recall.py and run_full.py get it too


def fetch(url, dest):
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url.rsplit('/', 1)[-1]} ...", file=sys.stderr)
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dest)
    return dest


def load_dictionaries(data_dir, use_wiktionary=True):
    """Download (once) and merge every dictionary source. Shared by pilot, recall and the full run."""
    import wiktionary
    webster = fetch(WEBSTER_URL, Path(data_dir) / "WebstersEnglishDictionary.txt")
    wn = fetch(WORDNET_URL, Path(data_dir) / "wordnet2022.zip")
    wikt = wiktionary.build_cache(Path(data_dir) / wiktionary.CACHE_NAME) if use_wiktionary else None
    return load_entries(str(webster), str(wn), wikt)


def unique_pool(entries, zipf_max, seed):
    """Filtered pool, shuffled by seed, one entry per word."""
    pool = build_pool(entries, zipf_max=zipf_max)
    random.Random(seed).shuffle(pool)
    seen, uniq = set(), []
    for e in pool:
        if e["word"] not in seen:
            seen.add(e["word"])
            uniq.append(e)
    return uniq


def make_client(mock):
    """AsyncTypeSafeClient, or one wired to the fake Jev in mock_jev.py."""
    if not mock:
        return AsyncTypeSafeClient()
    from mock_jev import mock_transport
    return AsyncTypeSafeClient(api_key="mock-key", transport=mock_transport())


class Limiter:
    """Spaces request starts to stay under the requests-per-second budget."""

    def __init__(self, rps):
        self.interval, self.next, self.lock = 1.0 / rps, 0.0, asyncio.Lock()

    async def wait(self):
        async with self.lock:
            now = time.monotonic()
            start = max(now, self.next)
            self.next = start + self.interval
        await asyncio.sleep(max(0.0, start - now))


def assign(rec, filled, per_bucket, threshold, reject_at):
    """Pick one bucket for a scored word, or a reason it was left out. Mutates `filled`."""
    s = rec["scores"]
    for reason in ("offensive", "familiar", "sad"):
        if s[reason] >= reject_at:
            return f"rejected:{reason}"
    ranked = sorted((b for b in POSITIVE_BUCKETS if s[b] >= threshold), key=lambda b: -s[b])
    for b in ranked:  # best-scoring bucket that still has room
        if len(filled[b]) < per_bucket:
            filled[b].append(rec)
            return b
    if ranked:
        return f"overflow:{ranked[0]}"
    if s["boring"] >= threshold:
        if len(filled["boring"]) < per_bucket:
            filled["boring"].append(rec)
            return "boring"
        return "overflow:boring"
    return "unsure"


async def run(args, pool):
    cache = ScoreCache(default_path(args.mock))
    filled = {b: [] for b in BUCKETS}
    scored, tokens, errors, consecutive_errors = [], 0, 0, 0
    sem, limiter = asyncio.Semaphore(args.concurrency), Limiter(args.rps)
    t0 = time.monotonic()
    async with make_client(args.mock) as client:
        for start in range(0, min(len(pool), args.max_words), args.wave):
            wave = pool[start:start + args.wave]
            results = await asyncio.gather(*(score_word(client, limiter, sem, cache, e, args.model, args.mock)
                                             for e in wave),
                                           return_exceptions=True)
            for entry, res in zip(wave, results):  # assign in pool order so runs are reproducible
                if isinstance(res, (TypeSafeAuthenticationError, TypeSafePermissionDeniedError)):
                    raise SystemExit(f"TypeSafe rejected the API key: {res}")
                if isinstance(res, Exception):
                    errors += 1
                    consecutive_errors += 1
                    if consecutive_errors >= 25:
                        raise SystemExit(f"25 requests in a row failed; last error: {res!r}")
                    continue
                consecutive_errors = 0
                tokens += res["input_tokens"]
                res["outcome"] = assign(res, filled, args.per_bucket, args.threshold, args.reject_at)
                scored.append(res)
            done = sum(min(len(v), args.per_bucket) for v in filled.values())
            print(f"\rscored {len(scored):>5}  |  " + "  ".join(f"{b} {len(filled[b])}" for b in BUCKETS)
                  + f"  |  {tokens / 1e6:.2f}M tok", end="", file=sys.stderr)
            if done == args.per_bucket * len(BUCKETS):
                break
    print(file=sys.stderr)
    cache.close()
    return filled, scored, tokens, errors, time.monotonic() - t0


def write_outputs(args, filled, scored, tokens, errors, elapsed, pool_size):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "scored.jsonl", "w") as f:
        for r in scored:
            f.write(json.dumps(r) + "\n")

    n = len(scored)
    rate = {b: sum(r["scores"][b] >= args.threshold for r in scored) for b in BUCKETS}
    rejects = {k: sum(r["outcome"] == f"rejected:{k}" for r in scored) for k in ("offensive", "familiar", "sad")}
    unsure = sum(r["outcome"] == "unsure" for r in scored)

    with open(out / "qc.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bucket", "word", "pos", "definition", "other_definitions", "spice", *SCORE_KEYS,
                    "zipf", "usage_tags", "sources", "verdict", "notes"])
        for b in BUCKETS:
            for r in filled[b]:
                d = r["definitions"]
                w.writerow([b, r["word"], r["pos"], d[r["best_definition"]],
                            " | ".join(x for i, x in enumerate(d) if i != r["best_definition"]), r["spice"],
                            *[r["scores"][k] for k in SCORE_KEYS], r["zipf"], " ".join(r["usage_tags"]),
                            " ".join(r["sources"]), "", ""])

    lines = [f"# Jev pilot: {args.per_bucket} words per bucket", "",
             f"Scored {n} random words from a pool of {pool_size:,} (Zipf <= {args.zipf_max}); "
             f"bucket threshold {args.threshold}, reject threshold {args.reject_at}. "
             f"{tokens:,} input tokens (about ${tokens / 1e6 * PRICE_PER_MTOK:.3f}), {elapsed:.0f}s, "
             f"{errors} failed requests." + (" MOCK RUN: scores are fake." if args.mock else ""), "",
             "Share of scored words at or above the threshold, per question:", ""]
    for b in BUCKETS:
        share = rate[b] / n if n else 0
        lines.append(f"- {b}: {rate[b]} of {n} ({share:.1%}), about {share * pool_size:,.0f} across the pool")
    lines += ["", f"Left out: {rejects['familiar']} too familiar, {rejects['offensive']} offensive, "
                  f"{rejects['sad']} sad medical, {unsure} unsure (no score over the threshold).", ""]
    for b in BUCKETS:
        lines += [f"## {b.replace('_', ' ')} ({len(filled[b])})", ""]
        for r in filled[b]:
            s = r["scores"]
            d = r["definitions"][r["best_definition"]]
            others = [k for k in POSITIVE_BUCKETS if k != b and s[k] >= args.threshold]
            also = f" (also {', '.join(others)})" if others else ""
            lines.append(f"- **{r['word']}** ({r['pos']}, {r['spice']}): {d}  \n  `{b} {s[b]:.2f} · familiar "
                         f"{s['familiar']:.2f} · zipf {r['zipf']}`{also}")
        lines.append("")
    (out / "qc.md").write_text("\n".join(lines))
    print("\n".join(lines[:2 + 3 + len(BUCKETS) + 3]))
    print(f"wrote {out / 'qc.md'}, {out / 'qc.csv'}, {out / 'scored.jsonl'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-bucket", type=int, default=10)
    ap.add_argument("--threshold", type=float, default=0.6, help="noul needed to count toward a bucket")
    ap.add_argument("--reject-at", type=float, default=0.5, help="noul at which familiar/offensive/sad rejects")
    ap.add_argument("--zipf-max", type=float, default=2.5, help="drop words more common than this (wordfreq Zipf)")
    ap.add_argument("--max-words", type=int, default=6000, help="stop after scoring this many words")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--rps", type=float, default=15, help="request starts per second (limit is 1,200/min)")
    ap.add_argument("--wave", type=int, default=64, help="words scored between progress checks")
    ap.add_argument("--model", default="jev-1.13.0", help="pinned so thresholds stay comparable")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--data", default=str(HERE / "cache"), help="where the dictionary files are cached")
    ap.add_argument("--out", default=str(HERE / "out" / "pilot"))
    ap.add_argument("--mock", action="store_true", help="use a fake Jev (for testing the pipeline)")
    ap.add_argument("--no-wiktionary", action="store_true", help="Webster's + WordNet only (skips a 2.8 GB stream)")
    args = ap.parse_args()

    if not args.mock and not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("Set TYPESAFE_API_KEY first (or pass --mock for a dry run).")
    entries = load_dictionaries(args.data, not args.no_wiktionary)
    print("building candidate pool ...", file=sys.stderr)
    uniq = unique_pool(entries, args.zipf_max, args.seed)
    print(f"pool: {len(uniq):,} words", file=sys.stderr)
    filled, scored, tokens, errors, elapsed = asyncio.run(run(args, uniq))
    write_outputs(args, filled, scored, tokens, errors, elapsed, len(uniq))


if __name__ == "__main__":
    main()
