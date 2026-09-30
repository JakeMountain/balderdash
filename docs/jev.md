# Jev cheat sheet

Jev is TypeSafe AI's classifier model. TypeSafe calls it a "System One" model. You send it text plus typed questions, and it returns probabilities. It never writes text.

It was released on 2026-09-15, which is probably after your training data, so **don't guess the API**. Use this sheet, `pipeline/pilot.py` (which runs against the real SDK), or the docs:

- Docs index: https://docs.typesafe.ai/llms.txt (every page is also available as `.md`)
- Known weak spots: https://docs.typesafe.ai/model-jaggedness/jev-1.13

Checked against the docs and the installed SDK (`typesafe-sdk` 0.7.1) on 2026-09-25. Re-checked 2026-09-27: `jev-1.13.0` is still current, and SDK 0.7.2 only adds an optional `http2` extra.

TypeSafe's own agent skill is installed (`typesafe@typesafe-ai`). It sends you to the live docs, which win over this sheet when they disagree. Beware of third-party write-ups: a HuggingFace blog post pointed at a different domain (`thejevai.com`) and key name (`JEV_API_KEY`).

## Endpoint

```
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer $TYPESAFE_API_KEY
{"state": <text | JSON object | array>, "model": "jev-1.13.0", "questions": {<name>: <question>, ...}}

GET https://api.typesafe.ai/v1/models      # lists aliases; versioned IDs are accepted either way
```

A real request from the pilot, trimmed:

```json
{
  "state": {"word": "wittol", "part_of_speech": "noun",
            "definitions": ["The wheatear.", "A man who knows his wife's infidelity and submits to it; a tame cuckold."]},
  "model": "jev-1.13.0",
  "questions": {
    "sad": {"type": "noul",
            "instructions": "Do the definitions in `definitions` describe a serious disease, disorder, or disability that people suffer from?",
            "criteria": {"true": "For example a cancer, ...", "false": "Not a serious medical condition. Minor bodily things like hiccups ... do not count."}},
    "spicy": {"type": "noul", "instructions": "Is at least one definition in `definitions` about sex, lust, kissing, genitals, or cheating on a partner?"},
    "best_definition": {"type": "choice",
                        "instructions": "In a word-bluffing game, ... Which of these definitions would be the most surprising or funny real answer?",
                        "criteria": {"d0": "The wheatear.", "d1": "A man who knows his wife's infidelity and submits to it; a tame cuckold."}}
  }
}
```

The response:

```json
{"model": "jev-1.13.0",
 "usage": {"input_tokens": 912, "output_tokens": 11},
 "answers": {"sad": {"type": "noul", "noul": 0.03},
             "best_definition": {"type": "choice", "choice": "d1", "confidence": 0.9, "probabilities": {"d0": 0.05, "d1": 0.95}}}}
```

The numbers above are illustrative.

## Question types

| Type | Use for | Fields you send | Answer |
| --- | --- | --- | --- |
| `noul` | yes/no; "Noul" is short for Bernoulli | `instructions`, optional `criteria: {"true": ..., "false": ...}` | `noul`: P(yes), 0–1. No confidence field. |
| `choice` | pick one of an unordered set | `instructions`, `criteria: {label: description or null}` | `choice`, `confidence`, `probabilities` per label |
| `score` | a position on ordered levels | `instructions`, `criteria: [level 0 description, level 1, ...]` | `score` (can fall between levels), `legend`, `probabilities`, `confidence` |

- Question names are for your code and are never sent to the model. Put the whole question in `instructions`.
- Refer to parts of the state by path in backticks, like `` `definitions` `` or `` `ticket.messages[0].text` ``.
- `instructions` and `criteria` values can also be JSON objects or arrays.

## Python SDK

```
pip install typesafe-sdk        # imports as typesafe_sdk
```

```python
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score, RetryPolicy

async with AsyncTypeSafeClient() as client:          # reads TYPESAFE_API_KEY
    resp = await client.system_one(state=state, questions={"gross": Noul(instructions="...")}, model="jev-1.13.0")
    resp.nouls["gross"].noul            # float
    resp.choices["best_definition"].choice
    resp.usage.input_tokens
    resp.model                          # the versioned ID that answered, e.g. "jev-1.13.0"
```

- **Client options:** `api_key`, `model`, `retry=RetryPolicy(...)`, `timeout`, `base_url`, and `transport` or `http_client`. The env vars are `TYPESAFE_API_KEY`, `TYPESAFE_DEFAULT_MODEL` and `TYPESAFE_BASE_URL`.
- **Sync client:** `TypeSafeClient` has the same interface without async.
- **Errors:** `TypeSafeAuthenticationError`, `TypeSafePermissionDeniedError`, `TypeSafeRateLimitError`, `TypeSafeBadRequestError`, `TypeSafeAPIConnectionError`, `TypeSafeAPITimeoutError`. All subclass `TypeSafeError`.
- **Retries:** the SDK retries 429s with backoff by default and honors `retry-after`.
- **Testing offline:** pass `transport=httpx2.MockTransport(handler)`. The SDK uses `httpx2`, a fork of httpx. `pipeline/mock_jev.py` shows the pattern.
- **JavaScript:** the JS SDK is `@typesafe-ai/sdk`. The game doesn't need Jev.

## Model, price, limits (jev-1.13)

| | |
| --- | --- |
| Versioned ID | `jev-1.13.0`. Aliases `jev-latest` and `jev-preview` point to it for now. |
| Price | $0.042 per million input tokens. Output is free. |
| Rate limits | 250,000 tokens/s and 1,200 requests/min. TypeSafe says limits are "adjusting dynamically" and can change without notice. |
| Context | 64k tokens per request. 32k for the state plus the longest single question. |
| Language | English is strongest. |

Pin the versioned ID. Thresholds tuned on one version don't carry over when an alias moves.

## How to ask well (from TypeSafe's guidance)

- **One snap judgment per question.** Split complex judgments into several questions and combine them in code with weights.
- **Put every question in one request.** Questions run in parallel against a state that's read once, so extra questions are nearly free. "Speculative fan-out" is fine: ask questions you might ignore.
- **It reads literally.** Write the exact condition and put boundary cases in `criteria`. If you catch yourself explaining what you really meant, that explanation belongs in the question.
- **No math, counting, or date comparison.** Do those in code, and ask one question per item when counting.
- **Keep the state small.** Irrelevant detail hurts accuracy. Filter in code first.
- **No invariants between questions.** A Noul and a Choice asking the same thing aren't comparable, and P(yes) + P(not-yes) needn't equal 1. Don't reuse a threshold across question types.
- **Adversarial or self-describing text can move answers.** Be explicit in criteria.
- **It's calibrated but a black box.** Scores come with no reasons, so measure against labeled data (here, the starter list and hand QC) before trusting a threshold.
