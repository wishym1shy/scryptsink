import os, sys, re, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scriptsync_core import *
from scriptsync_core import _forget_setup

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


def _cues(script, **kw):
    s = Settings(**kw)
    asr, _, end = speak([script])
    return [c.text for c in sync_words(parse_script(script, s), asr, end, s).cues]


def test_breath_cuts():
    """Issue #7: cut where a speaker would breathe, not just by character count."""
    cues = _cues("This turquoise ring is set in white gold bands. This turquoise one is the classic version, "
                 "and it has been our best seller for over ten years.")
    print(cues)
    assert not any(re.search(r"[.!?]\s", c) for c in cues), "two sentences joined in one cue"
    assert "in white gold bands." in cues or any(c.endswith("bands.") for c in cues)
    glue = {"a", "an", "the", "of", "to", "in", "with", "will", "and", "my", "your"}
    for script in ("We have the brand new Sorento with a three-row interior and it is honestly the best one we have.",
                   "Book your appointment online in less than two minutes. We are open seven days a week, and "
                   "walk-ins are always welcome at both of our locations.",
                   "Our team will walk you through every step of the process. From the first phone call to the "
                   "day we hand you the keys, you will always know what comes next."):
        cues = _cues(script)
        print(cues)
        assert all(len(c) <= 40 for c in cues)
        assert not any(re.search(r"[.!?]\s", c) for c in cues)
        assert not any(c.split()[-1].lower() in glue for c in cues[:-1]), cues
        assert not any(len(c.split()) == 1 for c in cues), cues


def test_pause_is_a_breath():
    """With no punctuation to go on, the cut lands on the speaker's pause."""
    asr, _, end = speak(["so this is the part where", "everyone gets really excited about it"], pause=0.8)
    s = Settings(max_chars=40)
    res = sync_words(["so this is the part where everyone gets really excited about it"], asr, end, s)
    assert [c.text for c in res.cues] == ["so this is the part where", "everyone gets really excited about it"], \
        [c.text for c in res.cues]


def test_max_words():
    cues = _cues("Welcome back to the channel. Today I will show you three simple ways to keep plants alive.",
                 max_words=4)
    print(cues)
    assert all(len(c.split()) <= 4 for c in cues)


def test_words_export():
    script = "Hello there friends.\nThis line is never said."
    asr, _, end = speak(["hello there friends"])
    s = Settings()
    res = sync_words(parse_script(script, s), asr, end, s)
    data = json.loads(make_words_json(res.words))
    assert [d["word"] for d in data] == "Hello there friends. This line is never said.".split()
    assert data[2]["word"] == "friends." and data[2]["heard"] and data[2]["line"] == 1
    assert not data[3]["heard"] and data[3]["line"] == 2
    assert all(d["start"] <= d["end"] for d in data)
    srt = make_words_srt(res.words, s)
    assert srt.count("-->") == 3 and "friends." in srt and "never" not in srt   # unheard words left out


def test_line_breaks_check():
    s = Settings()
    script = "Hello there friends, welcome to the show.\nToday we cook pasta."
    lines = check_line_breaks(script, "Hello there friends,\nwelcome to the show.\nToday we cook pasta.", s)
    assert lines == ["Hello there friends,", "welcome to the show.", "Today we cook pasta."]
    try:
        check_line_breaks(script, "Hello there friends,\nwelcome to our show!\nToday we cook pasta.", s)
        assert False, "changed words must be rejected"
    except SyncError as e:
        msg = str(e); print(msg)
        assert '"the show." to "our show!"' in msg and "your line 2" in msg
    try:
        check_line_breaks(script, "Hello friends,\nwelcome to the show.\nToday we cook pasta. Enjoy!", s)
        assert False
    except SyncError as e:
        assert 'dropped "there"' in str(e) and 'added "Enjoy!"' in str(e), e


def test_line_breaks_run_job_reuses_transcript():
    """Re-cut import: one cue per user line, timings from the saved transcript (no new listening pass)."""
    import tempfile
    d = tempfile.mkdtemp()
    clip = os.path.join(d, "clip.mp4"); open(clip, "wb").write(b"not really a video")
    calls = os.path.join(d, "calls.txt")
    plugin = os.path.join(d, "plugin.py")
    open(plugin, "w").write(
        "import os\n"
        "def transcribe(path, language, hint, progress, cancel):\n"
        f"    open({calls!r}, 'a').write('x')\n"
        "    words, t = [], 0.5\n"
        "    for w in 'hello there friends welcome to the show today we cook pasta'.split():\n"
        "        words.append((w, t, t + 0.3, 0.9)); t += 0.35\n"
        "    return words, t + 0.5, 'en'\n")
    old_env = {k: os.environ.get(k) for k in ("SCRIPTSYNC_ASR_PLUGIN", "LOCALAPPDATA")}
    os.environ["SCRIPTSYNC_ASR_PLUGIN"] = plugin
    os.environ["LOCALAPPDATA"] = d
    try:
        script = "Hello there friends, welcome to the show. Today we cook pasta."
        s = Settings(export_words=True)
        res1 = run_job(Job(clip, script_text=script), s)
        breaks = "Hello there friends,\nwelcome to the show.\nToday we cook pasta."
        res2 = run_job(Job(clip, script_text=script, line_breaks=breaks), s)
        assert [c.text for c in res2.cues] == breaks.split("\n"), [c.text for c in res2.cues]
        assert open(calls).read() == "x", "the second run must reuse the saved transcript"
        assert os.path.exists(res2.words_json_path) and os.path.exists(res2.words_srt_path)
        assert res1.srt_path != res2.srt_path and os.path.exists(res1.srt_path), "earlier sync overwritten"
        assert os.path.basename(res2.srt_path).startswith("clip_synced_40ch_0w_30fps_")
        assert res2.report_path == res2.srt_path[:-4] + ".review.txt"
        assert "your line breaks" in res2.report_text
        try:
            run_job(Job(clip, script_text=script, line_breaks="Hello friends,\nwelcome."), s); assert False
        except SyncError as e:
            assert "don't match" in str(e)
    finally:
        for k, v in old_env.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v


def test_llm_prompt_has_rules_and_script():
    p = llm_prompt(["Hello there.", "Second line"], Settings(max_chars=32, max_words=4))
    assert "32 characters" in p and "4 words" in p and p.rstrip().endswith("Hello there.\nSecond line")
    assert "Do NOT change" in p


def test_clip_frame_rate():
    """Each clip's subtitles snap to that clip's own frame rate; audio-only clips use the default."""
    import subprocess, tempfile
    ff = find_ffmpeg()
    if not ff:
        print("skipped (no ffmpeg)"); return
    d = tempfile.mkdtemp()
    clips = {}
    for name, rate in (("a.mp4", "25"), ("b.mp4", "30000/1001"), ("c.mp4", "24000/1001")):
        clips[name] = os.path.join(d, name)
        subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s=32x32:d=1:r={rate}",
                        "-c:v", "mpeg4", clips[name]], check=True)
    wav = os.path.join(d, "voice.wav")
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "sine=duration=1", wav], check=True)
    assert detect_fps(clips["a.mp4"]) == 25.0
    assert detect_fps(clips["b.mp4"]) == 30000 / 1001
    assert detect_fps(clips["c.mp4"]) == 24000 / 1001
    assert detect_fps(wav) is None and detect_fps(os.path.join(d, "missing.mp4")) is None
    info = probe_clip(clips["a.mp4"])
    assert (info["width"], info["height"]) == (32, 32) and abs(info["duration"] - 1.0) < 0.1, info
    winfo = probe_clip(wav)
    assert winfo["fps"] is None and winfo["width"] is None and abs(winfo["duration"] - 1.0) < 0.1, winfo
    s = Settings(fps=30.0)
    assert clip_fps(Job(clips["a.mp4"]), s) == (25.0, "read from the clip")
    assert clip_fps(Job(wav), s) == (30.0, "clip has no video; default used")
    assert clip_fps(Job(clips["a.mp4"], fps=50.0), s) == (50.0, "set for this clip")
    assert clip_fps(Job(clips["a.mp4"], fps=0.0), s)[0] == 0.0
    assert clip_fps(Job(clips["a.mp4"]), Settings(fps=24.0, match_clip_fps=False))[0] == 24.0
    assert fps_name(30000 / 1001) == "29.97 fps" and fps_name(0) == "not snapped"


def test_run_job_snaps_to_the_clips_frame_rate():
    import subprocess, tempfile
    ff = find_ffmpeg()
    if not ff:
        print("skipped (no ffmpeg)"); return
    d = tempfile.mkdtemp()
    clip = os.path.join(d, "clip.mp4")
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=32x32:d=4:r=25",
                    "-c:v", "mpeg4", clip], check=True)
    plugin = os.path.join(d, "plugin.py")
    open(plugin, "w").write(
        "def transcribe(path, language, hint, progress, cancel):\n"
        "    words, t = [], 0.513\n"
        "    for w in 'one two three four five six seven eight'.split():\n"
        "        words.append((w, t, t + 0.31, 0.9)); t += 0.377\n"
        "    return words, t + 0.5, 'en'\n")
    old_env = {k: os.environ.get(k) for k in ("SCRIPTSYNC_ASR_PLUGIN", "LOCALAPPDATA")}
    os.environ["SCRIPTSYNC_ASR_PLUGIN"] = plugin
    os.environ["LOCALAPPDATA"] = d
    try:
        res = run_job(Job(clip, script_text="one two three four\nfive six seven eight"),
                      Settings(premiere_zero_fix=False))
        assert res.fps == 25.0 and "read from the clip" in res.report_text and "25 fps" in res.report_text
        for c in res.cues:
            for t in (c.start, c.end):
                assert abs(t * 25 - round(t * 25)) < 1e-6, t
    finally:
        for k, v in old_env.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v


def test_output_names():
    """Every sync gets a new name: clip + synced + max chars + max words + fps + date/time."""
    import tempfile
    when = time.mktime((2026, 11, 6, 14, 32, 5, 0, 0, -1))
    s = Settings(max_chars=32, max_words=4, fps=30000 / 1001)
    assert output_stem("/x/My Clip.mp4", s, when) == "My Clip_synced_32ch_4w_29.97fps_2026-11-06_14-32-05"
    assert output_stem("a.mov", Settings(fps=0), when).startswith("a_synced_40ch_0w_nosnap_")
    assert fps_label(25.0) == "25fps" and fps_label(24000 / 1001) == "23.976fps" and fps_label(23.5) == "23.5fps"
    d = tempfile.mkdtemp()
    open(os.path.join(d, "c_synced_x.srt"), "w").close()
    assert unique_stem(d, "c_synced_x") == "c_synced_x_2"
    assert unique_stem(d, "c_synced_y") == "c_synced_y"


def test_outputs_are_not_taken_for_scripts():
    import tempfile
    d = tempfile.mkdtemp()
    for f in ("clip.mp4", "clip_synced_40ch_0w_30fps_2026-11-06_14-32-05.srt",
              "clip_synced_40ch_0w_30fps_2026-11-06_14-32-05.review.txt", "clip.review.txt",
              "clip.synced.srt", "clip_synced_40ch_0w_30fps_2026-11-06_14-32-05.words.srt"):
        open(os.path.join(d, f), "w").close()
    assert find_script_for(os.path.join(d, "clip.mp4")) is None
    open(os.path.join(d, "clip.srt"), "w").close()          # a real (old) subtitle used as the script
    assert find_script_for(os.path.join(d, "clip.mp4")).endswith("clip.srt")


def test_logging_keeps_paths_private_and_records_steps():
    """The log must be safe to paste into a public issue: no folder names, no script text."""
    import tempfile, logging
    d = tempfile.mkdtemp()
    client = os.path.join(d, "Acme Client Videos")          # a folder name that must never reach the log
    os.makedirs(client)
    clip = os.path.join(client, "promo.mp4"); open(clip, "wb").write(b"not really a video")
    plugin = os.path.join(d, "plugin.py")
    open(plugin, "w").write(
        "def transcribe(path, language, hint, progress, cancel):\n"
        "    words, t = [], 0.5\n"
        "    for w in 'secret launch words here'.split():\n"
        "        words.append((w, t, t + 0.3, 0.9)); t += 0.35\n"
        "    return words, t + 0.5, 'en'\n")
    old_env = {k: os.environ.get(k) for k in ("SCRIPTSYNC_ASR_PLUGIN", "LOCALAPPDATA")}
    os.environ["SCRIPTSYNC_ASR_PLUGIN"] = plugin
    os.environ["LOCALAPPDATA"] = d
    try:
        path = setup_logging()
        assert path == log_path() and path.startswith(d)
        res = run_job(Job(clip, script_text="Secret launch words here."), Settings())
        try:                                              # a crash inside run_job is logged with its traceback
            run_job(Job(clip, script_text="x", out_dir=os.path.join(client, "out")), Settings(max_chars="oops"))
        except Exception:
            pass
        try:
            run_job(Job(os.path.join(client, "missing.mp4"), script_text="x"), Settings())
        except SyncError:
            pass
        logging.getLogger("scriptsync").handlers[0].flush()
        text = open(path, encoding="utf-8").read()
        print(text)
        assert "sync start: promo.mp4" in text and "step: listening took" in text and "sync done in" in text
        assert "Traceback" in text and "sync crashed" in text and "sync failed" in text
        assert "Acme Client" not in text, "a private folder name leaked into the log"
        assert "<clip folder>" in text
        assert "Secret launch" not in text and "secret launch" not in text, "script/transcript text leaked"
        home = os.path.expanduser("~")
        assert len(home) <= 3 or home not in text
        diag = diagnostics()
        assert "faster-whisper:" in diag and "Acme Client" not in diag
    finally:
        setup_logging(directory=tempfile.mkdtemp())       # detach from the temp folder
        for k, v in old_env.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v


def test_log_rotates():
    import tempfile, logging
    d = tempfile.mkdtemp()
    setup_logging(directory=d)
    lg = logging.getLogger("scriptsync")
    for i in range(30000):
        lg.info("filler line %d %s", i, "x" * 40)
    for h in lg.handlers: h.flush()
    files = sorted(os.listdir(d))
    assert files[:2] == ["scryptsink.log", "scryptsink.log.1"] and len(files) <= 1 + LOG_BACKUPS, files
    assert all(os.path.getsize(os.path.join(d, f)) <= LOG_MAX_BYTES + 200 for f in files)
    setup_logging(directory=tempfile.mkdtemp())


def test_data_folder_moves_to_new_name():
    """Renamed from Script Sync: the old ScriptSync folder (settings, transcripts, logs) moves over once."""
    import tempfile
    base = tempfile.mkdtemp()
    old = os.path.join(base, "ScriptSync"); os.makedirs(os.path.join(old, "cache"))
    open(os.path.join(old, "settings.json"), "w").write("{}")
    new = data_folder(base)
    assert new == os.path.join(base, "ScryptSink")
    assert os.path.exists(os.path.join(new, "settings.json")) and os.path.isdir(os.path.join(new, "cache"))
    assert not os.path.exists(old)
    os.makedirs(old)                                   # an old folder appearing later is left alone
    assert data_folder(base) == new and os.path.isdir(old)
    fresh = tempfile.mkdtemp()                          # nothing old: just the new name
    assert data_folder(fresh) == os.path.join(fresh, "ScryptSink")


def test_recut_from_saved_word_timings():
    """Issue #13: changing the limits re-cuts from the word timings, identical to a fresh sync with them."""
    import tempfile
    script = ("If you have been waiting for the right moment to upgrade your kitchen, this is it. "
              "Every cabinet in the showroom is on sale until the end of the month.")
    asr, _, end = speak([script])
    s40 = Settings()
    base = sync_words(parse_script(script, s40), asr, end, s40)
    base.settings = s40
    d = tempfile.mkdtemp()
    base.meta = {"video": os.path.join(d, "clip.mp4"), "label": "clip.mp4", "script_label": "x", "n_lines": 1,
                 "n_words": 10, "lang": "en", "out_dir": d, "own_line_breaks": False}
    t = time.time()
    short = recut(base, 18, 4)
    assert time.time() - t < 0.5
    fresh = sync_words(parse_script(script, Settings(max_chars=18, max_words=4)), asr, end,
                       Settings(max_chars=18, max_words=4))
    assert [(c.text, c.start, c.end) for c in short.cues] == [(c.text, c.start, c.end) for c in fresh.cues]
    assert all(len(c.text) <= 18 or len(c.text.split()) == 1 for c in short.cues)
    assert len(base.cues) < len(short.cues) and base.settings.max_chars == 40, "the original is untouched"
    write_result(short)
    assert os.path.basename(short.srt_path).startswith("clip_synced_18ch_4w_") and os.path.exists(short.srt_path)
    assert os.path.exists(short.report_path) and short.srt_text == open(short.srt_path, encoding="utf-8", newline="").read()


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


def test_missing_package_resets_launcher_setup():
    """#12: if a package is missing, the launcher's setup marker goes so the next launch repairs it."""
    import tempfile
    d = tempfile.mkdtemp()
    mark = os.path.join(d, SETUP_MARKER)
    open(mark, "w").close()
    old = sys.prefix, sys.base_prefix
    try:
        sys.prefix, sys.base_prefix = d, d          # not in a venv: leave everything alone
        _forget_setup()
        assert os.path.exists(mark)
        sys.base_prefix = old[1]                    # in the launcher's venv: marker removed
        _forget_setup()
        assert not os.path.exists(mark)
        _forget_setup()                             # already gone: no error
    finally:
        sys.prefix, sys.base_prefix = old


def test_launchers_accept_the_supported_pythons():
    """Both launchers try exactly PYTHON_MIN..PYTHON_MAX, newest first, and check that same range."""
    import re
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    want = [f"3.{m}" for m in range(PYTHON_MAX[1], PYTHON_MIN[1] - 1, -1)]
    rng = f"({PYTHON_MIN[0]},{PYTHON_MIN[1]}) <= sys.version_info[:2] <= ({PYTHON_MAX[0]},{PYTHON_MAX[1]})"
    bat = open(os.path.join(root, "run_windows.bat"), encoding="utf-8").read()
    mac = open(os.path.join(root, "run_mac.command"), encoding="utf-8").read()
    assert re.search(r"for %%V in \(([\d. ]+)\) do", bat).group(1).split() == want, "run_windows.bat"
    assert re.search(r"for p in ((?:python3\.\d+ )+)python3; do", mac).group(1).split() == \
        ["python" + v for v in want], "run_mac.command"
    for name, text in (("run_windows.bat", bat), ("run_mac.command", mac)):
        assert rng in text, f"{name} doesn't check {rng}"
        assert f"Python 3.{PYTHON_MIN[1]} to 3.{PYTHON_MAX[1]}" in text, f"{name} message names another range"
    assert "\r\n" in open(os.path.join(root, "run_windows.bat"), "rb").read().decode(), "bat must stay CRLF"


def test_no_word_alone_on_its_line():
    """'This is our best | effort.' reads worse than 'This is our | best effort.' (Short-form: 18 chars, 4 words).
    A one-word sentence ('Yes.') may still stand alone."""
    from types import SimpleNamespace
    from scriptsync_core import _split_words

    def cut(text):
        t, ws = 0.0, []
        for w in text.split():
            d = 0.12 + 0.05 * len(w)
            ws.append(SimpleNamespace(text=w, start=t, end=t + d))
            t += d + 0.06
        return [" ".join(w.text for w in chunk) for chunk in _split_words(ws, Settings(max_chars=18, max_words=4))]

    assert cut("This is our best effort.") == ["This is our", "best effort."], cut("This is our best effort.")
    got = cut("Yes. This is our best effort.")
    assert got[0] == "Yes." and all(len(c.split()) > 1 for c in got[1:]), got


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            print("---", n); f()
    print("ALL OK")
