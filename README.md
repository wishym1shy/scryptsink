# scryptsink

**Script Sync**: give it a clip and the writer's script, get back a timed subtitle file (`.srt`) whose text is
**the script exactly as written** and whose timing comes from the **actual audio**.

No copy-pasting a transcript line by line. No auto-transcript to patch up. No dependence on any one editor:
the output is a plain SRT that Premiere Pro, DaVinci Resolve, Final Cut, CapCut and others can import.

> Status: early. The matching engine is tested against simulated speech-recognition mistakes; the real
> speech-model path (`faster-whisper`) has had little testing on real footage so far. Please open an issue with anything odd.

## Why

When a writer supplies the script and an editor receives pre-cut footage, subtitles end up being synced by hand,
or by generating an auto-transcript and pasting the script into it. Both are slow, and the auto-transcript's
spelling still has to be fixed.

Script Sync treats it as an alignment problem instead: the speech model only supplies *when* each word was said.
The *words* always come from the script.

## How it works

1. **Listen** - a speech model ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)) transcribes the clip
   with a timestamp per word. Its spelling doesn't matter.
2. **Match** - script words are aligned to spoken words using exact-match anchors, then a sequence alignment
   (Needleman-Wunsch) in the gaps. It tolerates mis-hearings, skipped words and ad-libs, and speaks out numbers
   (`$25,000` matches "twenty five thousand dollars").
3. **Time** - each script word takes the timestamp of the spoken word it matched. Words never heard are
   interpolated and flagged.
4. **Cue** - the script's own line breaks become subtitle cues, split further at pauses/punctuation when too long.
5. **Flag** - every cue is graded **OK / CHECK / BAD**, and a review sheet lists what to look at.

Nothing is dropped silently:

- Script text that was **never heard** is left out of the SRT but listed in the review sheet.
- Speech that is **not in the script** (ad-libs, extra takes) is listed, not subtitled.
- If under 40% of the script is found in the audio you get a warning (wrong script? wrong language? loud music?).

## Install and run

Needs Python 3.9+ ([python.org](https://www.python.org/downloads/); on Windows tick "Add python.exe to PATH").

| System | Start |
|---|---|
| Windows | double-click `run_windows.bat` |
| macOS | double-click `run_mac.command` (first time: right-click, Open) |

The first launch creates a virtual environment and installs `requirements.txt` (a few minutes, needs internet).
The first sync downloads the speech model once (about 460 MB for the default "Balanced" size).

Manual install, if you prefer:

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip
.venv/bin/python scriptsync_gui.py
```

## Using the app

1. **Add clips** or **Add a folder**. A script next to its clip with the same name
   (`clip.mp4` + `clip.docx` / `.txt` / `.md` / `.srt`) is paired automatically; otherwise select the row and
   **Choose script file** or **Paste script**.
2. Press **Sync**.
3. Next to each clip (or in the folder you pick) you get:
   - `clipname.synced.srt`
   - `clipname.review.txt`
4. The Review panel colours each subtitle: green OK, amber CHECK, red BAD, with a note on what to look at.

An existing `.srt` also works as the script: only its text is used and the timing is redone from the footage,
which helps when footage was re-cut after the SRT was made.

### What the flags mean

| Flag | Meaning |
|---|---|
| OK | Words were heard where the script puts them. |
| CHECK | Some words not heard or heard differently (the note says which). Timing is usually fine; confirm text and sync. |
| BAD | Most of the line wasn't found; its timing is a guess. Check by ear. |

### Settings

- **Listening quality** - base / small (default) / medium / large-v3-turbo. Use a bigger one for noisy audio.
- **Language** - auto-detect, English, Tagalog/Filipino, Spanish.
- **Max characters per subtitle** - default 40; set it to match your caption style.
- **More options** - ignore `[bracketed notes]`, strip `Name:` speaker labels, keep or re-flow the writer's line
  breaks, shortest/longest subtitle, hold subtitles through short pauses, include never-heard lines, and a Premiere
  fix (Premiere can drop a first cue that starts at exactly `00:00:00,000`, so it starts at `00:00:00,067`).

Styling (font, size, position, colours) is done in your editor; the SRT carries text and timing only.

## Command line

```
python scriptsync_core.py clip.mp4 script.docx -o out_folder --model small --max-chars 40
```

Everything runs locally; clips and scripts never leave your machine. Transcripts are cached in
`%LOCALAPPDATA%\ScriptSync\cache` (Windows) or `~/.cache/ScriptSync/cache` so re-syncing an edited script is instant.
An NVIDIA GPU is used automatically when available, otherwise the CPU (a 60 s clip takes very roughly 15-40 s
on the default model).

## Limitations

- Numbers said differently from how they're written ("2025" vs "twenty twenty five") show up as CHECK.
- Overlapping speakers are flagged rather than separated; there is no per-speaker colouring.
- The cue-splitting defaults are guesses; tune them for your style.
- Not yet tested across many accents, noisy footage or long-form content.

## Development

```
python tests/test_core.py     # unit tests; no model or audio needed
python tests/stress.py        # simulated speech-model errors vs ground-truth timing
```

The engine (`scriptsync_core.py`) uses only the standard library for matching and cue building, so it can be
tested without a speech model. On simulated 8% mis-hearings and 4% dropped words the median word-timing error
is about 30 ms. See [`CLAUDE.md`](CLAUDE.md) for contributor and AI-agent rules.

### Contributing

All changes go through pull requests, and **every PR is reviewed and merged by the repository owner by hand**.
Please don't expect (or script) automated merging.

## License

[MIT](LICENSE) &copy; 2026 wishym1shy
