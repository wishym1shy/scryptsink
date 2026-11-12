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

ScryptSink (formerly "Script Sync") takes a clip and the writer's script and produces a timed `.srt` whose text is the script,
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
4. The script's own line breaks become cues; long lines are cut where a speaker would breathe (sentence end,
   clause punctuation, audio pause, never between words that belong together, never a word alone on its line
   unless it is a whole sentence). The weights are the `COST_*` constants; `tests/cuts.py` measures the result for the
   Short-form shape (18 characters, 4 words) and at 32/40 characters, and CI holds it to its `LIMITS`.
   Users can also supply their own line breaks (by hand or from an outside AI tool); they're checked word-for-word
   against the script. The app never calls an AI service or stores an API key.
5. Confidence per cue -> OK / CHECK / BAD, written to a review file.

Design rules that should not regress:

- Subtitle **text is always the writer's script**, never the model's transcript.
- Script text that was never heard is **left out of the SRT but listed in the review report**; nothing disappears silently.
- Speech that is not in the script is reported, not subtitled.
- Python 3.9+ compatible; the GUI must work with the stock Windows python.org install (tkinter included).
- The launchers only accept Python `PYTHON_MIN`..`PYTHON_MAX` (`scriptsync_core.py`): the versions the speech
  engine's dependencies have ready-made packages for. To change the range, update the constant, both launchers
  and the README together; `tests/test_core.py` checks they agree, and CI's "Installs on every supported Python"
  job checks the range really installs (and says when the next Python does).

## Testing

```
python tests/test_core.py     # unit tests, no model or audio needed
python tests/stress.py        # simulated speech-model errors vs ground-truth timing
python tests/cuts.py          # cue-cut quality (lower is better)
```

Before opening a PR, run all three. Currently the stress test reports a median word-timing error of
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

- One focused change per PR, descriptive PR title and body (what, why, how tested).
- **Every new branch is created from the latest `main`, and every PR targets `main`.** Fetch first
  (`git fetch origin main && git checkout -b <branch> origin/main`). Never branch from another feature
  branch and never open a PR whose base is anything other than `main`. No stacked PRs: a PR merged into a
  non-`main` base never reaches `main` (this happened with #10 and #11).
- If two open PRs touch the same lines, keep them independent anyway. After the owner merges one, update
  the other branch by merging `origin/main` into it (not rebasing, which would need a force-push) and fix
  any conflicts there, so the owner never has to.
- **CI must pass** (Actions > CI: tests on Windows/macOS/Linux, Python 3.9 + 3.14, 3.9 compatibility, installs on every supported Python, GUI smoke
  test). If a check fails, fix it with follow-up commits on the same branch; never weaken a check or its limits to
  make a PR pass without saying so and why in the PR.
- Label PRs `enhancement`, `bug` or `documentation`: release notes are grouped by these labels.
- **Releases are manual and the owner's decision.** Agents never run the Release workflow, create tags or
  releases, or publish a draft. Bumping `APP_VERSION` is a normal PR, made only when the owner asks.
- Do not add a dependency without saying why in the PR.
- Never leave test media or generated `.srt` files in the tree (`.gitignore` covers them).
