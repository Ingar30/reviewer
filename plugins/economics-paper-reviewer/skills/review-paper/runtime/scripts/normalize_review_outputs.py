from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from reviewer_config import ReviewerConfig, load_reviewers_config

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}
ASSESSMENT_RANK = {"yes": 1, "cannot_verify": 2, "partially": 3, "no": 4}
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}
ISSUE_CLASSES = {
    "manuscript_issue",
    "parser_artifact",
    "reference_integrity",
    "bibliography_maintenance",
    "copyedit_issue",
    "cannot_verify",
}
PROCESS_NOTE_RE = re.compile(
    r"\b(?:skill|tool|session|local checks|no files were written|no files were edited)\b",
    re.IGNORECASE,
)
SEMANTIC_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "been", "being",
    "abstract", "body", "by", "conclusion", "does", "even", "for", "from",
    "has", "have", "in", "into", "is", "it", "its", "itself", "manuscript",
    "of", "on", "only", "or", "paper", "result", "results", "study", "table",
    "that", "the", "their", "this", "though", "to", "was", "were", "which",
    "while", "with", "wording",
}
LOCATOR_RE = re.compile(
    r"\b(?P<kind>tables?|figures?|equations?|eqs?\.?|columns?|cols?\.?|panels?|"
    r"appendix|appendices|sections?|pages?|experiments?)\s*"
    r"(?:\(\s*)?(?P<label>(?:[a-z]\.?)?\d+(?:\.\d+)*(?:[a-z])?)(?:\s*\))?"
    r"(?:\s*[-\u2013\u2014]\s*(?:[a-z]\.?)?\d+(?:\.\d+)*(?:[a-z])?)?",
    re.IGNORECASE,
)
QUESTION_RE = re.compile(r"\bq(?:uestion)?\s*(?P<label>\d+(?:\.\d+)*)\b", re.IGNORECASE)
NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<open>\()?\s*(?P<sign>[+\-\u2212])?\s*"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"(?P<unit>\s*%|\s+percentage\s+points?|\s+percent(?:age)?)?"
    r"\s*(?P<close>\))?(?![A-Za-z0-9_])"
)
DIRECTION_WORDS = {
    "positive": "up",
    "positively": "up",
    "increase": "up",
    "increases": "up",
    "increased": "up",
    "increasing": "up",
    "higher": "up",
    "larger": "up",
    "greater": "up",
    "above": "up",
    "overstate": "up",
    "overstates": "up",
    "overstated": "up",
    "overstatement": "up",
    "upward": "up",
    "rise": "up",
    "rises": "up",
    "rising": "up",
    "negative": "down",
    "negatively": "down",
    "decrease": "down",
    "decreases": "down",
    "decreased": "down",
    "decreasing": "down",
    "lower": "down",
    "smaller": "down",
    "less": "down",
    "below": "down",
    "understate": "down",
    "understates": "down",
    "understated": "down",
    "understatement": "down",
    "downward": "down",
    "decline": "down",
    "declines": "down",
    "declining": "down",
}
SINGLE_ANCHOR_STRONG_SCORE = 0.72


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


def canonical_locator_kind(kind: str) -> str:
    normalized = kind.lower().rstrip(".")
    if normalized.startswith("tab"):
        return "table"
    if normalized.startswith("fig"):
        return "figure"
    if normalized.startswith(("equation", "eq")):
        return "equation"
    if normalized.startswith(("column", "col")):
        return "column"
    if normalized.startswith("panel"):
        return "panel"
    if normalized.startswith("append"):
        return "appendix"
    if normalized.startswith("section"):
        return "section"
    if normalized.startswith("page"):
        return "page"
    return "experiment"


def structured_locators(text: str | None) -> tuple[dict[str, set[str]], list[tuple[int, int]]]:
    value = text or ""
    locators: dict[str, set[str]] = {}
    spans: list[tuple[int, int]] = []
    for match in LOCATOR_RE.finditer(value):
        kind = canonical_locator_kind(match.group("kind"))
        label = match.group("label").lower().replace(" ", "")
        locators.setdefault(kind, set()).add(label)
        spans.append(match.span())
    for match in QUESTION_RE.finditer(value):
        locators.setdefault("question", set()).add(match.group("label"))
        spans.append(match.span())
    return locators, spans


def normalized_magnitude(value: str, unit: str | None) -> str:
    normalized = value.replace(",", "")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    normalized = normalized.lstrip("0")
    if not normalized:
        normalized = "0"
    elif normalized.startswith("."):
        normalized = "0" + normalized
    normalized_unit = (unit or "").strip().lower()
    if "point" in normalized_unit:
        normalized += "pp"
    elif normalized_unit:
        normalized += "%"
    return normalized


def numeric_signature(text: str | None) -> list[tuple[str, str | None]]:
    value = text or ""
    _locators, locator_spans = structured_locators(value)
    signature = []
    for match in NUMBER_RE.finditer(value):
        if any(match.start() < end and match.end() > start for start, end in locator_spans):
            continue
        following = value[match.end():].lstrip()
        if re.match(r"[+*/^]\s*[a-z]", following, re.IGNORECASE):
            continue
        sign = match.group("sign")
        if sign == "\u2212":
            sign = "-"
        signature.append(
            (
                normalized_magnitude(match.group("number"), match.group("unit")),
                sign,
            )
        )
    return signature


def direction_signature(text: str | None) -> set[str]:
    words = re.findall(r"[a-z]+", (text or "").lower())
    return {direction for word in words if (direction := DIRECTION_WORDS.get(word))}


def explicit_text_conflict(left: str | None, right: str | None) -> bool:
    left_locators, _left_spans = structured_locators(left)
    right_locators, _right_spans = structured_locators(right)
    for kind in set(left_locators) & set(right_locators):
        if left_locators[kind].isdisjoint(right_locators[kind]):
            return True

    left_numbers = numeric_signature(left)
    right_numbers = numeric_signature(right)
    if left_numbers and right_numbers:
        left_values = {value for value, _sign in left_numbers}
        right_values = {value for value, _sign in right_numbers}
        if left_values.isdisjoint(right_values):
            return True
        if not (left_values <= right_values or right_values <= left_values):
            return True
        left_sequence = [value for value, _sign in left_numbers]
        right_sequence = [value for value, _sign in right_numbers]
        if (
            len(left_sequence) >= 2
            and len(left_sequence) == len(right_sequence)
            and left_values == right_values
            and left_sequence != right_sequence
        ):
            return True
        for value in left_values & right_values:
            left_signs = {sign for number, sign in left_numbers if number == value and sign}
            right_signs = {sign for number, sign in right_numbers if number == value and sign}
            if left_signs and right_signs and left_signs.isdisjoint(right_signs):
                return True
        left_signed = [(value, sign) for value, sign in left_numbers if sign]
        right_signed = [(value, sign) for value, sign in right_numbers if sign]
        if (
            len(left_signed) >= 2
            and [value for value, _sign in left_signed]
            == [value for value, _sign in right_signed]
            and left_signed != right_signed
        ):
            return True

    left_directions = direction_signature(left)
    right_directions = direction_signature(right)
    return bool(
        left_directions
        and right_directions
        and left_directions.isdisjoint(right_directions)
    )


def semantic_tokens(*values: str | None) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", " ".join(comparable_text(value) for value in values))
    normalized = []
    for token in tokens:
        if token in SEMANTIC_STOPWORDS or len(token) < 2:
            continue
        if len(token) > 6 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 6 and token.endswith("ing"):
            token = token[:-3]
        elif len(token) > 5 and token.endswith("ed"):
            token = token[:-2]
        elif len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "is", "us")):
            token = token[:-1]
        normalized.append(token)
    return normalized


def token_cosine(left: list[str], right: list[str]) -> tuple[float, int]:
    if not left or not right:
        return 0.0, 0
    left_counts = Counter(left)
    right_counts = Counter(right)
    shared = set(left_counts) & set(right_counts)
    dot = sum(left_counts[token] * right_counts[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    return dot / (left_norm * right_norm), len(shared)


def finding_summary(finding: dict[str, Any]) -> str:
    summary = finding.get("finding_summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    evidence = finding.get("evidence_summary")
    if isinstance(evidence, str) and evidence.strip():
        return evidence.strip()
    return str(finding.get("claim_text") or "").strip()


def location_page(finding: dict[str, Any]) -> int | None:
    location = finding.get("location") or {}
    page = location.get("page")
    return page if isinstance(page, int) else None


def issue_class(reviewer: ReviewerConfig, finding: dict[str, Any]) -> str:
    explicit = finding.get("issue_type")
    if explicit in ISSUE_CLASSES:
        return explicit
    category = compact_text(finding.get("category"))
    assessment = finding.get("assessment")
    if assessment == "cannot_verify" or "cannot_verify" in category:
        return "cannot_verify"
    if reviewer.normalization_role == "crossref":
        if "parser" in category or "false_positive" in category or "numbering_consistency" in category:
            return "parser_artifact"
        return "manuscript_issue"
    if reviewer.normalization_role == "reference":
        if "outdated" in category or "metadata_typo" in category:
            return "bibliography_maintenance"
        return "reference_integrity"
    if reviewer.normalization_role == "copyedit":
        return "copyedit_issue"
    return "manuscript_issue"


def merge_anchor(
    reviewer: str, finding: dict[str, Any], klass: str
) -> dict[str, Any]:
    return {
        "reviewer": reviewer,
        "issue_class": klass,
        "page": location_page(finding),
        "finding_summary": finding_summary(finding),
        "claim_text": finding.get("claim_text"),
        "quote": (finding.get("location") or {}).get("text_quote"),
    }


def pair_merge_score(
    anchor: dict[str, Any], reviewer: str, finding: dict[str, Any], klass: str
) -> float | None:
    if anchor.get("issue_class") != klass or anchor.get("reviewer") == reviewer:
        return None
    page = location_page(finding)
    anchor_page = anchor.get("page")
    if page is not None and anchor_page is not None and page != anchor_page:
        return None

    summary = finding_summary(finding)
    claim = finding.get("claim_text")
    anchor_summary = anchor.get("finding_summary")
    anchor_claim = anchor.get("claim_text")
    if explicit_text_conflict(anchor_summary, summary) or explicit_text_conflict(anchor_claim, claim):
        return None
    summary_similarity = similarity(anchor_summary, summary)
    claim_similarity = similarity(anchor_claim, claim)
    summary_cosine, summary_shared = token_cosine(
        semantic_tokens(anchor_summary), semantic_tokens(summary)
    )
    combined_cosine, combined_shared = token_cosine(
        semantic_tokens(anchor_summary, anchor_claim), semantic_tokens(summary, claim)
    )

    eligible = (
        summary_similarity >= 0.72
        or (
            summary_cosine >= 0.38
            and summary_shared >= 4
            and (
                summary_similarity >= 0.32
                or summary_shared >= 6
                or combined_cosine >= 0.75
            )
        )
        or (combined_cosine >= 0.55 and combined_shared >= 8)
        or (
            claim_similarity >= 0.85
            and combined_cosine >= 0.45
            and combined_shared >= 8
            and summary_cosine >= 0.25
            and summary_shared >= 3
        )
    )
    if not eligible:
        return None
    return max(
        summary_similarity,
        summary_cosine,
        combined_cosine,
        claim_similarity * 0.95,
    )


def group_merge_score(
    group: dict[str, Any], reviewer: str, finding: dict[str, Any], klass: str
) -> float | None:
    if reviewer in group.get("source_reviewers", []):
        return None
    anchors = group.get("_merge_anchors")
    if not anchors:
        anchors = [
            {
                "reviewer": (group.get("source_reviewers") or [None])[0],
                "issue_class": group.get("issue_class"),
                "page": (group.get("primary_location") or {}).get("page"),
                "finding_summary": group.get("finding_summary"),
                "claim_text": group.get("claim_text"),
                "quote": group.get("primary_quote"),
            }
        ]
    summary = finding_summary(finding)
    claim = finding.get("claim_text")
    if any(
        explicit_text_conflict(anchor.get("finding_summary"), summary)
        or explicit_text_conflict(anchor.get("claim_text"), claim)
        for anchor in anchors
    ):
        return None
    page = location_page(finding)
    known_pages = {
        anchor.get("page") for anchor in anchors if isinstance(anchor.get("page"), int)
    }
    if page is not None and known_pages and page not in known_pages:
        return None
    scores = [
        score
        for anchor in anchors
        if (score := pair_merge_score(anchor, reviewer, finding, klass)) is not None
    ]
    if (
        len(anchors) >= 2
        and len(scores) == 1
        and scores[0] < SINGLE_ANCHOR_STRONG_SCORE
    ):
        return None
    return max(scores) if scores else None


def should_merge(group: dict[str, Any], reviewer: str, finding: dict[str, Any], klass: str) -> bool:
    return group_merge_score(group, reviewer, finding, klass) is not None


def stronger_severity(left: str, right: str) -> str:
    return left if SEVERITY_RANK.get(left, 0) >= SEVERITY_RANK.get(right, 0) else right


def stronger_assessment(left: str, right: str) -> str:
    return left if ASSESSMENT_RANK.get(left, 0) >= ASSESSMENT_RANK.get(right, 0) else right


def weaker_confidence(left: str, right: str) -> str:
    return left if CONFIDENCE_RANK.get(left, 2) <= CONFIDENCE_RANK.get(right, 2) else right


def add_to_group(group: dict[str, Any], reviewer: str, finding: dict[str, Any]) -> None:
    finding_id = finding["id"]
    location = finding.get("location") or {}
    group["_merge_anchors"].append(
        merge_anchor(reviewer, finding, group["issue_class"])
    )
    group["source_findings"].append({"reviewer": reviewer, "id": finding_id})
    group["source_finding_details"].append(
        {
            "reviewer": reviewer,
            "id": finding_id,
            "category": finding.get("category"),
            "issue_type": finding.get("issue_type"),
            "finding_summary": finding_summary(finding),
            "claim_text": finding.get("claim_text"),
            "evidence_summary": finding.get("evidence_summary"),
            "severity": finding.get("severity"),
            "assessment": finding.get("assessment"),
            "confidence": finding.get("confidence"),
            "cannot_verify_reason": finding.get("cannot_verify_reason"),
            "location": location,
        }
    )
    if reviewer not in group["source_reviewers"]:
        group["source_reviewers"].append(reviewer)
    if finding.get("category") not in group["categories"]:
        group["categories"].append(finding.get("category"))
    group["source_assessments"].append(
        {"reviewer": reviewer, "id": finding_id, "assessment": finding.get("assessment")}
    )
    group["severity"] = stronger_severity(group["severity"], finding.get("severity", "low"))
    group["assessment"] = stronger_assessment(group["assessment"], finding.get("assessment", "yes"))
    group["confidence"] = weaker_confidence(group["confidence"], finding.get("confidence", "medium"))
    if location and location not in group["locations"]:
        group["locations"].append(location)
    if location.get("text_quote") and location.get("text_quote") not in group["quotes"]:
        group["quotes"].append(location.get("text_quote"))
    if finding.get("evidence_summary"):
        group["evidence_summaries"].append(
            {"reviewer": reviewer, "id": finding_id, "text": finding["evidence_summary"]}
        )
    if finding.get("cannot_verify_reason"):
        group["cannot_verify_reasons"].append(
            {"reviewer": reviewer, "id": finding_id, "text": finding["cannot_verify_reason"]}
        )
    for source_object in finding.get("source_objects", []) or []:
        group["source_objects"].append({"reviewer": reviewer, "id": finding_id, "source_object": source_object})
    for link in finding.get("claim_evidence_links", []) or []:
        group["claim_evidence_links"].append({"reviewer": reviewer, "id": finding_id, "link": link})
    if finding.get("numeric_check"):
        group["numeric_checks"].append({"reviewer": reviewer, "id": finding_id, "numeric_check": finding["numeric_check"]})
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
        "confidence": finding.get("confidence", "medium"),
        "source_reviewers": [],
        "source_findings": [],
        "source_finding_details": [],
        "categories": [],
        "finding_summary": finding_summary(finding),
        "claim_text": finding.get("claim_text", ""),
        "primary_location": location,
        "primary_quote": location.get("text_quote"),
        "locations": [],
        "quotes": [],
        "evidence_summaries": [],
        "cannot_verify_reasons": [],
        "source_objects": [],
        "claim_evidence_links": [],
        "numeric_checks": [],
        "suggested_fixes": [],
        "source_assessments": [],
        "_merge_anchors": [],
    }
    add_to_group(group, reviewer, finding)
    return group


def normalize(paper_id: str, reviews_dir: Path, reviewers: list[ReviewerConfig]) -> dict[str, Any]:
    missing = [reviewer.output for reviewer in reviewers if not (reviews_dir / reviewer.output).exists()]
    if missing:
        raise FileNotFoundError(f"Missing reviewer outputs in {reviews_dir}: {', '.join(missing)}")

    reviewer_outputs = []
    groups: list[dict[str, Any]] = []
    pending_findings: list[tuple[str, dict[str, Any], str]] = []
    process_notes_removed = 0

    for reviewer_config in reviewers:
        path = reviews_dir / reviewer_config.output
        data = read_json(path)
        reviewer = data.get("reviewer")
        if reviewer != reviewer_config.name:
            raise ValueError(f"{path} has reviewer={reviewer!r}, expected {reviewer_config.name!r}")
        if data.get("paper_id") != paper_id:
            raise ValueError(f"{path} has paper_id={data.get('paper_id')!r}, expected {paper_id!r}")
        retained_notes = [
            note
            for note in data.get("notes", [])
            if not PROCESS_NOTE_RE.search(note)
        ]
        process_notes_removed += len(data.get("notes", [])) - len(retained_notes)
        reviewer_outputs.append(
            {
                "reviewer": reviewer,
                "path": str(path.as_posix()),
                "run_status": data.get("run_status"),
                "finding_count": len(data.get("findings", [])),
                "summary": data.get("summary"),
                "notes": retained_notes,
            }
        )

        for finding in data.get("findings", []):
            klass = issue_class(reviewer_config, finding)
            pending_findings.append((reviewer, finding, klass))

    pending_findings.sort(
        key=lambda item: (
            item[2],
            location_page(item[1]) if location_page(item[1]) is not None else 1_000_000,
            item[0],
            str(item[1].get("id") or ""),
        )
    )
    for reviewer, finding, klass in pending_findings:
        candidates = []
        for index, group in enumerate(groups):
            score = group_merge_score(group, reviewer, finding, klass)
            if score is not None:
                candidates.append((score, -index, group))
        if candidates:
            _score, _tie_breaker, target = max(candidates, key=lambda item: (item[0], item[1]))
            add_to_group(target, reviewer, finding)
        else:
            groups.append(new_group(reviewer, finding, klass))

    class_counts = Counter(group["issue_class"] for group in groups)
    severity_counts = Counter(group["severity"] for group in groups)

    class_order = {
        "manuscript_issue": 0,
        "reference_integrity": 1,
        "cannot_verify": 2,
        "bibliography_maintenance": 3,
        "parser_artifact": 4,
        "copyedit_issue": 5,
    }
    groups.sort(
        key=lambda group: (
            class_order.get(group["issue_class"], 99),
            -SEVERITY_RANK.get(group["severity"], 0),
            group["source_findings"][0]["id"],
        )
    )
    for index, group in enumerate(groups, start=1):
        group.pop("_merge_anchors", None)
        group["canonical_id"] = f"CANON-{index:03d}"
        assessment_counts = Counter(
            item.get("assessment") for item in group.get("source_assessments", [])
        )
        group["assessment_counts"] = {
            str(key): value for key, value in assessment_counts.items() if key is not None
        }
        group["assessment_consensus"] = (
            "agreed" if len(group["assessment_counts"]) <= 1 else "mixed"
        )

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
    parser.add_argument("--reviewers-config", default="config/reviewers.json")
    args = parser.parse_args()

    reviewers = load_reviewers_config(args.reviewers_config)
    bundle = normalize(args.paper_id, Path(args.reviews_dir), reviewers)
    write_json(Path(args.output), bundle)
    print(f"Wrote normalized bundle: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
