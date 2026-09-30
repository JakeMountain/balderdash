# Bluff Dictionary

A Balderdash variant played on obscure words whose real definitions are already funny or gross, so silly bluffs don't stick out. `SPEC.md` has the design. A Python pipeline builds `data/words.json`; a web game in `game/` plays it.

## Layout

- `pipeline/`: dictionary loaders (Webster's 1913, WordNet 2022, Wiktionary), filters, Jev questions (`questions.py`), and the run scripts below.
- `game/`: Vite + React client, Cloudflare Worker with one Durable Object per room. See `game/README.md`.
- `data/words.json`: the product. Currently the 255 starter words.
- `docs/jev.md`: Jev summary. Jev postdates your training data; use it, the TypeSafe skill, and docs.typesafe.ai rather than guessing.

## Pipeline

Run from `pipeline/`. Every Jev answer is cached in `cache/scores.sqlite`, so re-cuts are free. `--mock` dry-runs anything that calls Jev.

| Step | Command | Status |
| --- | --- | --- |
| Pilot QC sample | `python pilot.py` | done |
| Starter-list recall | `python recall.py` | done (73%) |
| Score a sample | `python run_full.py --limit N` | 40,000 scored; resumable |
| Cut candidates | `python selection.py` | thresholds in `thresholds.json` |
| Late questions for old words | `python backfill.py` | then `run_full.py --no-backfill` |
| Pick the sense to show | `python best_sense.py` | per-bucket question per definition |
| Viewer data | `python export_viewer.py` | writes `docs/words.json` |
| Threshold review | `python review.py` | done; verdicts in `out/review/verdicts.jsonl` |
| Rewrite | `rewrite.py` | next |
| QC tool + export to `words.json` | | after rewrite |

Decided:

- Jev is pinned to `jev-1.13.0`, with one request per word carrying every question. Jev classifies; code does filtering, quotas and caps.
- Buckets: oddly_specific 30%, misleading (sounds like it means something else) 20%, gross 15%, sounds_funny 15%, insult 10%, wildcard 10%. Every word also gets a `category` for the game's room filter. The list is about 1,500 words, with no phrases in v1.
- Spice tier: spicy if spicy ≥ 0.5; cheeky if cheeky or gross ≥ 0.5; otherwise mild. Spicy words are capped at 10% of the list; the hand pass judges how far is too far.
- Fix a bad bucket by rewording its question, not by moving its threshold. Stop for review after the pilot, threshold, and final QC steps.

## Rewrite (next)

- **Input:** word, pos, source definitions verbatim with their dictionary, and Jev's `best_definition` index.
- **Output:** `definition` (at most 15 words, casual, lowercase start, no trailing period, restating only the source), `dealer_note` (source facts only, or null), two `decoys` (plausible fakes, not near the real meaning), and `archaic`.
- **Grounding check:** one Jev request per rewrite, state `{word, part_of_speech, rewrite, source}`:
  - `grounded` Noul: "does `rewrite` mean the same as `source`?"
  - `relation` Choice: same / adds_claim / different.
  - Accept only grounded ≥ 0.8 and `same` at confidence ≥ 0.8; everything else goes to `needs_fix`. No meaning from model memory.

## Conventions

- Keys live in `.env` (gitignored): `TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`. `pilot.py` loads it.
- Python 3.10+, minimal dependencies. Scripts resolve paths relative to themselves.
- Keep the Jev state small (word, part of speech, definitions). Write questions literally, with boundary cases in `criteria`. Teach `mock_jev.py` any new question shape before calling the real API.
- Don't name a module after a stdlib one (`select.py` broke asyncio).
