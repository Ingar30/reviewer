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
REFERENCE_SECTION = "Reference Integrity"
PARSER_SECTION = "Appendix: Parser and Preprocessing Limitations"
CANNOT_VERIFY_SECTION = "Items Marked Cannot Verify"
BIBLIOGRAPHY_APPENDIX_SECTION = "Appendix: Bibliography Maintenance"
GRAMMAR_APPENDIX_SECTION = "Appendix: Grammar and Copyediting Issues"
TRACEABILITY_APPENDIX_SECTION = "Appendix: Traceability Map"

SEVERITY_POINTS = {"high": 60, "medium": 35, "low": 10}
CONFIDENCE_POINTS = {"high": 15, "medium": 8, "low": 0}
TOP_SYNTHESIS_SCORE = 55
MAX_SYNTHESIS_FINDINGS = 8
MAX_EDITOR_INPUT_BYTES = 1_000_000


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
    return " ".join(("" if value is None else str(value)).split())


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


def finding_problem_text(finding: dict[str, Any]) -> str:
    return compact(
        finding.get("finding_summary")
        or finding.get("evidence_summary")
        or finding.get("claim_text")
    )


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
            ("source_consistency_auditor", "Source consistency"),
            ("numerical_auditor", "Numerical"),
            ("claim_evidence_auditor", "Claim/evidence"),
            ("identification_auditor", "Identification"),
            ("robustness_auditor", "Robustness"),
            ("sample_construction_auditor", "Sample construction"),
            ("abstract_conclusion_consistency_auditor", "Abstract/conclusion consistency"),
            ("limitations_external_validity_auditor", "External validity"),
            ("model_equation_auditor", "Model/equation"),
            ("theory_logic_auditor", "Theory logic"),
            ("literature_auditor", "Literature"),
            ("data_availability_replication_auditor", "Replication"),
            ("institutional_context_auditor", "Institutional context"),
            ("power_multiple_testing_auditor", "Power/multiple testing"),
            ("design_randomization_auditor", "Experimental design"),
            ("economic_magnitude_auditor", "Economic magnitude"),
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
    if issue_class == "reference_integrity":
        return REFERENCE_SECTION, "material source problems belong in the reference-integrity section"
    if issue_class == "bibliography_maintenance":
        return BIBLIOGRAPHY_APPENDIX_SECTION, "routine citation maintenance belongs in its appendix"
    if "literature_auditor" in reviewers:
        return LITERATURE_SECTION, "literature-auditor findings belong in the literature section"
    if issue_class == "manuscript_issue" and finding_confidence(finding) == "high" and score >= TOP_SYNTHESIS_SCORE:
        return HIGHEST_PRIORITY_SECTION, "high-confidence substantive issue for cross-agent synthesis"
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


def requires_body_coverage(finding: dict[str, Any]) -> bool:
    if finding.get("severity") not in {"high", "medium"}:
        return False
    return finding.get("issue_class") in {
        "manuscript_issue",
        "cannot_verify",
        "reference_integrity",
    }


def selector_path_for_bundle(bundle_path: Path) -> Path:
    return bundle_path.parent.parent / "selection" / "reviewer_selection.json"


def selection_reason_map(selection_json: dict[str, Any] | None) -> dict[str, str]:
    if not selection_json:
        return {}
    reasons = {}
    for item in selection_json.get("selected_optional_reviewers", []):
        if isinstance(item, dict) and item.get("name"):
            reasons[str(item["name"])] = str(
                item.get("reason") or "selected by reviewer applicability routing"
            )
    return reasons


def active_reviewer_rows(
    reviewers: list[Any],
    bundle_json: dict[str, Any],
    review_json_by_name: dict[str, Any],
    selection_json: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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
            reason = (
                "universal quality-baseline reviewer"
                if reviewer.selection_policy == "mandatory"
                else "active conditional specialist"
            )
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
                "summary": str(output.get("summary") or review_json.get("summary") or ""),
                "notes": output.get("notes") or review_json.get("notes") or [],
            }
        )
    return rows


def optional_reviewer_rows(
    selection_json: dict[str, Any] | None, reviewers: list[Any]
) -> list[list[str]]:
    selected = [
        [
            str(item.get("name") or ""),
            str(item.get("reason") or "selected by reviewer applicability routing"),
        ]
        for item in (selection_json or {}).get("selected_optional_reviewers", [])
        if isinstance(item, dict) and item.get("name")
    ]
    if selected:
        return selected
    return [
        [
            reviewer.name,
            "Active conditional specialist; applicability provenance unavailable.",
        ]
        for reviewer in reviewers
        if reviewer.selection_policy == "optional"
    ]


def reviewer_status_caveats(rows: list[dict[str, Any]]) -> list[list[str]]:
    caveats = []
    for row in rows:
        status = row.get("status", "unknown")
        if status != "ok":
            detail = row.get("summary") or "; ".join(row.get("notes") or [])
            caveats.append([row["reviewer"], status, detail or row["selection_reason"]])
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
    optional_rows = optional_reviewer_rows(selection_json, reviewers)

    chunks = ["# Deterministic Editor Brief\n\n"]
    chunks.append(
        "Use this brief only as a retrieval and coverage map. The normalized bundle remains "
        "authoritative for evidence, editorial judgment, and traceability. Candidate routes and "
        "internal scores are advisory heuristics that cannot distinguish confirmed corrections "
        "from judgment-dependent critiques. Inspect the complete bundle and override the suggested "
        "order whenever the evidence warrants it. Do not reproduce run summaries, scoring tables, "
        "routing tables, reviewer-count tables, or this wording in the final report.\n\n"
    )
    chunks.append("## Run Summary\n\n")
    chunks.append(f"- paper_id: `{paper_id}`\n")
    chunks.append(f"- canonical findings: `{len(findings)}`\n")
    chunks.append(f"- issue classes: `{json.dumps(bundle_json.get('summary', {}).get('issue_class_counts', {}), sort_keys=True)}`\n")
    chunks.append(f"- severities: `{json.dumps(bundle_json.get('summary', {}).get('severity_counts', {}), sort_keys=True)}`\n")
    chunks.append(f"- confidences: `{json.dumps(dict(confidence_counts), sort_keys=True)}`\n\n")
    chunks.append("## Review Configuration Guidance\n\n")
    chunks.append(f"- Mandatory baseline reviewers: {baseline_reviewers or 'none recorded'}.\n")
    selection_mode = (selection_json or {}).get("selection_mode")
    if selection_mode == "applicability":
        chunks.append(
            f"- Applicability routing classified the paper as "
            f"`{selection_json.get('paper_type', 'unknown')}` with "
            f"`{selection_json.get('selection_confidence', 'unknown')}` confidence.\n"
        )
        chunks.append(
            "- Conditional specialists may be skipped only when their entire remit is clearly "
            "absent; mixed, unknown, or lower-confidence classifications expand to the full "
            "conditional roster.\n"
        )
    elif selection_mode == "static":
        chunks.append(
            "- This is a legacy exhaustive run in which every then-enabled optional reviewer ran.\n"
        )
    elif selection_mode == "dynamic":
        chunks.append(
            f"- This is a legacy dynamically routed run classified as "
            f"`{selection_json.get('paper_type', 'unknown')}` with "
            f"`{selection_json.get('selection_confidence', 'unknown')}` confidence.\n"
        )
    elif selection_json:
        chunks.append("- Reviewer-selection provenance uses an unrecognized legacy mode.\n")
    else:
        chunks.append(
            "- Selection provenance is unavailable; the active configured optional reviewers listed below were run.\n"
        )
    chunks.append(
        "- In the final report, use at most one short plain-language paragraph near the end to "
        "describe review scope and material coverage limitations. Do not name agents, state reviewer "
        "counts, or narrate routing unless a specific coverage gap affects confidence.\n\n"
    )
    chunks.append("Optional reviewers used and why:\n")
    chunks.append(markdown_table(["Reviewer", "Selection reason"], optional_rows))
    status_caveats = reviewer_status_caveats(active_rows)
    if status_caveats:
        chunks.append("\nReviewer status caveats to mention only if they materially limit confidence:\n")
        chunks.append(markdown_table(["Reviewer", "Status", "Coverage summary"], status_caveats))

    chunks.append("\n## Machine-Ranked Candidate Findings (Advisory Only)\n\n")
    chunks.append(
        "These candidates are retrieval aids, not a final priority list. The heuristic can "
        "over-promote interpretive concerns and under-promote single-reviewer arithmetic or source "
        "contradictions. Apply the editor prompt's evidence tiers after reading every canonical "
        "finding.\n\n"
    )
    chunks.append(
        markdown_table(
            ["Canonical ID", "Severity", "Confidence", "Issue"],
            [
                [
                    finding.get("canonical_id"),
                    finding.get("severity"),
                    finding_confidence(finding),
                    short_text(finding_problem_text(finding)),
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
                    short_text(finding_problem_text(finding)),
                ]
                for finding, section, _reason, score in sorted(
                    routed,
                    key=lambda item: item[0].get("canonical_id", ""),
                )
                if section == ADDITIONAL_FINDINGS_SECTION
            ],
        )
    )

    required_coverage = [
        finding for finding in findings if requires_body_coverage(finding)
    ]
    chunks.append("\n## Required Body Coverage Audit\n\n")
    chunks.append(
        "Before finalizing, silently confirm that every row below is addressed substantively outside "
        "the traceability map. One discussion may cover several genuinely related rows. Parser, routine "
        "bibliography-maintenance, and copyediting findings are excluded here and may be covered only in "
        "their technical appendices.\n\n"
    )
    chunks.append(
        markdown_table(
            ["Canonical ID", "Class", "Severity", "Location", "Issue"],
            [
                [
                    canonical_id_text(finding),
                    finding.get("issue_class"),
                    finding.get("severity"),
                    primary_location_text(finding),
                    short_text(finding_problem_text(finding)),
                ]
                for finding in required_coverage
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
                    short_text(finding_problem_text(finding)),
                    canonical_id_text(finding),
                    source_id_text(finding),
                ]
                for finding, section, _reason, _score in routed
            ],
        )
    )

    return "".join(chunks).rstrip() + "\n"


def reviewer_provenance_markdown(
    reviewers: list[Any],
    review_paths: list[Path],
    review_json_by_name: dict[str, Any],
) -> str:
    rows = []
    for reviewer, path in zip(reviewers, review_paths, strict=True):
        review_json = review_json_by_name.get(reviewer.name, {})
        rows.append(
            [
                review_json.get("reviewer") or reviewer.name,
                path.as_posix(),
                review_json.get("run_status") or "unknown",
                len(review_json.get("findings", [])),
            ]
        )
    return markdown_table(["Reviewer", "Validated JSON path", "Status", "Findings"], rows)


def editor_input_document(
    *,
    paper_id: str,
    editor_prompt_text: str,
    bundle_path: Path,
    bundle_json: dict[str, Any],
    reviews_dir: Path,
    reviewers: list[Any],
    review_paths: list[Path],
    review_json_by_name: dict[str, Any],
    selection_json: dict[str, Any] | None,
    compact_bundle: bool,
) -> str:
    bundle_text = json.dumps(
        bundle_json,
        ensure_ascii=False,
        indent=None if compact_bundle else 2,
        separators=(",", ":") if compact_bundle else None,
    )
    chunks = [editor_prompt_text]
    chunks.append("\n\n# Editor Input Metadata\n\n")
    chunks.append(f"- paper_id: `{paper_id}`\n")
    chunks.append(f"- normalized_bundle: `{bundle_path.as_posix()}`\n")
    chunks.append(f"- reviews_dir: `{reviews_dir.as_posix()}`\n")
    chunks.append("\n\n")
    chunks.append(
        editor_brief_markdown(
            paper_id, bundle_json, reviewers, review_json_by_name, selection_json
        )
    )
    chunks.append("\n\n# Normalized Editor Bundle\n\n```json\n")
    chunks.append(bundle_text)
    chunks.append("\n```\n")
    chunks.append("\n\n# Validated Reviewer Output Provenance\n\n")
    chunks.append(
        "The files below were identity-, schema-, semantic-, and provenance-validated before "
        "normalization. Their substantive finding details are preserved in the normalized bundle; "
        "the paths are retained for auditability only.\n\n"
    )
    chunks.append(
        reviewer_provenance_markdown(reviewers, review_paths, review_json_by_name)
    )
    return "".join(chunks)


def bounded_editor_input(
    document_args: dict[str, Any], max_bytes: int = MAX_EDITOR_INPUT_BYTES
) -> tuple[str, str, int]:
    editor_input = editor_input_document(**document_args, compact_bundle=False)
    serialization = "pretty"
    byte_count = len(editor_input.encode("utf-8"))
    if byte_count > max_bytes:
        editor_input = editor_input_document(**document_args, compact_bundle=True)
        serialization = "minified"
        byte_count = len(editor_input.encode("utf-8"))
    if byte_count > max_bytes:
        raise ValueError(
            f"Editor input is {byte_count:,} UTF-8 bytes after lossless minification, "
            f"exceeding the {max_bytes:,}-byte safety budget. "
            "The builder will not truncate evidence."
        )
    return editor_input, serialization, byte_count


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

    document_args = {
        "paper_id": args.paper_id,
        "editor_prompt_text": read(editor_prompt),
        "bundle_path": bundle,
        "bundle_json": bundle_json,
        "reviews_dir": reviews_dir,
        "reviewers": reviewers,
        "review_paths": review_paths,
        "review_json_by_name": review_json_by_name,
        "selection_json": selection_json,
    }
    editor_input, serialization, byte_count = bounded_editor_input(document_args)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(editor_input, encoding="utf-8")
    print(f"Wrote editor input: {output} ({byte_count:,} bytes, {serialization} bundle)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
