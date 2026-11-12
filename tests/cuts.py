"""Cut-quality check: how often cues join two sentences, end on a word that belongs with the next one
("the | car", "will | be"), leave a word alone on its line, or split a sentence into very uneven lines
("This is our best | effort." rather than "This is our | best effort."). Lower is better.
Measured for the Short-form shape (18 characters, 4 words) and at 32 and 40 characters.
Run before/after changing the cue splitter (e.g. the COST_* weights in scriptsync_core.py):

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
 "This is our best effort. We stand behind every single thing we make, and we hope you can taste it.",
]


# Fixed list so the score means the same thing whichever version of the splitter is measured.
GLUE = set("""a an the of to in on at for with from by into onto over under about and but or so because if
than my your his her its our their this that these those is are was were be been has have had will would can
could should must do does did not""".split())


SENT_END = re.compile(r"[.!?][\"')]*$")
SHAPES = [("Short-form", 18, 4), ("32 characters", 32, 0), ("40 characters", 40, 0)]
MEASURES = ["two sentences in one cue", "ends on a glue word", "lone words", "uneven lines"]


def score(max_chars, max_words=0):
    """-> (cues, {measure: count}, [flagged cue descriptions])"""
    n = dict.fromkeys(MEASURES, 0)
    cues, bad = 0, []
    for sc in SAMPLES:
        asr, _, end = speak([sc])
        s = core.Settings(max_chars=max_chars, max_words=max_words)
        res = core.sync_words(core.parse_script(sc, s), asr, end, s)
        texts = [c.text for c in res.cues]
        for k, t in enumerate(texts):
            cues += 1
            ws = t.split()
            if any(SENT_END.search(w) for w in ws[:-1]):
                n["two sentences in one cue"] += 1; bad.append("two sentences   " + t)
            if k + 1 < len(texts) and re.sub(r"\W+$", "", ws[-1]).lower() in GLUE and not re.search(r"\W$", ws[-1]):
                n["ends on a glue word"] += 1; bad.append("ends on glue    " + t)
            starts_sentence = k == 0 or SENT_END.search(texts[k - 1])
            if len(ws) == 1 and not (starts_sentence and SENT_END.search(ws[0])):    # "Yes." alone is fine
                n["lone words"] += 1; bad.append("lone word       " + t)
            if k + 1 < len(texts) and not SENT_END.search(t):                   # the sentence goes on
                a, b = len(t), len(texts[k + 1])
                if min(a, b) / max(a, b) < 0.4:
                    n["uneven lines"] += 1; bad.append(f"uneven lines    {t} | {texts[k + 1]}")
    return cues, n, bad


# --check (used by CI): today's values. Lower a limit when the splitter gets better; never raise one
# without saying why in the PR.
LIMITS = {
    "Short-form":    {"two sentences in one cue": 0, "ends on a glue word": 6, "lone words": 0, "uneven lines": 3},
    "32 characters": {"two sentences in one cue": 0, "ends on a glue word": 0, "lone words": 0, "uneven lines": 1},
    "40 characters": {"two sentences in one cue": 0, "ends on a glue word": 0, "lone words": 0, "uneven lines": 0},
}

if __name__ == "__main__":
    failed = False
    for name, mc, mw in SHAPES:
        cues, n, bad = score(mc, mw)
        print(f"{name}: {cues} cues | " + " | ".join(f"{k}: {v}" for k, v in n.items()))
        if "-v" in sys.argv:
            for b in bad:
                print("   " + b)
        for k, v in n.items():
            if v > LIMITS[name][k]:
                print(f"FAIL at {name}: {k} = {v} (limit {LIMITS[name][k]})")
                failed = True
    if "--check" in sys.argv:
        print("FAIL" if failed else "OK: within limits")
        sys.exit(1 if failed else 0)
