# Word pipeline

Builds the game's word list from standard dictionaries, with Jev (TypeSafe's classifier model) doing the judging. See `../SPEC.md` ("Dictionary pipeline") for the design and `../docs/jev.md` for the API.

## Pilot (built and tested against a mock)

```
pip install -r requirements.txt
export TYPESAFE_API_KEY=...
python pilot.py            # real run: scores random words until each bucket has 10
python pilot.py --mock     # dry run with a fake Jev; scores are meaningless
```

The first run downloads two dictionaries (about 40 MB) into `cache/`:

- Webster's Unabridged, the 1913 text from Project Gutenberg (public domain), via github.com/matthewreagan/WebstersEnglishDictionary
- Open English WordNet 2022 (CC BY 4.0), via nltk_data on GitHub

A run costs $0.25 at most. It stops at 6,000 words, at about 1,000 input tokens each and $0.042 per million.

| File | What it does |
| --- | --- |
| `webster.py` | Parses the Gutenberg text into word, part of speech, senses, and usage tags (Obs., Colloq., Scot., ...) |
| `wordnet.py` | Reads WordNet data files straight from the zip. No nltk needed. |
| `pool.py` | Merges both sources by (word, part of speech), cleans senses, applies the filters and Zipf bound |
| `questions.py` | The Jev question set and the spice-tier rule |
| `pilot.py` | Sampling, async scoring with a rate limiter, bucket assignment, QC outputs |
| `mock_jev.py` | Fake `/v1/systemone` endpoint using the real wire format, plugged in through the SDK's `transport` |

Outputs go to `out/pilot/`:

- `qc.md`: the words grouped by bucket, for reading
- `qc.csv`: the same words with every score, plus blank `verdict` and `notes` columns
- `scored.jsonl`: every word scored, including rejects, for re-cutting thresholds without paying again

## Known rough edges

- Webster's senses sometimes keep a trailing example or author citation, e.g. "Furfurous bread. Sydney Smith."
- Common words used in an obscure sense (lights, fuller, prat) fail the Zipf bound. So do hyphenated words whose parts are common (smell-feast).
- Only 165 of the 255 starter words exist in these two dictionaries. Wiktionary would close most of that gap.

## Beyond the pilot (built, mock-tested)

| File | What it does |
| --- | --- |
| `wiktionary.py` | Streams kaikki.org's raw dump once (2.8 GB, about 2 min) into a slim English cache, `cache/wiktionary-en-v2.jsonl.gz` |
| `score_cache.py` | SQLite cache of every Jev answer, keyed by word, pos, model, state hash, question hash. Mock runs use a separate file |
| `recall.py` | Starter-list recall and the casual-definition grounding check. Writes `out/recall/recall.md` |
| `run_full.py` | Scores the whole pool; resumable, prints the real tokens-per-word after 500 |
| `selection.py` | Thresholds (`thresholds.json`), quotas, caps; candidates plus band samples for review |

`--no-wiktionary` on pilot, recall and run_full skips the Wiktionary source.
