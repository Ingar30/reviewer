"""Prepare an isolated Python environment on the current execution host.

Check-only by default. Never installs Python, switches hosts, starts agents, or
changes a global environment. Use the installed/trusted bundle, not checkpoint code.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from work_plugin import doctor


def pinned_requirements(source: Path) -> None:
    """Reject installer directives, URLs and unpinned additions before setup."""
    names = set()
    for line in (source / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)", line)
        if not match:
            raise ValueError("Environment setup requires simple pinned package==version requirements.")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in names:
            raise ValueError("Environment setup found duplicate package requirements.")
        names.add(name)
    if not names:
        raise ValueError("Environment setup requires at least one pinned dependency.")


def setup_command(command: list[str], *, timeout: int = 600) -> str:
    # Do not echo pip output: host configuration can include private index URLs.
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError(f"Environment setup command failed (exit {result.returncode}); "
                         "check host network/package availability. No global packages were changed.")
    return result.stdout


def prepare(source: Path, destination: Path | None = None, *, allow_install: bool = False) -> dict:
    source = source.resolve()
    environment = doctor(source)
    result = {"status": "ready", "python": sys.executable, "environment": environment,
              "installed": False,
              "hosting": "unverified: this helper cannot establish local versus OpenAI-hosted execution"}
    if environment["status"] == "ready" and not environment["version_differences"]:
        return result
    if sys.version_info < (3, 12):
        return {**result, "status": "python_unavailable",
                "message": "The host needs Python 3.12+. This helper does not install an interpreter."}
    if not allow_install:
        return {**result, "status": "installation_permission_required",
                "message": "A fresh isolated environment is needed. Request permission before package installation."}
    if destination is None:
        raise ValueError("Choose a fresh environment directory outside the installed plugin and review run.")
    # An installed runtime lives at PLUGIN/skills/review-paper/runtime.
    protected = source.parents[2] if source.name == "runtime" and source.parent.name == "review-paper" else source
    raw = destination.absolute()
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError("Linked environment directories are not supported.")
    destination = raw.resolve()
    if (destination.exists() or destination.is_relative_to(protected)
            or protected.is_relative_to(destination)):
        raise ValueError("Use a new environment directory outside the installed plugin; existing paths are never reused.")
    pinned_requirements(source)
    # Reserve without overwriting; failed environments are retained for inspection.
    destination.mkdir(parents=True, exist_ok=False)
    setup_command([sys.executable, "-I", "-m", "venv", "--copies", str(destination)])
    python = destination / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    setup_command([str(python), "-I", "-m", "pip", "--isolated", "--disable-pip-version-check",
                   "--no-input", "install", "--index-url", "https://pypi.org/simple",
                   "--only-binary=:all:", "--no-cache-dir", "--retries", "0", "--timeout", "30",
                   "--requirement", str(source / "requirements.txt"),
                   "--report", str(destination / "install-report.json")])
    # Check through the same doctor used by every review; no second dependency roster.
    checked = json.loads(setup_command([str(python), "-B", str(source / "scripts/work_plugin.py"), "doctor"],
                                      timeout=60))
    if checked.get("status") != "ready" or checked.get("version_differences"):
        raise ValueError("The isolated environment did not pass the pinned dependency check. Do not start a review.")
    return {**result, "python": str(python), "environment": checked, "installed": True,
            "install_receipt": str(destination / "install-report.json")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, help="Fresh directory outside the plugin and the review RUN.")
    parser.add_argument("--allow-install", action="store_true", help="Only after explicit permission on this host.")
    args = parser.parse_args()
    try:
        result = prepare(Path(__file__).resolve().parents[1], args.venv, allow_install=args.allow_install)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result = {"status": "setup_failed",
                  "message": "Isolated setup failed. Check the destination, Python venv support and host network/package "
                             "availability. No global environment was changed. Preserve any partial environment; "
                             "use a fresh directory for another authorized attempt."}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
