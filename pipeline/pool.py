"""Build the candidate pool: dictionary entries -> structural filters -> obscurity bounds."""
import re

from wordfreq import zipf_frequency

import webster
import wiktionary
import wordnet

WORD_RE = re.compile(r"^[a-z][a-z-]{3,19}$")  # 4-20 chars, plain letters and hyphens, single token
DERIVED_RE = re.compile(
    r"^(In an? [\w-]+ (manner|way|degree)|In the manner of|The (quality|state|condition|act) of being|"
    r"The quality or state of being|Characterized by [\w-]+ness|Somewhat [\w-]+)",
    re.I,
)
# Case-sensitive on purpose: "pertaining to Abelard" (a cross-reference) is junk, "pertaining to the rump" is not.
PERTAIN_RE = re.compile(r"^(Of or pertaining|Of or relating|Pertaining|Relating) to [A-Z]")
TAXON_RE = re.compile(r"^(A|An|The) (genus|family|order|suborder|tribe|class|subclass|division) of\b|"
                      # bare "Any polychaete of the family X"; a real description ("Any of various owls of Asia
                      # and Australasia, of the genus Ninox") has more words before the taxon and stays
                      r"^(Any|A|An)( [\w-]+){1,3} (of|in) the (sub)?(family|genus|order|class|phylum|tribe) [A-Z]",
                      re.I)
# Wiktionary's pointers to other entries, which slip past its form_of/alt_of fields.
WIKT_XREF_RE = re.compile(r"^(Synonym|Alternative (form|spelling)|Obsolete (form|spelling)|Archaic (form|spelling)|"
                          r"Dated (form|spelling)|Nonstandard (form|spelling)|Eye dialect spelling|Abbreviation|"
                          r"Initialism|Acronym|Clipping|Ellipsis|Contraction|Misspelling|Plural|Diminutive) of\b", re.I)
# Chemistry-shaped senses that carry no topic tag.
CHEM_RE = re.compile(r"\b(isomers?|derivative of|glycosides?|flavon\w*|alkaloids?|herbicides?|fungicides?|"
                     r"insecticides?|esters?|amino acids?|enzymes?|inhibitors?|compounds? of|salts? of|"
                     r"hydrocarbons?|polymers?|-yl\b)", re.I)
CITATION_RE = re.compile(r"(?<=[.;])\s+(?:[A-Z][\w'`]*\.?\s*){1,4}\.?$")  # trailing "Shak." / "Sir W. Scott."
PRONUNCIATION_JUNK_RE = re.compile(r"\s*--\s*[A-Z][\w`*\"]*$")  # trailing "--Tit`i*va"tion"


def clean_sense(s):
    s = PRONUNCIATION_JUNK_RE.sub("", s).strip()
    s2 = CITATION_RE.sub("", s).strip()
    if len(s2.split()) >= 3:  # don't let the citation stripper eat a short definition
        s = s2
    s = s.replace("`", "").replace("*", "").replace('"', "")
    return s.rstrip(" ;,")


def load_entries(webster_txt, wordnet_zip, wiktionary_cache=None):
    merged = {}
    # Modern glosses lead (WordNet, then Wiktionary); Webster's archaic senses follow.
    sources = [("wordnet", wordnet.parse(wordnet_zip))]
    if wiktionary_cache:
        sources.append(("wiktionary", wiktionary.parse(wiktionary_cache)))
    sources.append(("webster", webster.parse(webster_txt)))
    for src, entries in sources:
        for e in entries:
            key = (e["word"], e["pos"])
            m = merged.setdefault(key, {"word": e["word"], "pos": e["pos"], "senses": [], "tags": set(), "sources": set()})
            m["sources"].add(src)
            m["tags"].update(e.get("tags", []))
            for s in e["senses"]:
                s = clean_sense(s)
                if s and s not in m["senses"]:
                    m["senses"].append(s)
    return list(merged.values())


TRANSPARENT_RE = re.compile(r"^(?:one who|one that|he who|that which|the act of|the practice of|to make|to become)\s+(\w+)", re.I)


SHORT_SENSE_WORDS = 7
WORD_TOKEN_RE = re.compile(r"[a-z]+")


def transparent(word, sense):
    """True when the sense just spells out the word's own parts.

    'contradicter' = 'one who contradicts'; also short senses built from the word's own stem, like
    'nonsolitary' = 'not solitary', 'solderable' = 'that can be soldered', 'rhizophytic' = 'relating to rhizophytes'.
    """
    m = TRANSPARENT_RE.match(sense)
    if m and len(m.group(1)) >= 4 and word[:5] == m.group(1).lower()[:5]:
        return True
    tokens = WORD_TOKEN_RE.findall(sense.lower())
    if len(tokens) > SHORT_SENSE_WORDS:
        return False
    # a 5+ letter sense word whose first 5 letters sit inside the headword, and that isn't the whole headword
    if any(len(t) >= 5 and t[:5] in word and t != word for t in tokens):
        return True
    # short stems behind an affix: 'nonboring' = 'that does not bore', 'doglessly' = 'without a dog'
    core = strip_affixes(word)
    return core != word and len(core) >= 3 and any(len(t) >= 3 and shares_stem(core, t) for t in tokens)


def shares_stem(a, b):
    """Common prefix covers the shorter word, give or take a final letter ('bore' / 'boring', 'dog' / 'dog')."""
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n >= 3 and n >= min(len(a), len(b)) - 1


AFFIX_PREFIXES = ("non", "un", "dis", "anti", "over", "under", "pre", "re", "sub", "mis")
AFFIX_SUFFIXES = ("lessly", "less", "fully", "ful", "ably", "able", "ibly", "ible", "ishly", "ish", "ly")


def strip_affixes(word):
    """The word with one common prefix and one common suffix removed."""
    w = word.replace("-", "")
    for p in AFFIX_PREFIXES:
        if w.startswith(p) and len(w) - len(p) >= 3:
            w = w[len(p):]
            break
    for s in AFFIX_SUFFIXES:
        if w.endswith(s) and len(w) - len(s) >= 3:
            w = w[:-len(s)]
            break
    return w


def usable(entry, max_senses=3, max_len=220):
    senses = []
    for s in entry["senses"]:
        if transparent(entry["word"], s):
            continue
        if (webster.XREF_RE.match(s) or WIKT_XREF_RE.match(s) or DERIVED_RE.match(s) or PERTAIN_RE.match(s)
                or TAXON_RE.match(s) or CHEM_RE.search(s) or len(s.split()) < 2):
            continue
        senses.append(s if len(s) <= max_len else s[:max_len].rsplit(" ", 1)[0] + "…")
        if len(senses) == max_senses:
            break
    return senses


def build_pool(entries, zipf_max=2.5, zipf_min=0.0):
    pool = []
    for e in entries:
        if not WORD_RE.match(e["word"]) or e["word"].endswith("ness"):
            continue
        z = zipf_frequency(e["word"], "en")
        if not (zipf_min <= z <= zipf_max):
            continue
        senses = usable(e)
        if not senses:
            continue
        pool.append({"word": e["word"], "pos": e["pos"], "definitions": senses, "zipf": round(z, 2),
                     "usage_tags": sorted(e["tags"]), "sources": sorted(e["sources"])})
    return pool
