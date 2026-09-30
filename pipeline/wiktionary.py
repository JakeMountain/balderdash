"""Load English Wiktionary via kaikki.org's wiktextract dump.

The raw dump (raw-wiktextract-data.jsonl.gz, about 2.8 GB, every language) is streamed once and
filtered down to a slim cache of English entries: {"word", "pos", "senses", "tags"} per line.
Nothing else from the dump is kept on disk.

Field names checked against the 2026-09-02 dump: word, pos, lang_code, senses[].glosses,
senses[].tags, senses[].topics, senses[].form_of, senses[].alt_of. For a subsense, glosses is [parent, subsense];
the parent also appears as its own sense, so only the last gloss is kept, unless it leans on the
parent ("a similar function"), in which case the parent is kept in front.

    python wiktionary.py          # build cache/wiktionary-en.jsonl.gz if missing, print stats
"""
import gzip
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

RAW_URL = "https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz"
POS_MAP = {"noun": "noun", "verb": "verb", "adj": "adjective", "adv": "adverb", "intj": "interjection"}
# Usage labels worth carrying into the pool (dialect cap, archaic note, review context).
USAGE_TAGS = {"obsolete", "archaic", "dialectal", "slang", "humorous", "rare", "colloquial", "informal",
              "vulgar", "derogatory", "offensive", "euphemistic", "nonstandard", "Scotland", "Northern-England",
              "Ireland", "regional", "historical"}
# Senses that point at another entry or aren't a real meaning.
SKIP_TAGS = {"form-of", "alt-of", "abbreviation", "initialism", "acronym", "misspelling", "no-gloss"}
# Narrow technical topics whose senses are never game material. Broad parents like natural-sciences are
# left alone on purpose: they also cover zoology and anatomy, where the gross and oddly specific words live.
SKIP_TOPICS = {"chemistry", "organic-chemistry", "inorganic-chemistry", "biochemistry", "physics", "mathematics",
               "geometry", "algebra", "computing", "programming", "electronics", "electrical-engineering",
               "electromagnetism", "genetics", "molecular-biology", "pharmacology", "pharmaceuticals",
               "particle-physics", "quantum-mechanics", "astronomy", "astrophysics", "statistics",
               "mineralogy", "crystallography", "biotechnology", "cytology", "immunology", "virology",
               "microbiology", "software", "Internet", "telecommunications"}
HERE = Path(__file__).resolve().parent
# A subsense gloss that only makes sense after its parent ("A person fulfilling a similar function at ...").
LEANS_ON_PARENT_RE = re.compile(r"\b(similar|such|same|this|these|that sense|the above|likewise|thereof|also)\b", re.I)
CACHE_NAME = "wiktionary-en-v3.jsonl.gz"  # bump when slim() changes, so the cache rebuilds


def slim(rec):
    """One raw dump record -> a slim entry, or None if it isn't a usable English entry."""
    if rec.get("lang_code") != "en" or rec.get("pos") not in POS_MAP or not rec.get("word"):
        return None
    senses, tags = [], set()
    for s in rec.get("senses", []):
        stags = set(s.get("tags", []))
        if "form_of" in s or "alt_of" in s or stags & SKIP_TAGS or SKIP_TOPICS & set(s.get("topics", [])):
            continue
        glosses = s.get("glosses") or []
        if not glosses:
            continue
        g = glosses[-1].strip()
        if len(glosses) > 1 and LEANS_ON_PARENT_RE.search(g):
            g = f"{glosses[-2].strip().rstrip('.')}; {g[0].lower()}{g[1:]}"
        if g and g not in senses:
            senses.append(g)
            tags |= stags & USAGE_TAGS
    if not senses:
        return None
    return {"word": rec["word"], "pos": POS_MAP[rec["pos"]], "senses": senses, "tags": sorted(tags)}


def build_cache(dest, url=RAW_URL):
    """Stream the raw dump and write the slim English cache. Takes a while; the download is the bottleneck."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"streaming {url.rsplit('/', 1)[-1]} (about 2.8 GB; only English entries are kept) ...", file=sys.stderr)
    seen = kept = 0
    t0 = time.monotonic()
    with urllib.request.urlopen(url) as resp, gzip.GzipFile(fileobj=resp) as raw, \
            gzip.open(tmp, "wt", encoding="utf-8") as out:
        for line in raw:
            seen += 1
            if b'"lang_code": "en"' not in line and b'"lang_code":"en"' not in line:
                continue  # cheap pre-filter; most of the dump is other languages
            e = slim(json.loads(line))
            if e:
                out.write(json.dumps(e, ensure_ascii=False) + "\n")
                kept += 1
            if seen % 200_000 == 0:
                print(f"\r{seen:,} records read, {kept:,} English entries kept, {time.monotonic() - t0:.0f}s",
                      end="", file=sys.stderr)
    print(file=sys.stderr)
    tmp.replace(dest)
    return dest


def parse(path):
    """Yield slim entries from the cache, in the same shape webster.parse and wordnet.parse produce."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


if __name__ == "__main__":
    p = build_cache(HERE / "cache" / CACHE_NAME)
    n = words = 0
    last = None
    for e in parse(p):
        n += 1
        words += e["word"] != last
        last = e["word"]
    print(f"{p}: {n:,} entries (word, pos), about {words:,} distinct words")
