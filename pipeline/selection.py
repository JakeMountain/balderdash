#!/usr/bin/env python3
"""Selection: cut candidates from cached scores with thresholds, quotas and diversity caps (SPEC part 2, "Selection").

    python selection.py                   # reads out/full/scored.jsonl
    python selection.py --mock            # reads out/full-mock/scored.jsonl

Plain code over scores, so rerunning is free. Thresholds live in thresholds.json; review.py proposes new ones.

1. Reject any word with familiar, offensive, or sad >= --reject-at.
2. Each word goes to its highest-scoring bucket at or above that bucket's threshold.
3. Within a bucket, rank by bucket score minus familiar, and fill the quota. Each bucket fills its verb floor first.
4. Caps while filling: one word per family (shared 5-letter stem and meaning), 3 per learned root, spicy <= 10%,
   dialect <= 15%.
5. Short buckets hand their leftover slots to oddly specific first, then the others in order.

The wildcard share (10%) is LLM and QC favorites, not code, so it's reported and left empty.

Outputs:
    out/selection/candidates.jsonl   the cut, in bucket then rank order
    out/selection/selection.md       counts per bucket, caps hit, and shortfalls
    out/review/bands/<bucket>.jsonl  up to 50 words per 0.1 score band per bucket, for review.py
"""
import argparse
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from questions import POSITIVE_BUCKETS

HERE = Path(__file__).resolve().parent
SHARES = {"oddly_specific": 0.30, "misleading": 0.20, "gross": 0.15, "insult": 0.10, "sounds_funny": 0.15}
WILDCARD_SHARE = 0.10
VERB_FLOOR, SPICY_CAP, DIALECT_CAP, ROOT_CAP = 0.15, 0.10, 0.15, 3
DIALECT_TAGS = {"scot", "prov. eng", "prov", "dial", "local", "dialectal", "Scotland", "Northern-England", "Ireland",
                "regional"}
# Learned roots that would otherwise pile up (a list of coprophagy words is one joke told five times).
LEARNED_ROOTS = ["copro", "scato", "pyg", "phagia", "phagy", "phagous", "phile", "philia", "phobia", "mania", "mancy",
                 "latry", "logy", "cracy", "gamy", "cide", "orexia", "rrhea", "rrhoea", "algia", "osis", "itis",
                 "emia", "cephal", "derm", "gastr", "odont", "podo", "rhino", "ophthalm", "necro", "hemo", "haemo",
                 "urin", "uro", "sarco", "trich"]
BANDS = [round(0.3 + 0.1 * i, 1) for i in range(7)]  # 0.3-0.4 ... 0.9-1.0
BAND_SIZE = 50
STOP = {"with", "that", "which", "from", "into", "being", "having", "used", "person", "something", "someone", "their",
        "this", "other", "very", "made", "kind", "sort", "especially", "one's", "about"}


def roots_of(word):
    w = word.replace("-", "")
    return [r for r in LEARNED_ROOTS if (w.startswith(r) if len(r) <= 4 else r in w)]


def content_words(text):
    return {t[:6] for t in re.findall(r"[a-z]{4,}", text.lower()) if t not in STOP}


def is_dialect(rec):
    return bool(DIALECT_TAGS & set(rec.get("usage_tags", [])))


def assign(rec, thresholds, reject_at):
    s = rec["scores"]
    for r in ("offensive", "familiar", "sad"):
        if s[r] >= reject_at:
            return f"rejected:{r}"
    over = [b for b in POSITIVE_BUCKETS if s.get(b, 0) >= thresholds[b]]  # misleading is missing on early words
    if not over:
        return None
    return max(over, key=lambda b: (s[b], -POSITIVE_BUCKETS.index(b)))  # ties go to the earlier (favored) bucket


class Picker:
    """Holds the global caps and family/root bookkeeping while buckets fill."""

    def __init__(self, target):
        self.target, self.picked, self.why = target, [], Counter()
        self.stems, self.roots, self.spicy, self.dialect = defaultdict(list), Counter(), 0, 0

    def fits(self, rec):
        stem = rec["word"].replace("-", "")[:5]
        for other in self.stems[stem]:
            if content_words(rec["definition"]) & content_words(other["definition"]) or \
                    rec["word"].startswith(other["word"]) or other["word"].startswith(rec["word"]):
                self.why["family"] += 1
                return False
        if any(self.roots[r] >= ROOT_CAP for r in roots_of(rec["word"])):
            self.why["learned root"] += 1
            return False
        if rec["spice"] == "spicy" and self.spicy >= SPICY_CAP * self.target:
            self.why["spicy cap"] += 1
            return False
        if is_dialect(rec) and self.dialect >= DIALECT_CAP * self.target:
            self.why["dialect cap"] += 1
            return False
        return True

    def take(self, rec, bucket):
        rec = {**rec, "bucket": bucket}
        self.picked.append(rec)
        self.stems[rec["word"].replace("-", "")[:5]].append(rec)
        for r in roots_of(rec["word"]):
            self.roots[r] += 1
        self.spicy += rec["spice"] == "spicy"
        self.dialect += is_dialect(rec)


def fill(picker, ranked, bucket, n, used):
    """Take up to n words from ranked into bucket, verbs first up to the floor. Returns how many were taken."""
    taken = 0
    verb_goal = math.ceil(VERB_FLOOR * n)
    for want_verbs in (True, False):
        for rec in ranked:
            if taken >= n or (want_verbs and taken >= verb_goal):
                break
            if rec["word"] in used or (want_verbs and rec["pos"] != "verb") or not picker.fits(rec):
                continue
            picker.take(rec, bucket)
            used.add(rec["word"])
            taken += 1
    return taken


def band_samples(records, thresholds, reject_at, out_dir, seed):
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    live = [r for r in records if not any(r["scores"][k] >= reject_at for k in ("offensive", "familiar", "sad"))]
    counts = {}
    for b in POSITIVE_BUCKETS:
        rows = []
        for lo in BANDS:
            inband = [r for r in live if lo <= r["scores"].get(b, 0) < lo + 0.1 or (lo == BANDS[-1] and r["scores"].get(b, 0) >= lo)]
            sample = rng.sample(inband, min(BAND_SIZE, len(inband)))
            counts[(b, lo)] = (len(sample), len(inband))
            rows += [{"bucket": b, "band": lo, "word": r["word"], "pos": r["pos"], "definition": r["definition"],
                      "definitions": r["definitions"], "score": r["scores"][b], "usage_tags": r["usage_tags"]}
                     for r in sample]
        with open(out_dir / f"{b}.jsonl", "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scored", default=None, help="default out/full/scored.jsonl (out/full-mock/ with --mock)")
    ap.add_argument("--thresholds", default=str(HERE / "thresholds.json"))
    ap.add_argument("--reject-at", type=float, default=0.5)
    ap.add_argument("--target", type=int, default=3500, help="candidates to cut; about 45% survive the hand pass")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()
    scored = Path(args.scored or HERE / "out" / ("full-mock" if args.mock else "full") / "scored.jsonl")
    thresholds = json.loads(Path(args.thresholds).read_text())

    records = []
    for line in open(scored, encoding="utf-8"):
        r = json.loads(line)
        r["definition"] = r["definitions"][r["best_definition"]]
        records.append(r)

    outcomes, by_bucket = Counter(), defaultdict(list)
    for r in records:
        o = assign(r, thresholds, args.reject_at)
        outcomes[o or "unsure"] += 1
        if o in POSITIVE_BUCKETS:
            by_bucket[o].append(r)
    for b in by_bucket:
        by_bucket[b].sort(key=lambda r: -(r["scores"][b] - r["scores"]["familiar"]))

    picker, used = Picker(args.target), set()
    quota = {b: round(SHARES[b] * args.target) for b in POSITIVE_BUCKETS}
    got = {b: fill(picker, by_bucket[b], b, quota[b], used) for b in POSITIVE_BUCKETS}
    leftover = sum(quota[b] - got[b] for b in POSITIVE_BUCKETS)
    extra = Counter()
    for b in POSITIVE_BUCKETS:  # oddly specific first
        if leftover <= 0:
            break
        n = fill(picker, by_bucket[b], b, leftover, used)
        extra[b] += n
        leftover -= n

    sel = Path(args.out) / "selection"
    sel.mkdir(parents=True, exist_ok=True)
    order = {b: i for i, b in enumerate(POSITIVE_BUCKETS)}
    picked = sorted(picker.picked, key=lambda r: (order[r["bucket"]], -(r["scores"][r["bucket"]] - r["scores"]["familiar"])))
    with open(sel / "candidates.jsonl", "w", encoding="utf-8") as f:
        for r in picked:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    bands = band_samples(records, thresholds, args.reject_at, Path(args.out) / "review" / "bands", args.seed)

    n = len(picked)
    pos, spice = Counter(r["pos"] for r in picked), Counter(r["spice"] for r in picked)
    L = ["# Selection", "", f"From {len(records):,} scored words ({scored.name}). Thresholds: "
         + ", ".join(f"{b} {thresholds[b]}" for b in POSITIVE_BUCKETS) + f"; reject at {args.reject_at}.", "",
         "Outcomes: " + ", ".join(f"{k} {v:,}" for k, v in outcomes.most_common()), "",
         f"**{n:,} candidates of a {args.target:,} target** (plus {round(WILDCARD_SHARE * args.target)} wildcard slots "
         f"left for LLM and QC favorites).", "",
         "| Bucket | Quota | Filled | Extra from others' leftovers | Eligible pool |", "| --- | --- | --- | --- | --- |"]
    for b in POSITIVE_BUCKETS:
        L.append(f"| {b} | {quota[b]} | {got[b]} | {extra[b]} | {len(by_bucket[b]):,} |")
    L += ["", f"Verbs {pos['verb']} ({pos['verb'] / max(n, 1):.0%}, floor {VERB_FLOOR:.0%}); "
          f"spicy {spice['spicy']} ({spice['spicy'] / max(n, 1):.0%}, cap {SPICY_CAP:.0%}); "
          f"dialect {sum(map(is_dialect, picked))} (cap {DIALECT_CAP:.0%}). "
          f"Parts of speech: {dict(pos)}. Spice: {dict(spice)}.", ""]
    if pos["verb"] < VERB_FLOOR * n:
        L += [f"**Verb floor missed:** every eligible verb was taken and verbs are still under {VERB_FLOOR:.0%}. "
              "Lowering a bucket threshold for verbs only, or a verb-specific pass, is the fix; it needs a decision.",
              ""]
    L += [
          "Skipped by caps while filling: " + (", ".join(f"{k} {v}" for k, v in picker.why.items()) or "none"), "",
          "Band samples written for review (sampled / in band):", ""]
    for b in POSITIVE_BUCKETS:
        L.append(f"- {b}: " + ", ".join(f"{lo:.1f} {bands[(b, lo)][0]}/{bands[(b, lo)][1]:,}" for lo in BANDS))
    (sel / "selection.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
