#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if [ ! -d ".venv" ]; then
  "$PYTHON" -m venv .venv
fi

./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

echo
echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
echo "Run tests with: python -m unittest"

if ! command -v codex >/dev/null 2>&1; then
  echo "Warning: Codex CLI was not found on PATH. Install/authenticate Codex before running scripts/review_paper.py." >&2
fi
