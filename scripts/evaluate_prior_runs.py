from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from check_final_report import report_failures


PILOT_REVIEWERS = {
    "data_availability_replication_auditor",
    "institutional_context_auditor",
    "power_multiple_testing_auditor",
    "design_randomization_auditor",
    "economic_magnitude_auditor",
}


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def score_from_penalties(*penalties: float) -> float:
    return max(0.0, min(100.0, 100.0 - sum(penalties)))


def page_quality_metrics(repo: Path, paper_id: str, parsed_dir: Path) -> dict[str, Any]:
    manifest = read_json(parsed_dir / "manifest.json", {})
    manifest_quality = (manifest.get("summary") or {}).get("page_quality") or {}
    page_index = read_json(parsed_dir / "page_index.json", [])
    low_text_pages = []
    unstable_order_pages = []
    raw_norm_ratios = []
    chars = []
    scanned_pages = []

    for page in page_index:
        page_num = page.get("pdf_page_number")
        char_count = page.get("extracted_char_count") or 0
        chars.append(char_count)
        if page.get("likely_scanned"):
            scanned_pages.append(page_num)
        if char_count < 250 and not page.get("likely_scanned"):
            low_text_pages.append(page_num)

        raw_path = repo / str(page.get("raw_text_path", ""))
        normalized_path = repo / str(page.get("normalized_text_path", ""))
        raw = read_text(raw_path)
        normalized = read_text(normalized_path)
        if raw and normalized:
            ratio = len(normalized) / max(len(raw), 1)
            raw_norm_ratios.append(ratio)
            raw_lines = max(1, len([line for line in raw.splitlines() if line.strip()]))
            norm_lines = max(1, len([line for line in normalized.splitlines() if line.strip()]))
            if norm_lines > raw_lines * 2.25 and len(normalized) > 1000:
                unstable_order_pages.append(page_num)

    page_count = len(page_index)
    avg_chars = statistics.mean(chars) if chars else 0
    median_ratio = statistics.median(raw_norm_ratios) if raw_norm_ratios else 1.0
    if manifest_quality:
        low_text_pages = manifest_quality.get("low_text_pages", low_text_pages)
        unstable_order_pages = manifest_quality.get("suspicious_order_pages", unstable_order_pages)
        median_ratio = manifest_quality.get("raw_normalized_char_ratio_median", median_ratio)
    score = score_from_penalties(
        4.0 * len(low_text_pages),
        3.0 * len(unstable_order_pages),
        1.5 * len(scanned_pages),
        20.0 if median_ratio < 0.65 or median_ratio > 1.35 else 0.0,
    )
    return {
        "page_count": page_count,
        "avg_extracted_chars": round(avg_chars, 1),
        "likely_scanned_pages": scanned_pages,
        "low_text_pages": low_text_pages,
        "sparse_plausible_pages": manifest_quality.get("sparse_plausible_pages", []),
        "unstable_order_pages": unstable_order_pages,
        "raw_normalized_char_ratio_median": round(median_ratio, 3),
        "score": round(score, 1),
    }


def caption_metrics(parsed_dir: Path) -> dict[str, Any]:
    tables = read_json(parsed_dir / "tables" / "table_inventory.json", [])
    figures = read_json(parsed_dir / "figures" / "figure_inventory.json", [])
    table_sources = Counter(item.get("source", "unknown") for item in tables)
    figure_sources = Counter(item.get("source", "unknown") for item in figures)
    raw_caption_count = table_sources.get("caption_text_fallback_raw_text", 0) + figure_sources.get(
        "raw_text_caption_fallback", 0
    )
    precise_caption_count = sum(1 for item in tables if item.get("source") == "caption_text_fallback")
    precise_caption_count += sum(1 for item in figures if item.get("source") == "caption")
    total_captioned = len(tables) + len(figures)
    table_parse_ok = sum(1 for item in tables if item.get("row_count", 0) > 0 and item.get("col_count", 0) > 0)
    parsed_table_ratio = table_parse_ok / len(tables) if tables else 1.0
    raw_ratio = raw_caption_count / total_captioned if total_captioned else 0.0
    score = score_from_penalties(35.0 * raw_ratio, 25.0 * (1.0 - parsed_table_ratio))
    return {
        "table_count": len(tables),
        "figure_count": len(figures),
        "table_sources": dict(table_sources),
        "figure_sources": dict(figure_sources),
        "raw_caption_fallback_count": raw_caption_count,
        "precise_caption_count": precise_caption_count,
        "parsed_table_ratio": round(parsed_table_ratio, 3),
        "score": round(score, 1),
    }


def normalization_metrics(editor_dir: Path) -> dict[str, Any]:
    bundle = read_json(editor_dir / "normalized_bundle.json", {})
    source_outputs = bundle.get("source_reviewer_outputs", [])
    source_findings = sum(item.get("finding_count", 0) for item in source_outputs)
    canonical = bundle.get("canonical_findings", [])
    cross_agent = sum(1 for finding in canonical if len(finding.get("source_reviewers", [])) > 1)
    merge_ratio = len(canonical) / source_findings if source_findings else 1.0
    cross_agent_ratio = cross_agent / len(canonical) if canonical else 0.0
    issue_class_counts = bundle.get("summary", {}).get("issue_class_counts", {})
    score = score_from_penalties(
        20.0 if source_findings and merge_ratio > 0.95 else 0.0,
        10.0 if source_findings and cross_agent_ratio < 0.05 else 0.0,
    )
    return {
        "source_finding_count": source_findings,
        "canonical_finding_count": len(canonical),
        "merge_ratio": round(merge_ratio, 3),
        "cross_agent_group_count": cross_agent,
        "cross_agent_ratio": round(cross_agent_ratio, 3),
        "issue_class_counts": issue_class_counts,
        "score": round(score, 1),
    }


def report_metrics(report_path: Path, editor_dir: Path) -> dict[str, Any]:
    text = read_text(report_path)
    bundle = read_json(editor_dir / "normalized_bundle.json", {})
    failures = report_failures(text, bundle=bundle) if text else ["report missing"]
    has_external_sources = "## Appendix: External Sources" in text
    external_evidence_count = 0
    for finding in bundle.get("canonical_findings", []):
        for source in finding.get("source_objects", []):
            source_object = source.get("source_object") or {}
            if source_object.get("url"):
                external_evidence_count += 1
    score = score_from_penalties(15.0 * len(failures), 15.0 if external_evidence_count and not has_external_sources else 0.0)
    return {
        "report_chars": len(text.strip()),
        "failures": failures,
        "has_external_sources_appendix": has_external_sources,
        "external_source_object_count": external_evidence_count,
        "score": round(score, 1),
    }


def selector_metrics(selection_dir: Path, editor_dir: Path) -> dict[str, Any]:
    selection = read_json(selection_dir / "reviewer_selection.json", {})
    selected_optional = [item.get("name") for item in selection.get("selected_optional_reviewers", []) if item.get("name")]
    pilot_selected = [name for name in selected_optional if name in PILOT_REVIEWERS]
    bundle = read_json(editor_dir / "normalized_bundle.json", {})
    zero_finding_selected = []
    for output in bundle.get("source_reviewer_outputs", []):
        name = output.get("reviewer")
        if name in selected_optional and output.get("finding_count", 0) == 0:
            zero_finding_selected.append(name)
    optional_count = len(selected_optional)
    score = score_from_penalties(
        max(0, optional_count - 9) * 4.0,
        len(pilot_selected) * 2.0,
        len(zero_finding_selected) * 8.0,
    )
    return {
        "paper_type": selection.get("paper_type"),
        "selection_confidence": selection.get("selection_confidence"),
        "selected_optional_count": optional_count,
        "pilot_selected": pilot_selected,
        "zero_finding_selected_optional": zero_finding_selected,
        "score": round(score, 1),
    }


def resume_metrics(paper_root: Path) -> dict[str, Any]:
    required = {
        "parsed_manifest": paper_root / "parsed" / "manifest.json",
        "selection": paper_root / "selection" / "selected_reviewers.json",
        "reviews": paper_root / "reviews",
        "normalized_bundle": paper_root / "editor" / "normalized_bundle.json",
        "editor_input": paper_root / "editor" / "editor_input.md",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    review_json_count = len(list((paper_root / "reviews").glob("*.json"))) if (paper_root / "reviews").exists() else 0
    score = score_from_penalties(18.0 * len(missing), 20.0 if review_json_count == 0 else 0.0)
    return {"missing_resume_artifacts": missing, "review_json_count": review_json_count, "score": round(score, 1)}


def evaluate_paper(repo: Path, paper_id: str, work_root: Path | None = None, outputs_root: Path | None = None) -> dict[str, Any]:
    paper_root = (work_root or repo / "work") / paper_id
    parsed_dir = paper_root / "parsed"
    output_report = (outputs_root or repo / "outputs") / paper_id / "report.md"
    metrics = {
        "paper_id": paper_id,
        "preprocessing": page_quality_metrics(repo, paper_id, parsed_dir),
        "caption_extraction": caption_metrics(parsed_dir),
        "normalization": normalization_metrics(paper_root / "editor"),
        "report_checking": report_metrics(output_report, paper_root / "editor"),
        "selector_breadth": selector_metrics(paper_root / "selection", paper_root / "editor"),
        "resume_readiness": resume_metrics(paper_root),
    }
    metrics["overall_score"] = round(
        statistics.mean(section["score"] for key, section in metrics.items() if isinstance(section, dict) and "score" in section),
        1,
    )
    return metrics


def available_papers(root: Path) -> list[str]:
    return sorted(path.name for path in root.glob("paper*") if path.is_dir())


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    sections = [
        "preprocessing",
        "caption_extraction",
        "normalization",
        "report_checking",
        "selector_breadth",
        "resume_readiness",
    ]
    return {
        "paper_count": len(results),
        "section_scores": {
            section: round(statistics.mean(item[section]["score"] for item in results), 1) if results else 0.0
            for section in sections
        },
        "overall_score": round(statistics.mean(item["overall_score"] for item in results), 1) if results else 0.0,
    }


def markdown_report(data: dict[str, Any]) -> str:
    lines = [
        "# Prior Run Evaluation",
        "",
        f"Paper count: {data['summary']['paper_count']}",
        "",
        "## Section Scores",
        "",
        "| Section | Mean score |",
        "| --- | ---: |",
    ]
    for section, score in data["summary"]["section_scores"].items():
        lines.append(f"| {section} | {score:.1f} |")
    lines.extend(
        [
            f"| overall | {data['summary']['overall_score']:.1f} |",
            "",
            "## Paper Scores",
            "",
            "| Paper | Overall | Preprocess | Captions | Normalize | Report | Selector | Resume |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in data["papers"]:
        lines.append(
            "| {paper_id} | {overall_score:.1f} | {pre:.1f} | {cap:.1f} | {norm:.1f} | {rep:.1f} | {sel:.1f} | {res:.1f} |".format(
                paper_id=item["paper_id"],
                overall_score=item["overall_score"],
                pre=item["preprocessing"]["score"],
                cap=item["caption_extraction"]["score"],
                norm=item["normalization"]["score"],
                rep=item["report_checking"]["score"],
                sel=item["selector_breadth"]["score"],
                res=item["resume_readiness"]["score"],
            )
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate prior actual reviewer runs against limitation-oriented metrics.")
    parser.add_argument("--papers", nargs="*", default=None, help="Paper IDs to evaluate; defaults to work/paper*.")
    parser.add_argument("--work-root", default="work", help="Root containing paper work directories.")
    parser.add_argument("--outputs-root", default="outputs", help="Root containing paper report directories.")
    parser.add_argument("--output-json", default="work/evaluations/prior_run_evaluation.json")
    parser.add_argument("--output-md", default="work/evaluations/prior_run_evaluation.md")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    work_root = Path(args.work_root)
    if not work_root.is_absolute():
        work_root = repo / work_root
    outputs_root = Path(args.outputs_root)
    if not outputs_root.is_absolute():
        outputs_root = repo / outputs_root
    papers = args.papers or available_papers(work_root)
    results = [evaluate_paper(repo, paper_id, work_root=work_root, outputs_root=outputs_root) for paper_id in papers]
    data = {"summary": aggregate(results), "papers": results}

    output_json = repo / args.output_json
    output_md = repo / args.output_md
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(markdown_report(data), encoding="utf-8")
    print(f"wrote {output_json.relative_to(repo)}")
    print(f"wrote {output_md.relative_to(repo)}")
    print(json.dumps(data["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
