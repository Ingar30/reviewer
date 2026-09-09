"""Deterministic routing shared by the CLI and the skills-only Work adapter."""
from __future__ import annotations

from reviewer_config import ReviewerConfig

REVIEWER_SELECTION_MODE = "applicability"
THEORY_REVIEWER_NAME = "theory_logic_auditor"


def parser_quality_gate_findings(data: dict) -> tuple[list[dict], list[dict]]:
    blockers = []
    warnings = []
    for finding in data.get("findings", []):
        if finding.get("issue_type") != "parser_artifact":
            continue
        severity = finding.get("severity")
        confidence = finding.get("confidence")
        if severity == "high" and confidence == "high":
            blockers.append(finding)
        elif severity in {"high", "medium"}:
            warnings.append(finding)
    return blockers, warnings


def reviewer_catalog(reviewers: list[ReviewerConfig]) -> list[dict[str, object]]:
    return [
        {
            "name": reviewer.name,
            "id_prefix": reviewer.id_prefix,
            "prompt": reviewer.prompt,
            "search": reviewer.search,
            "normalization_role": reviewer.normalization_role,
        }
        for reviewer in reviewers
    ]


def enforce_conservative_applicability(
    selection: dict, optional_reviewers: list[ReviewerConfig]
) -> dict:
    """Expand an uncertain selection and guarantee theory coverage for theory papers."""
    guarded = {
        **selection,
        "selected_optional_reviewers": [
            dict(item) for item in selection.get("selected_optional_reviewers", [])
        ],
        "skipped_optional_reviewers": [
            dict(item) for item in selection.get("skipped_optional_reviewers", [])
        ],
        "notes": list(selection.get("notes", [])),
    }
    selected_by_name = {
        item["name"]: item for item in guarded["selected_optional_reviewers"]
    }
    skipped_by_name = {
        item["name"]: item for item in guarded["skipped_optional_reviewers"]
    }
    enabled_optional = [reviewer for reviewer in optional_reviewers if reviewer.enabled]
    uncertain = (
        guarded.get("paper_type") in {"mixed", "unknown"}
        or guarded.get("selection_confidence") != "high"
    )

    if uncertain:
        guarded["selected_optional_reviewers"] = [
            selected_by_name.get(reviewer.name)
            or {
                "name": reviewer.name,
                "reason": (
                    "Included by the conservative applicability guardrail because the paper "
                    "type or routing confidence is uncertain."
                ),
            }
            for reviewer in enabled_optional
        ]
        guarded["skipped_optional_reviewers"] = []
        guarded["notes"].append(
            "The wrapper expanded an uncertain classification to every conditional specialist."
        )
        return guarded

    if guarded.get("paper_type") == "theory" and THEORY_REVIEWER_NAME in skipped_by_name:
        selected_by_name[THEORY_REVIEWER_NAME] = {
            "name": THEORY_REVIEWER_NAME,
            "reason": (
                "Included by the conservative applicability guardrail because a theory paper "
                "requires a dedicated formal-logic audit."
            ),
        }
        skipped_by_name.pop(THEORY_REVIEWER_NAME)
        guarded["notes"].append(
            "The wrapper restored the theory-logic specialist required for a theory paper."
        )
    guarded["selected_optional_reviewers"] = [
        selected_by_name[reviewer.name]
        for reviewer in enabled_optional
        if reviewer.name in selected_by_name
    ]
    guarded["skipped_optional_reviewers"] = [
        skipped_by_name[reviewer.name]
        for reviewer in enabled_optional
        if reviewer.name in skipped_by_name
    ]
    return guarded


def validate_selection_output(
    selection: dict,
    paper_id: str,
    mandatory_reviewers: list[ReviewerConfig],
    optional_reviewers: list[ReviewerConfig],
) -> list[str]:
    errors = []
    if selection.get("paper_id") != paper_id:
        errors.append(f"selection paper_id={selection.get('paper_id')!r}, expected {paper_id!r}")
    valid_paper_types = {
        "empirical_causal",
        "empirical_descriptive",
        "theory",
        "methods",
        "literature_review",
        "mixed",
        "unknown",
    }
    if selection.get("paper_type") not in valid_paper_types:
        errors.append("selection paper_type is invalid")
    if selection.get("selection_confidence") not in {"high", "medium", "low"}:
        errors.append("selection_confidence is invalid")
    if selection.get("selection_mode") != REVIEWER_SELECTION_MODE:
        errors.append(f"selection_mode must be {REVIEWER_SELECTION_MODE!r}")

    optional_by_name = {reviewer.name: reviewer for reviewer in optional_reviewers if reviewer.enabled}
    mandatory_names = {reviewer.name for reviewer in mandatory_reviewers}
    selected_items = selection.get("selected_optional_reviewers", [])
    skipped_items = selection.get("skipped_optional_reviewers", [])
    if not isinstance(selected_items, list):
        errors.append("selected_optional_reviewers must be a list")
        selected_items = []
    if not isinstance(skipped_items, list):
        errors.append("skipped_optional_reviewers must be a list")
        skipped_items = []

    selected_names = []
    for index, item in enumerate(selected_items):
        if not isinstance(item, dict):
            errors.append(f"selected_optional_reviewers[{index}] must be an object")
            continue
        name = item.get("name")
        reason = item.get("reason")
        if not isinstance(name, str) or not name:
            errors.append(f"selected_optional_reviewers[{index}].name must be a non-empty string")
            continue
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"selected_optional_reviewers[{index}].reason must be a non-empty string")
        if name in mandatory_names:
            errors.append(f"selected reviewer is mandatory, not optional: {name}")
        if name not in optional_by_name:
            errors.append(f"selected reviewer is not an enabled optional reviewer: {name}")
        selected_names.append(name)

    duplicates = sorted({name for name in selected_names if selected_names.count(name) > 1})
    for name in duplicates:
        errors.append(f"selected reviewer is duplicated: {name}")
    skipped_names = []
    for index, item in enumerate(skipped_items):
        if not isinstance(item, dict):
            errors.append(f"skipped_optional_reviewers[{index}] must be an object")
            continue
        name = item.get("name")
        reason = item.get("reason")
        if not isinstance(name, str) or not name:
            errors.append(f"skipped_optional_reviewers[{index}].name must be a non-empty string")
            continue
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"skipped_optional_reviewers[{index}].reason must be a non-empty string")
        if name not in optional_by_name:
            errors.append(f"skipped reviewer is not an enabled optional reviewer: {name}")
        skipped_names.append(name)

    overlap = sorted(set(selected_names) & set(skipped_names))
    for name in overlap:
        errors.append(f"reviewer cannot be both selected and skipped: {name}")
    skipped_duplicates = sorted({name for name in skipped_names if skipped_names.count(name) > 1})
    for name in skipped_duplicates:
        errors.append(f"skipped reviewer is duplicated: {name}")
    accounted_for = set(selected_names) | set(skipped_names)
    for name in sorted(set(optional_by_name) - accounted_for):
        errors.append(f"enabled optional reviewer is neither selected nor skipped: {name}")
    return errors


def selected_reviewers_from_selection(
    selection: dict,
    mandatory_reviewers: list[ReviewerConfig],
    optional_reviewers: list[ReviewerConfig],
) -> list[ReviewerConfig]:
    optional_by_name = {reviewer.name: reviewer for reviewer in optional_reviewers}
    selected_names = [item["name"] for item in selection.get("selected_optional_reviewers", [])]
    selected_optional = [optional_by_name[name] for name in selected_names]
    return [*mandatory_reviewers, *selected_optional]
