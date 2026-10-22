from __future__ import annotations

import argparse
import json
import subprocess
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pipeline_paths import paper_run_paths
from backend_settings import read_run_manifest, resolve_backend
from review_paper import enforce_preflight_gate, agent_exec_command, run_required, codex_project_defaults
from claude_backend import DEFAULT_MODEL, EFFORTS, check_claude, require_same_backend, save_claude_output
from reviewer_config import load_reviewers_config
from resume_review import ReviewCheckpoint, digest, atomic_write_json, run_lease


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def require_paths(paths: dict[str, Path]) -> None:
    missing = [f"{name}: {path}" for name, path in paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("Editor refresh prerequisites are missing:\n- " + "\n- ".join(missing))


def archive_editor_products(report: Path, editor_dir: Path, editor_input: Path, log_dir: Path) -> Path:
    import tempfile
    log_dir.mkdir(parents=True, exist_ok=True)
    # Atomically reserve a short unique directory. A nested 32-character UUID
    # pushed otherwise valid Windows workspaces past MAX_PATH during refresh.
    attempt_log = Path(tempfile.mkdtemp(prefix="editor-", dir=log_dir))
    for old in [report, *editor_dir.glob("*.json"), editor_input]:
        if old.is_file():
            shutil.copy2(old, attempt_log / (old.name + ".previous"))
    return attempt_log


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
    manifest_path: Path, report: Path, repo: Path, reviewer_names: list[str],
    editor_settings: dict | None = None,
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
    if editor_settings:
        manifest["refreshed_editor"] = editor_settings
    atomic_write_json(manifest_path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate existing reviews, rebuild the normalized bundle, and refresh editor output."
    )
    parser.add_argument("--backend", choices=("codex", "claude"), default=None,
                        help="Execution CLI; defaults to the saved run/workspace, then codex.")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--max-repair-calls", type=int, default=1,
                        help="Per-paper extra call cap, including earlier repairs; at most one repair per stage.")
    parser.add_argument(
        "--run-editor",
        action="store_true",
        help="Run the selected CLI editor and final report check. By default only rerenders prompts and rebuilds editor input.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Override the editor model when --run-editor is used. "
            "Codex defaults come from .codex/config.toml; Claude reuses saved run settings."
        ),
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
        default=None,
        help=(
            "Override editor reasoning when --run-editor is used. "
            "Codex defaults come from .codex/config.toml; Claude reuses saved run settings."
        ),
    )
    args = parser.parse_args()
    if args.max_repair_calls < 0:
        parser.error("--max-repair-calls must be nonnegative")

    repo = repo_root()
    paths = paper_run_paths(repo, args.paper_id)
    with run_lease(paths.work_root):
        before = paths.run_manifest_path.read_bytes() if paths.run_manifest_path.exists() else None
        try:
            return execute_refresh(args, repo, paths)
        except BaseException as exc:
            if paths.run_manifest_path.is_file() and paths.run_manifest_path.read_bytes() != before:
                manifest = read_run_manifest(paths.run_manifest_path)
                if manifest and manifest.get("status") == "editor_pending":
                    manifest.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                                    failure_type=type(exc).__name__)
                    atomic_write_json(paths.run_manifest_path, manifest)
            raise


def execute_refresh(args, repo, paths):
    prior_manifest = read_run_manifest(paths.run_manifest_path)
    checkpoint_path = paths.work_root / "resume_checkpoint.json"
    if not prior_manifest or not checkpoint_path.is_file():
        raise ValueError("Editor refresh requires current acceptance receipts. Keep legacy artifacts with their original runtime; completion is unconfirmed.")
    saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    source = Path(prior_manifest["source_pdf"])
    if not source.is_absolute():
        source = repo / source
    if not source.is_file() or digest(source) != prior_manifest.get("source_pdf_sha256"):
        raise ValueError("Editor refresh refused: source PDF changed or missing.")
    checkpoint = ReviewCheckpoint(repo, paths, saved.get("settings", {}))
    checkpoint.load()
    expected = {r.name for r in checkpoint.reviewers if r.stage == "review"}
    if expected != set(checkpoint.data["accepted"]):
        raise ValueError("Editor refresh refused: unfinished reviewers lack acceptance receipts.")
    args.backend, backend_source = resolve_backend(repo, args.backend, prior_manifest)
    require_same_backend(args.backend, prior_manifest)
    print(f"[backend] {args.backend} ({backend_source})")
    if args.backend == "claude":
        prior = prior_manifest or {}
        args.model = args.model or prior.get("model") or DEFAULT_MODEL
        args.reasoning_effort = args.reasoning_effort or prior.get("reviewer_editor_reasoning_effort") or "xhigh"
        if args.reasoning_effort not in EFFORTS:
            raise ValueError("Claude does not support reasoning effort none; choose low through max.")
        if args.run_editor:
            check_claude(repo)
    print(f"[model] {args.model or codex_project_defaults(repo).get('model') or 'Codex default'}")
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
    # Preserve the prior completed synthesis, then explicitly mark this attempt
    # incomplete before rebuilding any editor product. A preparation-only refresh
    # must not leave an obsolete completion receipt attached to new inputs.
    attempt_log = archive_editor_products(report, editor_dir, editor_input, paths.log_dir)
    checkpoint.data.pop("report_sha256", None)
    checkpoint.data.pop("editor_files", None)
    checkpoint.save()
    prior_manifest.update(status="editor_pending", editor_refresh_attempt=str(attempt_log.relative_to(repo)))
    atomic_write_json(paths.run_manifest_path, prior_manifest)
    prepare_editor_input(args.paper_id, repo, paths, selected)

    if args.run_editor:
        from review_paper import run_editor
        args.agent_timeout_minutes = 45
        run_editor(args, repo, paths, attempt_log)
        checkpoint.complete()
        mark_run_manifest_complete(
            paths.run_manifest_path,
            report,
            repo,
            [reviewer.name for reviewer in review_stage],
            {"backend": args.backend,
             "model": args.model or codex_project_defaults(repo).get("model"),
             "reasoning_effort": args.reasoning_effort or codex_project_defaults(repo).get("model_reasoning_effort")},
        )

    print(f"editor input refreshed: {editor_input.relative_to(repo)}")
    if args.run_editor:
        print(f"report refreshed: {report.relative_to(repo)}")
    else:
        print("editor was not run; pass --run-editor to refresh the final report")
    return 0


def prepare_editor_input(paper_id, repo, paths, selected):
    """Shared deterministic assembly for refresh and a new derived synthesis."""
    parsed_dir, reviews_dir, prompts_dir = paths.parsed_dir, paths.reviews_dir, paths.prompts_dir
    selected_config_relative = str(paths.selected_reviewers_config_path.relative_to(repo))
    bundle, editor_prompt, editor_input = paths.bundle_path, paths.editor_prompt_path, paths.editor_input_path
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
            paper_id,
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
            paper_id,
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
            paper_id,
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



if __name__ == "__main__":
    raise SystemExit(main())
