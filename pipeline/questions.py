"""The Jev question set. One yes/no (Noul) per property, plus a Choice to pick the best sense.

Written literally, with boundary cases in the criteria, per TypeSafe's jev-1.13 guidance.
State shape sent with every request: {"word": str, "part_of_speech": str, "definitions": [str, ...]}
"""
from typesafe_sdk import Choice, Noul

# Buckets filled in the pilot, in tie-break order (oddly specific first: it's the one to overindex on).
POSITIVE_BUCKETS = ["oddly_specific", "gross", "sounds_funny", "insult"]
BUCKETS = POSITIVE_BUCKETS + ["boring"]
# Asked and recorded, but used as filters or tags rather than buckets.
REJECTS = ["offensive", "familiar", "sad"]
TAGS = ["spicy", "cheeky"]
TIER_AT = 0.5


def spice_tier(scores):
    """mild / cheeky / spicy, so groups can filter by audience. Spicy = sexual; cheeky = crude but not sexual."""
    if scores["spicy"] >= TIER_AT:
        return "spicy"
    if scores["cheeky"] >= TIER_AT or scores["gross"] >= TIER_AT:
        return "cheeky"
    return "mild"

QUESTIONS = {
    "oddly_specific": Noul(
        instructions="Does at least one definition in `definitions` describe something so narrow or oddly "
                     "particular that a listener might assume it was a made-up joke definition?",
        criteria={
            "true": "A single word for a very specific person, act, object, or situation, such as a word for "
                    "someone who idly watches boats go by, or for tidying up in a panic just before guests arrive.",
            "false": "A general, ordinary, or technical meaning, such as a type of plant, a chemical compound, "
                     "a mineral, a common tool, or a plain quality like 'full of heaps'.",
        },
    ),
    "gross": Noul(
        instructions="Would most people find the thing described by at least one definition in `definitions` "
                     "gross or icky, the kind of thing that makes someone say 'ew'?",
        criteria={
            "true": "For example farting, burping, vomit, snot, earwax, dung, pus, sweaty feet, rotting flesh, "
                    "or picking your nose.",
            "false": "Nothing described would make most people say 'ew'. Dry medical, scientific, or anatomical "
                     "terms (a hormone, an enzyme, an organ, a lab finding) do not count just because they involve "
                     "the body, and neither do religious or cultural practices.",
        },
    ),
    "sounds_funny": Noul(
        instructions="Ignoring what it means, does the word in `word` sound silly, rude, or funny when said aloud?",
        criteria={
            "true": "The sound alone would make people smile or snicker: a silly rhythm, a goofy combination of "
                    "sounds, or a part that sounds like a rude word.",
            "false": "The word sounds plain, serious, or technical.",
        },
    ),
    "insult": Noul(
        instructions="Is at least one definition in `definitions` a colorful name for a kind of person, "
                     "especially a mocking or insulting one?",
        criteria={
            "true": "For example a name for a fool, a show-off, a glutton, a busybody, a coward, or a drunk.",
            "false": "None of the definitions is a name for a kind of person.",
        },
    ),
    "boring": Noul(
        instructions="Are all the definitions in `definitions` dry, technical, or ordinary, with nothing funny, "
                     "gross, surprising, or oddly specific in them?",
        criteria={
            "true": "For example a chemical compound, a legal term, a botanical description, a common tool, "
                    "or a plain adjective.",
            "false": "At least one definition is funny, gross, surprising, or oddly specific.",
        },
    ),
    "spicy": Noul(
        instructions="Is at least one definition in `definitions` about sex, lust, kissing, genitals, "
                     "or cheating on a partner?",
    ),
    "cheeky": Noul(
        instructions="Is the word in `word`, or any definition in `definitions`, crude, bodily, rude-sounding, "
                     "or mildly naughty, without being sexual?",
        criteria={
            "true": "For example butts, farts, underwear, drunkenness, toilets, or a name that sounds like a rude "
                    "word even though its meaning is innocent.",
            "false": "Nothing about the word or its definitions is crude or naughty, or the only naughty content "
                     "is sexual.",
        },
    ),
    "familiar": Noul(
        instructions="Would most English-speaking adults know what the word in `word` means?",
        criteria={
            "true": "Most adults have heard the word and could say roughly what it means.",
            "false": "Most adults have never heard the word, or would not know what it means.",
        },
    ),
    "offensive": Noul(
        instructions="Is the word in `word` a slur, an insult that targets people for their race, ethnicity, "
                     "nationality, religion, gender, sexuality, or disability, or a term tied to a hate group "
                     "or extremist ideology?",
        criteria={
            "true": "It is a slur, an insult aimed at one of those groups, or hate-group or extremist jargon, "
                    "such as a Ku Klux Klan title or a white-supremacist conspiracy term.",
            "false": "It is not a slur, does not insult any of those groups, and is not hate-group or extremist "
                     "jargon. General insults like 'fool' or 'drunkard' do not count.",
        },
    ),
    "sad": Noul(
        instructions="Do the definitions in `definitions` describe a serious disease, disorder, or disability "
                     "that people suffer from?",
        criteria={
            "true": "For example a cancer, a genetic disorder, a paralysis, or a mental illness.",
            "false": "Not a serious medical condition. Minor bodily things like hiccups, sneezing, "
                     "earwax, or a hangover do not count.",
        },
    ),
}


# Added after the first 40,000 words were scored. Those words only get these asked where they can matter
# (see backfill.py); run_full.py --no-backfill leaves them missing rather than re-asking everything.
LATE_QUESTIONS = ["misleading", "category"]
QUESTIONS["misleading"] = Noul(
    instructions="Does the word in `word` sound or look like it means something quite different from what the "
                 "definitions in `definitions` say?",
    criteria={
        "true": "The word suggests a wrong meaning: it contains or resembles a rude, bodily, or everyday word, or its "
                "sound hints at something unrelated. For example 'cockchafer' (a beetle), 'fartlek' (a running "
                "workout), 'titivate' (to tidy yourself up), 'poophyte' (a meadow plant), 'bumtrap' (a bailiff).",
        "false": "The word gives no wrong impression: its meaning is what its sound or parts suggest, or its sound "
                 "suggests no particular meaning at all.",
    },
)
# The game's room filter uses these; they match data/words.json's starter categories.
CATEGORIES = {
    "body": "The human body, its parts, fluids, smells, or ailments (but not excrement or toilets).",
    "toilet": "Excrement, urine, farting, toilets, chamber pots, or cleaning them.",
    "love": "Kissing, flirting, courtship, romance, sex, or cheating on a partner.",
    "people": "A name for a kind of person, such as a fool, a show-off, or a gossip.",
    "food_drink": "Food, drink, cooking, eating, or drinking alcohol.",
    "jobs": "A job, trade, occupation, or official role.",
    "creatures": "An animal, bird, fish, insect, or mythical creature.",
    "behavior": "An action, habit, mood, or way of behaving.",
    "things": "An object, tool, garment, instrument, or game.",
    "none": "None of the above, such as a plant, a place, a rock, or a scientific or technical idea.",
}
QUESTIONS["category"] = Choice(
    instructions="Which topic do the definitions in `definitions` belong to? If they fit several, pick the topic of "
                 "the most unusual definition.",
    criteria=CATEGORIES,
)
POSITIVE_BUCKETS.insert(1, "misleading")  # ahead of sounds_funny in ties: a misleading word is the better find


def questions_for(state):
    """Every question, plus a sense-picking Choice when the word has more than one definition."""
    qs = dict(QUESTIONS)
    defs = state["definitions"]
    if len(defs) > 1:
        qs["best_definition"] = Choice(
            instructions="In a word-bluffing game, players hear several definitions of `word` and guess the real "
                         "one. Which of these definitions would be the most surprising or funny real answer?",
            criteria={f"d{i}": d for i, d in enumerate(defs)},
        )
    return qs
