from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


SENSITIVE_FILENAME_RE = re.compile(
    r"(?:^|[._/-])(?:api[_-]?key|token|secret|password|passwd|credential|auth)(?:[._/-]|$)",
    re.IGNORECASE,
)

ASSIGNMENT_LHS_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_-]*)\s*[:=]")
SENSITIVE_PARTS = {"TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "AUTH"}

ALLOWLISTED_FILES = {
    ".env.example",
    "CONTRIBUTING.md",
    "README.md",
    "SECURITY.md",
    "docs/github_private_repo_setup.md",
    "docs/github_readiness_audit.md",
    "docs/public_release_checklist.md",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def suspicious_files(root: Path, paths: list[str]) -> list[str]:
    suspicious: list[str] = []
    for path in paths:
        if path in ALLOWLISTED_FILES:
            continue
        full_path = root / path
        if not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SENSITIVE_FILENAME_RE.search(path) or has_sensitive_assignment(text):
            suspicious.append(path)
    return suspicious


def has_sensitive_assignment(text: str) -> bool:
    for line in text.splitlines():
        match = ASSIGNMENT_LHS_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        if name != name.upper():
            continue
        parts = [part for part in name.replace("-", "_").split("_") if part]
        for index, part in enumerate(parts):
            if part not in SENSITIVE_PARTS:
                continue
            if index + 1 < len(parts) and parts[index + 1] == "RE":
                continue
            return True
        if any(left == "API" and right == "KEY" for left, right in zip(parts, parts[1:])):
            return True
    return False


def main() -> int:
    root = repo_root()
    suspicious = suspicious_files(root, tracked_files(root))
    if suspicious:
        print("Potential sensitive names found in shareable files:", file=sys.stderr)
        for path in suspicious:
            print(f"- {path}", file=sys.stderr)
        print("Inspect these files manually before pushing. Secret values are not printed.", file=sys.stderr)
        return 1
    print("OK: no unexpected sensitive names found in tracked/addable text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
