"""Fail-closed CLI checkpoints; no model calls or native-host orchestration."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from uuid import uuid4

from reviewer_config import load_reviewers_config
from validate_review_json import validate_review_output
from review_acceptance import POLICY_VERSION
from strict_json import read_json


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def runtime_snapshot(repo: Path) -> dict[str, str]:
    files = {repo / "AGENTS.md", repo / ".codex/config.toml"}
    for directory, suffixes in (("scripts", {".py"}), ("config", {".json"}),
            ("schemas", {".json"}), ("prompts/templates", {".txt"}),
            (".agents/skills/paper-reviewer", {".md", ".txt", ".json"})):
        files.update(p for p in (repo / directory).rglob("*") if p.suffix in suffixes)
    return {p.relative_to(repo).as_posix(): digest(p) for p in sorted(files) if p.is_file()}


def preflight_receipt(repo, paths, settings, reviewers, *, reuse=False):
    """Freeze evidence before routing; never promote an old finding-only gate."""
    path = paths.work_root / "preflight_receipt.json"
    files = dict(runtime_snapshot(repo))
    for p in sorted(paths.parsed_dir.rglob("*")):
        if p.is_file():
            files[p.relative_to(repo).as_posix()] = digest(p)
    schema = json.loads((repo / "schemas/reviewer_output.schema.json").read_text(encoding="utf-8"))
    for reviewer in reviewers:
        p = paths.reviews_dir / reviewer.output
        data = read_json(p)
        errors = validate_review_output(data, schema, reviewers, repo=repo,
            expected_reviewer=reviewer.name, paper_id=settings["paper_id"], require_complete=True)
        if errors:
            raise ValueError("Preflight is incomplete/invalid: " + "; ".join(errors))
        files[p.relative_to(repo).as_posix()] = digest(p)
    current = {"format": 1, "acceptance_policy": POLICY_VERSION, "settings": settings, "files": files}
    if reuse:
        if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != current:
            raise ValueError("Cannot resume preflight: missing legacy receipt or changed runtime, evidence, output or settings. Retain originals.")
    else:
        atomic_write_json(path, current)


def atomic_write_json(path: Path, data) -> None:
    """Reuse the checkpoint writer's bounded Windows replacement semantics."""
    writer = ReviewCheckpoint.__new__(ReviewCheckpoint)
    writer.path, writer.data = path, data
    path.parent.mkdir(parents=True, exist_ok=True)
    writer.save()


@contextmanager
def run_lease(work_dir: Path):
    """An OS lock, released even after a crash; never infer liveness from a PID."""
    work_dir.mkdir(parents=True, exist_ok=True)
    with (work_dir / ".pipeline.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another pipeline is using this paper ID; wait for it to stop.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class ReviewCheckpoint:
    """Reuse only successful, validated outputs from identical inputs/settings."""

    def __init__(self, repo: Path, paths, settings: dict):
        self.repo, self.paths, self.settings = repo, paths, settings
        self.path = paths.run_manifest_path.with_name("resume_checkpoint.json")
        self.data = {}
        self.reviewers = load_reviewers_config(paths.selected_reviewers_config_path)
        self.schema = json.loads((repo / "schemas/reviewer_output.schema.json").read_text(encoding="utf-8"))

    def files(self) -> dict[str, str]:
        files = set()
        # Freeze both the installed runtime and ordinary-checkout runtime. New files
        # are detected too. Mutable logs/editor products are intentionally excluded.
        for root, suffixes in (
            (self.repo / "scripts", {".py"}), (self.repo / "config", {".json"}),
            (self.repo / "schemas", {".json"}), (self.repo / "prompts/templates", {".txt"}),
            (self.repo / ".agents/skills/paper-reviewer", {".md", ".txt", ".json"}),
            (self.paths.parsed_dir, None), (self.paths.selection_dir, None),
            (self.paths.prompts_dir, {".txt"}),
        ):
            files.update(p for p in root.rglob("*") if p.is_file()
                         and (suffixes is None or p.suffix in suffixes))
        files.update(self.repo / name for name in ("AGENTS.md", ".codex/config.toml"))
        files.update(self.paths.reviews_dir / r.output for r in self.reviewers if r.stage == "preflight")
        config = Path(self.settings["reviewers_config"])
        files.add(config if config.is_absolute() else self.repo / config)
        manifest = self.paths.parsed_dir / "manifest.json"
        if manifest.is_file():
            source = read_json(manifest).get("source_pdf")
            if source:
                source = Path(source)
                files.add(source if source.is_absolute() else self.repo / source)
        # External reviewer configs are supported, keyed by their absolute path.
        return {(p.relative_to(self.repo).as_posix() if p.is_relative_to(self.repo) else str(p)): digest(p)
                for p in sorted(files) if p.is_file()}

    def save(self):
        pending = self.path.with_suffix(".pending")
        pending.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        # Windows readers (including sync/indexing software) can briefly deny
        # replacement. Keep the previous checkpoint intact: never truncate it,
        # remove it first, or treat an uncommitted pending file as accepted work.
        for attempt in range(6):
            try:
                pending.replace(self.path)
                return
            except PermissionError as exc:
                if getattr(exc, "winerror", None) not in (5, 32, 33):
                    raise
                if attempt == 5:
                    raise RuntimeError(
                        f"Windows kept checkpoint {self.path} locked after bounded retries. "
                        f"The previous checkpoint is unchanged; the pending update is at {pending}. "
                        "Close applications holding the file and retry with --resume-incomplete "
                        "if a checkpoint exists, otherwise repeat the original command."
                    ) from exc
                if attempt == 0:
                    print("[checkpoint] Windows file lock; retrying the atomic save.")
                time.sleep(0.1 * 2 ** attempt)

    def create(self):
        self.data = {"format": 2, "acceptance_policy": POLICY_VERSION,
                     "settings": self.settings, "files": self.files(), "accepted": {}}
        self.save()

    def validate(self, reviewer):
        path = self.paths.reviews_dir / reviewer.output
        data = read_json(path)
        errors = validate_review_output(data, self.schema, self.reviewers, repo=self.repo,
                                       expected_reviewer=reviewer.name, paper_id=self.settings["paper_id"],
                                       require_complete=True)
        if errors:
            raise ValueError(f"Invalid saved review {reviewer.name}: " + "; ".join(errors))

    def accept(self, reviewer, result, started_at):
        path = self.paths.reviews_dir / reviewer.output
        if result.returncode != 0 or not path.is_file() or path.stat().st_mtime < started_at:
            return
        try:
            self.verify_inputs()
            self.validate(reviewer)
        except (OSError, ValueError) as exc:
            print(f"[checkpoint] not accepted: {exc}")
            return
        self.data["accepted"][reviewer.name] = digest(path)
        self.save()

    def verify_inputs(self):
        if self.data.get("files") != self.files():
            raise ValueError("Runtime or manuscript evidence changed during the review; results are not accepted.")

    def load(self):
        if not self.path.is_file():
            raise ValueError("No selective-resume checkpoint. Use the original runtime and "
                             "--resume-after-preflight or --refresh-editor for older runs.")
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        if self.data.get("format") != 2 or self.data.get("acceptance_policy") != POLICY_VERSION:
            raise ValueError("Cannot resume: legacy acceptance policy. Keep the original runtime/artifacts; no completion is inferred.")
        if self.data.get("settings") != self.settings:
            raise ValueError("Cannot resume: PDF, backend, model, effort or reviewer configuration differs.")
        if self.data.get("files") != self.files():
            raise ValueError("Cannot resume: runtime, parsed artifacts, selection, prompts or preflight changed.")
        known = {r.name for r in self.reviewers if r.stage == "review"}
        if set(self.data["accepted"]) - known:
            raise ValueError("Cannot resume: checkpoint contains an unknown reviewer.")
        for reviewer in self.reviewers:
            if reviewer.stage == "preflight" or reviewer.name in self.data["accepted"]:
                self.validate(reviewer)
            if reviewer.name in self.data["accepted"]:
                if digest(self.paths.reviews_dir / reviewer.output) != self.data["accepted"][reviewer.name]:
                    raise ValueError(f"Cannot resume: accepted review changed: {reviewer.name}")
        if self.data.get("report_sha256"):
            if digest(self.paths.report_path) != self.data["report_sha256"]:
                raise ValueError("Cannot resume: completed report changed.")
            if self.data.get("editor_files") != self.editor_files():
                raise ValueError("Cannot resume: editorial decisions, evidence ledger or receipt changed.")

    def attempt_dir(self) -> Path:
        # Keep enough path budget for long reviewer names on Windows. mkdtemp
        # supplies collision-safe isolation without a nested 32-character UUID.
        self.paths.log_dir.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="resume-", dir=self.paths.log_dir))
        # Preserve unsuccessful or unreceipted candidates before rerunning them.
        candidates = [self.paths.reviews_dir / r.output for r in self.reviewers
                      if r.stage == "review" and r.name not in self.data["accepted"]]
        if not self.data.get("report_sha256"):
            candidates.append(self.paths.report_path)
        for path in candidates:
            if path.exists():
                path.replace(folder / (path.name + ".previous"))
        return folder

    def complete(self):
        self.verify_inputs()
        if {r.name for r in self.reviewers if r.stage == "review"} != set(self.data["accepted"]):
            raise ValueError("Cannot complete a report with unfinished reviewers.")
        for reviewer in self.reviewers:
            self.validate(reviewer)
            if reviewer.stage == "review" and digest(self.paths.reviews_dir / reviewer.output) != self.data["accepted"][reviewer.name]:
                raise ValueError("Accepted reviewer output changed before completion: " + reviewer.name)
        self.data["editor_files"] = self.editor_files()
        self.data["report_sha256"] = digest(self.paths.report_path)
        self.save()

    def editor_files(self):
        names = ("editor_decisions.json", "editor_receipt.json", "normalized_bundle.json",
                 "coverage_ledger.json", "evidence_checks.json")
        return {name: digest(self.paths.editor_dir / name) for name in names}
