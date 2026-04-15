from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFAULT_REQUIRED_HEADINGS = [
    "## Executive Summary",
    "## Highest-Priority Manuscript Issues",
    "## Suggested Revision Checklist",
]

META_NOTE_RE = re.compile(
    r"\b(?:done\.|wrote the final|report (?:is|was) saved|saved to|appears only under ignored status)\b",
    re.IGNORECASE,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check that an editor output is a real report.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--min-chars", type=int, default=2000)
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")

    text = path.read_text(encoding="utf-8")
    failures = []
    if len(text.strip()) < args.min_chars:
        failures.append(f"report is too short: {len(text.strip())} chars < {args.min_chars}")
    if META_NOTE_RE.search(text):
        failures.append("report appears to contain a run-status/meta note")
    for heading in DEFAULT_REQUIRED_HEADINGS:
        if heading not in text:
            failures.append(f"missing required heading: {heading}")
    if not re.search(r"\b(?:CANON-\d{3}|[A-Z]+-[A-Z]+-\d{3}|claim_evidence_\d{3}|NA-\d{3})\b", text):
        failures.append("report does not mention canonical or source finding identifiers")

    if failures:
        print("INVALID")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
