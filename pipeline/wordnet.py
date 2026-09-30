"""Minimal reader for WordNet-format data files (Open English WordNet 2022 from nltk_data).

Download: https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet2022.zip
License: CC BY 4.0 (Open English WordNet) + WordNet license.
Yields one entry per (lemma, pos) with up to a few glosses, most common sense first.
"""
import os
import zipfile

POS_FILES = {"noun": "data.noun", "verb": "data.verb", "adjective": "data.adj", "adverb": "data.adv"}


def _read(root_or_zip, name):
    if root_or_zip.endswith(".zip"):
        with zipfile.ZipFile(root_or_zip) as z:
            member = next(m for m in z.namelist() if m.endswith("/" + name))
            return z.read(member).decode("utf-8", "replace").splitlines()
    return open(os.path.join(root_or_zip, name), encoding="utf-8", errors="replace").read().splitlines()


def parse(root_or_zip):
    out = {}
    for pos, fname in POS_FILES.items():
        for line in _read(root_or_zip, fname):
            if not line or line.startswith("  "):
                continue  # license header lines start with two spaces
            head, _, gloss = line.partition(" | ")
            parts = head.split()
            w_cnt = int(parts[3], 16)
            lemmas = [parts[4 + 2 * k] for k in range(w_cnt)]
            gloss = gloss.strip().split("; \"")[0].strip()  # drop example sentences
            for lem in lemmas:
                word = lem.split("(")[0].replace("_", " ").lower()  # strip adj markers like (a)
                if any(c.isupper() for c in lem.split("(")[0]):
                    continue  # proper nouns
                key = (word, pos)
                out.setdefault(key, {"word": word, "pos": pos, "senses": [], "tags": [], "source": "wordnet"})
                if gloss and gloss not in out[key]["senses"]:
                    out[key]["senses"].append(gloss)
    return list(out.values())
