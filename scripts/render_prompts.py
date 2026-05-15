from __future__ import annotations

import argparse
import re
from pathlib import Path

from reviewer_config import load_reviewers_config

EDITOR_TEMPLATE = "editor_report.txt"

PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def render_template(template: str, values: dict[str, str]) -> str:
    rendered = template.format(**values)
    remaining = sorted(set(PLACEHOLDER_RE.findall(rendered)))
    if remaining:
        raise ValueError(f"Unresolved placeholders after rendering: {', '.join(remaining)}")
    return rendered


def append_parser_repair_note(rendered: str, parser_repair_notes: str | None) -> str:
    if not parser_repair_notes:
        return rendered
    return (
        rendered.rstrip()
        + "\n\nParser repair overlay:\n"
        + f"`{parser_repair_notes}`\n\n"
        + "Before treating a parsed table, figure, page-text passage, or inventory entry as primary evidence, "
        + "check the parser repair overlay for known parser-quality limitations, repaired overlay artifacts, "
        + "preferred fallback artifacts, and artifacts that should not be relied on as primary evidence.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render reusable Codex prompt templates for one paper run.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--parsed-dir", required=True)
    parser.add_argument("--reviews-dir", required=True)
    parser.add_argument("--schema-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--templates-dir", default="prompts/templates")
    parser.add_argument("--editor-bundle-path", default=None)
    parser.add_argument("--reviewers-config", default="config/reviewers.json")
    parser.add_argument("--parser-repair-notes", default=None)
    args = parser.parse_args()

    templates_dir = Path(args.templates_dir)
    output_dir = Path(args.output_dir)
    editor_bundle_path = args.editor_bundle_path or f"work/{args.paper_id}/editor/normalized_bundle.json"
    reviewers = load_reviewers_config(args.reviewers_config)

    values = {
        "paper_id": args.paper_id,
        "parsed_dir": args.parsed_dir,
        "reviews_dir": args.reviews_dir,
        "schema_path": args.schema_path,
        "editor_bundle_path": editor_bundle_path,
    }

    template_files = {reviewer.prompt: reviewer for reviewer in reviewers}
    missing = [name for name in template_files if not (templates_dir / name).exists()]
    if not (templates_dir / EDITOR_TEMPLATE).exists():
        missing.append(EDITOR_TEMPLATE)
    if missing:
        raise FileNotFoundError(f"Missing prompt templates in {templates_dir}: {', '.join(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for template_name, reviewer in template_files.items():
        template_path = templates_dir / template_name
        output_path = output_dir / reviewer.prompt
        rendered = render_template(template_path.read_text(encoding="utf-8"), values)
        if reviewer.stage == "review":
            rendered = append_parser_repair_note(rendered, args.parser_repair_notes)
        output_path.write_text(rendered, encoding="utf-8")
        written.append(str(output_path))

    editor_template_path = templates_dir / EDITOR_TEMPLATE
    editor_output_path = output_dir / EDITOR_TEMPLATE
    editor_rendered = render_template(editor_template_path.read_text(encoding="utf-8"), values)
    editor_output_path.write_text(editor_rendered, encoding="utf-8")
    written.append(str(editor_output_path))

    print("\n".join(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
