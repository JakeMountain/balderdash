# Hand pass: brief

Cut the 3,150 candidates in `docs/words.json` down to the keepers, before anything is rewritten.

## Input

`docs/words.json`, committed. Candidates are the entries whose `source` is not `starter` (the 255 starters are already curated; leave them alone). Each candidate has:

- `word`, `pos`
- `definition`: the sense currently highlighted, chosen by Jev per bucket; `others`: the remaining senses
- `bucket`: why it was selected (oddly_specific, misleading, gross, sounds_funny, insult); `scores`: Jev's answers, 0 to 1
- `category`, `spice`, `tags` (usage labels like slang or obsolete), `zipf`, `source`

No score cache is needed; everything the pass judges is in that file.

## Judge each word

Use SPEC.md, "What makes a good word". Kill a word if it is:

- **Too well known**, or its meaning is guessable from its parts (nonboring, doglessly).
- **A slur**, or a hate-group or extremist term; **a sad medical term** (a disease or disability people suffer from).
- **Dull**: a technical, botanical, chemical or otherwise dry sense with nothing funny, gross or surprising in it.
- **Needs a history lesson**: a real definition over about 15 words to be understood, or a niche group label.
- **A recent internet coinage** with no life outside one community.

Spicy is allowed; the owner decided it can run free. Keep spicy words that are funny, and kill ones that are only explicit. Say which you're doing in the notes so it can be audited.

For each keeper, check the highlighted `definition` is the right one to play. If another sense in `others` is better, give its index in the combined list (`definition` first, then `others` in order). Keep a word only if the sense you choose is one players could plausibly bluff around.

Check `category` and fix it only when it is clearly wrong.

## Output

`data/hand_pass.jsonl`, one line per candidate, in file order:

```json
{"word": "bummaree", "keep": true, "sense": 0, "category": null, "note": "Smithfield porter; nice specific job"}
```

- `sense`: index in `[definition, *others]` of the sense to play; omit it when `keep` is false.
- `category`: only if you're changing it, otherwise `null`.
- `note`: a few words on any kill or non-obvious keep. Keep it short.

Work in batches, commit and push after each. Target is about 1,500 keepers in total including the starters, so expect to keep roughly 45% of the candidates, in the bucket mix `misleading` 20%, `oddly_specific` 30%, `gross` 15%, `sounds_funny` 15%, `insult` 10%, leaving room for a wildcard 10%. Don't fill a quota by keeping weak words; short is fine.

## After this

`rewrite.py` runs on the keepers only, using the sense you chose, then the export writes `data/words.json`. This pass is deliberately before rewriting so the rewrite budget isn't spent on words that get killed.
