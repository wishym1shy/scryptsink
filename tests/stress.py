"""Stress test: simulate a speech model with realistic mistakes, compare assigned times to ground truth."""
import os, sys, random, statistics
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scriptsync_core import *
VOC = "car engine price today welcome check amazing interior leather seats drive power great deal honestly warranty trim hybrid mileage".split()
def run(seed, sub=0.08, dele=0.04):
    r = random.Random(seed); s = Settings(max_chars=200, max_cue_seconds=60)
    lines = [" ".join(r.choice(VOC) + ("," if r.random()<.1 else "") for _ in range(r.randint(6,14))).capitalize()+"." for _ in range(8)]
    asr, truth = [], []   # truth: per script word true start
    t = 0.5; skip = r.randrange(8) if r.random() < .5 else -1
    for li, ln in enumerate(lines):
        if li == r.randrange(8):   # ad-lib before some line
            for w in "so yeah this one is special".split():
                asr.append(AsrWord(w, t, t+.3)); t += .35
            t += .3
        for w in ln.split():
            d = .15 + .05*len(w)
            if li == skip: truth.append(None); continue
            truth.append(t)
            x = r.random()
            if x < dele: pass
            elif x < dele+sub: asr.append(AsrWord(r.choice(VOC+["banana","okay"]), t+r.uniform(-.05,.05), t+d))
            else: asr.append(AsrWord(w.strip(",.").lower(), t+r.uniform(-.05,.05), t+d))
            t += d + .04
        t += r.uniform(.3,.9)
    words, off = align_script(parse_script("\n".join(lines), s), asr, t)
    errs = [abs(w.start - tr) for w, tr in zip(words, truth) if tr is not None]
    return errs
allerr = []
for seed in range(200): allerr += run(seed)
allerr.sort()
print(f"{len(allerr)} words | median {statistics.median(allerr)*1000:.0f} ms | p90 {allerr[int(.9*len(allerr))]*1000:.0f} ms | p99 {allerr[int(.99*len(allerr))]*1000:.0f} ms | >1s: {sum(e>1 for e in allerr)/len(allerr)*100:.2f}%")
