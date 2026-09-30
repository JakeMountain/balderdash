"""Parse Project Gutenberg's Webster's Unabridged (1913 text, 2009 release) into entries.

Each entry: word, pos, senses (list of short definition strings), tags (usage labels like
Obs., Colloq., Prov. Eng.). Source text: WebstersEnglishDictionary.txt from
github.com/matthewreagan/WebstersEnglishDictionary (public domain).
"""
import re

HEAD_RE = re.compile(r"^[A-Z][A-Z\-' ]*(;\s*[A-Z][A-Z\-' ]*)*$")
POS_MAP = [
    (r"n\.\s*pl\.", "noun"), (r"n\.", "noun"),
    (r"v\.\s*t\.", "verb"), (r"v\.\s*i\.", "verb"), (r"v\.", "verb"),
    (r"a\.", "adjective"), (r"adv\.", "adverb"), (r"interj\.", "interjection"),
]
TAG_RE = re.compile(r"\[([^\]]{1,40})\]")
USAGE_TAGS = {"obs", "colloq", "archaic", "r", "prov. eng", "scot", "slang", "cant", "low",
              "vulgar", "dial", "local", "eng", "u. s", "prov", "humorous", "jocose", "ludicrous"}
SKIP_PARA = ("Note:", "Syn.", "--", "Etym:", "Also,", "See ")
XREF_RE = re.compile(r"^(See|Same as|Alt\. of|Obs\. form|Variant of|imp\. |p\. ?p\.|pl\. of|Of or pertaining to [A-Z])")


def _pos(header: str):
    # header looks like: Gar`dy*loo", n. Etym: [...]   or   Me*phit"ic, Me*phit"ic*al, a. Etym: ...
    head = header.split("Etym:")[0]
    m = re.search(r",\s*(n\.\s*pl\.|n\.|v\.\s*[ti]\.|v\.|a\.|adv\.|interj\.)(?=[\s,;&\[]|$)", head)
    if not m:
        return None
    raw = m.group(1)
    for pat, name in POS_MAP:
        if re.fullmatch(pat, raw.replace(" ", "")) or re.fullmatch(pat, raw):
            return name
    return None


def _sense_text(par_lines):
    """Take the definition sentence(s) of a paragraph, dropping the trailing citation lines."""
    out = []
    for k, ln in enumerate(par_lines):
        out.append(ln.strip())
        if len(ln) < 60:  # a short line ends the wrapped definition; what follows is quotations
            break
        nxt = par_lines[k + 1].strip() if k + 1 < len(par_lines) else ""
        if ln.rstrip().endswith(".") and nxt[:1].isupper():  # sentence ended at the wrap; next line is a quote
            break
    return " ".join(out)


def _clean(text):
    tags = [t.strip().rstrip(".").lower() for t in TAG_RE.findall(text)]
    tags = [t for t in tags if any(t.startswith(u) for u in USAGE_TAGS)]
    text = TAG_RE.sub("", text)
    text = re.sub(r"^\d+\.\s*", "", text)
    text = re.sub(r"^\([^)]{1,30}\)\s*", "", text)  # leading domain label like (Zoöl.)
    text = re.sub(r"^Defn:\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ;,")
    return text, tags


def parse(path):
    text = open(path, encoding="utf-8-sig").read().replace("\r\n", "\n")
    lines = text.split("\n")
    entries, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i]
        if HEAD_RE.match(ln) and i + 1 < n and lines[i + 1][:1].isalpha() and (i == 0 or lines[i - 1] == ""):
            word = ln.split(";")[0].strip().lower()
            header = lines[i + 1]
            pos = _pos(header)
            j = i + 2
            while j < n and lines[j] != "":  # rest of the header block (wrapped etymology)
                j += 1
            senses, tags = [], []
            pending_label = False
            while j < n:
                while j < n and lines[j] == "":
                    j += 1
                if j >= n or (HEAD_RE.match(lines[j]) and j + 1 < n and lines[j + 1][:1].isalpha()):
                    break
                par = []
                while j < n and lines[j] != "":
                    par.append(lines[j]); j += 1
                first = par[0].strip()
                if first.startswith(SKIP_PARA):
                    continue
                if re.fullmatch(r"\d+\.\s*\([^)]*\)", first) and len(par) == 1:
                    pending_label = True  # "1. (Zoöl.)" then a Defn: paragraph follows
                    continue
                if first.startswith("Defn:") or re.match(r"^\d+\.\s", first) or pending_label:
                    s, t = _clean(_sense_text(par))
                    tags += t
                    pending_label = False
                    if s and not re.match(r"^\(?[a-z]\)", s):
                        senses.append(s)
            if pos and senses:
                entries.append({"word": word, "pos": pos, "senses": senses, "tags": sorted(set(tags))})
            i = j
            continue
        i += 1
    return entries


def usable_senses(senses, max_n=3, max_len=220):
    out = []
    for s in senses:
        if XREF_RE.match(s) or len(s.split()) < 2:
            continue
        out.append(s if len(s) <= max_len else s[:max_len].rsplit(" ", 1)[0] + "…")
        if len(out) == max_n:
            break
    return out
