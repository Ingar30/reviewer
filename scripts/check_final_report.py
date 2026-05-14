from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_REQUIRED_HEADINGS = [
    "## Executive Summary",
    "## Review Configuration",
    "## Highest-Priority Cross-Agent Findings",
    "## Suggested Revision Priorities",
    "## Additional Findings",
]
GRAMMAR_APPENDIX_HEADING = "## Appendix: Grammar and Copyediting Issues"
TRACEABILITY_APPENDIX_HEADING = "## Appendix: Traceability Map"
EXTERNAL_SOURCES_APPENDIX_RE = re.compile(r"^## Appendix: External Sources", re.MULTILINE)

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


def report_failures(text: str, *, bundle: dict | None = None, min_chars: int = 2000) -> list[str]:
    failures = []
    if len(text.strip()) < min_chars:
        failures.append(f"report is too short: {len(text.strip())} chars < {min_chars}")
    if META_NOTE_RE.search(text):
        failures.append("report appears to contain a run-status/meta note")
    for heading in DEFAULT_REQUIRED_HEADINGS:
        if heading not in text:
            failures.append(f"missing required heading: {heading}")
    if not re.search(r"\b(?:CANON-\d{3}|[A-Z]+-[A-Z]+-\d{3}|claim_evidence_\d{3}|NA-\d{3})\b", text):
        failures.append("report does not mention canonical or source finding identifiers")

    if bundle:
        if TRACEABILITY_APPENDIX_HEADING not in text:
            failures.append(f"missing traceability appendix heading: {TRACEABILITY_APPENDIX_HEADING}")
        if bundle_has_copyedit_findings(bundle) and GRAMMAR_APPENDIX_HEADING not in text:
            failures.append(f"missing grammar appendix heading: {GRAMMAR_APPENDIX_HEADING}")
        urls = external_source_urls(bundle)
        if urls and not EXTERNAL_SOURCES_APPENDIX_RE.search(text):
            failures.append("missing external-sources appendix heading despite external source URLs in bundle")
        for url in sorted(urls):
            if EXTERNAL_SOURCES_APPENDIX_RE.search(text) and url not in text:
                failures.append(f"missing external source URL from report: {url}")
        for finding in bundle.get("canonical_findings", []):
            canonical_id = finding.get("canonical_id")
            if canonical_id and canonical_id not in text:
                failures.append(f"missing canonical identifier from bundle: {canonical_id}")
            for source in finding.get("source_findings", []):
                reviewer = source.get("reviewer")
                source_id = source.get("id")
                if reviewer and source_id and f"{reviewer}:{source_id}" not in text:
                    failures.append(f"missing source finding identifier from bundle: {reviewer}:{source_id}")
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
