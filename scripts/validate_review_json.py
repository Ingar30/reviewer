from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from reviewer_config import ReviewerConfig, load_reviewers_config


def path_label(parts: list[Any]) -> str:
    return ".".join(str(part) for part in parts)


def reviewer_by_name(reviewers: list[ReviewerConfig], name: str) -> ReviewerConfig | None:
    return next((reviewer for reviewer in reviewers if reviewer.name == name), None)


def is_cannot_verify(finding: dict[str, Any]) -> bool:
    category = " ".join(str(finding.get("category", "")).lower().split())
    return (
        finding.get("assessment") == "cannot_verify"
        or finding.get("issue_type") == "cannot_verify"
        or "cannot_verify" in category
    )


def semantic_errors(data: dict[str, Any], reviewers: list[ReviewerConfig]) -> list[str]:
    errors = []
    reviewer_name = data.get("reviewer")
    reviewer = reviewer_by_name(reviewers, reviewer_name) if isinstance(reviewer_name, str) else None
    if reviewer is None:
        errors.append(f"reviewer {reviewer_name!r} is not configured")
        id_pattern = None
    else:
        id_pattern = re.compile(rf"^{re.escape(reviewer.id_prefix)}-\d{{3}}$")

    seen_ids: set[str] = set()
    for index, finding in enumerate(data.get("findings", [])):
        if not isinstance(finding, dict):
            continue
        finding_id = finding.get("id")
        label = f"findings.{index}"
        if isinstance(finding_id, str):
            if finding_id in seen_ids:
                errors.append(f"{label}.id duplicates another finding id: {finding_id}")
            seen_ids.add(finding_id)
            if id_pattern and not id_pattern.match(finding_id):
                errors.append(f"{label}.id must match {reviewer.id_prefix}-###")

        if not finding.get("issue_type"):
            errors.append(f"{label}.issue_type is required by the hardened reviewer contract")
        if not finding.get("confidence"):
            errors.append(f"{label}.confidence is required by the hardened reviewer contract")

        location = finding.get("location") or {}
        if isinstance(location, dict):
            precision = location.get("precision")
            if not precision:
                errors.append(f"{label}.location.precision is required by the hardened reviewer contract")
            if precision == "missing" and any(location.get(key) is not None for key in ["page", "page_label", "section", "text_quote"]):
                errors.append(f"{label}.location has precision=missing but still includes concrete location fields")
            if precision == "exact" and (location.get("page") is None or not location.get("text_quote")):
                errors.append(f"{label}.location has precision=exact but lacks page or text_quote")

        if is_cannot_verify(finding) and not finding.get("cannot_verify_reason"):
            errors.append(f"{label}.cannot_verify_reason is required for cannot_verify findings")

        source_objects = finding.get("source_objects") or []
        if not is_cannot_verify(finding) and not source_objects:
            errors.append(f"{label}.source_objects is required for verifiable findings")
        source_ids = {item.get("id") for item in source_objects if isinstance(item, dict)}
        for link_index, link in enumerate(finding.get("claim_evidence_links") or []):
            if not isinstance(link, dict):
                continue
            ids = link.get("source_object_ids") or []
            if not ids:
                errors.append(f"{label}.claim_evidence_links.{link_index}.source_object_ids must not be empty")
            missing = [source_id for source_id in ids if source_id not in source_ids]
            if missing:
                errors.append(f"{label}.claim_evidence_links.{link_index} references undeclared source object ids: {', '.join(missing)}")

        if reviewer and reviewer.name == "numerical_auditor" and not is_cannot_verify(finding):
            if not finding.get("numeric_check"):
                errors.append(f"{label}.numeric_check is required for verifiable numerical_auditor findings")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--reviewers-config", default="config/reviewers.json")
    args = parser.parse_args()

    schema_path = Path(args.schema)
    input_path = Path(args.input)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = json.loads(input_path.read_text(encoding="utf-8"))
    reviewers = load_reviewers_config(args.reviewers_config)

    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    failures = []
    for err in errors:
        path = path_label(list(err.path))
        failures.append(f"{path}: {err.message}")
    failures.extend(semantic_errors(data, reviewers))

    if failures:
        print("INVALID")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
