"""Cut-quality check: how often cues join two sentences, end on a word that belongs with the next one
("the | car", "will | be"), or are a lone word. Lower is better. Run before/after changing the cue splitter:

    python tests/cuts.py          # summary
    python tests/cuts.py -v       # also list every flagged cue
"""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import scriptsync_core as core
from test_core import speak

SAMPLES = [
 "This turquoise ring is set in white gold bands. This turquoise one is the classic version, and it has been our best seller for over ten years.",
 "We have the brand new Sorento with a three-row interior and it is honestly the best one we have. It starts at $25,000 and comes with a free oil change for life!",
 "If you have been waiting for the right moment to upgrade your kitchen, this is it. Every cabinet in the showroom is on sale until the end of the month.",
 "Our team will walk you through every step of the process. From the first phone call to the day we hand you the keys, you will always know what comes next.",
 "The new menu launches on Friday. Come in early, grab a coffee and try the seasonal pastries before they sell out, because last year they were gone by noon.",
 "Welcome back to the channel. In today's video I am going to show you three simple ways to keep your plants alive through the winter months.",
 "She said the house on the corner of Maple Street was built in 1924 by a local carpenter. Nobody has lived there for almost twenty years.",
 "Book your appointment online in less than two minutes. We are open seven days a week, and walk-ins are always welcome at both of our locations.",
]


# Fixed list so the score means the same thing whichever version of the splitter is measured.
GLUE = set("""a an the of to in on at for with from by into onto over under about and but or so because if
than my your his her its our their this that these those is are was were be been has have had will would can
could should must do does did not""".split())


def score(max_chars):
    joins = glue = orphans = cues = 0
    bad = []
    for sc in SAMPLES:
        asr, _, end = speak([sc])
        s = core.Settings(max_chars=max_chars)
        res = core.sync_words(core.parse_script(sc, s), asr, end, s)
        for k, c in enumerate(res.cues):
            cues += 1
            ws = c.text.split()
            if any(re.search(r"[.!?][\"')]*$", w) for w in ws[:-1]):
                joins += 1; bad.append("two sentences   " + c.text)
            if k + 1 < len(res.cues) and re.sub(r"\W+$", "", ws[-1]).lower() in GLUE and not re.search(r"\W$", ws[-1]):
                glue += 1; bad.append("ends on glue    " + c.text)
            if len(ws) == 1 and not re.search(r"[.!?,;:]$", ws[0]):
                orphans += 1; bad.append("lone word       " + c.text)
    return cues, joins, glue, orphans, bad


# --check (used by CI): today's splitter scores 0 / 0 / 0 at both widths; allow a little slack
LIMITS = {"two sentences in one cue": 0, "ends on a glue word": 1, "lone words": 1}

if __name__ == "__main__":
    failed = False
    for mc in (32, 40):
        cues, j, g, o, bad = score(mc)
        print(f"max_chars={mc}: {cues} cues | two sentences in one cue: {j} | ends on a glue word: {g} | lone words: {o}")
        if "-v" in sys.argv:
            for b in bad:
                print("   " + b)
        for (name, limit), value in zip(LIMITS.items(), (j, g, o)):
            if value > limit:
                print(f"FAIL at max_chars={mc}: {name} = {value} (limit {limit})")
                failed = True
    if "--check" in sys.argv:
        print("FAIL" if failed else "OK: within limits")
        sys.exit(1 if failed else 0)
