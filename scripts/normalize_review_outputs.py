from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


REVIEWER_FILES = [
    "crossref_auditor.json",
    "numerical_auditor.json",
    "claim_evidence_auditor.json",
    "literature_auditor.json",
    "reference_auditor.json",
]

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}
ASSESSMENT_RANK = {"yes": 1, "cannot_verify": 2, "partially": 3, "no": 4}
PROCESS_NOTE_RE = re.compile(
    r"\b(?:skill|tool|session|local checks|no files were written|no files were edited|requested custom agent)\b",
    re.IGNORECASE,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def compact_text(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def comparable_text(value: str | None) -> str:
    text = compact_text(value)
    text = re.sub(r"[^a-z0-9.%]+", " ", text)
    return " ".join(text.split())


def similarity(a: str | None, b: str | None) -> float:
    left = comparable_text(a)
    right = comparable_text(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def location_page(finding: dict[str, Any]) -> int | None:
    location = finding.get("location") or {}
    page = location.get("page")
    return page if isinstance(page, int) else None


def issue_class(reviewer: str, finding: dict[str, Any]) -> str:
    category = compact_text(finding.get("category"))
    assessment = finding.get("assessment")
    if assessment == "cannot_verify" or "cannot_verify" in category:
        return "cannot_verify"
    if reviewer == "crossref_auditor":
        if "parser" in category or "false_positive" in category or "numbering_consistency" in category:
            return "parser_artifact"
        return "manuscript_issue"
    if reviewer == "reference_auditor":
        if "outdated" in category or "metadata_typo" in category:
            return "bibliography_maintenance"
        return "reference_integrity"
    return "manuscript_issue"


def should_merge(group: dict[str, Any], reviewer: str, finding: dict[str, Any], klass: str) -> bool:
    if group["issue_class"] != klass:
        return False
    page = location_page(finding)
    group_pages = {loc.get("page") for loc in group["locations"]}
    if page is not None and group_pages and page not in group_pages:
        return False

    claim = finding.get("claim_text")
    quote = (finding.get("location") or {}).get("text_quote")
    claim_similarity = similarity(group.get("claim_text"), claim)
    quote_similarity = similarity(group.get("primary_quote"), quote)
    if reviewer in group.get("source_reviewers", []):
        return claim_similarity >= 0.85 or quote_similarity >= 0.85

    if claim_similarity >= 0.52:
        return True
    if quote_similarity >= 0.62:
        return True

    categories = " ".join(group.get("categories", []))
    new_category = compact_text(finding.get("category"))
    numeric_overlap = any(token in categories for token in ["numeric", "sign", "table_text"])
    numeric_overlap = numeric_overlap and any(token in new_category for token in ["numeric", "sign", "table_text"])
    return bool(numeric_overlap and page is not None and page in group_pages)


def stronger_severity(left: str, right: str) -> str:
    return left if SEVERITY_RANK.get(left, 0) >= SEVERITY_RANK.get(right, 0) else right


def stronger_assessment(left: str, right: str) -> str:
    return left if ASSESSMENT_RANK.get(left, 0) >= ASSESSMENT_RANK.get(right, 0) else right


def add_to_group(group: dict[str, Any], reviewer: str, finding: dict[str, Any]) -> None:
    finding_id = finding["id"]
    location = finding.get("location") or {}
    group["source_findings"].append({"reviewer": reviewer, "id": finding_id})
    if reviewer not in group["source_reviewers"]:
        group["source_reviewers"].append(reviewer)
    if finding.get("category") not in group["categories"]:
        group["categories"].append(finding.get("category"))
    group["severity"] = stronger_severity(group["severity"], finding.get("severity", "low"))
    group["assessment"] = stronger_assessment(group["assessment"], finding.get("assessment", "yes"))
    if location and location not in group["locations"]:
        group["locations"].append(location)
    if location.get("text_quote") and location.get("text_quote") not in group["quotes"]:
        group["quotes"].append(location.get("text_quote"))
    if finding.get("evidence_summary"):
        group["evidence_summaries"].append(
            {"reviewer": reviewer, "id": finding_id, "text": finding["evidence_summary"]}
        )
    if finding.get("suggested_fix"):
        group["suggested_fixes"].append(
            {"reviewer": reviewer, "id": finding_id, "text": finding["suggested_fix"]}
        )


def new_group(reviewer: str, finding: dict[str, Any], klass: str) -> dict[str, Any]:
    location = finding.get("location") or {}
    group = {
        "canonical_id": "",
        "issue_class": klass,
        "severity": finding.get("severity", "low"),
        "assessment": finding.get("assessment", "yes"),
        "source_reviewers": [],
        "source_findings": [],
        "categories": [],
        "claim_text": finding.get("claim_text", ""),
        "primary_location": location,
        "primary_quote": location.get("text_quote"),
        "locations": [],
        "quotes": [],
        "evidence_summaries": [],
        "suggested_fixes": [],
    }
    add_to_group(group, reviewer, finding)
    return group


def normalize(paper_id: str, reviews_dir: Path) -> dict[str, Any]:
    missing = [filename for filename in REVIEWER_FILES if not (reviews_dir / filename).exists()]
    if missing:
        raise FileNotFoundError(f"Missing reviewer outputs in {reviews_dir}: {', '.join(missing)}")

    reviewer_outputs = []
    groups: list[dict[str, Any]] = []
    process_notes_removed = 0

    for filename in REVIEWER_FILES:
        path = reviews_dir / filename
        data = read_json(path)
        reviewer = data.get("reviewer")
        if data.get("paper_id") != paper_id:
            raise ValueError(f"{path} has paper_id={data.get('paper_id')!r}, expected {paper_id!r}")
        reviewer_outputs.append(
            {
                "reviewer": reviewer,
                "path": str(path.as_posix()),
                "run_status": data.get("run_status"),
                "finding_count": len(data.get("findings", [])),
            }
        )
        process_notes_removed += sum(1 for note in data.get("notes", []) if PROCESS_NOTE_RE.search(note))

        for finding in data.get("findings", []):
            klass = issue_class(reviewer, finding)
            target = next((group for group in groups if should_merge(group, reviewer, finding, klass)), None)
            if target is None:
                groups.append(new_group(reviewer, finding, klass))
            else:
                add_to_group(target, reviewer, finding)

    class_counts = Counter(group["issue_class"] for group in groups)
    severity_counts = Counter(group["severity"] for group in groups)

    class_order = {
        "manuscript_issue": 0,
        "reference_integrity": 1,
        "cannot_verify": 2,
        "bibliography_maintenance": 3,
        "parser_artifact": 4,
    }
    groups.sort(
        key=lambda group: (
            class_order.get(group["issue_class"], 99),
            -SEVERITY_RANK.get(group["severity"], 0),
            group["source_findings"][0]["id"],
        )
    )
    for index, group in enumerate(groups, start=1):
        group["canonical_id"] = f"CANON-{index:03d}"

    return {
        "paper_id": paper_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_reviewer_outputs": reviewer_outputs,
        "summary": {
            "canonical_finding_count": len(groups),
            "issue_class_counts": dict(class_counts),
            "severity_counts": dict(severity_counts),
            "process_notes_removed": process_notes_removed,
        },
        "canonical_findings": groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize and deduplicate reviewer JSON outputs.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--reviews-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    bundle = normalize(args.paper_id, Path(args.reviews_dir))
    write_json(Path(args.output), bundle)
    print(f"Wrote normalized bundle: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
