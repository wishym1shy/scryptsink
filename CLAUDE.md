# CLAUDE.md

Instructions for AI agents (Claude Code and others) working in this repository.

## Hard rule: agents never merge pull requests

**Agents must not merge pull requests. Ever.** Every PR must be reviewed and approved by hand by the
repository owner (`wishym1shy`) before it is merged, and the owner performs the merge.

This means an agent must NOT:

- run `gh pr merge`, call the merge API, or click/script any "Merge" button, in any merge mode
  (merge commit, squash, rebase);
- enable auto-merge, add the PR to a merge queue, or use `--admin` / branch-protection bypasses;
- push directly to `main`, or force-push to any shared branch;
- approve its own PR, or approve PRs on the owner's behalf;
- merge a branch into `main` locally and push the result;
- dismiss or resolve review comments just to get a PR through.

What an agent does instead: work on a feature branch, open a PR, report the PR link, and **stop**.
If review feedback arrives, push follow-up commits to the same branch. Merging is the owner's decision,
even when CI is green, the change is tiny, or the owner said "looks good" earlier in a chat: only the
owner's own approval on the PR counts.

If a task seems to require merging, stop and ask the owner. Do not look for a workaround.

## Public repository hygiene

This repository is public. Never commit:

- real names, employers, client or company names, or anything that identifies them;
- footage, audio, subtitles from real projects, or test media (generate synthetic clips instead);
- API keys, tokens, `.env` files, speech-model weights, or personal file paths.

Keep wording in docs, comments and test data generic.

## What this project is

Script Sync takes a clip and the writer's script and produces a timed `.srt` whose text is the script,
exactly as written, with timing taken from the audio. Desktop GUI (tkinter) plus a command line.

- `scriptsync_core.py` - engine. Standard library only for matching/cue building; the speech model
  (`faster-whisper`) is imported lazily. Also holds the CLI (`python scriptsync_core.py clip script`).
- `scriptsync_gui.py` - tkinter app. Must stay usable by non-technical users: no command line needed.
- `run_windows.bat`, `run_mac.command` - first-run setup (venv + requirements) and launch.
- `tests/` - unit tests, a simulated-mistakes accuracy test, and GUI/pipeline smoke helpers.

## How it works (keep in mind when changing it)

1. Transcribe with word timestamps (spelling of the transcript is irrelevant).
2. Align script tokens to spoken tokens: exact-match anchors first, then Needleman-Wunsch in the gaps.
   Numbers are spoken out ("$25,000" -> twenty five thousand dollars) on both sides before matching.
3. Each script word inherits the time of the spoken word it matched. Unheard words are interpolated and flagged.
4. The script's own line breaks become cues; long lines are split at pauses/punctuation.
5. Confidence per cue -> OK / CHECK / BAD, written to a review file.

Design rules that should not regress:

- Subtitle **text is always the writer's script**, never the model's transcript.
- Script text that was never heard is **left out of the SRT but listed in the review report**; nothing disappears silently.
- Speech that is not in the script is reported, not subtitled.
- Python 3.9+ compatible; the GUI must work with the stock Windows python.org install (tkinter included).

## Testing

```
python tests/test_core.py     # unit tests, no model or audio needed
python tests/stress.py        # simulated speech-model errors vs ground-truth timing
```

Before opening a PR, run both. Currently the stress test reports a median word-timing error of
about 30 ms and well under 1% of words more than 1 s off; a change that makes this noticeably worse
needs a reason in the PR description.

GUI smoke test (Linux, needs `xvfb`, `python3-tk` and `ffmpeg`/`espeak-ng` to make a test clip):

```
python tests/make_test_clip.py /tmp/ss_test
SCRIPTSYNC_ASR_PLUGIN=tests/fake_plugin.py xvfb-run -a python tests/gui_smoke.py /tmp/ss_test /tmp/ss.png
```

`SCRIPTSYNC_ASR_PLUGIN=<file.py>` swaps the speech model for a stand-in that defines
`transcribe(path, language, hint, progress, cancel)`. This is for tests only.

## Workflow

- Branch from `main`, one focused change per PR, descriptive PR title and body (what, why, how tested).
- Do not add a dependency without saying why in the PR.
- Never leave test media or generated `.srt` files in the tree (`.gitignore` covers them).
