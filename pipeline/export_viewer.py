#!/usr/bin/env python3
"""Write docs/words.json for the GitHub Pages word viewer: current candidates plus the starter words.

    python export_viewer.py

Candidates show their raw dictionary definition until rewrite.py exists: the one best_sense.py picked if it has
run, otherwise the best_definition Choice's pick. All definitions are kept.
"""
import json
from pathlib import Path

from questions import POSITIVE_BUCKETS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SHOWN_SCORES = POSITIVE_BUCKETS + ["boring", "familiar", "spicy", "cheeky", "offensive", "sad"]


def main():
    words = []
    for w in json.loads((ROOT / "data" / "words.json").read_text(encoding="utf-8"))["words"]:
        words.append({"word": w["word"], "pos": w["pos"], "definition": w["definition"], "others": [],
                      "note": w.get("dealer_note"), "category": w["category"], "bucket": None, "spice": w["spice"],
                      "source": "starter", "scores": {}, "tags": w.get("usage_tags", [])})
    picks_path = HERE / "out" / "selection" / "best_sense.json"
    picks = json.loads(picks_path.read_text(encoding="utf-8")) if picks_path.exists() else {}
    for r in map(json.loads, open(HERE / "out" / "selection" / "candidates.jsonl", encoding="utf-8")):
        d = r["definitions"]
        best = picks.get(r["word"], {}).get("index", r["best_definition"])
        words.append({"word": r["word"], "pos": r["pos"], "definition": d[best],
                      "others": [x for i, x in enumerate(d) if i != best], "note": None,
                      "category": r.get("category"), "bucket": r["bucket"], "spice": r["spice"],
                      "source": " + ".join(r["sources"]),
                      "scores": {k: round(r["scores"][k], 2) for k in SHOWN_SCORES if k in r["scores"]},
                      "zipf": r["zipf"], "tags": r["usage_tags"]})
    out = ROOT / "docs" / "words.json"
    out.write_text(json.dumps({"count": len(words), "words": words}, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"wrote {len(words):,} words to {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
