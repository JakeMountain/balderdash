# Hand pass: judging criteria by bucket

Written after a first pass that killed too much for the wrong reasons. Read with `hand_pass.md` (input and output format). Every candidate is judged against its own bucket's question, plus the shared gates below.

## What the game needs from a word

A player sees the word and the real definition, writes a fake one, and everyone votes. A word works when (1) most people don't know it, so the real definition is a surprise; (2) the real definition is short and readable at a glance; (3) a fake definition can plausibly compete with it. The definition doesn't have to be funny. In some buckets the word is the joke.

## Shared gates (apply to every bucket)

**Kill outright**
- **Slurs and hate.** Slurs, hate-group or extremist terms, ethnic, religious, sexual-orientation or disability insults, and anything with "-tard" in it.
- **Gendered or sexual-shaming insults.** Slut, strumpet, harlot and their kin.
- **Sad.** Diseases and conditions people suffer from, self-harm, and bereavement.
- **Too dark.** Torture, sexual violence, child abuse, cruelty to animals.
- **Only explicit.** Sexual or scatological words whose only content is being crude. Keep the ones that are funny, oddly specific, or a good trap (a spicy word is fine). The rule is not "no spice".
- **Coinages that live in one community.** Fandom, furry, incel, Discord, 4chan, streamer, political-tribe words, and one-off portmanteaus ("nerdgasm", "hamsicle"). Established words with a life outside one community are fine ("bikeshedding").
- **Fictional-creature entries** (D&D, Pokémon, fursona words).

**Playability**
- **Circular or bare.** "To surpass in X", "resembling Y", "the state of being a Z", and "only used in the phrase...".
- **Two competing senses.** The word has a common modern sense that is not the one we would show (menstruum, excoriate, congee). That creates arguments, so kill it. If the common sense is itself unknown to most groups, it is fine.
- **Needs specialist context.** A dry description that only makes sense inside sumo, heraldry, soil science, chemistry, taxonomy, or a trade. Judge the idea, not the source text. A 30-word source sentence that compresses to "a medieval wandering scholar known for ribald songs" is fine.
- **Guessable from parts.** Test: would someone who has never seen the word guess the real meaning? "outvomit" and "wificide" fail. "binology" passes, because "-ology" points at the wrong genre.
- **Family duplicates.** Keep one word per meaning, the rarest and best-sounding.

**Familiarity.** Jev's `familiar` score is coarse (every candidate is under 0.5, and 97% are under 0.2), so it cannot decide anything alone. Kill for familiarity only if a majority of ordinary adults would know the meaning ("abattoir"). Words that only a word-nerd, a gamer or a programmer would know are unfamiliar to most groups and stay.

**Definition length.** Judge whether the idea takes more than about 15 words to understand, not how long the source sentence is.

## Bucket criteria

**oddly_specific (30%): the definition is the joke.** A word for something nobody needs a word for.
- Keep: a concrete, vivid referent (a job, custom, tool, game, food, ritual, category of person or thing) that is short and surprising; a real attested word, not an obvious coinage; nothing in the word hints at the meaning.
- Kill: trade or hobby jargon that reads dry (sumo ranks, heraldic charges, mollisol), notional units and hypotheticals ("megawarhol"), obvious compounds, and anything sad or dark.

**misleading (20%): the word sounds like it means something else.** The gap between sound and meaning is the joke.
- Keep: the sound suggests a strong wrong idea (rude, gross, medical, animal, person) and the real meaning is plain and short. A plain real meaning is the point: a plant, bird or fish whose silly name misleads is a good word ("gutwort", "pisscutter", "bumbarrel").
- Kill: names that do not mislead, so that the real meaning is what the word already suggests; technical words whose only interest is being technical; unreadable taxonomic definitions; words with a dominant competing sense. Do not kill for a "dull" definition.

**gross (15%): exactly as gross as it sounds.** The real meaning is as crude as any bluff.
- Keep: vivid, specific, concrete gross things (a bodily product, a filth, a food, a parasite's behavior) that are short and unfamiliar. A funny-sounding synonym for a common act ("bowk", "zook") is acceptable, in small numbers.
- Kill: clinical or Greek/Latin terms whose root gives the meaning away (coprophilic, necrophagic), procedure and disease names, bare medical synonyms, and anything that is only about suffering. Parasite, insect, and food facts are fine because they are gross, not sad.

**sounds_funny (15%): funny to say.** Judge the word.
- Keep: silly phonetics, reduplication, cartoon rhythm; a real dictionary, dialect or established slang word; unfamiliar; a short definition of any kind. A plain definition is fine.
- Kill: funny only because of profanity, coinages, and one-word-per-family duplicates (keep the best of "thingamajig" words).

**insult (10%): colorful put-downs.** Judge the word.
- Keep: unfamiliar, vivid, old or dialect insults aimed at behavior or character (fool, braggart, miser, drunk, scold, sneak). A plain definition is fine.
- Kill: slurs, gendered or sexual-shaming insults, class, ethnic, regional or generational labels, ableist insults, political-tribe coinages, and internet insults.

## Sense choice

Pick the sense that best satisfies the bucket, not necessarily the highlighted one. Prefer an obscure sense the group won't have heard over the common one, unless that produces a dispute.

## Notes

Every kill gets a coded note; a keep gets a note only when non-obvious.
