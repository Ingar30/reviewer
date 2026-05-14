from __future__ import annotations

import subprocess
import sys
import argparse
from pathlib import Path


ALLOWED_PRIVATE_PLACEHOLDERS = {
    "inputs/README.md",
    "work/README.md",
    "outputs/README.md",
}

PRIVATE_PREFIXES = (
    "inputs/",
    "work/",
    "outputs/",
    "data/raw/",
)

PRIVATE_PATH_PARTS = (
    "/raw/",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def git_files(root: Path, *, include_untracked: bool) -> list[str]:
    command = ["git", "ls-files"]
    if include_untracked:
        command.extend(["--cached", "--others", "--exclude-standard"])
    result = subprocess.run(
        command,
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def private_tracking_violations(paths: list[str]) -> list[str]:
    violations: list[str] = []
    for path in paths:
        if path in ALLOWED_PRIVATE_PLACEHOLDERS:
            continue
        if path.startswith(PRIVATE_PREFIXES) or any(part in path for part in PRIVATE_PATH_PARTS):
            violations.append(path)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that shareable Git files exclude private paper inputs and generated artifacts."
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Also inspect untracked files that are not ignored, useful before the first GitHub commit.",
    )
    args = parser.parse_args()

    violations = private_tracking_violations(git_files(repo_root(), include_untracked=args.include_untracked))
    if violations:
        print("Refusing to share repository with private/runtime artifacts tracked:", file=sys.stderr)
        for path in violations:
            print(f"- {path}", file=sys.stderr)
        return 1
    scope = "tracked and addable files" if args.include_untracked else "tracked files"
    print(f"OK: {scope} do not include private input/work/output artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
