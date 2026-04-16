from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_NORMALIZATION_ROLES = {"manuscript", "crossref", "reference"}


@dataclass(frozen=True)
class ReviewerConfig:
    name: str
    prompt: str
    output: str
    id_prefix: str
    search: bool
    enabled: bool
    normalization_role: str


def default_reviewers_config_path(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / "config" / "reviewers.json"


def _require_string(item: dict[str, Any], key: str, index: int) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"reviewers[{index}].{key} must be a non-empty string")
    return value.strip()


def load_reviewers_config(path: Path | str | None = None, *, enabled_only: bool = True) -> list[ReviewerConfig]:
    config_path = Path(path) if path is not None else default_reviewers_config_path()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    reviewers = data.get("reviewers")
    if not isinstance(reviewers, list) or not reviewers:
        raise ValueError(f"{config_path} must contain a non-empty reviewers list")

    parsed: list[ReviewerConfig] = []
    names: set[str] = set()
    outputs: set[str] = set()
    prompts: set[str] = set()
    id_prefixes: set[str] = set()

    for index, item in enumerate(reviewers):
        if not isinstance(item, dict):
            raise ValueError(f"reviewers[{index}] must be an object")
        name = _require_string(item, "name", index)
        prompt = _require_string(item, "prompt", index)
        output = _require_string(item, "output", index)
        id_prefix = _require_string(item, "id_prefix", index)
        role = _require_string(item, "normalization_role", index)
        if role not in VALID_NORMALIZATION_ROLES:
            valid = ", ".join(sorted(VALID_NORMALIZATION_ROLES))
            raise ValueError(f"reviewers[{index}].normalization_role must be one of: {valid}")
        search = item.get("search", False)
        enabled = item.get("enabled", True)
        if not isinstance(search, bool):
            raise ValueError(f"reviewers[{index}].search must be a boolean")
        if not isinstance(enabled, bool):
            raise ValueError(f"reviewers[{index}].enabled must be a boolean")
        if name in names:
            raise ValueError(f"Duplicate reviewer name in {config_path}: {name}")
        if output in outputs:
            raise ValueError(f"Duplicate reviewer output in {config_path}: {output}")
        if prompt in prompts:
            raise ValueError(f"Duplicate reviewer prompt in {config_path}: {prompt}")
        if id_prefix in id_prefixes:
            raise ValueError(f"Duplicate reviewer id_prefix in {config_path}: {id_prefix}")
        names.add(name)
        outputs.add(output)
        prompts.add(prompt)
        id_prefixes.add(id_prefix)
        parsed.append(
            ReviewerConfig(
                name=name,
                prompt=prompt,
                output=output,
                id_prefix=id_prefix,
                search=search,
                enabled=enabled,
                normalization_role=role,
            )
        )

    if enabled_only:
        parsed = [reviewer for reviewer in parsed if reviewer.enabled]
    if not parsed:
        raise ValueError(f"{config_path} has no enabled reviewers")
    return parsed
