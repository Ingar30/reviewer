from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from reviewer_config import ReviewerConfig, load_reviewers_config
from reviewer_routing import reviewer_catalog

EDITOR_TEMPLATE = "editor_report.txt"
REVIEWER_CONTRACT_TEMPLATE = "reviewer_contract.txt"
SELECTOR_TEMPLATE = "reviewer_selection.txt"

PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def render_template(template: str, values: dict[str, str]) -> str:
    rendered = template.format(**values)
    remaining = sorted(set(PLACEHOLDER_RE.findall(rendered)))
    if remaining:
        raise ValueError(f"Unresolved placeholders after rendering: {', '.join(remaining)}")
    return rendered


def render_review_prompts(
    templates_dir: Path, output_dir: Path, reviewers: list[ReviewerConfig], values: dict[str, str]
) -> list[Path]:
    """Render the same reviewer contract and editor prompt for every execution host."""
    values = {key: Path(value).as_posix() if key.endswith(("_dir", "_path")) else value
              for key, value in values.items()}
    template_files = {reviewer.prompt: reviewer for reviewer in reviewers}
    missing = [name for name in template_files if not (templates_dir / name).exists()]
    if not (templates_dir / EDITOR_TEMPLATE).exists():
        missing.append(EDITOR_TEMPLATE)
    if not (templates_dir / REVIEWER_CONTRACT_TEMPLATE).exists():
        missing.append(REVIEWER_CONTRACT_TEMPLATE)
    if missing:
        raise FileNotFoundError(f"Missing prompt templates in {templates_dir}: {', '.join(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    reviewer_contract = render_template(
        (templates_dir / REVIEWER_CONTRACT_TEMPLATE).read_text(encoding="utf-8"), values
    )
    written = []
    for template_name, reviewer in template_files.items():
        template_path = templates_dir / template_name
        output_path = output_dir / reviewer.prompt
        rendered = render_template(template_path.read_text(encoding="utf-8"), values)
        rendered = rendered.rstrip() + "\n\n" + reviewer_contract.strip() + "\n"
        output_path.write_text(rendered, encoding="utf-8")
        written.append(output_path)

    editor_template_path = templates_dir / EDITOR_TEMPLATE
    editor_output_path = output_dir / EDITOR_TEMPLATE
    editor_rendered = render_template(editor_template_path.read_text(encoding="utf-8"), values)
    editor_output_path.write_text(editor_rendered, encoding="utf-8")
    written.append(editor_output_path)
    return written


def render_selection_prompt(
    templates_dir: Path, paper_id: str, parsed_dir: str, selection_schema_path: str,
    optional_reviewers: list[ReviewerConfig],
) -> str:
    return render_template(
        (templates_dir / SELECTOR_TEMPLATE).read_text(encoding="utf-8"),
        {"paper_id": paper_id, "parsed_dir": Path(parsed_dir).as_posix(),
         "selection_schema_path": Path(selection_schema_path).as_posix(),
         "optional_reviewer_catalog": json.dumps(reviewer_catalog(optional_reviewers), indent=2)},
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
    args = parser.parse_args()
    values = {
        "paper_id": args.paper_id, "parsed_dir": args.parsed_dir,
        "reviews_dir": args.reviews_dir, "schema_path": args.schema_path,
        "editor_bundle_path": args.editor_bundle_path or f"work/{args.paper_id}/editor/normalized_bundle.json",
    }
    written = render_review_prompts(Path(args.templates_dir), Path(args.output_dir),
                                    load_reviewers_config(args.reviewers_config), values)

    print("\n".join(str(path) for path in written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
