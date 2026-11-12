# scryptsink

**ScryptSink** (formerly Script Sync): give it a clip and the writer's script, get back a timed subtitle file (`.srt`) whose text is
**the script exactly as written** and whose timing comes from the **actual audio**.

No copy-pasting a transcript line by line. No auto-transcript to patch up. No dependence on any one editor:
the output is a plain SRT that Premiere Pro, DaVinci Resolve, Final Cut, CapCut and others can import.

**[Download the latest release](https://github.com/wishym1shy/scryptsink/releases/latest)** (Windows and macOS), then see
[Install and run](#install-and-run).

> Status: early. The matching engine is tested against simulated speech-recognition mistakes; the real
> speech-model path (`faster-whisper`) has had little testing on real footage so far. Please open an issue with anything odd.

## Why

When a writer supplies the script and an editor receives pre-cut footage, subtitles end up being synced by hand,
or by generating an auto-transcript and pasting the script into it. Both are slow, and the auto-transcript's
spelling still has to be fixed.

ScryptSink treats it as an alignment problem instead: the speech model only supplies *when* each word was said.
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

**Python 3.14** from [python.org](https://www.python.org/downloads/) (any version from 3.9 to 3.14 works). On
Windows, tick **"Add python.exe to PATH"** on the first installer screen.

Don't pick a newer Python than 3.14 yet: part of the speech engine isn't available for it, so setup can't
finish. The big download button on python.org may offer a newer one; scroll down to **Looking for a specific
release?** and choose the newest 3.14. Already have a newer Python? Keep it and install 3.14 next to it; the
launcher picks the one that works.

### 2. Download ScryptSink

1. Go to the **[latest release](https://github.com/wishym1shy/scryptsink/releases/latest)** and, under
   **Assets**, download **`ScryptSink-<version>.zip`** (not "Source code").
2. Extract the ZIP. On Windows: right-click it, **Extract All**. Don't run the launcher from inside the
   zip preview, it won't work.
3. Move the extracted folder somewhere permanent (for example `Documents\ScryptSink`). The first launch
   creates a `.venv` folder inside it, so don't put it somewhere temporary or read-only.

You should end up with a folder like this (the launchers must stay beside the `.py` files, so don't move
`run_windows.bat` out on its own):

```
ScryptSink-0.1.1/
  run_windows.bat
  run_mac.command
  scriptsync_core.py
  scriptsync_gui.py
  requirements.txt
  README.md
  LICENSE
```

**Updating to a new version:** download the new release's ZIP and extract it as a new folder. Its first
launch runs setup again (a few minutes). Your settings, transcript cache and downloaded speech models are
kept outside the folder, so nothing is lost; once the new version works, delete the old folder.

Want the latest unreleased changes instead? Use the green **Code** button > **Download ZIP**, or
`git clone https://github.com/wishym1shy/scryptsink`. These may include work that hasn't been tested as
much as a release.

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
   (`clip.mp4` + `clip.docx` / `.txt` / `.md` / `.srt`) is paired automatically. Otherwise **double-click the
   clip** (or **Edit or replace…** in the panel on the right) to paste its script, or use
   **Import .txt / .srt instead…** in that window to pick a file.
2. Press **Sync** (all clips) or **Sync this clip** in the panel. The panel shows the selected clip's script,
   frame rate, its last subtitle file and the result.
3. Next to each clip (or in the folder you pick) you get a subtitle file and its review sheet, named after the
   clip and the settings used, plus the date and time of the sync:
   - `clipname_synced_40ch_0w_30fps_2026-11-06_14-32-05.srt`
   - `clipname_synced_40ch_0w_30fps_2026-11-06_14-32-05.review.txt`

   `40ch` = max characters per subtitle, `0w` = max words (0 = no limit), `30fps` = the frame rate the times
   were snapped to (`nosnap` = off). Every sync makes new files, so earlier versions are never overwritten:
   sync again with different settings and compare.
4. The Review panel colours each subtitle: green OK, amber CHECK, red BAD, with a note on what to look at.

The **status bar** at the bottom always says what the app is doing: Standing by (yellow), Clips loaded / Ready
(orange), Running with a timer, then Finished in m:ss (green), or Stopped / Error (red; click **Details…** for what
went wrong). **Ctrl+Enter** starts a sync.

**Night mode:** the sun/moon button at the top right switches between light and night. Until you use it, the app
follows your system's light/dark setting.

An existing `.srt` also works as the script: only its text is used and the timing is redone from the footage,
which helps when footage was re-cut after the SRT was made.

### What the flags mean

| Flag | Meaning |
|---|---|
| OK | Words were heard where the script puts them. |
| CHECK | Some words not heard or heard differently (the note says which). Timing is usually fine; confirm text and sync. |
| BAD | Most of the line wasn't found; its timing is a guess. Check by ear. |

### Subtitle style

Pick a preset:

| Preset | Max characters | Max words | On screen |
|---|---|---|---|
| **Short-form** (Reels, Shorts, TikTok) | 18 | 4 | 0.8–5 s |
| **Standard** (default) | 40 | any | 0.8–5 s |
| **Long-form** (interviews, YouTube) | 42 | any | 0.8–7 s |
| **Custom** | your own | your own | your own |

**Custom** shows every value, grouped as Listening, Subtitle shape and Output. Picking a preset again only changes
Subtitle shape.

- **Listening** - quality base / small (default) / medium / large-v3-turbo (use a bigger one for noisy audio), and
  language: auto-detect, English, Tagalog/Filipino, Spanish.
- **Frame rate** (per clip, in the clip panel) - subtitle times are snapped to whole frames of each clip's own
  frame rate, read from the video. Pick a rate to override it, or **Don't snap**. Audio-only clips use the default
  under More options (30). Subtitles in continuous speech always touch, so they never blink.
- **More options…** (a separate window) - ignore `[bracketed notes]`, strip `Name:` speaker labels, keep or re-flow
  the writer's line breaks, name hints for the listener, a Premiere fix (Premiere can drop a first cue that starts
  at exactly `00:00:00,000`, so it starts at `00:00:00,067`), include never-heard lines, word timings, transcript
  re-use, the speech model folder, and Troubleshooting.

Styling (font, size, position, colours) is done in your editor; the SRT carries text and timing only.

### Re-cut after syncing

Above the subtitle list, drag **Max characters** (or change **Max words**): the subtitles re-cut instantly from the
word timings found during the sync, with no listening again. Changed subtitles are marked ✎. **Save as new .srt**
writes it next to the earlier version (the name says the new limits); **Undo** goes back to the saved cut.

### Your own line breaks (by hand or with an AI tool)

Prefer to decide the breaks yourself? After a sync, select the clip and choose **More > Apply my own line breaks…**. The window
opens with the current subtitles, one per line: move the line breaks, press **Use this script**, and the clip is
re-timed straight away from its saved transcript (no new listening pass). Leave the window empty to go back to
automatic cuts.

To have an AI tool do it, choose **More > Copy AI prompt**, paste it into the AI tool you already use, copy its answer and
paste that into **Apply my own line breaks…**.

**ScryptSink never calls an AI service itself and has no place for an API key.** Everything it does runs on your
machine; the AI step, if you want one, happens in your own tool, and ScryptSink only reads the text you paste back.
AI tools sometimes "tidy up" wording, so ScryptSink checks that every word and punctuation mark is exactly as in
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
`%LOCALAPPDATA%\ScryptSink\cache` (Windows) or `~/.cache/ScryptSink/cache` so re-syncing an edited script is instant.
An NVIDIA GPU is used automatically when available, otherwise the CPU (a 60 s clip takes very roughly 15-40 s
on the default model).

## Troubleshooting

ScryptSink keeps a log of what it does (app version, settings used, how long each step took, which device the
speech model ran on, and the full details of any error). It stays on your computer:

- Windows: `%LOCALAPPDATA%\ScryptSink\logs\scryptsink.log`
- macOS / Linux: `~/.cache/ScryptSink/logs/scryptsink.log`

It is capped at about 5 MB (older entries are dropped). In the app: **More options > Troubleshooting**:
**Open log folder**, or **Copy diagnostic info** to put the version, system details and the end of the log on the
clipboard for a bug report. Folder paths are replaced by placeholders such as `<clip folder>` and `<home>`, and the
log never contains your script or subtitle text; clip file names are included, so read it before posting it publicly.
On the command line, add `-v` to also print the log to the terminal.

## Limitations

- Numbers said differently from how they're written ("2025" vs "twenty twenty five") show up as CHECK.
- Overlapping speakers are flagged rather than separated; there is no per-speaker colouring.
- Cue cutting is rule-based: it can't tell an adjective from a noun, so it may still split something like
  "last | year" when a line has to be cut and there is no better place. Fix those by re-cutting, or with **More > Apply my own line breaks…**.
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

Every pull request is checked automatically (**Actions > CI**): the unit tests, the timing-accuracy and cut-quality
checks on Windows, macOS and Linux with Python 3.9 and 3.14, a Python 3.9 compatibility check, a check that the
requirements install on every supported Python (3.9 to 3.14), and a GUI smoke test.

### Releases (maintainer)

Releases are **manual**, so one version can bundle any number of merged fixes and features:

1. Bump `APP_VERSION` in `scriptsync_core.py` in a pull request, and merge it.
2. **Actions > Release > Run workflow**, enter the same version (e.g. `0.2.0`).
3. It checks the version, runs the tests again, and creates a **draft** release `v0.2.0` with a ready-to-download
   `ScryptSink-0.2.0.zip` and notes listing every pull request merged since the last release, grouped by label
   (`enhancement` = New features, `bug` = Fixes, `documentation`).
4. Read the draft on the Releases page, edit the notes if you like, and press **Publish**.

## License

[MIT](LICENSE) &copy; 2026 wishym1shy
