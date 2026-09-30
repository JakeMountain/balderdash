#!/usr/bin/env python3
"""Starter-list recall: do the hand-picked starter words clear a bucket, and are their casual definitions real?

    python recall.py              # real run; costs well under a cent
    python recall.py --mock       # dry run with the fake Jev

Two checks per starter word found in the pool:
1. Scoring, exactly as the full run does it (same state, same questions, same cache). A word that clears no
   bucket at --threshold, or that a reject question throws out, is a miss. Target: 80%+ clear some bucket.
2. Grounding: one Noul asking whether the starter's casual definition means the same thing as at least one of
   the word's dictionary senses. The starter definitions were written from memory, so under 0.8 is flagged.

Starter words not in the pool are listed with the reason (not in any dictionary, or which filter dropped them).

Outputs (in --out, default pipeline/out/recall/): recall.md, recall.csv
"""
import argparse
import asyncio
import csv
import json
import os
import sys
from pathlib import Path

from typesafe_sdk import Noul
from wordfreq import zipf_frequency

from pilot import HERE, Limiter, load_dictionaries, make_client
from pool import WORD_RE, build_pool, clean_sense
from questions import POSITIVE_BUCKETS, REJECTS
from score_cache import ScoreCache, ask, default_path, score_word

STARTER = HERE.parent / "data" / "words.json"
MAX_GROUNDING_SENSES = 8  # the starter's sense may not be in the first 3 the scoring request sees

CASUAL_MATCH = Noul(
    instructions="Does the definition in `casual` mean the same thing as at least one of the definitions in "
                 "`definitions`?",
    criteria={
        "true": "`casual` is a looser or more informal restatement of one of the definitions. Casual wording, "
                "slang, and dropped detail are fine as long as the thing described is the same.",
        "false": "`casual` describes something different from every definition, or adds a claim that none of "
                 "them makes.",
    },
)


def why_not_in_pool(word, pos, entries_by_word, zipf_max):
    """A short reason a starter word didn't make the pool."""
    if " " in word:
        return "phrase (v1 has no phrases)"
    es = entries_by_word.get(word)
    if not es:
        return "not in any dictionary"
    if not WORD_RE.match(word):
        return "length or characters (4-20 letters)"
    if word.endswith("ness"):
        return "-ness"
    z = zipf_frequency(word, "en")
    if z > zipf_max:
        return f"too common (Zipf {z:.2f})"
    return "no usable senses (cross-reference, inflection, or taxonomy only)"


async def run(args, starters, pool_by_word, entries_by_word):
    cache = ScoreCache(default_path(args.mock))
    sem, limiter = asyncio.Semaphore(args.concurrency), Limiter(args.rps)
    tokens = 0

    async def one(s, entry):
        nonlocal tokens
        rec = await score_word(client, limiter, sem, cache, entry, args.model, args.mock)
        raw = next((e for e in entries_by_word[s["word"]] if e["pos"] == entry["pos"]), entries_by_word[s["word"]][0])
        senses = [clean_sense(x) for x in raw["senses"]][:MAX_GROUNDING_SENSES]
        state = {"word": s["word"], "part_of_speech": entry["pos"], "definitions": senses, "casual": s["definition"]}
        ans, t = await ask(client, limiter, sem, cache, state, {"casual_match": CASUAL_MATCH}, args.model,
                           (s["word"], entry["pos"]), args.mock)
        tokens += rec["input_tokens"] + t
        return {**rec, "starter": s, "grounding_senses": senses, "casual_match": round(ans["casual_match"], 3)}

    async with make_client(args.mock) as client:
        jobs = []
        for s in starters:
            cands = pool_by_word.get(s["word"], [])
            if cands:
                entry = next((e for e in cands if e["pos"] == s["pos"]), cands[0])
                jobs.append(one(s, entry))
        results = await asyncio.gather(*jobs)
    cache.close()
    return results, tokens


def outcome(rec, threshold, reject_at):
    s = rec["scores"]
    for r in ("offensive", "familiar", "sad"):
        if s[r] >= reject_at:
            return f"rejected:{r}"
    cleared = sorted((b for b in POSITIVE_BUCKETS if s[b] >= threshold), key=lambda b: -s[b])
    return cleared[0] if cleared else "miss"


def write_outputs(args, starters, results, missing, tokens):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for r in results:
        r["outcome"] = outcome(r, args.threshold, args.reject_at)
    n = len(results)
    hits = [r for r in results if r["outcome"] in POSITIVE_BUCKETS]
    flagged = sorted((r for r in results if r["casual_match"] < args.match_at), key=lambda r: r["casual_match"])

    with open(out / "recall.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        keys = POSITIVE_BUCKETS + ["boring"] + REJECTS + ["spicy", "cheeky"]
        w.writerow(["word", "pos", "category", "outcome", *keys, "casual_match", "casual", "definitions",
                    "sources", "zipf"])
        for r in sorted(results, key=lambda r: r["word"]):
            w.writerow([r["word"], r["pos"], r["starter"]["category"], r["outcome"], *[r["scores"][k] for k in keys],
                        r["casual_match"], r["starter"]["definition"], " | ".join(r["definitions"]),
                        " ".join(r["sources"]), r["zipf"]])

    L = [f"# Starter-list recall", "",
         f"{len(starters)} starter words; {n} are in the pool and were scored. Bucket threshold {args.threshold}, "
         f"reject threshold {args.reject_at}, grounding flag under {args.match_at}. {tokens:,} input tokens spent "
         f"(cached answers are free)." + (" MOCK RUN: scores are fake." if args.mock else ""), "",
         f"**Recall: {len(hits)} of {n} ({len(hits) / n:.0%}) clear some bucket.** Target is 80%.", ""]
    L += ["| Bucket | Starter words clearing it (any score ≥ threshold) | Assigned (best bucket) |", "| --- | --- | --- |"]
    for b in POSITIVE_BUCKETS:
        L.append(f"| {b} | {sum(r['scores'][b] >= args.threshold for r in results)} "
                 f"| {sum(r['outcome'] == b for r in results)} |")
    L.append("")
    by_cat = {}
    for r in results:
        c = by_cat.setdefault(r["starter"]["category"], [0, 0])
        c[0] += r["outcome"] in POSITIVE_BUCKETS
        c[1] += 1
    L += ["By starter category: " + ", ".join(f"{c} {h}/{t}" for c, (h, t) in sorted(by_cat.items())), ""]

    for label, test in (("Rejected (a good word the reject questions threw out)", lambda o: o.startswith("rejected")),
                        ("Misses (cleared no bucket)", lambda o: o == "miss")):
        rows = [r for r in results if test(r["outcome"])]
        L += [f"## {label}: {len(rows)}", ""]
        for r in sorted(rows, key=lambda r: r["word"]):
            s = r["scores"]
            top = max(POSITIVE_BUCKETS, key=lambda b: s[b])
            L.append(f"- **{r['word']}** ({r['pos']}, {r['outcome']}): {r['starter']['definition']}  \n"
                     f"  `best {top} {s[top]:.2f} · boring {s['boring']:.2f} · familiar {s['familiar']:.2f} · "
                     f"offensive {s['offensive']:.2f} · sad {s['sad']:.2f}`  \n"
                     f"  Jev saw: {' / '.join(r['definitions'])}")
        L.append("")

    L += [f"## Casual definition doesn't match the dictionary (under {args.match_at}): {len(flagged)}", "",
          "Either the starter definition is wrong, or it uses a sense the dictionaries don't have. "
          "Check each one against a source before trusting it.", ""]
    for r in flagged:
        L.append(f"- **{r['word']}** ({r['casual_match']:.2f}): starter says \"{r['starter']['definition']}\"  \n"
                 f"  dictionary: {' / '.join(r['grounding_senses'][:4])}")
    L.append("")

    L += [f"## Not in the pool: {len(missing)}", ""]
    reasons = {}
    for word, why in missing:
        reasons.setdefault(why.split(" (")[0] if why.startswith("too common") else why, []).append(
            f"{word} ({why.split('(')[1][:-1]})" if why.startswith("too common") else word)
    for why, words in sorted(reasons.items(), key=lambda kv: -len(kv[1])):
        L.append(f"- {why} ({len(words)}): {', '.join(sorted(words))}")
    (out / "recall.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:6]))
    print(f"wrote {out / 'recall.md'}, {out / 'recall.csv'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threshold", type=float, default=0.6)
    ap.add_argument("--reject-at", type=float, default=0.5)
    ap.add_argument("--match-at", type=float, default=0.8, help="flag casual definitions scoring under this")
    ap.add_argument("--zipf-max", type=float, default=2.5)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--rps", type=float, default=15)
    ap.add_argument("--model", default="jev-1.13.0")
    ap.add_argument("--data", default=str(HERE / "cache"))
    ap.add_argument("--out", default=str(HERE / "out" / "recall"))
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--no-wiktionary", action="store_true")
    args = ap.parse_args()
    if not args.mock and not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("Set TYPESAFE_API_KEY first (or pass --mock for a dry run).")

    starters = json.loads(STARTER.read_text(encoding="utf-8"))["words"]
    entries = load_dictionaries(args.data, not args.no_wiktionary)
    entries_by_word, pool_by_word = {}, {}
    for e in entries:
        entries_by_word.setdefault(e["word"], []).append(e)
    for e in build_pool(entries, zipf_max=args.zipf_max):
        pool_by_word.setdefault(e["word"], []).append(e)
    missing = [(s["word"], why_not_in_pool(s["word"], s["pos"], entries_by_word, args.zipf_max))
               for s in starters if s["word"] not in pool_by_word]
    in_dict = sum(s["word"] in entries_by_word for s in starters)
    print(f"starter words: {in_dict} of {len(starters)} in the dictionaries, "
          f"{len(starters) - len(missing)} in the pool", file=sys.stderr)
    results, tokens = asyncio.run(run(args, starters, pool_by_word, entries_by_word))
    write_outputs(args, starters, results, missing, tokens)


if __name__ == "__main__":
    main()
