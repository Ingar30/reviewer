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

from pipeline_paths import paper_run_paths
from render_prompts import render_template
from reviewer_config import ReviewerConfig, load_reviewers_config, write_reviewers_config


SELECTOR_TEMPLATE = "reviewer_selection.txt"
SELECTOR_OUTPUT = "reviewer_selection.json"
MIN_EDITOR_REPORT_CHARS = 2000
EDITOR_REPORT_REQUIRED_HEADINGS = [
    "## Executive Summary",
    "## Review Configuration",
    "## Highest-Priority Cross-Agent Findings",
    "## Suggested Revision Priorities",
    "## Additional Findings",
]


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


def plausible_editor_report(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < MIN_EDITOR_REPORT_CHARS:
        return False
    if not stripped.startswith("# Multi-Agent Paper Review Report"):
        return False
    return all(heading in stripped for heading in EDITOR_REPORT_REQUIRED_HEADINGS)


def extract_editor_report_from_transcript(text: str) -> str | None:
    starts = [match.start() for match in re.finditer(r"(?m)^# Multi-Agent Paper Review Report\s*$", text)]
    for start in reversed(starts):
        candidate = text[start:]
        end_match = re.search(r"(?m)^(?:collab:|tokens used\b)", candidate)
        if end_match:
            candidate = candidate[: end_match.start()]
        candidate = candidate.strip()
        if plausible_editor_report(candidate):
            return candidate + "\n"
    return None


def recover_editor_report_if_needed(report_path: Path, editor_stderr_path: Path) -> None:
    current = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    if plausible_editor_report(current):
        return

    transcript = editor_stderr_path.read_text(encoding="utf-8") if editor_stderr_path.exists() else ""
    recovered = extract_editor_report_from_transcript(transcript)
    if recovered is None:
        raise RuntimeError(
            f"editor produced an invalid final report and no recoverable report was found in {editor_stderr_path}"
        )
    report_path.write_text(recovered, encoding="utf-8")
    print(f"[recover] final report recovered from editor transcript: {editor_stderr_path}")


def validate_reviewer_json(path: Path, expected_reviewer: str, paper_id: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("reviewer") != expected_reviewer:
        raise ValueError(f"{path} has reviewer={data.get('reviewer')!r}, expected {expected_reviewer!r}")
    if data.get("paper_id") != paper_id:
        raise ValueError(f"{path} has paper_id={data.get('paper_id')!r}, expected {paper_id!r}")


def parser_quality_gate_findings(data: dict) -> tuple[list[dict], list[dict]]:
    blockers = []
    warnings = []
    for finding in data.get("findings", []):
        if finding.get("issue_type") != "parser_artifact":
            continue
        severity = finding.get("severity")
        confidence = finding.get("confidence")
        assessment = finding.get("assessment")
        if severity == "high" and confidence == "high" and assessment in {"no", "partially"}:
            blockers.append(finding)
        elif severity in {"high", "medium"}:
            warnings.append(finding)
    return blockers, warnings


def repairable_parser_findings(data: dict) -> list[dict]:
    blockers, warnings = parser_quality_gate_findings(data)
    return [*blockers, *warnings]


def finding_label(finding: dict) -> str:
    finding_id = finding.get("id", "unknown-id")
    claim = " ".join(str(finding.get("claim_text", "")).split())
    return f"{finding_id}: {claim}" if claim else str(finding_id)


def enforce_preflight_gate(reviewer: ReviewerConfig, output_path: Path) -> None:
    if reviewer.name != "parser_quality_auditor":
        return
    data = json.loads(output_path.read_text(encoding="utf-8"))
    blockers, warnings = parser_quality_gate_findings(data)
    for finding in warnings:
        print(f"[warn] parser quality: {finding_label(finding)}")
    if blockers:
        blocker_text = "; ".join(finding_label(finding) for finding in blockers)
        raise RuntimeError(f"blocking parser-quality findings: {blocker_text}")


def reviewer_catalog(reviewers: list[ReviewerConfig]) -> list[dict[str, object]]:
    return [
        {
            "name": reviewer.name,
            "id_prefix": reviewer.id_prefix,
            "prompt": reviewer.prompt,
            "search": reviewer.search,
            "normalization_role": reviewer.normalization_role,
        }
        for reviewer in reviewers
    ]


def render_selector_prompt(
    repo: Path,
    paper_id: str,
    parsed_dir: Path,
    optional_reviewers: list[ReviewerConfig],
    selection_schema_path: Path,
    parser_repair_notes: Path | None = None,
) -> str:
    template = (repo / "prompts" / "templates" / SELECTOR_TEMPLATE).read_text(encoding="utf-8")
    catalog = json.dumps(reviewer_catalog(optional_reviewers), indent=2)
    rendered = render_template(
        template,
        {
            "paper_id": paper_id,
            "parsed_dir": str(parsed_dir.relative_to(repo)),
            "selection_schema_path": str(selection_schema_path.relative_to(repo)),
            "optional_reviewer_catalog": catalog,
        },
    )
    if parser_repair_notes:
        rendered += (
            "\n\nParser repair overlay available before reviewer selection:\n"
            f"`{parser_repair_notes.relative_to(repo)}`\n\n"
            "Use this overlay to avoid selecting reviewers whose primary evidence class is unresolved by the parsed artifacts, "
            "and to prefer reviewers who can work from verified fallback artifacts.\n"
        )
    return rendered


def run_reviewer_selector(
    repo: Path,
    paper_id: str,
    parsed_dir: Path,
    optional_reviewers: list[ReviewerConfig],
    selection_dir: Path,
    selection_schema_path: Path,
    log_dir: Path,
    parser_repair_notes: Path | None = None,
) -> tuple[dict, float]:
    selection_dir.mkdir(parents=True, exist_ok=True)
    output_path = selection_dir / SELECTOR_OUTPUT
    prompt_text = render_selector_prompt(
        repo,
        paper_id,
        parsed_dir,
        optional_reviewers,
        selection_schema_path,
        parser_repair_notes,
    )
    started_at = time.time() - 1.0
    run_required(
        "reviewer-selector",
        [
            codex_command(),
            "exec",
            "--output-schema",
            str(selection_schema_path.relative_to(repo)),
            "--output-last-message",
            str(output_path.relative_to(repo)),
            "-",
        ],
        repo,
        log_dir,
        input_text=prompt_text,
    )
    require_fresh_file(output_path, started_at, "reviewer selector output")
    return json.loads(output_path.read_text(encoding="utf-8")), started_at


def validate_selection_output(
    selection: dict,
    paper_id: str,
    mandatory_reviewers: list[ReviewerConfig],
    optional_reviewers: list[ReviewerConfig],
) -> list[str]:
    errors = []
    if selection.get("paper_id") != paper_id:
        errors.append(f"selection paper_id={selection.get('paper_id')!r}, expected {paper_id!r}")
    valid_paper_types = {
        "empirical_causal",
        "empirical_descriptive",
        "theory",
        "methods",
        "literature_review",
        "mixed",
        "unknown",
    }
    if selection.get("paper_type") not in valid_paper_types:
        errors.append("selection paper_type is invalid")
    if selection.get("selection_confidence") not in {"high", "medium", "low"}:
        errors.append("selection_confidence is invalid")

    optional_by_name = {reviewer.name: reviewer for reviewer in optional_reviewers if reviewer.enabled}
    mandatory_names = {reviewer.name for reviewer in mandatory_reviewers}
    selected_items = selection.get("selected_optional_reviewers", [])
    skipped_items = selection.get("skipped_optional_reviewers", [])
    if not isinstance(selected_items, list):
        errors.append("selected_optional_reviewers must be a list")
        selected_items = []
    if not isinstance(skipped_items, list):
        errors.append("skipped_optional_reviewers must be a list")
        skipped_items = []

    selected_names = []
    for index, item in enumerate(selected_items):
        if not isinstance(item, dict):
            errors.append(f"selected_optional_reviewers[{index}] must be an object")
            continue
        name = item.get("name")
        reason = item.get("reason")
        if not isinstance(name, str) or not name:
            errors.append(f"selected_optional_reviewers[{index}].name must be a non-empty string")
            continue
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"selected_optional_reviewers[{index}].reason must be a non-empty string")
        if name in mandatory_names:
            errors.append(f"selected reviewer is mandatory, not optional: {name}")
        if name not in optional_by_name:
            errors.append(f"selected reviewer is not an enabled optional reviewer: {name}")
        selected_names.append(name)

    duplicates = sorted({name for name in selected_names if selected_names.count(name) > 1})
    for name in duplicates:
        errors.append(f"selected reviewer is duplicated: {name}")

    skipped_names = []
    for index, item in enumerate(skipped_items):
        if not isinstance(item, dict):
            errors.append(f"skipped_optional_reviewers[{index}] must be an object")
            continue
        name = item.get("name")
        reason = item.get("reason")
        if not isinstance(name, str) or not name:
            errors.append(f"skipped_optional_reviewers[{index}].name must be a non-empty string")
            continue
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"skipped_optional_reviewers[{index}].reason must be a non-empty string")
        if name not in optional_by_name:
            errors.append(f"skipped reviewer is not an enabled optional reviewer: {name}")
        skipped_names.append(name)

    overlap = sorted(set(selected_names) & set(skipped_names))
    for name in overlap:
        errors.append(f"reviewer cannot be both selected and skipped: {name}")
    return errors


def selected_reviewers_from_selection(
    selection: dict,
    mandatory_reviewers: list[ReviewerConfig],
    optional_reviewers: list[ReviewerConfig],
) -> list[ReviewerConfig]:
    optional_by_name = {reviewer.name: reviewer for reviewer in optional_reviewers}
    selected_names = [item["name"] for item in selection.get("selected_optional_reviewers", [])]
    selected_optional = [optional_by_name[name] for name in selected_names]
    return [*mandatory_reviewers, *selected_optional]


def run_reviewer_batch(
    reviewers: list[ReviewerConfig],
    repo: Path,
    prompts_dir: Path,
    reviews_dir: Path,
    schema_path: Path,
    log_dir: Path,
) -> float:
    if not reviewers:
        return time.time() - 1.0
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
    return reviewer_started_at


def render_prompts_command(
    *,
    paper_id: str,
    parsed_dir: Path,
    reviews_dir: Path,
    schema_path: Path,
    prompts_dir: Path,
    reviewers_config: str,
    repo: Path,
    parser_repair_notes: Path | None = None,
) -> list[str]:
    command = [
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
        reviewers_config,
    ]
    if parser_repair_notes:
        command.extend(["--parser-repair-notes", str(parser_repair_notes.relative_to(repo))])
    return command


def validate_reviewer_batch(
    reviewers: list[ReviewerConfig],
    reviewer_started_at: float,
    repo: Path,
    paper_id: str,
    reviews_dir: Path,
    schema_path: Path,
    reviewers_config: str,
    log_dir: Path,
    keep_going: bool,
) -> list[str]:
    validation_errors = []
    for reviewer in reviewers:
        output_path = reviews_dir / reviewer.output
        try:
            require_fresh_file(output_path, reviewer_started_at, f"{reviewer.name} output")
            validate_reviewer_json(output_path, reviewer.name, paper_id)
            run_required(
                f"validate-{reviewer.name}",
                [
                    sys.executable,
                    "scripts/validate_review_json.py",
                    "--schema",
                    str(schema_path.relative_to(repo)),
                    "--input",
                    str(output_path.relative_to(repo)),
                    "--reviewers-config",
                    str((repo / reviewers_config).relative_to(repo) if not Path(reviewers_config).is_absolute() else reviewers_config),
                ],
                repo,
                log_dir,
            )
            enforce_preflight_gate(reviewer, output_path)
        except Exception as exc:
            validation_errors.append(f"{reviewer.name}: {exc}")
            if not keep_going:
                break
    return validation_errors


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
    parser.add_argument(
        "--reviewer-selection",
        choices=["dynamic", "static"],
        default="dynamic",
        help="Use dynamic optional-reviewer selection or run all enabled reviewers.",
    )
    parser.add_argument(
        "--parser-repair",
        choices=["off", "plan"],
        default="off",
        help="Optionally run a post-preflight parser repair-planning agent before substantive review.",
    )
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
    paths = paper_run_paths(repo, paper_id)
    parsed_dir = paths.parsed_dir
    prompts_dir = paths.prompts_dir
    reviews_dir = paths.reviews_dir
    repair_dir = paths.repair_dir
    selection_dir = paths.selection_dir
    log_dir = paths.log_dir
    outputs_dir = paths.outputs_dir
    report_path = paths.report_path
    schema_path = repo / "schemas" / "reviewer_output.schema.json"
    selection_schema_path = repo / "schemas" / "reviewer_selection.schema.json"
    bundle_path = paths.bundle_path
    editor_input_path = paths.editor_input_path
    parser_repair_notes_path = paths.parser_repair_notes_path
    reviewers_config_path = repo / args.reviewers_config if not Path(args.reviewers_config).is_absolute() else Path(args.reviewers_config)
    reviewers = load_reviewers_config(reviewers_config_path)
    preflight_reviewers = [reviewer for reviewer in reviewers if reviewer.stage == "preflight"]
    standard_reviewers = [reviewer for reviewer in reviewers if reviewer.stage == "review"]
    mandatory_reviewers = [
        reviewer for reviewer in standard_reviewers if reviewer.selection_policy == "mandatory"
    ]
    optional_reviewers = [
        reviewer for reviewer in standard_reviewers if reviewer.selection_policy == "optional"
    ]
    selected_reviewers_config_path = paths.selected_reviewers_config_path

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
        render_prompts_command(
            paper_id=paper_id,
            parsed_dir=parsed_dir,
            reviews_dir=reviews_dir,
            schema_path=schema_path,
            prompts_dir=prompts_dir,
            reviewers_config=str((repo / args.reviewers_config).relative_to(repo) if not Path(args.reviewers_config).is_absolute() else args.reviewers_config),
            repo=repo,
        ),
        repo,
        log_dir,
    )

    preflight_started_at = run_reviewer_batch(
        preflight_reviewers, repo, prompts_dir, reviews_dir, schema_path, log_dir
    )
    preflight_errors = validate_reviewer_batch(
        preflight_reviewers,
        preflight_started_at,
        repo,
        paper_id,
        reviews_dir,
        schema_path,
        args.reviewers_config,
        log_dir,
        args.keep_going,
    )
    if preflight_errors:
        raise RuntimeError("Preflight reviewer validation/gate failed: " + "; ".join(preflight_errors))

    active_parser_repair_notes = None
    if args.parser_repair == "plan":
        parser_quality_outputs = [reviews_dir / reviewer.output for reviewer in preflight_reviewers if reviewer.name == "parser_quality_auditor"]
        if not parser_quality_outputs:
            raise RuntimeError("Parser repair requested, but parser_quality_auditor is not configured")
        parser_quality_data = json.loads(parser_quality_outputs[0].read_text(encoding="utf-8"))
        repairable_findings = repairable_parser_findings(parser_quality_data)
        if repairable_findings:
            print(
                "[repair] parser-quality findings: "
                + ", ".join(finding_label(finding) for finding in repairable_findings)
            )
            run_required(
                "parser-repair-agent",
                [
                    sys.executable,
                    "scripts/run_parser_repair_agent.py",
                    "--paper-id",
                    paper_id,
                    "--parsed-dir",
                    str(parsed_dir.relative_to(repo)),
                    "--parser-quality-output",
                    str(parser_quality_outputs[0].relative_to(repo)),
                    "--output-dir",
                    str(repair_dir.relative_to(repo)),
                    "--notes-output",
                    str(parser_repair_notes_path.relative_to(repo)),
                    "--log-dir",
                    str(log_dir.relative_to(repo)),
                ],
                repo,
                log_dir,
            )
            active_parser_repair_notes = parser_repair_notes_path
        else:
            print("[repair] skipped: parser-quality preflight reported no high/medium parser-artifact issues")

    active_reviewers_config = args.reviewers_config
    if args.reviewer_selection == "dynamic":
        selection, _selection_started_at = run_reviewer_selector(
            repo,
            paper_id,
            parsed_dir,
            optional_reviewers,
            selection_dir,
            selection_schema_path,
            log_dir,
            active_parser_repair_notes,
        )
        selection_errors = validate_selection_output(selection, paper_id, mandatory_reviewers, optional_reviewers)
        if selection_errors:
            raise RuntimeError("Reviewer selection failed: " + "; ".join(selection_errors))
        standard_reviewers = selected_reviewers_from_selection(selection, mandatory_reviewers, optional_reviewers)
        write_reviewers_config(selected_reviewers_config_path, [*preflight_reviewers, *standard_reviewers])
        active_reviewers_config = str(selected_reviewers_config_path.relative_to(repo))
        print("[selection] selected reviewers: " + ", ".join(reviewer.name for reviewer in standard_reviewers))
        run_required(
            "render-selected-prompts",
            render_prompts_command(
                paper_id=paper_id,
                parsed_dir=parsed_dir,
                reviews_dir=reviews_dir,
                schema_path=schema_path,
                prompts_dir=prompts_dir,
                reviewers_config=active_reviewers_config,
                repo=repo,
                parser_repair_notes=active_parser_repair_notes,
            ),
            repo,
            log_dir,
        )
    else:
        write_reviewers_config(selected_reviewers_config_path, [*preflight_reviewers, *standard_reviewers])
        if active_parser_repair_notes:
            active_reviewers_config = str(selected_reviewers_config_path.relative_to(repo))
            run_required(
                "render-repaired-prompts",
                render_prompts_command(
                    paper_id=paper_id,
                    parsed_dir=parsed_dir,
                    reviews_dir=reviews_dir,
                    schema_path=schema_path,
                    prompts_dir=prompts_dir,
                    reviewers_config=active_reviewers_config,
                    repo=repo,
                    parser_repair_notes=active_parser_repair_notes,
                ),
                repo,
                log_dir,
            )

    reviewer_started_at = run_reviewer_batch(
        standard_reviewers, repo, prompts_dir, reviews_dir, schema_path, log_dir
    )
    validation_errors = validate_reviewer_batch(
        standard_reviewers,
        reviewer_started_at,
        repo,
        paper_id,
        reviews_dir,
        schema_path,
        active_reviewers_config,
        log_dir,
        args.keep_going,
    )
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
            active_reviewers_config,
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
            active_reviewers_config,
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
    recover_editor_report_if_needed(report_path, editor_result.stderr_path)

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
