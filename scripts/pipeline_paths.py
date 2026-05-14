from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SELECTED_REVIEWERS_CONFIG = "selected_reviewers.json"
PARSER_REPAIR_NOTES = "parser_repair_notes.md"
NORMALIZED_BUNDLE = "normalized_bundle.json"
EDITOR_INPUT = "editor_input.md"
EDITOR_REPORT_PROMPT = "editor_report.txt"
REPORT = "report.md"


@dataclass(frozen=True)
class PaperRunPaths:
    repo: Path
    paper_id: str
    work_root: Path
    parsed_dir: Path
    prompts_dir: Path
    reviews_dir: Path
    editor_dir: Path
    repair_dir: Path
    selection_dir: Path
    log_dir: Path
    outputs_dir: Path
    selected_reviewers_config_path: Path
    parser_repair_notes_path: Path
    bundle_path: Path
    editor_prompt_path: Path
    editor_input_path: Path
    report_path: Path


def paper_run_paths(repo: Path, paper_id: str) -> PaperRunPaths:
    work_root = repo / "work" / paper_id
    prompts_dir = work_root / "prompts"
    editor_dir = work_root / "editor"
    outputs_dir = repo / "outputs" / paper_id
    selection_dir = work_root / "selection"
    repair_dir = work_root / "repair"
    return PaperRunPaths(
        repo=repo,
        paper_id=paper_id,
        work_root=work_root,
        parsed_dir=work_root / "parsed",
        prompts_dir=prompts_dir,
        reviews_dir=work_root / "reviews",
        editor_dir=editor_dir,
        repair_dir=repair_dir,
        selection_dir=selection_dir,
        log_dir=work_root / "logs",
        outputs_dir=outputs_dir,
        selected_reviewers_config_path=selection_dir / SELECTED_REVIEWERS_CONFIG,
        parser_repair_notes_path=repair_dir / PARSER_REPAIR_NOTES,
        bundle_path=editor_dir / NORMALIZED_BUNDLE,
        editor_prompt_path=prompts_dir / EDITOR_REPORT_PROMPT,
        editor_input_path=editor_dir / EDITOR_INPUT,
        report_path=outputs_dir / REPORT,
    )
