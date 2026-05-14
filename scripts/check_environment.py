from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path


REQUIRED_MODULES = [
    "fitz",
    "pdfplumber",
    "pandas",
    "jsonschema",
    "pydantic",
    "dateutil",
    "rapidfuzz",
    "tabulate",
]

REQUIRED_PATHS = [
    "config/reviewers.json",
    "schemas/reviewer_output.schema.json",
    "schemas/reviewer_selection.schema.json",
    "schemas/parser_repair_plan.schema.json",
    "prompts/templates/editor_report.txt",
    "prompts/templates/parser_repair_plan.txt",
    "scripts/review_paper.py",
    "scripts/run_parser_repair_agent.py",
    "scripts/evaluate_parser_repair.py",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def missing_modules() -> list[str]:
    return [module for module in REQUIRED_MODULES if importlib.util.find_spec(module) is None]


def missing_paths(root: Path) -> list[str]:
    return [path for path in REQUIRED_PATHS if not (root / path).exists()]


def main() -> int:
    root = repo_root()
    failures: list[str] = []

    modules = missing_modules()
    if modules:
        failures.append("Missing Python modules: " + ", ".join(modules))

    paths = missing_paths(root)
    if paths:
        failures.append("Missing project files: " + ", ".join(paths))

    if shutil.which("codex") is None and shutil.which("codex.cmd") is None and shutil.which("codex.exe") is None:
        failures.append("Codex CLI was not found on PATH")

    if failures:
        for failure in failures:
            print(f"[fail] {failure}", file=sys.stderr)
        print("Run the setup steps in README.md and authenticate Codex before reviewing papers.", file=sys.stderr)
        return 1

    print("OK: environment looks ready for the reviewer pipeline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
