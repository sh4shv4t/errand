#!/usr/bin/env sh
# Errand one-command start for macOS / Linux: installs on first run, then opens the dashboard.
#   ./start.sh
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run: creating .venv and installing Errand..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e .
fi
[ -f .env ] || cp .env.example .env
exec .venv/bin/errand up "$@"
