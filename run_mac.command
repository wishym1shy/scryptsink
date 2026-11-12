#!/bin/bash
cd "$(dirname "$0")"
# Setup counts as finished only when this marker exists. It is written last, after the install
# worked, and holds a copy of requirements.txt, so an updated app re-runs the install too (#12).
MARK=.venv/setup-complete.txt

fail() { echo; echo "Setup did not finish. Check the internet connection and open this file again;"
         echo "it picks up where it stopped."; read -p "Press Enter"; exit 1; }

# Python versions ScryptSync can install on. Keep in step with PYTHON_MIN/PYTHON_MAX in scriptsync_core.py.
PYOK='import sys; sys.exit(not (3,9) <= sys.version_info[:2] <= (3,14))'
# The window needs Tk 8.6 or newer. Apple's own python3 (from the Xcode command line tools) only has the old,
# deprecated Tk 8.5 and the app can't start with it, so it is skipped; python.org's installer brings its own Tk.
TKOK='import sys, tkinter; sys.exit(tkinter.TkVersion < 8.6)'
usable() { "$1" -c "$PYOK" 2>/dev/null && "$1" -c "$TKOK" 2>/dev/null; }

# python.org installs into /Library/Frameworks; make sure those are found even if the Terminal's PATH lacks them.
for d in /Library/Frameworks/Python.framework/Versions/3.*/bin; do
  [ -d "$d" ] && PATH="$PATH:$d"
done

no_python() {
  echo
  if command -v python3 >/dev/null 2>&1 && python3 -c "$PYOK" 2>/dev/null; then
    echo "The Python on this Mac ($(python3 -c 'import platform; print(platform.python_version())' 2>/dev/null)) can't show ScryptSync's window:"
    echo "its window toolkit (Tk) is missing or too old. Apple's built-in Python has this problem."
    echo "Install Python 3.14 from https://www.python.org/downloads/ (you can keep the other version),"
    echo "then open this file again."
  elif command -v python3 >/dev/null 2>&1; then
    echo "ScryptSync can't use the Python on this Mac ($(python3 -c 'import platform; print(platform.python_version())' 2>/dev/null)):"
    echo "part of the speech engine isn't available for that version yet. ScryptSync works with Python 3.9 to 3.14."
    echo "Install Python 3.14 from https://www.python.org/downloads/ (under \"Looking for a specific release?\";"
    echo "you can keep the other version), then open this file again."
  else
    echo "Python is not installed yet. Install Python 3.14 from https://www.python.org/downloads/,"
    echo "then open this file again."
  fi
  read -p "Press Enter"; exit 1
}

fresh_venv() {
  rm -rf .venv
  # Newest supported Python first, so a Mac with several versions uses one that works.
  PY=""
  for p in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$p" >/dev/null 2>&1 && usable "$p"; then PY="$p"; break; fi
  done
  [ -n "$PY" ] || no_python
  echo "Using Python $("$PY" -c 'import platform; print(platform.python_version())') ($(command -v "$PY"))"
  "$PY" -m venv .venv || fail
}

install() {
  .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -r requirements.txt || fail
  .venv/bin/python -c "import faster_whisper, imageio_ffmpeg" 2>/dev/null
}

# Also redo setup if the .venv was built on a Python that can't run the app (e.g. Apple's built-in one).
if [ ! -x .venv/bin/python ] || ! cmp -s "$MARK" requirements.txt || ! usable .venv/bin/python; then
  if [ -d .venv ]; then
    echo "Setup didn't finish last time, or ScryptSync was updated. Finishing it now..."
  else
    echo "First-time setup (a few minutes, needs internet)..."
  fi
  echo "Please keep this window open until ScryptSync opens."
  rm -f "$MARK"
  # Reuse a .venv whose Python works and can run the app (saves re-downloading); otherwise start again.
  usable .venv/bin/python || fresh_venv
  if ! install; then
    # Installed but won't import (an earlier install was cut off half-way): rebuild once from scratch.
    echo "Some parts of the last setup were incomplete. Starting setup again from scratch..."
    fresh_venv
    install || fail
  fi
  cp requirements.txt "$MARK" || fail
fi
.venv/bin/python scriptsync_gui.py || {
  echo
  echo "ScryptSync closed because of an error (details above, and in the log:"
  echo "~/.cache/ScryptSync/logs/scryptsync.log). Please report it with that log."
  read -p "Press Enter"; exit 1
}
