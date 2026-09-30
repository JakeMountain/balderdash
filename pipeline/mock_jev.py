"""A fake Jev endpoint for dry runs: same wire format, made-up scores.

Scores come from keyword hints plus a hash of the word, so buckets fill and runs are repeatable.
They say nothing about what real Jev would answer.
"""
import hashlib
import json

import httpx2

HINTS = {
    "gross": ["dung", "excrement", "urine", "vomit", "sweat", "fart", "belch", "snot", "mucus", "pus", "rot", "stink", "fetid", "filth", "ordure"],
    "insult": ["fool", "blockhead", "rascal", "knave", "idler", "braggart", "glutton", "drunkard", "coward", "scoundrel", "simpleton", "fellow", "person who", "one who"],
    "oddly_specific": ["used for", "for holding", "made of", "one who", "a cry", "the act of"],
    "spicy": ["kiss", "lust", "wanton", "harlot", "adulter", "copulat", "amorous"],
    "cheeky": ["buttock", "rump", "drunk", "privy", "breech", "belch", "fart"],
    "sad": ["disease", "cancer", "tumor", "paralysis", "palsy"],
    "boring": ["compound", "genus", "acid", "mineral", "chemistry", "botany", "a kind of", "tissue", "salt of"],
}


STATE_SHAPES = [
    {"word", "part_of_speech", "definitions"},             # standard scoring
    {"word", "part_of_speech", "definitions", "casual"},   # recall: starter definition vs dictionary senses
    {"word", "part_of_speech", "rewrite", "source"},       # rewrite grounding check
]


def _overlap(a, text):
    """Share of the content words in `a` that appear in `text`, squashed into a fake probability."""
    words = [w for w in a.lower().replace(",", " ").split() if len(w) > 3]
    if not words:
        return 0.5
    share = sum(w[:5] in text for w in words) / len(words)
    return round(0.1 + 0.85 * share, 3)


def _h(word, key):
    return int(hashlib.sha256(f"{word}:{key}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _noul(key, word, text):
    base = 0.05 + 0.35 * _h(word, key)
    if any(k in text for k in HINTS.get(key, [])):
        base += 0.5
    if key == "boring":
        base += 0.25
    if key == "sounds_funny" and any(x in word for x in ("bum", "fud", "wog", "snoo", "gob", "wib", "dle", "ump")):
        base += 0.45
    return round(min(base, 0.99), 3)


def handler(request):
    body = json.loads(request.content)
    assert request.url.path.endswith("/v1/systemone"), request.url.path
    assert set(body) == {"state", "model", "questions"}, body.keys()
    state, questions = body["state"], body["questions"]
    assert set(state) in STATE_SHAPES, state.keys()
    word = state.get("word", "")
    text = " ".join(state.get("definitions", [state.get("source", "")])).lower()
    answers = {}
    for name, q in questions.items():
        assert q["type"] in ("noul", "choice"), q
        assert isinstance(q.get("instructions"), str) and q["instructions"], q
        if name in ("casual_match", "grounded"):  # "does A mean the same as B": word overlap stands in
            a = state.get("casual") or state.get("rewrite")
            answers[name] = {"type": "noul", "noul": _overlap(a, text)}
        elif q["type"] == "noul":
            answers[name] = {"type": "noul", "noul": _noul(name, word, text)}
        else:
            labels = list(q["criteria"])
            weights = [1 + _h(word, lab) for lab in labels]
            total = sum(weights)
            probs = {lab: round(w / total, 3) for lab, w in zip(labels, weights)}
            best = max(probs, key=probs.get)
            answers[name] = {"type": "choice", "choice": best, "confidence": probs[best], "probabilities": probs}
    usage = {"input_tokens": len(request.content) // 4, "output_tokens": len(answers)}
    return httpx2.Response(200, json={"model": "jev-1.13.0-mock", "usage": usage, "answers": answers})


def mock_transport():
    return httpx2.MockTransport(handler)
