import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scriptsync_core import *

def speak(segments, wps=2.8, pause=0.5, t=0.4):
    """segments: list of strings -> AsrWord list with plausible timing + ground truth (start,end) per segment"""
    words, truth = [], []
    for seg in segments:
        s0 = t
        for w in seg.split():
            d = 0.12 + 0.06 * len(w)
            words.append(AsrWord(w, t, t + d)); t += d + 0.03
        truth.append((s0, t)); t += pause
    return words, truth, t

def test_basic():
    script = ("Hey guys, welcome to Riverside Auto today.\n"
              "We have the brand new 2025 Sorento with a three row interior.\n"
              "It starts at $25,000 and honestly it's a steal.\n"
              "Come visit us today!")
    spoken = ["hey guys welcome to Riverside Auto today",
              "um so yeah check this out",                     # ad-lib, not in script
              "we have the brand new twenty twenty five Sorrento with a three row interior",
              "it starts at 25,000 and honestly it's a steal"]  # last line never spoken
    asr, truth, end = speak(spoken)
    s = Settings(max_chars=80, max_cue_seconds=10)
    lines = parse_script(script, s)
    res = sync_words(lines, asr, end, s)
    for c in res.cues: print(c.index, short_tc(c.start), short_tc(c.end), c.level, f"{c.conf:.2f}", c.text, c.notes)
    print("skipped:", res.skipped); print("off:", res.off_script); print("match%", res.match_pct)
    # line 1 timing close to truth
    assert abs(res.cues[0].start - truth[0][0]) < 0.1, res.cues[0].start
    # ad-lib detected
    assert any("check this out" in t for _,_,t in res.off_script)
    # last line (never spoken) skipped
    assert any("Come visit" in t for t,_ in res.skipped)
    # line 2 and 3 timing near truth, in order
    assert abs(res.cues[1].start - truth[2][0]) < 0.1
    assert abs(res.cues[2].start - truth[3][0]) < 0.1
    # fuzzy Sorento flagged but OK-ish; text is the SCRIPT's, not ASR's
    assert "Sorento" in res.cues[1].text and "Sorrento" not in res.cues[1].text
    # monotonic, no overlap
    for a,b in zip(res.cues, res.cues[1:]): assert a.end <= b.start, (a,b)
    assert res.cues[0].start >= 0.067 - 1e-9

def test_srt_format():
    c = [Cue(1, 0.067, 1.5, "Hi", 1, "ok", [], 0), Cue(2, 3661.0012, 3662.25, "There", 1, "ok", [], 1)]
    t = make_srt(c)
    assert "00:00:00,067 --> 00:00:01,500" in t and "01:01:01,001 --> 01:01:02,250" in t, t

def test_numbers():
    assert tokens_for("$25,000") == ["twenty","five","thousand","dollars"]
    assert tokens_for("25K") == ["twenty","five","thousand"]
    assert tokens_for("50%") == ["fifty","percent"]
    assert tokens_for("3.5") == ["three","point","five"]
    assert tokens_for("it's") == ["its"]
    assert tokens_for("look-alike") == ["lookalike"]
    assert tokens_for("car—honestly") == ["car","honestly"]
    assert tokens_for("...") == []

def test_script_parsing():
    s = Settings()
    lines = parse_script("Hello [laughs] there\n\n[MUSIC UP]\nSecond — line", s)
    assert lines == ["Hello there", "Second — line"], lines
    srt = "1\n00:00:01,000 --> 00:00:02,000\nHello\nthere\n\n2\n00:00:03,000 --> 00:00:04,000\nBye\n"
    assert parse_script(srt, s) == ["Hello there", "Bye"]

def test_long_line_split():
    s = Settings(max_chars=30)
    script = "This is a really long sentence, which should be split into several balanced cues."
    asr, truth, end = speak([script])
    res = sync_words(parse_script(script, s), asr, end, s)
    for c in res.cues: print(c.text)
    assert len(res.cues) >= 3 and all(len(c.text) <= 30 for c in res.cues)

def test_wrong_script_warns():
    asr, truth, end = speak(["completely different words about something else entirely here today"])
    res = sync_words(parse_script("Welcome to the showroom folks we have great deals on trucks", Settings()), asr, end, Settings(include_unheard=True))
    assert res.warnings, "should warn when script doesn't match"

def test_big_alignment_speed():
    import time
    words = ("the quick brown fox jumps over the lazy dog while a red car drives past " * 60).split()
    script = " ".join(words)
    spoken = list(words); 
    for i in range(10, len(spoken), 37): spoken[i] = "banana"
    del spoken[200:210]
    asr, _, end = speak([" ".join(spoken)])
    t=time.time(); res = sync_words(parse_script(script, Settings(keep_script_lines=True)), asr, end, Settings()); dt=time.time()-t
    print("big align", len(words), "words", f"{dt:.2f}s"); assert dt < 10

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            print("---", n); f()
    print("ALL OK")
