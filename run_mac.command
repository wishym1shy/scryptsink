#!/bin/bash
cd "$(dirname "$0")"
# Setup counts as finished only when this marker exists. It is written last, after the install
# worked, and holds a copy of requirements.txt, so an updated app re-runs the install too (#12).
MARK=.venv/setup-complete.txt

fail() { echo; echo "Setup did not finish. Check the internet connection and open this file again;"
         echo "it picks up where it stopped."; read -p "Press Enter"; exit 1; }

fresh_venv() {
  rm -rf .venv
  python3 -m venv .venv || { echo "Install Python 3.11+ from python.org first."; read -p "Press Enter"; exit 1; }
}

install() {
  .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -r requirements.txt || fail
  .venv/bin/python -c "import faster_whisper, imageio_ffmpeg" 2>/dev/null
}

if [ ! -x .venv/bin/python ] || ! cmp -s "$MARK" requirements.txt; then
  if [ -d .venv ]; then
    echo "Setup didn't finish last time, or ScryptSink was updated. Finishing it now..."
  else
    echo "First-time setup (a few minutes, needs internet)..."
  fi
  echo "Please keep this window open until ScryptSink opens."
  rm -f "$MARK"
  # Reuse a .venv whose Python works (saves re-downloading); otherwise start it again.
  .venv/bin/python -c "import sys" 2>/dev/null || fresh_venv
  if ! install; then
    # Installed but won't import (an earlier install was cut off half-way): rebuild once from scratch.
    echo "Some parts of the last setup were incomplete. Starting setup again from scratch..."
    fresh_venv
    install || fail
  fi
  cp requirements.txt "$MARK" || fail
fi
exec .venv/bin/python scriptsync_gui.py
