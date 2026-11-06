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
4. **Cue** - the script's own line breaks become subtitle cues. Lines that are too long are cut where a speaker
   would breathe: after a sentence (two sentences never share a cue if it can be avoided), then after a comma or
   other clause punctuation, then at real pauses in the audio. Words that belong together ("the car",
   "in the morning", "will be", "25 percent", names) are kept together, and one-word cues are avoided.
5. **Flag** - every cue is graded **OK / CHECK / BAD**, and a review sheet lists what to look at.

Nothing is dropped silently:

- Script text that was **never heard** is left out of the SRT but listed in the review sheet.
- Speech that is **not in the script** (ad-libs, extra takes) is listed, not subtitled.
- If under 40% of the script is found in the audio you get a warning (wrong script? wrong language? loud music?).

## Install and run

### 1. Install Python (once)

Python 3.9 or newer from [python.org](https://www.python.org/downloads/). On Windows, tick
**"Add python.exe to PATH"** on the first installer screen.

### 2. Download the whole project

The launcher needs the other files in this repo next to it (`scriptsync_core.py`, `scriptsync_gui.py`
and `requirements.txt`), so don't download `run_windows.bat` on its own.

1. On the repo page click the green **Code** button, then **Download ZIP**.
2. Extract the ZIP. On Windows: right-click it, **Extract All**. Don't run the launcher from inside the
   zip preview, it won't work.
3. Move the extracted folder somewhere permanent (for example `Documents\scryptsink`). The first launch
   creates a `.venv` folder inside it, so don't put it somewhere temporary or read-only.

Or, if you use git: `git clone https://github.com/wishym1shy/scryptsink`

You should end up with a folder like this (the launchers must stay beside the `.py` files):

```
scryptsink/
  run_windows.bat
  run_mac.command
  scriptsync_core.py
  scriptsync_gui.py
  requirements.txt
  ...
```

### 3. Start it

| System | Start |
|---|---|
| Windows | open the folder and double-click `run_windows.bat` |
| macOS | open the folder and double-click `run_mac.command` (first time: right-click, Open) |

The first launch creates a virtual environment and installs `requirements.txt` (a few minutes, needs internet).
After that it opens in seconds. The first sync downloads the speech model once (about 460 MB for the
default "Balanced" size).

Windows may show a SmartScreen warning for the `.bat` file because it was downloaded from the internet.
Choose **More info**, then **Run anyway** if you trust the source (you can read the file first; it is short).

**Where things are installed.** The app itself (and its `.venv`) lives in the folder you extracted. Speech models
go to the shared Hugging Face cache by default (`%USERPROFILE%\.cache\huggingface\hub` on Windows,
`~/.cache/huggingface/hub` on macOS). To keep them somewhere else, for example a bigger drive, set
**More options > Speech model folder** before your first sync (or `--model-dir` / the `SCRIPTSYNC_MODEL_DIR`
environment variable on the command line). Changing it later downloads the model again into the new folder.

### Manual install (optional)

From inside the project folder:

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip
.venv/bin/python scriptsync_gui.py            # Windows: .venv\Scripts\python scriptsync_gui.py
```

## Using the app

1. **Add clips** or **Add a folder**. A script next to its clip with the same name
   (`clip.mp4` + `clip.docx` / `.txt` / `.md` / `.srt`) is paired automatically; otherwise select the row and
   **Choose script file** or **Paste script**.
2. Press **Sync**.
3. Next to each clip (or in the folder you pick) you get a subtitle file and its review sheet, named after the
   clip and the settings used, plus the date and time of the sync:
   - `clipname_synced_40ch_0w_30fps_2026-11-06_14-32-05.srt`
   - `clipname_synced_40ch_0w_30fps_2026-11-06_14-32-05.review.txt`

   `40ch` = max characters per subtitle, `0w` = max words (0 = no limit), `30fps` = the frame rate the times
   were snapped to (`nosnap` = off). Every sync makes new files, so earlier versions are never overwritten:
   sync again with different settings and compare.
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
- **Max characters** per subtitle - default 40; set it to match your caption style.
- **Max words** per subtitle - 0 = no limit. Short-form video often looks best with 2-4.
- **Frame rate** (per clip, in the clip toolbar) - subtitle times are snapped to whole frames of each clip's own
  frame rate, read from the video (shown in the **Frame rate** column). Select a clip and pick a rate to override it,
  or **Don't snap**. Audio-only clips use the default under More options (30). Subtitles in continuous speech always
  touch, so they never blink.
- **More options** - ignore `[bracketed notes]`, strip `Name:` speaker labels, keep or re-flow the writer's line
  breaks, shortest/longest subtitle, hold subtitles through short pauses, include never-heard lines, the frame rate
  for audio-only clips, and a Premiere fix (Premiere can drop a first cue that starts at exactly `00:00:00,000`, so
  it starts at `00:00:00,067`).

Styling (font, size, position, colours) is done in your editor; the SRT carries text and timing only.

### Your own line breaks (by hand or with an AI tool)

Prefer to decide the breaks yourself? After a sync, select the clip and click **Apply line breaks…**. The window
opens with the current subtitles, one per line: move the line breaks, press **Use this script**, and the clip is
re-timed straight away from its saved transcript (no new listening pass). Leave the window empty to go back to
automatic cuts.

To have an AI tool do it, click **Copy AI prompt**, paste it into the AI tool you already use, copy its answer and
paste that into **Apply line breaks…**.

**Script Sync never calls an AI service itself and has no place for an API key.** Everything it does runs on your
machine; the AI step, if you want one, happens in your own tool, and Script Sync only reads the text you paste back.
AI tools sometimes "tidy up" wording, so Script Sync checks that every word and punctuation mark is exactly as in
the script and refuses the line breaks otherwise, listing each word that was changed, added or dropped.

### Word timings for other tools

Tick **More options > Also save every word's timing** to also get:

- `<same name as the .srt>.words.json` - every script word with `word`, `start`, `end` (seconds), `confidence`, `heard`,
  `heard_as` and `line`;
- `<same name as the .srt>.words.srt` - one word per subtitle.

## Command line

```
python scriptsync_core.py clip.mp4 script.docx -o out_folder --model small --max-chars 40
```

More options: `--fps 25` (frame rate to snap to; default `auto` = the clip's own, `0` = don't snap), `--max-words 4`, `--words` (also write the word-timing files), `--print-prompt` (print the AI-tool
prompt for this script and exit) and `--line-breaks recut.txt` (use your own line breaks; checked against the script).

Everything runs locally; clips and scripts never leave your machine. Transcripts are cached in
`%LOCALAPPDATA%\ScriptSync\cache` (Windows) or `~/.cache/ScriptSync/cache` so re-syncing an edited script is instant.
An NVIDIA GPU is used automatically when available, otherwise the CPU (a 60 s clip takes very roughly 15-40 s
on the default model).

## Limitations

- Numbers said differently from how they're written ("2025" vs "twenty twenty five") show up as CHECK.
- Overlapping speakers are flagged rather than separated; there is no per-speaker colouring.
- Cue cutting is rule-based: it can't tell an adjective from a noun, so it may still split something like
  "last | year" when a line has to be cut and there is no better place. Fix those with **Apply line breaks…**.
- Not yet tested across many accents, noisy footage or long-form content.

## Development

```
python tests/test_core.py     # unit tests; no model or audio needed
python tests/stress.py        # simulated speech-model errors vs ground-truth timing
python tests/cuts.py          # cue-cut quality on sample scripts (sentence joins, split phrases, lone words)
```

The engine (`scriptsync_core.py`) uses only the standard library for matching and cue building, so it can be
tested without a speech model. On simulated 8% mis-hearings and 4% dropped words the median word-timing error
is about 30 ms. See [`CLAUDE.md`](CLAUDE.md) for contributor and AI-agent rules.

### Contributing

All changes go through pull requests, and **every PR is reviewed and merged by the repository owner by hand**.
Please don't expect (or script) automated merging.

## License

[MIT](LICENSE) &copy; 2026 wishym1shy
