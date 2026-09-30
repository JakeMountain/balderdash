#!/usr/bin/env python3
"""Threshold review: keep rates per score band from hand verdicts, and a proposed threshold per bucket.

    python review.py

Reads out/review/verdicts.jsonl, one line per band-sample word:
    {"bucket", "band", "word", "keep": bool, "why": null | "dull" | "content"}
"dull" means the word isn't funny or surprising enough; a higher threshold can fix that.
"content" means it's out for what it is (explicit sex, grim, offensive); no threshold fixes that, so those words
are left out of the dullness keep rate and checked against the spicy/offensive scores instead.

Proposed threshold: the lowest band from which every band above keeps at least --target of its non-content words.
Writes out/review/review.md. Once the thresholds are approved, edit thresholds.json and rerun selection.py.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=float, default=0.5, help="keep rate a band needs, content kills excluded")
    ap.add_argument("--scored", default=str(HERE / "out" / "full" / "scored.jsonl"))
    args = ap.parse_args()
    verdicts = [json.loads(l) for l in open(HERE / "out" / "review" / "verdicts.jsonl", encoding="utf-8")]
    scores = {}
    for line in open(args.scored, encoding="utf-8"):
        r = json.loads(line)
        scores[r["word"]] = r["scores"]

    L = ["# Threshold review", "",
         f"{len(verdicts)} band-sample words judged by hand against SPEC part 1, \"What makes a good word\". "
         f"`dull` kills can be fixed by a higher threshold; `content` kills (explicit, grim, offensive) cannot.", ""]
    by = defaultdict(lambda: defaultdict(list))
    for v in verdicts:
        by[v["bucket"]][v["band"]].append(v)
    proposals = {}
    for bucket, bands in by.items():
        L += [f"## {bucket}", "", "| Band | Kept | Keep rate | Keep rate, content kills excluded | Content kills |",
              "| --- | --- | --- | --- | --- |"]
        rates = {}
        for band in sorted(bands):
            vs = bands[band]
            kept = sum(v["keep"] for v in vs)
            content = sum(v["why"] == "content" for v in vs)
            rates[band] = kept / max(1, len(vs) - content)
            L.append(f"| {band:.1f} | {kept}/{len(vs)} | {kept / len(vs):.0%} | {rates[band]:.0%} | {content} |")
        ok = sorted(bands)
        proposal = None
        for band in ok:
            if all(rates[b] >= args.target for b in ok if b >= band):
                proposal = band
                break
        proposals[bucket] = proposal
        L += ["", f"Proposed threshold: **{proposal}**" if proposal is not None else
              f"No band clears {args.target:.0%}; keep the current threshold and lean on hand QC.", ""]

    # Can a score catch the content kills? Compare spicy/offensive for content kills vs keepers.
    L += ["## Content kills vs scores", "",
          "Share of each group at or above a spicy cutoff (words with their scores available):", "",
          "| spicy ≥ | content kills caught | keepers lost |", "| --- | --- | --- |"]
    content = [scores[v["word"]] for v in verdicts if v["why"] == "content" and v["word"] in scores]
    keepers = [scores[v["word"]] for v in verdicts if v["keep"] and v["word"] in scores]
    for cut in (0.5, 0.7, 0.8, 0.9):
        c = sum(s["spicy"] >= cut for s in content)
        k = sum(s["spicy"] >= cut for s in keepers)
        L.append(f"| {cut} | {c}/{len(content)} ({c / max(1, len(content)):.0%}) | "
                 f"{k}/{len(keepers)} ({k / max(1, len(keepers)):.0%}) |")
    L.append("")
    out = HERE / "out" / "review" / "review.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nproposed: {json.dumps(proposals)}\nwrote {out}")


if __name__ == "__main__":
    main()
