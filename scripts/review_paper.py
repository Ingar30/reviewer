from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pipeline_paths import paper_run_paths
from backend_settings import read_run_manifest, remember_backend, resolve_backend, slugify
from resume_review import ReviewCheckpoint, run_lease, atomic_write_json, preflight_receipt
from review_acceptance import require_complete
from claude_backend import (
    DEFAULT_MODEL as CLAUDE_DEFAULT_MODEL, EFFORTS as CLAUDE_EFFORTS,
    check_claude, claude_exec_command, claude_failure_hint, require_same_backend, save_claude_output,
)
from check_final_report import (
    DEFAULT_REQUIRED_HEADINGS as EDITOR_REPORT_REQUIRED_HEADINGS,
    REVIEW_SCOPE_HEADINGS as EDITOR_REPORT_SCOPE_HEADINGS,
    report_min_chars,
)
from render_prompts import SELECTOR_TEMPLATE, render_selection_prompt
from reviewer_config import ReviewerConfig, load_reviewers_config, split_reviewers, write_reviewers_config
from reviewer_routing import (
    REVIEWER_SELECTION_MODE,
    THEORY_REVIEWER_NAME,
    enforce_conservative_applicability,
    parser_quality_gate_findings,
    reviewer_catalog,
    selected_reviewers_from_selection,
    validate_selection_output,
)


SELECTOR_OUTPUT = "reviewer_selection.json"
REASONING_EFFORT_CHOICES = ("none", "low", "medium", "high", "xhigh", "max")


@dataclass
class RunResult:
    label: str
    returncode: int
    stdout_path: Path
    stderr_path: Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def codex_project_defaults(repo: Path) -> dict[str, object]:
    config_path = repo / ".codex" / "config.toml"
    if not config_path.exists():
        return {}
    with config_path.open("rb") as handle:
        return tomllib.load(handle)


def git_metadata(repo: Path) -> dict[str, object]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        return {"commit": commit, "dirty": dirty}
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def write_run_manifest(path: Path, data: dict[str, object]) -> None:
    atomic_write_json(path, data)


def codex_command() -> str:
    for candidate in ("codex.cmd", "codex.exe", "codex"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError("Could not find Codex CLI on PATH. Install Codex or add codex.cmd to PATH.")


def codex_exec_command(
    *, model: str | None = None, reasoning_effort: str | None = None, search: bool = False
) -> list[str]:
    command = [codex_command()]
    if search:
        command.append("--search")
    else:
        command.extend(["-c", 'web_search="disabled"'])
    if model:
        command.extend(["--model", model])
    if reasoning_effort:
        command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    command.append("exec")
    # Model tools may read evidence, never publish or modify it. The CLI itself
    # writes --output-last-message outside the model tool sandbox.
    command.extend(["--sandbox", "read-only"])
    if os.environ.get("ECONOMICS_REVIEWER_NON_GIT") == "1":
        command.append("--skip-git-repo-check")
    return command


def run_command(
    label: str,
    command: list[str],
    cwd: Path,
    log_dir: Path,
    input_text: str | None = None,
    timeout_seconds: float | None = None,
) -> RunResult:
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_label = slugify(label)
    stdout_path = log_dir / f"{safe_label}.stdout.log"
    stderr_path = log_dir / f"{safe_label}.stderr.log"

    print(f"[run] {label}")
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            start_new_session=os.name != "nt",
        )
        try:
            process.communicate(input=input_text, timeout=timeout_seconds)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            stop_process(process)
            stderr.write(f"\nTimed out after {timeout_seconds:.0f} seconds.\n")
            returncode = 124
        finally:
            stop_process(process)
    if returncode != 0:
        if hint := claude_failure_hint(stdout_path):
            with stderr_path.open("a", encoding="utf-8") as handle:
                handle.write("\n" + hint + "\n")
            print(f"[error] {hint}")
        print(f"[fail] {label} exited {returncode}; see {stderr_path}")
    else:
        print(f"[ok] {label}")
    return RunResult(label, returncode, stdout_path, stderr_path)


def stop_process(process) -> None:
    """Stop only a process tree started by this wrapper, preserving its log files."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait()


def agent_exec_command(
    *, backend: str = "codex", model: str | None = None,
    reasoning_effort: str | None = None, search: bool = False,
    output_path: Path, schema_path: Path | None = None,
) -> list[str]:
    if backend == "claude":
        return claude_exec_command(
            model=model, reasoning_effort=reasoning_effort, search=search, schema_path=schema_path,
        )
    if backend != "codex":
        raise ValueError(f"Unknown backend: {backend}")
    command = codex_exec_command(model=model, reasoning_effort=reasoning_effort, search=search)
    if schema_path:
        command.extend(["--output-schema", str(schema_path)])
    command.extend(["--output-last-message", str(output_path), "-"])
    return command


def run_required(
    label: str,
    command: list[str],
    cwd: Path,
    log_dir: Path,
    input_text: str | None = None,
    timeout_seconds: float | None = None,
) -> RunResult:
    result = run_command(
        label,
        command,
        cwd,
        log_dir,
        input_text=input_text,
        timeout_seconds=timeout_seconds,
    )
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
    model: str | None = None,
    reasoning_effort: str | None = None,
    backend: str = "codex",
    *, prompt_override: str | None = None,
) -> tuple[ReviewerConfig, subprocess.Popen[str], Path, Path, float]:
    prompt_path = prompts_dir / reviewer.prompt
    output_path = reviews_dir / reviewer.output
    stdout_path = log_dir / f"{reviewer.name}.stdout.log"
    stderr_path = log_dir / f"{reviewer.name}.stderr.log"
    prompt_text = prompt_override if prompt_override is not None else prompt_path.read_text(encoding="utf-8")
    archive_previous_output(output_path, log_dir)

    command = agent_exec_command(
        backend=backend, model=model, reasoning_effort=reasoning_effort, search=reviewer.search,
        schema_path=(repo / schema_path) if backend == "claude" else schema_path,
        output_path=output_path,
    )

    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    print(f"[start] {reviewer.name}")
    process = None
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=stdout_handle, stderr=stderr_handle,
            text=True, encoding="utf-8", errors="replace", cwd=repo,
            start_new_session=os.name != "nt",
        )
        assert process.stdin is not None
        process.stdin.write(prompt_text)
        process.stdin.close()
    except BaseException:
        if process is not None:
            stop_process(process)
        stdout_handle.close()
        stderr_handle.close()
        raise
    process._reviewer_stdout_handle = stdout_handle  # type: ignore[attr-defined]
    process._reviewer_stderr_handle = stderr_handle  # type: ignore[attr-defined]
    if backend == "claude":
        process._claude_output = (output_path, repo / schema_path)  # type: ignore[attr-defined]
    return reviewer, process, stdout_path, stderr_path, time.monotonic()


def wait_reviewer(
    reviewer: ReviewerConfig,
    process: subprocess.Popen[str],
    stdout_path: Path,
    stderr_path: Path,
    started_at: float,
    timeout_seconds: float | None = None,
) -> RunResult:
    remaining = None
    if timeout_seconds is not None:
        remaining = max(0.1, timeout_seconds - (time.monotonic() - started_at))
    try:
        returncode = process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        stop_process(process)
        returncode = 124
        with stderr_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\nTimed out after {timeout_seconds:.0f} seconds.\n")
    process._reviewer_stdout_handle.close()  # type: ignore[attr-defined]
    process._reviewer_stderr_handle.close()  # type: ignore[attr-defined]
    if returncode == 0 and hasattr(process, "_claude_output"):
        try:
            save_claude_output(stdout_path, *process._claude_output)
        except (ValueError, OSError) as exc:
            with stderr_path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n{exc}\n")
            returncode = 1
    if returncode == 0:
        print(f"[ok] {reviewer.name}")
    else:
        if hasattr(process, "_claude_output") and (hint := claude_failure_hint(stdout_path)):
            with stderr_path.open("a", encoding="utf-8") as handle:
                handle.write("\n" + hint + "\n")
            print(f"[error] {hint}")
        print(f"[fail] {reviewer.name} exited {returncode}; see {stderr_path}")
    return RunResult(reviewer.name, returncode, stdout_path, stderr_path)


def require_fresh_file(path: Path, started_at: float, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if path.stat().st_mtime < started_at:
        raise RuntimeError(f"{label} is stale and was not regenerated in this run: {path}")


def archive_previous_output(path: Path, log_dir: Path) -> None:
    """Existence after a call cannot be satisfied by a same-second stale file."""
    if path.exists():
        from uuid import uuid4
        log_dir.mkdir(parents=True, exist_ok=True)
        path.replace(log_dir / (path.name + "." + uuid4().hex + ".previous"))


def plausible_editor_report(text: str, *, bundle: dict | None = None) -> bool:
    stripped = text.strip()
    if len(stripped) < report_min_chars(bundle):
        return False
    if not stripped.startswith("# Multi-Agent Paper Review Report"):
        return False
    return all(heading in stripped for heading in EDITOR_REPORT_REQUIRED_HEADINGS) and any(
        heading in stripped for heading in EDITOR_REPORT_SCOPE_HEADINGS
    )


def extract_editor_report_from_transcript(text: str, *, bundle: dict | None = None) -> str | None:
    starts = [match.start() for match in re.finditer(r"(?m)^# Multi-Agent Paper Review Report\s*$", text)]
    for start in reversed(starts):
        candidate = text[start:]
        end_match = re.search(r"(?m)^(?:collab:|tokens used\b)", candidate)
        if end_match:
            candidate = candidate[: end_match.start()]
        candidate = candidate.strip()
        if plausible_editor_report(candidate, bundle=bundle):
            return candidate + "\n"
    return None


def recover_editor_report_if_needed(report_path: Path, editor_stderr_path: Path,
                                   *, bundle: dict | None = None) -> None:
    current = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    if plausible_editor_report(current, bundle=bundle):
        return

    transcript = editor_stderr_path.read_text(encoding="utf-8") if editor_stderr_path.exists() else ""
    recovered = extract_editor_report_from_transcript(transcript, bundle=bundle)
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


def finding_label(finding: dict) -> str:
    finding_id = finding.get("id", "unknown-id")
    summary = " ".join(str(finding.get("finding_summary", "")).split())
    if not summary:
        summary = " ".join(str(finding.get("claim_text", "")).split())
    return f"{finding_id}: {summary}" if summary else str(finding_id)


def enforce_preflight_gate(reviewer: ReviewerConfig, output_path: Path) -> None:
    data = json.loads(output_path.read_text(encoding="utf-8"))
    require_complete(data)
    if reviewer.name != "parser_quality_auditor":
        return
    blockers, warnings = parser_quality_gate_findings(data)
    for finding in warnings:
        print(f"[warn] parser quality: {finding_label(finding)}")
    if blockers:
        blocker_text = "; ".join(finding_label(finding) for finding in blockers)
        raise RuntimeError(f"blocking parser-quality findings: {blocker_text}")


def render_selector_prompt(
    repo: Path,
    paper_id: str,
    parsed_dir: Path,
    optional_reviewers: list[ReviewerConfig],
    selection_schema_path: Path,
) -> str:
    return render_selection_prompt(
        repo / "prompts/templates", paper_id, str(parsed_dir.relative_to(repo)),
        str(selection_schema_path.relative_to(repo)), optional_reviewers,
    )


def run_reviewer_selector(
    repo: Path,
    paper_id: str,
    parsed_dir: Path,
    optional_reviewers: list[ReviewerConfig],
    selection_dir: Path,
    selection_schema_path: Path,
    log_dir: Path,
    model: str | None = None,
    reasoning_effort: str | None = None,
    timeout_seconds: float | None = None,
    backend: str = "codex",
) -> tuple[dict, float]:
    selection_dir.mkdir(parents=True, exist_ok=True)
    output_path = selection_dir / SELECTOR_OUTPUT
    archive_previous_output(output_path, log_dir)
    prompt_text = render_selector_prompt(
        repo,
        paper_id,
        parsed_dir,
        optional_reviewers,
        selection_schema_path,
    )
    started_at = time.time() - 1.0
    result = run_required(
        "reviewer-selector",
        agent_exec_command(
            backend=backend, model=model, reasoning_effort=reasoning_effort,
            schema_path=selection_schema_path if backend == "claude" else selection_schema_path.relative_to(repo),
            output_path=output_path.relative_to(repo),
        ),
        repo,
        log_dir,
        input_text=prompt_text,
        timeout_seconds=timeout_seconds,
    )
    if backend == "claude":
        save_claude_output(result.stdout_path, output_path, selection_schema_path)
    require_fresh_file(output_path, started_at, "reviewer selector output")
    return json.loads(output_path.read_text(encoding="utf-8")), started_at






def run_reviewer_batch(
    reviewers: list[ReviewerConfig],
    repo: Path,
    prompts_dir: Path,
    reviews_dir: Path,
    schema_path: Path,
    log_dir: Path,
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_parallel: int = 4,
    timeout_seconds: float | None = None,
    backend: str = "codex",
    on_result=None,
    max_repair_calls: int = 0,
) -> float:
    if not reviewers:
        return time.time() - 1.0
    from resume_review import digest, runtime_snapshot
    parsed = prompts_dir.parent / "parsed"
    def evidence_snapshot():
        snapshot = {**runtime_snapshot(repo), **{str(p): digest(p) for p in parsed.rglob("*") if p.is_file()}}
        manifest = parsed / "manifest.json"
        if manifest.is_file():
            source = json.loads(manifest.read_text(encoding="utf-8")).get("source_pdf")
            if source:
                source = Path(source)
                source = source if source.is_absolute() else repo / source
                snapshot[str(source)] = digest(source)
        return snapshot
    frozen = evidence_snapshot()
    reviewer_started_at = time.time() - 1.0
    for start in range(0, len(reviewers), max_parallel):
        batch = reviewers[start : start + max_parallel]
        running, reviewer_results = [], []
        try:
            for reviewer in batch:
                running.append(start_reviewer(
                    reviewer, repo, prompts_dir, reviews_dir,
                    schema_path.relative_to(repo), log_dir, model, reasoning_effort, backend,
                ))
            for item in running:
                result = wait_reviewer(*item, timeout_seconds=timeout_seconds)
                if evidence_snapshot() != frozen:
                    raise ValueError("Runtime or source evidence changed during reviewer execution; not accepted.")
                reviewer = item[0]
                output = reviews_dir / reviewer.output
                if result.returncode == 0:
                    errors = reviewer_output_errors(output, reviewer, repo, parsed.parent.name, schema_path)
                    if errors:
                        from stage_repair import reserve_repair
                        repair = reserve_repair(parsed.parent, reviewer.name, max_repair_calls, output, errors,
                            (prompts_dir / reviewer.prompt).read_text(encoding="utf-8"), repo) if output.is_file() else None
                        if repair:
                            repair_dir, prompt = repair
                            print(f"[repair] {reviewer.name}: one additional call; errors retained in {repair_dir}")
                            retry = start_reviewer(reviewer, repo, prompts_dir, reviews_dir, schema_path.relative_to(repo),
                                repair_dir, model, reasoning_effort, backend, prompt_override=prompt)
                            try:
                                result = wait_reviewer(*retry, timeout_seconds=timeout_seconds)
                            finally:
                                stop_process(retry[1])
                            if result.returncode == 0:
                                errors = reviewer_output_errors(output, reviewer, repo, parsed.parent.name, schema_path)
                        if errors:
                            (log_dir / (reviewer.name + ".validation.json")).write_text(json.dumps(errors, indent=2)+"\n", encoding="utf-8")
                            print(f"[invalid] {reviewer.name}: " + "; ".join(errors))
                reviewer_results.append(result)
                if evidence_snapshot() != frozen:
                    raise ValueError("Runtime or source evidence changed during reviewer execution; not accepted.")
                if on_result:
                    on_result(item[0], result, reviewer_started_at)
        finally:
            finished = {result.label for result in reviewer_results}
            for item in running:
                reviewer, process = item[:2]
                if reviewer.name in finished:
                    continue
                stop_process(process)
                result = wait_reviewer(*item)
                if on_result:
                    on_result(reviewer, result, reviewer_started_at)
        failed_reviewers = [result for result in reviewer_results if result.returncode != 0]
        if failed_reviewers:
            failures = ", ".join(
                f"{result.label} ({result.returncode})" for result in failed_reviewers
            )
            raise RuntimeError(f"Reviewer run failed: {failures}")
    return reviewer_started_at


def reviewer_output_errors(path, reviewer, repo, paper_id, schema_path):
    from strict_json import read_json
    from validate_review_json import validate_review_output
    try:
        return validate_review_output(read_json(path), read_json(schema_path), [reviewer], repo=repo,
            expected_reviewer=reviewer.name, paper_id=paper_id, require_complete=True)
    except (OSError, ValueError) as exc:
        return [str(exc)]


def render_prompts_command(
    *,
    paper_id: str,
    parsed_dir: Path,
    reviews_dir: Path,
    schema_path: Path,
    prompts_dir: Path,
    reviewers_config: str,
    repo: Path,
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
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description="Run the full paper-review pipeline for one PDF.")
    parser.add_argument("--backend", choices=("codex", "claude"), default=None,
                        help="Execution CLI; remembers explicit choices for new reviews. Otherwise uses the saved run/workspace, then codex.")
    parser.add_argument("--pdf", required=True, help="Path to source PDF, usually under inputs/")
    parser.add_argument("--paper-id", default=None, help="Optional paper id; defaults to the PDF filename stem")
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue validating remaining reviewer outputs after a reviewer-output validation error.",
    )
    parser.add_argument("--reviewers-config", default="config/reviewers.json")
    parser.add_argument("--max-repair-calls", type=int, default=1,
                        help="Total extra output-repair calls for this paper (default 1, 0 disables); at most one per stage, including resumes.")
    parser.add_argument(
        "--resume-incomplete", action="store_true",
        help="Reuse validated completed reviewers with identical PDF, settings and runtime; retry only unfinished stages.",
    )
    parser.add_argument(
        "--resume-after-preflight",
        action="store_true",
        help=(
            "Reuse existing deterministic parsed artifacts and validated preflight JSON for the same "
            "paper ID and PDF hash, then continue from reviewer selection."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Override the model used by all agents. Codex defaults come from "
            ".codex/config.toml; --backend claude defaults to claude-opus-5-5."
        ),
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORT_CHOICES,
        default="xhigh",
        help=(
            "Override the reasoning effort for substantive reviewers and the editor. "
            "The recommended default is xhigh."
        ),
    )
    parser.add_argument(
        "--preflight-reasoning-effort",
        choices=REASONING_EFFORT_CHOICES,
        default="high",
        help="Reasoning effort for parser-quality preflight. Default: high.",
    )
    parser.add_argument(
        "--selector-reasoning-effort",
        choices=REASONING_EFFORT_CHOICES,
        default="high",
        help="Reasoning effort for conservative reviewer applicability routing. Default: high.",
    )
    parser.add_argument(
        "--max-parallel-reviewers",
        type=int,
        default=4,
        help="Maximum reviewer agents to run at once. Default: 4.",
    )
    parser.add_argument(
        "--agent-timeout-minutes",
        type=float,
        default=45.0,
        help="Timeout for each preflight, substantive reviewer, and editor agent. Default: 45 minutes.",
    )
    parser.add_argument(
        "--selector-timeout-minutes",
        type=float,
        default=15.0,
        help="Timeout for reviewer applicability routing. Default: 15 minutes.",
    )
    args = parser.parse_args()

    if args.resume_incomplete and args.resume_after_preflight:
        parser.error("Choose --resume-incomplete or --resume-after-preflight, not both.")

    if args.max_parallel_reviewers < 1:
        raise ValueError("--max-parallel-reviewers must be at least 1")
    if args.max_repair_calls < 0:
        raise ValueError("--max-repair-calls must be nonnegative")
    if args.agent_timeout_minutes <= 0 or args.selector_timeout_minutes <= 0:
        raise ValueError("agent timeouts must be greater than zero")

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
    with run_lease(repo / "work" / paper_id):
        manifest_path = paper_run_paths(repo, paper_id).run_manifest_path
        previous = manifest_path.read_bytes() if manifest_path.exists() else None
        try:
            return execute_pipeline(args, repo, pdf_path, paper_id)
        except BaseException as exc:
            # Do not alter old evidence on a rejected recovery attempt.
            if manifest_path.exists() and manifest_path.read_bytes() != previous:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                                stopped_at_utc=utc_now(), failure_type=type(exc).__name__)
                write_run_manifest(manifest_path, manifest)
            raise


def execute_pipeline(args, repo: Path, pdf_path: Path, paper_id: str) -> int:
    paths = paper_run_paths(repo, paper_id)
    parsed_dir = paths.parsed_dir
    prompts_dir = paths.prompts_dir
    reviews_dir = paths.reviews_dir
    selection_dir = paths.selection_dir
    log_dir = paths.log_dir
    outputs_dir = paths.outputs_dir
    report_path = paths.report_path
    schema_path = repo / "schemas" / "reviewer_output.schema.json"
    selection_schema_path = repo / "schemas" / "reviewer_selection.schema.json"
    bundle_path = paths.bundle_path
    editor_input_path = paths.editor_input_path
    reviewers_config_path = repo / args.reviewers_config if not Path(args.reviewers_config).is_absolute() else Path(args.reviewers_config)
    reviewers = load_reviewers_config(reviewers_config_path)
    preflight_reviewers, mandatory_reviewers, optional_reviewers = split_reviewers(reviewers)
    standard_reviewers = [reviewer for reviewer in reviewers if reviewer.stage == "review"]
    selected_reviewers_config_path = paths.selected_reviewers_config_path

    prior_manifest = read_run_manifest(paths.run_manifest_path)
    explicit_backend = args.backend
    args.backend, backend_source = resolve_backend(repo, explicit_backend, prior_manifest)
    preserve_preference = os.environ.get("ECONOMICS_REVIEWER_PRESERVE_BACKEND_PREFERENCE") == "1"
    if preserve_preference:
        backend_source = "launcher selection"
    project_defaults = codex_project_defaults(repo)
    if args.backend == "claude":
        args.model = args.model or CLAUDE_DEFAULT_MODEL
        if any(effort not in CLAUDE_EFFORTS for effort in (
            args.reasoning_effort, args.preflight_reasoning_effort, args.selector_reasoning_effort,
        )):
            raise ValueError("Claude does not support reasoning effort none; choose low through max.")
    effective_model = args.model or project_defaults.get("model")
    effective_reasoning = args.reasoning_effort or project_defaults.get("model_reasoning_effort")
    source_pdf_sha256 = file_sha256(pdf_path)
    require_same_backend(args.backend, prior_manifest)
    print(f"[backend] {args.backend} ({backend_source})")
    print(f"[model] {effective_model or 'Codex default'}")
    checkpoint_settings = {
        "paper_id": paper_id, "source_pdf_sha256": source_pdf_sha256,
        "backend": args.backend, "model": effective_model,
        "reasoning_effort": effective_reasoning,
        "preflight_reasoning_effort": args.preflight_reasoning_effort,
        "selector_reasoning_effort": args.selector_reasoning_effort,
        "reviewers_config": args.reviewers_config,
    }
    if args.resume_incomplete:
        return resume_incomplete(args, repo, paths, checkpoint_settings)
    if args.resume_after_preflight:
        if not prior_manifest:
            raise RuntimeError("--resume-after-preflight requires an existing valid run_manifest.json")
        if prior_manifest.get("source_pdf_sha256") != source_pdf_sha256:
            raise RuntimeError("Cannot resume: source PDF hash differs from the prior run")
        required_resume_paths = [parsed_dir / "manifest.json"] + [
            reviews_dir / reviewer.output for reviewer in preflight_reviewers
        ]
        missing_resume_paths = [path for path in required_resume_paths if not path.is_file()]
        if missing_resume_paths:
            raise RuntimeError(
                "Cannot resume; missing parsed/preflight artifacts: "
                + ", ".join(str(path.relative_to(repo)) for path in missing_resume_paths)
            )
        try:
            parsed_manifest = json.loads(
                (parsed_dir / "manifest.json").read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError("Cannot resume: parsed manifest is not valid JSON") from exc
        if parsed_manifest.get("source_pdf_sha256") != source_pdf_sha256:
            raise RuntimeError(
                "Cannot resume: parsed artifacts do not record the current source PDF hash"
            )
        preflight_receipt(repo, paths, checkpoint_settings, preflight_reviewers, reuse=True)
    claude_version = check_claude(repo) if args.backend == "claude" else None
    if explicit_backend is not None and not args.resume_after_preflight and not preserve_preference:
        remember_backend(repo, args.backend)
    run_started = time.time()
    run_manifest: dict[str, object] = {
        "paper_id": paper_id,
        "status": "running",
        "started_at_utc": utc_now(),
        "source_pdf": str(pdf_path.relative_to(repo) if repo in pdf_path.parents else pdf_path),
        "source_pdf_sha256": source_pdf_sha256,
        "model": effective_model,
        "backend": args.backend,
        "backend_source": backend_source,
        "reviewer_editor_reasoning_effort": effective_reasoning,
        "preflight_reasoning_effort": args.preflight_reasoning_effort,
        "selector_reasoning_effort": args.selector_reasoning_effort,
        "reviewer_selection": REVIEWER_SELECTION_MODE,
        "max_parallel_reviewers": args.max_parallel_reviewers,
        "agent_timeout_minutes": args.agent_timeout_minutes,
        "selector_timeout_minutes": args.selector_timeout_minutes,
        "reviewers_config": args.reviewers_config,
        "resumed_after_preflight": args.resume_after_preflight,
        "python": sys.version,
        "git": git_metadata(repo),
        "capabilities": {
            "requested": {"model_tools": "read-only", "non_search_roles": "web_search disabled"},
            "effective": "host-dependent; requested capabilities are not an enforcement receipt",
            "isolation": "degraded: read-only execution does not isolate absolute-path reads or connected tools",
            "inference": "cloud-backed; disabling search does not make inference local",
        },
    }
    if claude_version:
        run_manifest["backend_version"] = claude_version
        run_manifest["backend_permissions"] = "read-only tools; search roles also WebSearch/WebFetch; dontAsk"
    if args.resume_after_preflight:
        run_manifest["reused_preflight"] = prior_manifest.get("reused_preflight") or {
            "backend": prior_manifest.get("backend", "codex"), "model": prior_manifest.get("model"),
            "reasoning_effort": prior_manifest.get("preflight_reasoning_effort"),
        }
    write_run_manifest(paths.run_manifest_path, run_manifest)

    log_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    print(f"[paper] {paper_id}")
    print(f"[pdf] {pdf_path}")
    print(f"[reasoning] preflight={args.preflight_reasoning_effort}, selector={args.selector_reasoning_effort}, reviewers/editor={effective_reasoning or 'Codex default'}")

    if not args.resume_after_preflight:
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
    else:
        print("[resume] reusing deterministic parsed artifacts and preflight outputs")

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

    if args.resume_after_preflight:
        for reviewer in preflight_reviewers:
            output_path = reviews_dir / reviewer.output
            validate_reviewer_json(output_path, reviewer.name, paper_id)
            run_required(
                f"validate-resumed-{reviewer.name}",
                [
                    sys.executable,
                    "scripts/validate_review_json.py",
                    "--schema",
                    str(schema_path.relative_to(repo)),
                    "--input",
                    str(output_path.relative_to(repo)),
                    "--reviewers-config",
                    args.reviewers_config,
                ],
                repo,
                log_dir,
            )
            enforce_preflight_gate(reviewer, output_path)
    else:
        preflight_started_at = run_reviewer_batch(
            preflight_reviewers,
            repo,
            prompts_dir,
            reviews_dir,
            schema_path,
            log_dir,
            args.model,
            args.preflight_reasoning_effort,
            args.max_parallel_reviewers,
            args.agent_timeout_minutes * 60,
            args.backend,
            max_repair_calls=args.max_repair_calls,
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

    if not args.resume_after_preflight:
        preflight_receipt(repo, paths, checkpoint_settings, preflight_reviewers)

    selection, _selection_started_at = run_reviewer_selector(
        repo,
        paper_id,
        parsed_dir,
        optional_reviewers,
        selection_dir,
        selection_schema_path,
        log_dir,
        args.model,
        args.selector_reasoning_effort,
        args.selector_timeout_minutes * 60,
        args.backend,
    )
    selection_errors = validate_selection_output(
        selection,
        paper_id,
        mandatory_reviewers,
        optional_reviewers,
    )
    if selection_errors:
        raise RuntimeError("Reviewer applicability routing failed: " + "; ".join(selection_errors))
    selection = enforce_conservative_applicability(selection, optional_reviewers)
    selection_errors = validate_selection_output(
        selection,
        paper_id,
        mandatory_reviewers,
        optional_reviewers,
    )
    if selection_errors:
        raise RuntimeError(
            "Conservative reviewer applicability guardrail failed: "
            + "; ".join(selection_errors)
        )
    write_run_manifest(selection_dir / SELECTOR_OUTPUT, selection)
    standard_reviewers = selected_reviewers_from_selection(
        selection, mandatory_reviewers, optional_reviewers
    )
    write_reviewers_config(
        selected_reviewers_config_path, [*preflight_reviewers, *standard_reviewers]
    )
    active_reviewers_config = str(selected_reviewers_config_path.relative_to(repo))
    print(
        "[selection] applicability roster: "
        + ", ".join(reviewer.name for reviewer in standard_reviewers)
    )
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
        ),
        repo,
        log_dir,
    )

    checkpoint = ReviewCheckpoint(repo, paths, checkpoint_settings)
    checkpoint.create()
    reviewer_started_at = run_reviewer_batch(
        standard_reviewers,
        repo,
        prompts_dir,
        reviews_dir,
        schema_path,
        log_dir,
        args.model,
        args.reasoning_effort,
        args.max_parallel_reviewers,
        args.agent_timeout_minutes * 60,
        args.backend,
        on_result=checkpoint.accept,
        max_repair_calls=args.max_repair_calls,
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

    finish_review(args, repo, paths, log_dir)
    checkpoint.complete()
    run_manifest.update(
        {
            "status": "complete", "completed_at_utc": utc_now(),
            "duration_seconds": round(time.time() - run_started, 3),
            "selected_reviewers": [reviewer.name for reviewer in standard_reviewers],
            "report": str(report_path.relative_to(repo)),
        }
    )
    write_run_manifest(paths.run_manifest_path, run_manifest)
    print(f"[done] report: {report_path.relative_to(repo)}")
    print(f"[logs] {log_dir.relative_to(repo)}")
    return 0


def resume_incomplete(args, repo, paths, settings) -> int:
    checkpoint = ReviewCheckpoint(repo, paths, settings)
    checkpoint.load()  # Fail closed before changing saved artifacts or calling a model.
    if checkpoint.data.get("report_sha256"):
        manifest = json.loads(paths.run_manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "complete":
            manifest.update(status="complete", completed_at_utc=utc_now(),
                            recovered_completion_receipt=True)
            write_run_manifest(paths.run_manifest_path, manifest)
        print(f"[done] completed report retained: {paths.report_path.relative_to(repo)}")
        return 0
    if args.backend == "claude":
        check_claude(repo)
    for reviewer in checkpoint.reviewers:
        if reviewer.stage == "preflight":
            enforce_preflight_gate(reviewer, paths.reviews_dir / reviewer.output)
    missing = [r for r in checkpoint.reviewers
               if r.stage == "review" and r.name not in checkpoint.data["accepted"]]
    log_dir = checkpoint.attempt_dir()
    manifest = json.loads(paths.run_manifest_path.read_text(encoding="utf-8"))
    manifest.update(status="running", resumed_at_utc=utc_now(),
                    resume_attempt=str(log_dir.relative_to(repo)))
    write_run_manifest(paths.run_manifest_path, manifest)
    print(f"[resume] retained {len(checkpoint.data['accepted'])} reviewers; {len(missing)} unfinished")
    run_reviewer_batch(
        missing, repo, paths.prompts_dir, paths.reviews_dir,
        repo / "schemas/reviewer_output.schema.json", log_dir,
        settings["model"], args.reasoning_effort, args.max_parallel_reviewers,
        args.agent_timeout_minutes * 60, args.backend, on_result=checkpoint.accept,
        max_repair_calls=args.max_repair_calls,
    )
    if any(r.name not in checkpoint.data["accepted"] for r in missing):
        raise RuntimeError("Unfinished reviewers failed validation; see retained attempt logs.")
    finish_review(args, repo, paths, log_dir)
    checkpoint.complete()
    manifest = json.loads(paths.run_manifest_path.read_text(encoding="utf-8"))
    manifest.update(status="complete", completed_at_utc=utc_now(),
                    resumed_incomplete=True, report=str(paths.report_path.relative_to(repo)),
                    selected_reviewers=[r.name for r in checkpoint.reviewers if r.stage == "review"])
    write_run_manifest(paths.run_manifest_path, manifest)
    print(f"[done] report: {paths.report_path.relative_to(repo)}")
    print(f"[logs] {log_dir.relative_to(repo)}")
    return 0


def finish_review(args, repo, paths, log_dir):
    """Shared deterministic assembly and editor path for fresh and selective-resume runs."""
    paper_id = slugify(args.paper_id or Path(args.pdf).stem)
    reviews_dir, prompts_dir = paths.reviews_dir, paths.prompts_dir
    bundle_path, editor_input_path, report_path = paths.bundle_path, paths.editor_input_path, paths.report_path
    active_reviewers_config = str(paths.selected_reviewers_config_path.relative_to(repo))

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

    run_editor(args, repo, paths, log_dir)


def run_editor(args, repo, paths, log_dir):
    """One editorial contract for fresh runs and editor-only refresh."""
    bundle_path, editor_input_path, report_path = paths.bundle_path, paths.editor_input_path, paths.report_path
    editor_input = editor_input_path.read_text(encoding="utf-8")
    decisions_path = paths.editor_dir / "editor_decisions.json"
    archive_previous_output(decisions_path, log_dir)
    editor_started_at = time.time()
    editor_schema = repo / "schemas/editor_decisions.schema.json"
    from editor_decisions import assemble
    active_log, prompt = log_dir, editor_input
    for attempt in range(2):
        editor_started_at = time.time()
        editor_result = run_required(
            "editor", agent_exec_command(backend=args.backend, model=args.model,
                reasoning_effort=args.reasoning_effort, output_path=decisions_path.relative_to(repo),
                schema_path=editor_schema), repo, active_log, input_text=prompt,
            timeout_seconds=args.agent_timeout_minutes * 60,
        )
        try:
            if args.backend == "claude":
                save_claude_output(editor_result.stdout_path, decisions_path, editor_schema)
            require_fresh_file(decisions_path, editor_started_at, "editor decisions")
            assemble(decisions_path, bundle_path, report_path, editor_schema)
            break
        except (ValueError, OSError) as exc:
            from stage_repair import reserve_repair
            repair = reserve_repair(paths.work_root, "editor", getattr(args, "max_repair_calls", 1),
                decisions_path, [str(exc)], editor_input, repo) if attempt == 0 and decisions_path.is_file() else None
            if repair is None:
                raise
            active_log, prompt = repair
            archive_previous_output(decisions_path, active_log)
            print(f"[repair] editor: one additional call; rejected draft retained in {active_log}")

    check_result = run_required(
        "check-final-report",
        [
            sys.executable,
            "scripts/check_final_report.py",
            "--input",
            str(report_path.relative_to(repo)),
            "--bundle",
            str(bundle_path.relative_to(repo)),
            "--decisions", str(decisions_path.relative_to(repo)),
        ],
        repo,
        log_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
