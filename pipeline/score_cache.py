"""SQLite cache of Jev answers, so nothing is ever paid for twice.

    scores(word, pos, model, state_hash, qset_hash, question, value)

- qset_hash is per question: a hash of that question's wire JSON. Rewording one question re-scores only it.
- state_hash is a hash of the exact state sent. If a word's definitions change (say, Wiktionary is merged in),
  its old answers are not reused against the new input.
- value is P(yes) for a Noul, and the index of the chosen label for a Choice.

Mock runs use a separate file (scores-mock.sqlite) so fake scores can never leak into real ones.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

from questions import LATE_QUESTIONS, questions_for, spice_tier

HERE = Path(__file__).resolve().parent
SCORE_KEYS = ["oddly_specific", "gross", "sounds_funny", "insult", "boring", "spicy", "cheeky", "familiar", "offensive",
              "sad", "misleading"]


def _h(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def qset_hash(question):
    return _h(question.model_dump(exclude_none=True))


def default_path(mock):
    return HERE / "cache" / ("scores-mock.sqlite" if mock else "scores.sqlite")


class ScoreCache:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS scores(
            word TEXT, pos TEXT, model TEXT, state_hash TEXT, qset_hash TEXT, question TEXT, value REAL,
            PRIMARY KEY(word, pos, model, state_hash, qset_hash, question))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS requests(
            word TEXT, pos TEXT, model TEXT, questions INTEGER, input_tokens INTEGER,
            at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        self.db.commit()

    def lookup(self, word, pos, model, state_hash, hashes):
        """{question: value} for every question whose current hash is cached."""
        rows = self.db.execute("SELECT question, qset_hash, value FROM scores "
                               "WHERE word=? AND pos=? AND model=? AND state_hash=?", (word, pos, model, state_hash))
        return {q: v for q, h, v in rows if hashes.get(q) == h}

    def store(self, word, pos, model, state_hash, rows, input_tokens):
        self.db.executemany("INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?,?)",
                            [(word, pos, model, state_hash, h, q, v) for q, h, v in rows])
        self.db.execute("INSERT INTO requests(word, pos, model, questions, input_tokens) VALUES (?,?,?,?,?)",
                        (word, pos, model, len(rows), input_tokens))
        self.db.commit()

    def close(self):
        self.db.close()


async def ask(client, limiter, sem, cache, state, questions, model, key, mock=False):
    """Answer `questions` about `state`, calling Jev only for the ones not cached.

    Returns ({name: noul float | choice label}, input tokens spent on this call).
    `key` is the (word, pos) row key.
    """
    hashes = {name: qset_hash(q) for name, q in questions.items()}
    sh = _h(state)
    cached = cache.lookup(*key, model, sh, hashes)
    missing = {n: q for n, q in questions.items() if n not in cached}
    tokens = 0
    if missing:
        async with sem:
            await limiter.wait()
            resp = await client.system_one(state=state, questions=missing, model=model)
        if not mock and resp.model != model:
            raise RuntimeError(f"asked for {model}, {resp.model} answered; refusing to cache under the pinned ID")
        rows = []
        for n, q in missing.items():
            if q.type == "noul":
                rows.append((n, hashes[n], round(resp.nouls[n].noul, 4)))
            else:
                rows.append((n, hashes[n], list(q.criteria).index(resp.choices[n].choice)))
        tokens = resp.usage.input_tokens or 0
        cache.store(*key, model, sh, rows, tokens)
        cached.update({n: v for n, _, v in rows})
    out = {}
    for n, q in questions.items():
        v = cached[n]
        out[n] = list(q.criteria)[int(v)] if q.type == "choice" else v
    return out, tokens


def state_for(entry):
    return {"word": entry["word"], "part_of_speech": entry["pos"], "definitions": entry["definitions"]}


async def score_word(client, limiter, sem, cache, entry, model, mock=False, backfill=True):
    """The standard scoring of one pool entry: every question in questions.py, one request, cached.

    With backfill=False, a word already scored before LATE_QUESTIONS existed is served from the cache as is,
    instead of paying a request just for the late questions; they're simply missing from its record.
    """
    state = state_for(entry)
    qs = questions_for(state)
    if not backfill:
        cached = cache.lookup(entry["word"], entry["pos"], model, _h(state), {n: qset_hash(q) for n, q in qs.items()})
        if cached and all(n in cached for n in qs if n not in LATE_QUESTIONS):
            qs = {n: q for n, q in qs.items() if n in cached}
    ans, tokens = await ask(client, limiter, sem, cache, state, qs, model, (entry["word"], entry["pos"]), mock)
    scores = {k: round(ans[k], 3) for k in SCORE_KEYS if k in ans}
    best = int(ans["best_definition"][1:]) if "best_definition" in ans else 0
    return {**entry, "scores": scores, "spice": spice_tier(scores), "best_definition": best,
            "category": ans.get("category"), "model": model, "input_tokens": tokens}
