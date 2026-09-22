"""Run offline acceptance against a local wheel/checkout launcher; never call real Codex."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_uv_launcher import exercise_pipeline, fake_codex_environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory to retain synthetic test artifacts")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- LAUNCHER [launcher arguments]")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("supply a launcher command after --")
    output = args.output.resolve()
    if output.exists():
        parser.error("--output must be a new directory; existing test evidence is never overwritten")
    output.mkdir(parents=True)
    summary = exercise_pipeline(command, output, fake_codex_environment(output))
    summary.update({"command": command, "validation": "mocked Codex only; no live review"})
    (output / "validation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
