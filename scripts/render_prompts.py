from __future__ import annotations

import argparse
import re
from pathlib import Path


TEMPLATE_FILES = {
    "crossref_audit.txt": "crossref_audit.txt",
    "numerical_audit.txt": "numerical_audit.txt",
    "claim_evidence_audit.txt": "claim_evidence_audit.txt",
    "literature_audit.txt": "literature_audit.txt",
    "reference_audit.txt": "reference_audit.txt",
    "editor_report.txt": "editor_report.txt",
}

PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def render_template(template: str, values: dict[str, str]) -> str:
    rendered = template.format(**values)
    remaining = sorted(set(PLACEHOLDER_RE.findall(rendered)))
    if remaining:
        raise ValueError(f"Unresolved placeholders after rendering: {', '.join(remaining)}")
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description="Render reusable Codex prompt templates for one paper run.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--parsed-dir", required=True)
    parser.add_argument("--reviews-dir", required=True)
    parser.add_argument("--schema-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--templates-dir", default="prompts/templates")
    parser.add_argument("--editor-bundle-path", default=None)
    args = parser.parse_args()

    templates_dir = Path(args.templates_dir)
    output_dir = Path(args.output_dir)
    editor_bundle_path = args.editor_bundle_path or f"work/{args.paper_id}/editor/normalized_bundle.json"

    values = {
        "paper_id": args.paper_id,
        "parsed_dir": args.parsed_dir,
        "reviews_dir": args.reviews_dir,
        "schema_path": args.schema_path,
        "editor_bundle_path": editor_bundle_path,
    }

    missing = [name for name in TEMPLATE_FILES if not (templates_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing prompt templates in {templates_dir}: {', '.join(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for template_name, output_name in TEMPLATE_FILES.items():
        template_path = templates_dir / template_name
        output_path = output_dir / output_name
        rendered = render_template(template_path.read_text(encoding="utf-8"), values)
        output_path.write_text(rendered, encoding="utf-8")
        written.append(str(output_path))

    print("\n".join(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
