from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from reviewer_config import load_reviewers_config

HIGHEST_PRIORITY_SECTION = "Highest-Priority Cross-Agent Findings"
ADDITIONAL_FINDINGS_SECTION = "Additional Findings"
AGENT_SECTION = ADDITIONAL_FINDINGS_SECTION
LITERATURE_SECTION = "Literature Positioning and Novelty"
REFERENCE_SECTION = "Reference Integrity and Bibliography Maintenance"
PARSER_SECTION = "Parser and Preprocessing Caveats"
CANNOT_VERIFY_SECTION = "Items Marked Cannot Verify"
GRAMMAR_APPENDIX_SECTION = "Appendix: Grammar and Copyediting Issues"
TRACEABILITY_APPENDIX_SECTION = "Appendix: Traceability Map"

SEVERITY_POINTS = {"high": 60, "medium": 35, "low": 10}
CONFIDENCE_POINTS = {"high": 15, "medium": 8, "low": 0}
TOP_SYNTHESIS_SCORE = 55
MAX_SYNTHESIS_FINDINGS = 5


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


def canonical_id_text(finding: dict[str, Any]) -> str:
    return str(finding.get("canonical_id") or "")


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


def finding_area(finding: dict[str, Any]) -> str:
    issue_class = finding.get("issue_class")
    if issue_class == "manuscript_issue":
        reviewers = reviewer_names(finding)
        area_by_reviewer = [
            ("crossref_auditor", "Cross-reference"),
            ("numerical_auditor", "Numerical"),
            ("claim_evidence_auditor", "Claim/evidence"),
            ("identification_auditor", "Identification"),
            ("robustness_auditor", "Robustness"),
            ("sample_construction_auditor", "Sample construction"),
            ("abstract_conclusion_consistency_auditor", "Abstract/conclusion consistency"),
            ("limitations_external_validity_auditor", "External validity"),
        ]
        for reviewer, area in area_by_reviewer:
            if reviewer in reviewers:
                return area
        return "Manuscript"
    if issue_class == "reference_integrity":
        return "Reference integrity"
    if issue_class == "bibliography_maintenance":
        return "Bibliography maintenance"
    if issue_class == "parser_artifact":
        return "Parser/preprocessing"
    if issue_class == "cannot_verify":
        return "Cannot verify"
    if issue_class == "copyedit_issue":
        return "Grammar/copyediting"
    return "Other"


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
    return ADDITIONAL_FINDINGS_SECTION, "lower-priority substantive item for the additional-findings table"


def cap_synthesis_routes(
    routed: list[tuple[dict[str, Any], str, str, int]],
) -> list[tuple[dict[str, Any], str, str, int]]:
    synthesis = sorted(
        [item for item in routed if item[1] == HIGHEST_PRIORITY_SECTION],
        key=lambda item: (-item[3], item[0].get("canonical_id", "")),
    )
    keep_ids = {item[0].get("canonical_id") for item in synthesis[:MAX_SYNTHESIS_FINDINGS]}
    capped = []
    for finding, section, reason, score in routed:
        if section == HIGHEST_PRIORITY_SECTION and finding.get("canonical_id") not in keep_ids:
            capped.append(
                (
                    finding,
                    ADDITIONAL_FINDINGS_SECTION,
                    f"substantive issue below the top {MAX_SYNTHESIS_FINDINGS} synthesis findings",
                    score,
                )
            )
        else:
            capped.append((finding, section, reason, score))
    return capped


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


def optional_reviewer_rows(selection_json: dict[str, Any] | None) -> list[list[str]]:
    if not selection_json:
        return []
    return [
        [str(item.get("name") or ""), str(item.get("reason") or "selected by reviewer selector")]
        for item in selection_json.get("selected_optional_reviewers", [])
        if isinstance(item, dict) and item.get("name")
    ]


def reviewer_status_caveats(rows: list[dict[str, str]]) -> list[list[str]]:
    caveats = []
    for row in rows:
        status = row.get("status", "unknown")
        if status != "ok":
            caveats.append([row["reviewer"], status, row["selection_reason"]])
    return caveats


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
    routed = cap_synthesis_routes([(finding, *route_finding(finding), finding_score(finding)) for finding in findings])
    confidence_counts = Counter()
    for finding in findings:
        confidence_counts[finding_confidence(finding)] += 1

    synthesis_candidates = sorted(
        [
            (finding, section, reason, score)
            for finding, section, reason, score in routed
            if section == HIGHEST_PRIORITY_SECTION
        ],
        key=lambda item: (-item[3], item[0].get("canonical_id", "")),
    )

    active_rows = active_reviewer_rows(reviewers, bundle_json, review_json_by_name, selection_json)
    baseline_reviewers = ", ".join(row["reviewer"] for row in active_rows if row["selection_policy"] == "mandatory")
    optional_rows = optional_reviewer_rows(selection_json)

    chunks = ["# Deterministic Editor Brief\n\n"]
    chunks.append("Use this brief as the organizing map for the report. The normalized bundle remains authoritative for details and traceability. This brief is internal guidance; do not reproduce run summaries, scoring tables, routing tables, reviewer-count tables, or this wording in the final report.\n\n")
    chunks.append("## Run Summary\n\n")
    chunks.append(f"- paper_id: `{paper_id}`\n")
    chunks.append(f"- canonical findings: `{len(findings)}`\n")
    chunks.append(f"- issue classes: `{json.dumps(bundle_json.get('summary', {}).get('issue_class_counts', {}), sort_keys=True)}`\n")
    chunks.append(f"- severities: `{json.dumps(bundle_json.get('summary', {}).get('severity_counts', {}), sort_keys=True)}`\n")
    chunks.append(f"- confidences: `{json.dumps(dict(confidence_counts), sort_keys=True)}`\n\n")
    chunks.append("## Review Configuration Guidance\n\n")
    chunks.append(f"- Mandatory baseline reviewers: {baseline_reviewers or 'none recorded'}.\n")
    if selection_json:
        chunks.append(f"- Reviewer selector classified the paper as `{selection_json.get('paper_type', 'unknown')}` with `{selection_json.get('selection_confidence', 'unknown')}` confidence.\n")
    chunks.append("- In the final report, summarize reviewer selection in prose only; do not print reviewer-count or active-reviewer tables.\n\n")
    chunks.append("Optional reviewers used and why:\n")
    chunks.append(markdown_table(["Reviewer", "Selection reason"], optional_rows))
    status_caveats = reviewer_status_caveats(active_rows)
    if status_caveats:
        chunks.append("\nReviewer status caveats to mention only if they materially limit confidence:\n")
        chunks.append(markdown_table(["Reviewer", "Status", "Selection reason"], status_caveats))

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

    chunks.append("\n## Additional Findings Candidates\n\n")
    chunks.append(
        markdown_table(
            ["Area", "Canonical ID", "Location", "Issue"],
            [
                [
                    finding_area(finding),
                    canonical_id_text(finding),
                    primary_location_text(finding),
                    short_text(finding.get("claim_text")),
                ]
                for finding, section, _reason, score in sorted(
                    routed,
                    key=lambda item: (-item[3], item[0].get("canonical_id", "")),
                )
                if section == ADDITIONAL_FINDINGS_SECTION
            ],
        )
    )

    chunks.append("\n## Section Routing Guidance\n\n")
    chunks.append(
        markdown_table(
            ["Canonical ID", "Recommended section", "Reason", "Location"],
            [
                [
                    finding.get("canonical_id"),
                    section,
                    reason,
                    primary_location_text(finding),
                ]
                for finding, section, reason, _score in routed
            ],
        )
    )

    chunks.append("\n## Traceability Map Rows\n\n")
    chunks.append(
        markdown_table(
            ["Report section", "Finding", "Canonical ID", "Source finding IDs"],
            [
                [
                    section,
                    short_text(finding.get("claim_text")),
                    canonical_id_text(finding),
                    source_id_text(finding),
                ]
                for finding, section, _reason, _score in routed
            ],
        )
    )

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
