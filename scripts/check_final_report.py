from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_REQUIRED_HEADINGS = [
    "## Executive Summary",
    "## Highest-Priority Cross-Agent Findings",
    "## Suggested Revision Priorities",
    "## Additional Findings",
]
REVIEW_SCOPE_HEADINGS = (
    "## Appendix: Review Scope and Limitations",
    "## Review Configuration",
)
GRAMMAR_APPENDIX_HEADING = "## Appendix: Grammar and Copyediting Issues"
TRACEABILITY_APPENDIX_HEADING = "## Appendix: Traceability Map"
EXTERNAL_SOURCES_APPENDIX_RE = re.compile(r"^## Appendix: External Sources", re.MULTILINE)
HEADING_RE = re.compile(r"^## ", re.MULTILINE)
URL_RE = re.compile(r"https?://[^\s<>\]]+")
CANONICAL_ID_RE = re.compile(r"\bCANON-\d{3}\b")
SOURCE_ID_RE = re.compile(
    r"\b[a-z][a-z0-9_]*:(?:[A-Z][A-Z0-9_-]*-\d{3}|claim_evidence_\d{3}|NA-\d{3})\b"
)

META_NOTE_RE = re.compile(
    r"\b(?:done\.|wrote the final|report (?:is|was) saved|saved to|appears only under ignored status)\b",
    re.IGNORECASE,
)


def bundle_has_copyedit_findings(bundle: dict) -> bool:
    return any(
        finding.get("issue_class") == "copyedit_issue"
        for finding in bundle.get("canonical_findings", [])
        if isinstance(finding, dict)
    )


def external_source_urls(bundle: dict) -> set[str]:
    urls = set()
    for finding in bundle.get("canonical_findings", []):
        if not isinstance(finding, dict):
            continue
        for source in finding.get("source_objects", []) or []:
            source_object = source.get("source_object") or {}
            url = source_object.get("url")
            if isinstance(url, str) and url.strip():
                urls.add(url.strip())
    return urls


def urls_in_text(text: str) -> set[str]:
    urls = set()
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:")
        while url.endswith(")") and url.count(")") > url.count("("):
            url = url[:-1]
        if url:
            urls.add(url)
    return urls


def external_sources_appendix_text(text: str) -> str:
    match = EXTERNAL_SOURCES_APPENDIX_RE.search(text)
    if not match:
        return ""
    next_heading = HEADING_RE.search(text, match.end())
    end = next_heading.start() if next_heading else len(text)
    return text[match.start():end]


def heading_section_text(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    next_heading = HEADING_RE.search(text, start + len(heading))
    end = next_heading.start() if next_heading else len(text)
    return text[start:end]


def traceability_failures(text: str, bundle: dict) -> list[str]:
    failures = []
    appendix = heading_section_text(text, TRACEABILITY_APPENDIX_HEADING)
    if not appendix:
        return [f"missing traceability appendix heading: {TRACEABILITY_APPENDIX_HEADING}"]

    body = text.replace(appendix, "", 1)
    if CANONICAL_ID_RE.search(body) or SOURCE_ID_RE.search(body):
        failures.append("canonical and source finding identifiers must appear only in the traceability appendix")

    expected_by_canonical = {}
    expected_source_ids = set()
    for finding in bundle.get("canonical_findings", []):
        if not isinstance(finding, dict):
            continue
        canonical_id = finding.get("canonical_id")
        if not canonical_id:
            continue
        source_ids = {
            f"{source.get('reviewer')}:{source.get('id')}"
            for source in finding.get("source_findings", [])
            if source.get("reviewer") and source.get("id")
        }
        expected_by_canonical[str(canonical_id)] = source_ids
        expected_source_ids.update(source_ids)

    actual_canonical_ids = set(CANONICAL_ID_RE.findall(appendix))
    unknown_canonical_ids = actual_canonical_ids - set(expected_by_canonical)
    for canonical_id in sorted(unknown_canonical_ids):
        failures.append(f"unknown canonical identifier in traceability appendix: {canonical_id}")

    actual_source_ids = set(SOURCE_ID_RE.findall(appendix))
    for source_id in sorted(actual_source_ids - expected_source_ids):
        failures.append(f"unknown source finding identifier in traceability appendix: {source_id}")

    table_rows = [line for line in appendix.splitlines() if line.strip().startswith("|")]
    for canonical_id, expected_sources in expected_by_canonical.items():
        matching_rows = [row for row in table_rows if canonical_id in CANONICAL_ID_RE.findall(row)]
        if not matching_rows:
            failures.append(f"missing canonical identifier from traceability table: {canonical_id}")
            continue
        if len(matching_rows) != 1:
            failures.append(f"canonical identifier must appear in exactly one traceability row: {canonical_id}")
            continue
        row_sources = set(SOURCE_ID_RE.findall(matching_rows[0]))
        for source_id in sorted(expected_sources - row_sources):
            failures.append(f"missing source finding identifier from {canonical_id} row: {source_id}")
        for source_id in sorted(row_sources - expected_sources):
            failures.append(f"source finding identifier is mapped to the wrong canonical row {canonical_id}: {source_id}")
    return failures


def report_failures(text: str, *, bundle: dict | None = None, min_chars: int = 2000) -> list[str]:
    failures = []
    if len(text.strip()) < min_chars:
        failures.append(f"report is too short: {len(text.strip())} chars < {min_chars}")
    if META_NOTE_RE.search(text):
        failures.append("report appears to contain a run-status/meta note")
    for heading in DEFAULT_REQUIRED_HEADINGS:
        if heading not in text:
            failures.append(f"missing required heading: {heading}")
    if not any(heading in text for heading in REVIEW_SCOPE_HEADINGS):
        failures.append(
            "missing review-scope heading: expected Appendix: Review Scope and Limitations "
            "or legacy Review Configuration"
        )
    if not re.search(r"\b(?:CANON-\d{3}|[A-Z]+-[A-Z]+-\d{3}|claim_evidence_\d{3}|NA-\d{3})\b", text):
        failures.append("report does not mention canonical or source finding identifiers")

    if bundle:
        failures.extend(traceability_failures(text, bundle))
        if bundle_has_copyedit_findings(bundle) and GRAMMAR_APPENDIX_HEADING not in text:
            failures.append(f"missing grammar appendix heading: {GRAMMAR_APPENDIX_HEADING}")
        bundle_urls = external_source_urls(bundle)
        appendix = external_sources_appendix_text(text)
        appendix_urls = urls_in_text(appendix)
        body_text = text.replace(appendix, "") if appendix else text
        cited_bundle_urls = urls_in_text(body_text) & bundle_urls
        unknown_urls = urls_in_text(text) - bundle_urls
        for url in sorted(unknown_urls):
            failures.append(f"report cites URL not present in reviewer evidence: {url}")
        if cited_bundle_urls and not appendix:
            failures.append("missing external-sources appendix heading despite external source URLs cited in report")
        for url in sorted(cited_bundle_urls - appendix_urls):
            failures.append(f"missing external source URL from external-sources appendix: {url}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check that an editor output is a real report.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--bundle", default=None, help="Optional normalized bundle for traceability coverage checks.")
    parser.add_argument("--min-chars", type=int, default=2000)
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")

    text = path.read_text(encoding="utf-8")
    bundle = None
    if args.bundle:
        bundle_path = Path(args.bundle)
        if not bundle_path.exists():
            raise FileNotFoundError(f"Bundle not found: {bundle_path}")
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    failures = report_failures(text, bundle=bundle, min_chars=args.min_chars)

    if failures:
        print("INVALID")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
