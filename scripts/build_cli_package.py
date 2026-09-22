"""Allowlisted CLI distribution resources, derived from canonical sources."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from build_work_plugin import canonical_files, runtime_scripts, source_bytes

# Subprocess entry points are explicit; ordinary Python imports follow automatically.
CLI_ENTRYPOINTS = (
    "review_paper.py", "refresh_editor.py", "preprocess_pdf.py", "render_prompts.py",
    "validate_review_json.py", "normalize_review_outputs.py", "build_editor_input.py",
    "check_final_report.py", "check_environment.py", "render_report_pdf.py",
)


def cli_payload(repo: Path) -> dict[str, bytes]:
    resources = {name for name in canonical_files(repo) if not name.startswith("scripts/")}
    resources.update({"AGENTS.md", ".codex/config.toml"})
    resources.update("scripts/" + name for name in runtime_scripts(
        repo, entrypoints=CLI_ENTRYPOINTS, excluded=frozenset()
    ))
    payload = {name: source_bytes(repo / name) for name in sorted(resources)}
    manifest = {"format": 1, "files": {
        name: hashlib.sha256(content).hexdigest() for name, content in payload.items()
    }}
    payload[".reviewer-workspace.json"] = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    return payload
