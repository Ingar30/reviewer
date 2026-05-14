from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from pipeline_paths import paper_run_paths


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


def codex_command() -> str:
    from review_paper import codex_command as resolve_codex_command

    return resolve_codex_command()


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh editor input/report from existing parsed and reviewer artifacts.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument(
        "--run-editor",
        action="store_true",
        help="Run Codex editor and final report check. By default only rerenders prompts and rebuilds editor input.",
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
            "normalized bundle": bundle,
        }
    )
    prompts_dir.mkdir(parents=True, exist_ok=True)
    editor_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

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
            str(selected_reviewers.relative_to(repo)),
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
            str(selected_reviewers.relative_to(repo)),
        ],
        repo,
    )

    if args.run_editor:
        editor_text = editor_input.read_text(encoding="utf-8")
        run_command(
            [
                codex_command(),
                "exec",
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

    print(f"editor input refreshed: {editor_input.relative_to(repo)}")
    if args.run_editor:
        print(f"report refreshed: {report.relative_to(repo)}")
    else:
        print("editor was not run; pass --run-editor to refresh the final report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
