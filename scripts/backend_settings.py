"""Local CLI backend preference; never probes or falls back between providers."""
from __future__ import annotations

import json
from pathlib import Path
import re
from uuid import uuid4


BACKENDS = ("codex", "claude")
SETTINGS_FILE = ".reviewer-settings.json"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "paper"


def read_run_manifest(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("backend", "codex") not in BACKENDS:
            raise ValueError
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read saved backend from {path}; keep the run and repair its manifest before continuing.") from exc
    return manifest


def resolve_backend(workspace: Path, explicit: str | None = None,
                    prior_manifest: dict | None = None) -> tuple[str, str]:
    if explicit is not None and explicit not in BACKENDS:
        raise ValueError("Choose --backend codex or --backend claude.")
    if prior_manifest is not None:
        # Runs made before the optional backend existed were all Codex runs.
        saved = prior_manifest.get("backend", "codex")
        if saved not in BACKENDS:
            raise ValueError("The saved run has an unknown backend; no provider was selected.")
        if explicit is not None and explicit != saved:
            raise ValueError(f"Saved run uses --backend {saved}; use a new paper ID/workspace to change backend.")
        return saved, "explicit choice" if explicit else "saved run"
    if explicit is not None:
        return explicit, "explicit choice"
    path = workspace / SETTINGS_FILE
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
            if (not isinstance(settings, dict) or settings.get("format") != 1
                    or settings.get("backend") not in BACKENDS):
                raise ValueError
        except (OSError, ValueError) as exc:
            raise ValueError(f"Invalid backend preference in {path}; choose --backend codex or --backend claude explicitly.") from exc
        return settings["backend"], "workspace preference"
    return "codex", "legacy default"


def remember_backend(workspace: Path, backend: str) -> None:
    if backend not in BACKENDS:
        raise ValueError("Cannot save an unknown backend.")
    path = workspace / SETTINGS_FILE
    pending = workspace / f".reviewer-settings-{uuid4().hex}.tmp"
    try:
        with pending.open("x", encoding="utf-8") as stream:
            json.dump({"format": 1, "backend": backend}, stream, indent=2)
            stream.write("\n")
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
