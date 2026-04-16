from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from reviewer_config import load_reviewers_config

HIGHEST_PRIORITY_SECTION = "Highest-Priority Cross-Agent Findings"
AGENT_SECTION = "Agent-by-Agent Findings"
LITERATURE_SECTION = "Literature Positioning and Novelty"
REFERENCE_SECTION = "Reference Integrity and Bibliography Maintenance"
PARSER_SECTION = "Parser and Preprocessing Caveats"
CANNOT_VERIFY_SECTION = "Items Marked Cannot Verify"
GRAMMAR_APPENDIX_SECTION = "Appendix: Grammar and Copyediting Issues"

SEVERITY_POINTS = {"high": 60, "medium": 35, "low": 10}
CONFIDENCE_POINTS = {"high": 15, "medium": 8, "low": 0}
TOP_SYNTHESIS_SCORE = 55


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(read(path))


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if not path.is_file():
        raise ValueError(f"Expected {label} to be a file: {path}")


def compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def source_id_text(finding: dict[str, Any]) -> str:
    return "; ".join(
        f"{source.get('reviewer')}:{source.get('id')}"
        for source in finding.get("source_findings", [])
        if source.get("reviewer") and source.get("id")
    )


def primary_location_text(finding: dict[str, Any]) -> str:
    location = finding.get("primary_location") or {}
    parts = []
    page = location.get("page")
    page_label = location.get("page_label")
    section = location.get("section")
    if page is not None:
        parts.append(f"page {page}")
    if page_label:
        parts.append(f"label {page_label}")
    if section:
        parts.append(str(section))
    return ", ".join(parts) if parts else "location not specified"


def short_text(value: Any, limit: int = 120) -> str:
    text = compact(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def finding_confidence(finding: dict[str, Any]) -> str:
    return str(finding.get("confidence") or "medium")


def finding_score(finding: dict[str, Any]) -> int:
    issue_class = finding.get("issue_class")
    severity = str(finding.get("severity") or "low")
    confidence = finding_confidence(finding)
    score = SEVERITY_POINTS.get(severity, 0) + CONFIDENCE_POINTS.get(confidence, 0)

    source_reviewers = finding.get("source_reviewers") or []
    if len(source_reviewers) > 1:
        score += 12 + (len(source_reviewers) - 2) * 4

    if issue_class == "manuscript_issue":
        score += 15
    elif issue_class == "reference_integrity":
        score += 4
    elif issue_class == "bibliography_maintenance":
        score -= 12
    elif issue_class == "parser_artifact":
        score += 10 if severity == "high" else -18
    elif issue_class == "copyedit_issue":
        score -= 45
    elif issue_class == "cannot_verify":
        score += 12 if severity == "high" else -5

    return score


def is_cannot_verify(finding: dict[str, Any]) -> bool:
    return (
        finding.get("issue_class") == "cannot_verify"
        or finding.get("assessment") == "cannot_verify"
        or bool(finding.get("cannot_verify_reasons"))
    )


def reviewer_names(finding: dict[str, Any]) -> set[str]:
    names = set(finding.get("source_reviewers") or [])
    for source in finding.get("source_findings", []):
        reviewer = source.get("reviewer")
        if reviewer:
            names.add(str(reviewer))
    return names


def route_finding(finding: dict[str, Any]) -> tuple[str, str]:
    issue_class = finding.get("issue_class")
    reviewers = reviewer_names(finding)
    score = finding_score(finding)

    if issue_class == "copyedit_issue":
        return GRAMMAR_APPENDIX_SECTION, "copyedit_issue findings belong in the grammar appendix"
    if issue_class == "parser_artifact":
        return PARSER_SECTION, "parser_artifact findings belong with preprocessing caveats"
    if is_cannot_verify(finding):
        return CANNOT_VERIFY_SECTION, "cannot-verify findings need explicit uncertainty handling"
    if issue_class in {"reference_integrity", "bibliography_maintenance"}:
        return REFERENCE_SECTION, "reference findings belong in the reference-integrity section"
    if "literature_auditor" in reviewers:
        return LITERATURE_SECTION, "literature-auditor findings belong in the literature section"
    if issue_class == "manuscript_issue" and score >= TOP_SYNTHESIS_SCORE:
        return HIGHEST_PRIORITY_SECTION, "high-scoring substantive issue for cross-agent synthesis"
    return AGENT_SECTION, "lower-priority substantive item for agent-by-agent coverage"


def selector_path_for_bundle(bundle_path: Path) -> Path:
    return bundle_path.parent.parent / "selection" / "reviewer_selection.json"


def selection_reason_map(selection_json: dict[str, Any] | None) -> dict[str, str]:
    if not selection_json:
        return {}
    reasons = {}
    for item in selection_json.get("selected_optional_reviewers", []):
        if isinstance(item, dict) and item.get("name"):
            reasons[str(item["name"])] = str(item.get("reason") or "selected by reviewer selector")
    return reasons


def active_reviewer_rows(
    reviewers: list[Any],
    bundle_json: dict[str, Any],
    review_json_by_name: dict[str, Any],
    selection_json: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    output_by_name = {
        item.get("reviewer"): item
        for item in bundle_json.get("source_reviewer_outputs", [])
        if isinstance(item, dict)
    }
    selector_reasons = selection_reason_map(selection_json)
    rows = []
    for reviewer in reviewers:
        reason = selector_reasons.get(reviewer.name)
        if reason is None:
            reason = "mandatory baseline reviewer" if reviewer.selection_policy == "mandatory" else "active configured reviewer"
        output = output_by_name.get(reviewer.name, {})
        review_json = review_json_by_name.get(reviewer.name, {})
        rows.append(
            {
                "reviewer": reviewer.name,
                "status": str(output.get("run_status") or review_json.get("run_status") or "unknown"),
                "finding_count": str(output.get("finding_count", len(review_json.get("findings", [])))),
                "role": reviewer.normalization_role,
                "selection_policy": reviewer.selection_policy,
                "selection_reason": reason,
            }
        )
    return rows


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_None._\n"
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        safe = [compact(cell).replace("|", "\\|") for cell in row]
        out.append("| " + " | ".join(safe) + " |")
    return "\n".join(out) + "\n"


def editor_brief_markdown(
    paper_id: str,
    bundle_json: dict[str, Any],
    reviewers: list[Any],
    review_json_by_name: dict[str, Any],
    selection_json: dict[str, Any] | None = None,
) -> str:
    findings = [item for item in bundle_json.get("canonical_findings", []) if isinstance(item, dict)]
    routed = [(finding, *route_finding(finding), finding_score(finding)) for finding in findings]
    source_counts = Counter()
    confidence_counts = Counter()
    for finding in findings:
        confidence_counts[finding_confidence(finding)] += 1
        for reviewer in reviewer_names(finding):
            source_counts[reviewer] += 1

    synthesis_candidates = sorted(
        [
            (finding, section, reason, score)
            for finding, section, reason, score in routed
            if section == HIGHEST_PRIORITY_SECTION
        ],
        key=lambda item: (-item[3], item[0].get("canonical_id", "")),
    )

    by_reviewer: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {"elevated": [], "additional": []})
    for finding, section, _reason, _score in routed:
        bucket = "elevated" if section == HIGHEST_PRIORITY_SECTION else "additional"
        for reviewer in sorted(reviewer_names(finding)):
            by_reviewer[reviewer][bucket].append(finding)

    chunks = ["# Deterministic Editor Brief\n\n"]
    chunks.append("Use this brief as the organizing map for the report. The normalized bundle remains authoritative for details and traceability.\n\n")
    chunks.append("## Run Summary\n\n")
    chunks.append(f"- paper_id: `{paper_id}`\n")
    chunks.append(f"- canonical findings: `{len(findings)}`\n")
    chunks.append(f"- issue classes: `{json.dumps(bundle_json.get('summary', {}).get('issue_class_counts', {}), sort_keys=True)}`\n")
    chunks.append(f"- severities: `{json.dumps(bundle_json.get('summary', {}).get('severity_counts', {}), sort_keys=True)}`\n")
    chunks.append(f"- confidences: `{json.dumps(dict(confidence_counts), sort_keys=True)}`\n\n")
    if selection_json:
        chunks.append("## Reviewer Selection\n\n")
        chunks.append(f"- paper_type: `{selection_json.get('paper_type', 'unknown')}`\n")
        chunks.append(f"- selection_confidence: `{selection_json.get('selection_confidence', 'unknown')}`\n")
        selected = [
            f"{item.get('name')} ({item.get('reason')})"
            for item in selection_json.get("selected_optional_reviewers", [])
            if isinstance(item, dict)
        ]
        chunks.append(f"- selected optional reviewers: `{'; '.join(selected) if selected else 'none'}`\n\n")

    chunks.append("## Active Reviewers\n\n")
    chunks.append(
        markdown_table(
            ["Reviewer", "Status", "Finding count", "Role", "Selection policy", "Selection reason"],
            [
                [
                    row["reviewer"],
                    row["status"],
                    row["finding_count"],
                    row["role"],
                    row["selection_policy"],
                    row["selection_reason"],
                ]
                for row in active_reviewer_rows(reviewers, bundle_json, review_json_by_name, selection_json)
            ],
        )
    )
    chunks.append("\n## Reviewer Finding Counts\n\n")
    chunks.append(markdown_table(["Reviewer", "Canonical findings"], sorted(source_counts.items())))

    chunks.append("\n## Findings Recommended For Cross-Agent Synthesis\n\n")
    chunks.append(
        markdown_table(
            ["Canonical ID", "Score", "Severity", "Confidence", "Agents", "Issue"],
            [
                [
                    finding.get("canonical_id"),
                    score,
                    finding.get("severity"),
                    finding_confidence(finding),
                    ", ".join(sorted(reviewer_names(finding))),
                    short_text(finding.get("claim_text")),
                ]
                for finding, _section, _reason, score in synthesis_candidates
            ],
        )
    )

    chunks.append("\n## Section Routing\n\n")
    chunks.append(
        markdown_table(
            ["Canonical ID", "Recommended section", "Reason", "Location", "Source IDs"],
            [
                [
                    finding.get("canonical_id"),
                    section,
                    reason,
                    primary_location_text(finding),
                    source_id_text(finding),
                ]
                for finding, section, reason, _score in routed
            ],
        )
    )

    chunks.append("\n## Agent-by-Agent Finding Index\n\n")
    for reviewer in reviewers:
        buckets = by_reviewer.get(reviewer.name, {"elevated": [], "additional": []})
        chunks.append(f"### {reviewer.name}\n\n")
        chunks.append("Elevated to cross-agent synthesis:\n")
        if buckets["elevated"]:
            for finding in buckets["elevated"]:
                chunks.append(f"- {finding.get('canonical_id')}: {short_text(finding.get('claim_text'))}\n")
        else:
            chunks.append("- None.\n")
        chunks.append("\nAdditional findings:\n")
        if buckets["additional"]:
            for finding in buckets["additional"]:
                section, _reason = route_finding(finding)
                chunks.append(f"- {finding.get('canonical_id')} ({section}): {short_text(finding.get('claim_text'))}\n")
        else:
            chunks.append("- None.\n")
        chunks.append("\n")

    return "".join(chunks).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one editor input file from prompt, bundle, and reviews.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--editor-prompt", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--reviews-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reviewers-config", default="config/reviewers.json")
    args = parser.parse_args()

    editor_prompt = Path(args.editor_prompt)
    bundle = Path(args.bundle)
    reviews_dir = Path(args.reviews_dir)
    output = Path(args.output)
    reviewers = load_reviewers_config(args.reviewers_config)

    require_file(editor_prompt, "editor prompt")
    require_file(bundle, "normalized editor bundle")
    bundle_json = read_json(bundle)
    if bundle_json.get("paper_id") != args.paper_id:
        raise ValueError(f"{bundle} has paper_id={bundle_json.get('paper_id')!r}, expected {args.paper_id!r}")
    selection_path = selector_path_for_bundle(bundle)
    selection_json = read_json(selection_path) if selection_path.exists() else None

    review_paths = []
    review_json_by_name = {}
    for reviewer in reviewers:
        filename = reviewer.output
        path = reviews_dir / filename
        require_file(path, f"reviewer output {filename}")
        review_json = read_json(path)
        if review_json.get("reviewer") != reviewer.name:
            raise ValueError(f"{path} has reviewer={review_json.get('reviewer')!r}, expected {reviewer.name!r}")
        if review_json.get("paper_id") != args.paper_id:
            raise ValueError(f"{path} has paper_id={review_json.get('paper_id')!r}, expected {args.paper_id!r}")
        review_paths.append(path)
        review_json_by_name[reviewer.name] = review_json

    chunks = []
    chunks.append(read(editor_prompt))
    chunks.append("\n\n# Editor Input Metadata\n\n")
    chunks.append(f"- paper_id: `{args.paper_id}`\n")
    chunks.append(f"- normalized_bundle: `{bundle.as_posix()}`\n")
    chunks.append(f"- reviews_dir: `{reviews_dir.as_posix()}`\n")
    chunks.append("\n\n")
    chunks.append(editor_brief_markdown(args.paper_id, bundle_json, reviewers, review_json_by_name, selection_json))
    chunks.append("\n\n# Normalized Editor Bundle\n\n```json\n")
    chunks.append(read(bundle))
    chunks.append("\n```\n")

    chunks.append("\n\n# Original Configured Reviewer Outputs\n")
    for path in review_paths:
        chunks.append(f"\n\n## {path.name}\n\n```json\n")
        chunks.append(read(path))
        chunks.append("\n```\n")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(chunks), encoding="utf-8")
    print(f"Wrote editor input: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
