from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TARGET_SEVERITIES = {"high", "medium"}
MITIGATED_STATUSES = {"mitigated", "partially_mitigated"}
SAFE_ACTIONS = {"prefer_existing_fallback", "add_reviewer_overlay", "requires_deterministic_preprocess_change"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def target_parser_findings(parser_quality: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        finding
        for finding in parser_quality.get("findings", [])
        if finding.get("issue_type") == "parser_artifact"
        and finding.get("severity") in TARGET_SEVERITIES
    ]


def evaluate_plan(parser_quality: dict[str, Any], plan: dict[str, Any] | None) -> dict[str, Any]:
    targets = target_parser_findings(parser_quality)
    repairs = plan.get("repairs", []) if plan else []
    by_id = {
        repair.get("parser_finding_id"): repair
        for repair in repairs
        if isinstance(repair, dict) and repair.get("parser_finding_id")
    }
    covered = [finding for finding in targets if finding.get("id") in by_id]
    mitigated = [
        finding
        for finding in targets
        if (by_id.get(finding.get("id")) or {}).get("status") in MITIGATED_STATUSES
    ]
    guided = [
        finding
        for finding in targets
        if len((by_id.get(finding.get("id")) or {}).get("reviewer_guidance", "").strip()) >= 40
    ]
    preferred = [
        finding
        for finding in targets
        if (by_id.get(finding.get("id")) or {}).get("preferred_source_paths")
    ]
    safe = [
        repair for repair in by_id.values() if repair.get("action") in SAFE_ACTIONS
    ]
    target_count = len(targets)
    denominator = target_count or 1
    coverage_score = round(100.0 * len(covered) / denominator, 1)
    mitigation_score = round(100.0 * len(mitigated) / denominator, 1)
    guidance_score = round(100.0 * len(guided) / denominator, 1)
    preferred_score = round(100.0 * len(preferred) / denominator, 1)
    safety_score = round(100.0 * len(safe) / max(len(by_id), 1), 1) if by_id else 0.0
    overall = round(
        coverage_score * 0.30
        + mitigation_score * 0.30
        + guidance_score * 0.20
        + preferred_score * 0.10
        + safety_score * 0.10,
        1,
    )
    return {
        "target_finding_count": target_count,
        "repair_count": len(repairs),
        "covered_count": len(covered),
        "mitigated_count": len(mitigated),
        "guided_count": len(guided),
        "preferred_source_count": len(preferred),
        "safe_action_count": len(safe),
        "coverage_score": coverage_score,
        "mitigation_score": mitigation_score,
        "guidance_score": guidance_score,
        "preferred_source_score": preferred_score,
        "safety_score": safety_score,
        "score": overall,
        "uncovered_finding_ids": [
            finding.get("id") for finding in targets if finding.get("id") not in by_id
        ],
        "unmitigated_finding_ids": [
            finding.get("id")
            for finding in targets
            if (by_id.get(finding.get("id")) or {}).get("status") not in MITIGATED_STATUSES
        ],
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"paper_count": 0, "mean_score": 0.0}
    return {
        "paper_count": len(results),
        "mean_score": round(sum(item["score"] for item in results) / len(results), 1),
        "mean_coverage_score": round(sum(item["coverage_score"] for item in results) / len(results), 1),
        "mean_mitigation_score": round(sum(item["mitigation_score"] for item in results) / len(results), 1),
        "mean_guidance_score": round(sum(item["guidance_score"] for item in results) / len(results), 1),
    }


def markdown_report(data: dict[str, Any]) -> str:
    lines = [
        "# Parser Repair Agent Evaluation",
        "",
        f"Paper count: {data['summary']['paper_count']}",
        f"Mean score: {data['summary']['mean_score']}",
        "",
        "| Paper | Score | Targets | Covered | Mitigated | Guidance | Unmitigated |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in data["results"]:
        unmitigated = ", ".join(item["unmitigated_finding_ids"]) or "none"
        lines.append(
            "| {paper_id} | {score:.1f} | {target_finding_count} | {covered_count} | "
            "{mitigated_count} | {guided_count} | {unmitigated} |".format(
                **item, unmitigated=unmitigated
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Score parser repair plans against parser-quality findings.")
    parser.add_argument("--papers", nargs="+", required=True)
    parser.add_argument("--work-root", default="work")
    parser.add_argument("--repair-root", default="work/experiments/parser-repair-agent")
    parser.add_argument("--output-json", default="work/evaluations/parser_repair_agent.json")
    parser.add_argument("--output-md", default="work/evaluations/parser_repair_agent.md")
    args = parser.parse_args()

    repo = repo_root()
    work_root = Path(args.work_root)
    if not work_root.is_absolute():
        work_root = repo / work_root
    repair_root = Path(args.repair_root)
    if not repair_root.is_absolute():
        repair_root = repo / repair_root

    results: list[dict[str, Any]] = []
    for paper_id in args.papers:
        parser_quality = read_json(work_root / paper_id / "reviews" / "parser_quality_auditor.json", {})
        plan = read_json(repair_root / paper_id / "repair" / "parser_repair_plan.json")
        metrics = evaluate_plan(parser_quality, plan)
        metrics["paper_id"] = paper_id
        results.append(metrics)

    data = {"summary": aggregate(results), "results": results}
    output_json = repo / args.output_json if not Path(args.output_json).is_absolute() else Path(args.output_json)
    output_md = repo / args.output_md if not Path(args.output_md).is_absolute() else Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(markdown_report(data), encoding="utf-8")
    print(json.dumps(data["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
