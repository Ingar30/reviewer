from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from reviewer_config import ReviewerConfig, load_reviewers_config


@dataclass
class RunResult:
    label: str
    returncode: int
    stdout_path: Path
    stderr_path: Path


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "paper"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def codex_command() -> str:
    for candidate in ("codex.cmd", "codex.exe", "codex"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError("Could not find Codex CLI on PATH. Install Codex or add codex.cmd to PATH.")


def run_command(label: str, command: list[str], cwd: Path, log_dir: Path, input_text: str | None = None) -> RunResult:
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_label = slugify(label)
    stdout_path = log_dir / f"{safe_label}.stdout.log"
    stderr_path = log_dir / f"{safe_label}.stderr.log"

    print(f"[run] {label}")
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        capture_output=True,
    )
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        print(f"[fail] {label} exited {completed.returncode}; see {stderr_path}")
    else:
        print(f"[ok] {label}")
    return RunResult(label, completed.returncode, stdout_path, stderr_path)


def run_required(label: str, command: list[str], cwd: Path, log_dir: Path, input_text: str | None = None) -> RunResult:
    result = run_command(label, command, cwd, log_dir, input_text=input_text)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}; see {result.stderr_path}")
    return result


def start_reviewer(
    reviewer: ReviewerConfig,
    repo: Path,
    prompts_dir: Path,
    reviews_dir: Path,
    schema_path: Path,
    log_dir: Path,
) -> tuple[ReviewerConfig, subprocess.Popen[str], Path, Path]:
    prompt_path = prompts_dir / reviewer.prompt
    output_path = reviews_dir / reviewer.output
    stdout_path = log_dir / f"{reviewer.name}.stdout.log"
    stderr_path = log_dir / f"{reviewer.name}.stderr.log"
    prompt_text = prompt_path.read_text(encoding="utf-8")

    command = [codex_command()]
    if reviewer.search:
        command.append("--search")
    command.extend(
        [
            "exec",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-",
        ]
    )

    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    print(f"[start] {reviewer.name}")
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo,
    )
    assert process.stdin is not None
    process.stdin.write(prompt_text)
    process.stdin.close()
    process._reviewer_stdout_handle = stdout_handle  # type: ignore[attr-defined]
    process._reviewer_stderr_handle = stderr_handle  # type: ignore[attr-defined]
    return reviewer, process, stdout_path, stderr_path


def wait_reviewer(
    reviewer: ReviewerConfig,
    process: subprocess.Popen[str],
    stdout_path: Path,
    stderr_path: Path,
) -> RunResult:
    returncode = process.wait()
    process._reviewer_stdout_handle.close()  # type: ignore[attr-defined]
    process._reviewer_stderr_handle.close()  # type: ignore[attr-defined]
    if returncode == 0:
        print(f"[ok] {reviewer.name}")
    else:
        print(f"[fail] {reviewer.name} exited {returncode}; see {stderr_path}")
    return RunResult(reviewer.name, returncode, stdout_path, stderr_path)


def require_fresh_file(path: Path, started_at: float, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if path.stat().st_mtime < started_at:
        raise RuntimeError(f"{label} is stale and was not regenerated in this run: {path}")


def validate_reviewer_json(path: Path, expected_reviewer: str, paper_id: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("reviewer") != expected_reviewer:
        raise ValueError(f"{path} has reviewer={data.get('reviewer')!r}, expected {expected_reviewer!r}")
    if data.get("paper_id") != paper_id:
        raise ValueError(f"{path} has paper_id={data.get('paper_id')!r}, expected {paper_id!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full paper-review pipeline for one PDF.")
    parser.add_argument("--pdf", required=True, help="Path to source PDF, usually under inputs/")
    parser.add_argument("--paper-id", default=None, help="Optional paper id; defaults to the PDF filename stem")
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue validating remaining reviewer outputs after a reviewer-output validation error.",
    )
    parser.add_argument("--reviewers-config", default="config/reviewers.json")
    args = parser.parse_args()

    repo = repo_root()
    pdf_path = Path(args.pdf)
    if not pdf_path.is_absolute():
        pdf_path = repo / pdf_path
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {pdf_path.name}")

    paper_id = slugify(args.paper_id or pdf_path.stem)
    work_root = repo / "work" / paper_id
    parsed_dir = work_root / "parsed"
    prompts_dir = work_root / "prompts"
    reviews_dir = work_root / "reviews"
    editor_dir = work_root / "editor"
    log_dir = work_root / "logs"
    outputs_dir = repo / "outputs" / paper_id
    report_path = outputs_dir / "report.md"
    schema_path = repo / "schemas" / "reviewer_output.schema.json"
    bundle_path = editor_dir / "normalized_bundle.json"
    editor_input_path = editor_dir / "editor_input.md"
    reviewers = load_reviewers_config(repo / args.reviewers_config if not Path(args.reviewers_config).is_absolute() else args.reviewers_config)

    log_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    print(f"[paper] {paper_id}")
    print(f"[pdf] {pdf_path}")

    run_required(
        "preprocess",
        [
            sys.executable,
            "scripts/preprocess_pdf.py",
            "--pdf",
            str(pdf_path),
            "--paper-id",
            paper_id,
        ],
        repo,
        log_dir,
    )

    run_required(
        "render-prompts",
        [
            sys.executable,
            "scripts/render_prompts.py",
            "--paper-id",
            paper_id,
            "--parsed-dir",
            str(parsed_dir.relative_to(repo)),
            "--reviews-dir",
            str(reviews_dir.relative_to(repo)),
            "--schema-path",
            str(schema_path.relative_to(repo)),
            "--output-dir",
            str(prompts_dir.relative_to(repo)),
            "--reviewers-config",
            str((repo / args.reviewers_config).relative_to(repo) if not Path(args.reviewers_config).is_absolute() else args.reviewers_config),
        ],
        repo,
        log_dir,
    )

    reviewer_started_at = time.time() - 1.0
    running = [
        start_reviewer(reviewer, repo, prompts_dir, reviews_dir, schema_path.relative_to(repo), log_dir)
        for reviewer in reviewers
    ]
    reviewer_results = [wait_reviewer(*item) for item in running]
    failed_reviewers = [result for result in reviewer_results if result.returncode != 0]
    if failed_reviewers:
        failures = ", ".join(f"{result.label} ({result.returncode})" for result in failed_reviewers)
        raise RuntimeError(f"Reviewer run failed: {failures}")

    validation_errors = []
    for reviewer in reviewers:
        output_path = reviews_dir / reviewer.output
        try:
            require_fresh_file(output_path, reviewer_started_at, f"{reviewer.name} output")
            validate_reviewer_json(output_path, reviewer.name, paper_id)
            result = run_required(
                f"validate-{reviewer.name}",
                [
                    sys.executable,
                    "scripts/validate_review_json.py",
                    "--schema",
                    str(schema_path.relative_to(repo)),
                    "--input",
                    str(output_path.relative_to(repo)),
                    "--reviewers-config",
                    str((repo / args.reviewers_config).relative_to(repo) if not Path(args.reviewers_config).is_absolute() else args.reviewers_config),
                ],
                repo,
                log_dir,
            )
        except Exception as exc:
            validation_errors.append(f"{reviewer.name}: {exc}")
            if not args.keep_going:
                break
    if validation_errors:
        raise RuntimeError("Reviewer validation failed: " + "; ".join(validation_errors))

    run_required(
        "normalize",
        [
            sys.executable,
            "scripts/normalize_review_outputs.py",
            "--paper-id",
            paper_id,
            "--reviews-dir",
            str(reviews_dir.relative_to(repo)),
            "--output",
            str(bundle_path.relative_to(repo)),
            "--reviewers-config",
            str((repo / args.reviewers_config).relative_to(repo) if not Path(args.reviewers_config).is_absolute() else args.reviewers_config),
        ],
        repo,
        log_dir,
    )

    run_required(
        "build-editor-input",
        [
            sys.executable,
            "scripts/build_editor_input.py",
            "--paper-id",
            paper_id,
            "--editor-prompt",
            str((prompts_dir / "editor_report.txt").relative_to(repo)),
            "--bundle",
            str(bundle_path.relative_to(repo)),
            "--reviews-dir",
            str(reviews_dir.relative_to(repo)),
            "--output",
            str(editor_input_path.relative_to(repo)),
            "--reviewers-config",
            str((repo / args.reviewers_config).relative_to(repo) if not Path(args.reviewers_config).is_absolute() else args.reviewers_config),
        ],
        repo,
        log_dir,
    )

    editor_started_at = time.time() - 1.0
    editor_input = editor_input_path.read_text(encoding="utf-8")
    editor_result = run_required(
        "editor",
        [
            codex_command(),
            "exec",
            "--output-last-message",
            str(report_path.relative_to(repo)),
            "-",
        ],
        repo,
        log_dir,
        input_text=editor_input,
    )
    require_fresh_file(report_path, editor_started_at, "final report")

    check_result = run_required(
        "check-final-report",
        [
            sys.executable,
            "scripts/check_final_report.py",
            "--input",
            str(report_path.relative_to(repo)),
            "--bundle",
            str(bundle_path.relative_to(repo)),
        ],
        repo,
        log_dir,
    )
    print(f"[done] report: {report_path.relative_to(repo)}")
    print(f"[logs] {log_dir.relative_to(repo)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
