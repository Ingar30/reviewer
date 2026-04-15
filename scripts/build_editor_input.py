from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REVIEWER_FILES = [
    "crossref_auditor.json",
    "numerical_auditor.json",
    "claim_evidence_auditor.json",
    "literature_auditor.json",
    "reference_auditor.json",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(read(path))


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if not path.is_file():
        raise ValueError(f"Expected {label} to be a file: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one editor input file from prompt, bundle, and reviews.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--editor-prompt", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--reviews-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    editor_prompt = Path(args.editor_prompt)
    bundle = Path(args.bundle)
    reviews_dir = Path(args.reviews_dir)
    output = Path(args.output)

    require_file(editor_prompt, "editor prompt")
    require_file(bundle, "normalized editor bundle")
    bundle_json = read_json(bundle)
    if bundle_json.get("paper_id") != args.paper_id:
        raise ValueError(f"{bundle} has paper_id={bundle_json.get('paper_id')!r}, expected {args.paper_id!r}")

    review_paths = []
    for filename in REVIEWER_FILES:
        path = reviews_dir / filename
        require_file(path, f"reviewer output {filename}")
        review_json = read_json(path)
        if review_json.get("paper_id") != args.paper_id:
            raise ValueError(f"{path} has paper_id={review_json.get('paper_id')!r}, expected {args.paper_id!r}")
        review_paths.append(path)

    chunks = []
    chunks.append(read(editor_prompt))
    chunks.append("\n\n# Editor Input Metadata\n\n")
    chunks.append(f"- paper_id: `{args.paper_id}`\n")
    chunks.append(f"- normalized_bundle: `{bundle.as_posix()}`\n")
    chunks.append(f"- reviews_dir: `{reviews_dir.as_posix()}`\n")
    chunks.append("\n\n# Normalized Editor Bundle\n\n```json\n")
    chunks.append(read(bundle))
    chunks.append("\n```\n")

    chunks.append("\n\n# Original Reviewer Outputs\n")
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
