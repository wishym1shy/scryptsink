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



def test_continuous_speech_cues_touch():
    """Issue #6: cues in one continuous run of speech must touch; a 1-frame gap reads as a blink."""
    script = "This is a really long sentence, which should be split into several balanced cues so we can see the gaps."
    asr, truth, end = speak([script])
    for fps in (30.0, 25.0, 24000 / 1001, 0.0):
        s = Settings(fps=fps)
        res = sync_words(parse_script(script, s), asr, end, s)
        assert len(res.cues) >= 3
        for a, b in zip(res.cues, res.cues[1:]):
            assert srt_time(a.end) == srt_time(b.start), (fps, a, b)
        assert "-->" in res.srt_text


def test_real_pause_keeps_gap_and_no_slivers():
    """A pause longer than bridge_gap stays a visible gap; no gap anywhere is shorter than min_gap."""
    asr, truth, end = speak(["Hello there friends", "Second line after a pause", "Third", "Fourth one"],
                            pause=1.2)
    s = Settings()
    res = sync_words(parse_script("Hello there friends\nSecond line after a pause\nThird\nFourth one", s),
                     asr, end, s)
    gaps = [b.start - a.end for a, b in zip(res.cues, res.cues[1:])]
    assert gaps[0] > 0.5, gaps
    assert all(g == 0 or g >= s.min_gap - 1e-9 for g in gaps), gaps
    # min-duration stretch of a short cue right before the next one must not leave a sliver either
    asr = [AsrWord("Hi", 1.0, 1.2), AsrWord("there", 1.95, 2.3)]
    s = Settings(bridge_gap=0.4, min_cue_seconds=0.8)
    res = sync_words(["Hi", "there"], asr, 3.0, s)
    g = res.cues[1].start - res.cues[0].end
    assert g == 0 or g >= s.min_gap - 1e-9, g


def test_frame_snapping():
    asr, truth, end = speak(["one two three four five six seven", "eight nine ten"], pause=0.9)
    for fps in (24.0, 25.0, 30.0):
        s = Settings(fps=fps, premiere_zero_fix=False)
        res = sync_words(["one two three four five six seven", "eight nine ten"], asr, end, s)
        for c in res.cues:
            for t in (c.start, c.end):
                assert abs(t * fps - round(t * fps)) < 1e-6, (fps, t)
            assert c.end > c.start


def test_decode_audio_without_pyav():
    """Regression: faster-whisper's own loader calls av.open(metadata_errors=...), which crashes on older
    PyAV. decode_audio must work (via ffmpeg) even if PyAV can't be imported at all."""
    import shutil, subprocess, tempfile
    ff = find_ffmpeg()
    if not ff:
        print("skipped (no ffmpeg)"); return
    d = tempfile.mkdtemp()
    wav = os.path.join(d, "tone.wav")
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-ar", "44100", wav], check=True)
    saved = sys.modules.get("av")
    sys.modules["av"] = None            # any `import av` now raises ImportError
    try:
        audio = decode_audio(wav)
    finally:
        if saved is None: sys.modules.pop("av", None)
        else: sys.modules["av"] = saved
    assert audio.dtype.name == "float32" and abs(len(audio) - 32000) < 400, len(audio)
    try:
        decode_audio(os.path.join(d, "missing.mp4")); assert False
    except SyncError as e:
        assert "Couldn't read the audio" in str(e), e


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            print("---", n); f()
    print("ALL OK")
