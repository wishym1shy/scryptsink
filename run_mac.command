#!/bin/bash
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "First-time setup (a few minutes, needs internet)..."
  python3 -m venv .venv || { echo "Install Python 3.11+ from python.org first."; read -p "Press Enter"; exit 1; }
  .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -r requirements.txt \
    || { echo "Setup failed."; rm -rf .venv; read -p "Press Enter"; exit 1; }
fi
exec .venv/bin/python scriptsync_gui.py
