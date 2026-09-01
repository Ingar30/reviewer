from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline_paths import paper_run_paths
from review_paper import enforce_preflight_gate
from reviewer_config import load_reviewers_config


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def require_paths(paths: dict[str, Path]) -> None:
    missing = [f"{name}: {path}" for name, path in paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("Editor refresh prerequisites are missing:\n- " + "\n- ".join(missing))


def run_command(command: list[str], cwd: Path, *, input_text: str | None = None) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        input=input_text,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(command)}")


def codex_exec_command(
    model: str | None = None, reasoning_effort: str | None = None
) -> list[str]:
    from review_paper import codex_exec_command as resolve_codex_exec_command

    return resolve_codex_exec_command(model=model, reasoning_effort=reasoning_effort)


def mark_run_manifest_complete(
    manifest_path: Path, report: Path, repo: Path, reviewer_names: list[str]
) -> None:
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    now = datetime.now(timezone.utc).isoformat()
    manifest.update(
        {
            "status": "complete",
            "completed_at_utc": now,
            "synthesis_refreshed_at_utc": now,
            "selected_reviewers": reviewer_names,
            "report": str(report.relative_to(repo)),
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate existing reviews, rebuild the normalized bundle, and refresh editor output."
    )
    parser.add_argument("--paper-id", required=True)
    parser.add_argument(
        "--run-editor",
        action="store_true",
        help="Run Codex editor and final report check. By default only rerenders prompts and rebuilds editor input.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Override the Codex model when --run-editor is used. "
            "When omitted, the project default from .codex/config.toml is used."
        ),
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["none", "minimal", "low", "medium", "high", "xhigh", "max"],
        default=None,
        help=(
            "Override Codex model_reasoning_effort when --run-editor is used. "
            "When omitted, the project default from .codex/config.toml is used."
        ),
    )
    args = parser.parse_args()

    repo = repo_root()
    paths = paper_run_paths(repo, args.paper_id)
    parsed_dir = paths.parsed_dir
    reviews_dir = paths.reviews_dir
    prompts_dir = paths.prompts_dir
    editor_dir = paths.editor_dir
    outputs_dir = paths.outputs_dir
    selected_reviewers = paths.selected_reviewers_config_path
    bundle = paths.bundle_path
    editor_prompt = paths.editor_prompt_path
    editor_input = paths.editor_input_path
    report = paths.report_path

    require_paths(
        {
            "parsed artifacts": parsed_dir,
            "reviews directory": reviews_dir,
            "selected reviewers": selected_reviewers,
        }
    )
    prompts_dir.mkdir(parents=True, exist_ok=True)
    editor_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    selected_config_relative = str(selected_reviewers.relative_to(repo))
    selected = load_reviewers_config(selected_reviewers)
    review_stage = [reviewer for reviewer in selected if reviewer.stage == "review"]
    require_paths(
        {
            reviewer.name: reviews_dir / reviewer.output
            for reviewer in selected
        }
    )
    for reviewer in selected:
        run_command(
            [
                sys.executable,
                "scripts/validate_review_json.py",
                "--schema",
                "schemas/reviewer_output.schema.json",
                "--input",
                str((reviews_dir / reviewer.output).relative_to(repo)),
                "--reviewers-config",
                selected_config_relative,
            ],
            repo,
        )
        if reviewer.stage == "preflight":
            enforce_preflight_gate(reviewer, reviews_dir / reviewer.output)
    run_command(
        [
            sys.executable,
            "scripts/normalize_review_outputs.py",
            "--paper-id",
            args.paper_id,
            "--reviews-dir",
            str(reviews_dir.relative_to(repo)),
            "--output",
            str(bundle.relative_to(repo)),
            "--reviewers-config",
            selected_config_relative,
        ],
        repo,
    )

    run_command(
        [
            sys.executable,
            "scripts/render_prompts.py",
            "--paper-id",
            args.paper_id,
            "--parsed-dir",
            str(parsed_dir.relative_to(repo)),
            "--reviews-dir",
            str(reviews_dir.relative_to(repo)),
            "--schema-path",
            "schemas/reviewer_output.schema.json",
            "--output-dir",
            str(prompts_dir.relative_to(repo)),
            "--editor-bundle-path",
            str(bundle.relative_to(repo)),
            "--reviewers-config",
            selected_config_relative,
        ],
        repo,
    )
    run_command(
        [
            sys.executable,
            "scripts/build_editor_input.py",
            "--paper-id",
            args.paper_id,
            "--editor-prompt",
            str(editor_prompt.relative_to(repo)),
            "--bundle",
            str(bundle.relative_to(repo)),
            "--reviews-dir",
            str(reviews_dir.relative_to(repo)),
            "--output",
            str(editor_input.relative_to(repo)),
            "--reviewers-config",
            selected_config_relative,
        ],
        repo,
    )

    if args.run_editor:
        editor_text = editor_input.read_text(encoding="utf-8")
        run_command(
            [
                *codex_exec_command(args.model, args.reasoning_effort),
                "--output-last-message",
                str(report.relative_to(repo)),
                "-",
            ],
            repo,
            input_text=editor_text,
        )
        run_command(
            [
                sys.executable,
                "scripts/check_final_report.py",
                "--input",
                str(report.relative_to(repo)),
                "--bundle",
                str(bundle.relative_to(repo)),
            ],
            repo,
        )
        mark_run_manifest_complete(
            paths.run_manifest_path,
            report,
            repo,
            [reviewer.name for reviewer in review_stage],
        )

    print(f"editor input refreshed: {editor_input.relative_to(repo)}")
    if args.run_editor:
        print(f"report refreshed: {report.relative_to(repo)}")
    else:
        print("editor was not run; pass --run-editor to refresh the final report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
