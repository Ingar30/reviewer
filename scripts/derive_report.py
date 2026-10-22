"""Create a new synthesis from accepted evidence; never upgrade an old checkpoint."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil

from backend_settings import read_run_manifest
from claude_backend import EFFORTS, check_claude, require_same_backend
from pipeline_paths import paper_run_paths
from refresh_editor import prepare_editor_input
from resume_review import ReviewCheckpoint, atomic_write_json, digest, preflight_receipt, run_lease, runtime_snapshot
from review_paper import run_editor
from strict_json import read_json

# A deliberately narrow boundary, not permission to ignore unknown runtime changes.
# Shared source/quantity/coverage validators and reviewer/routing prompts are upstream.
DOWNSTREAM_RESOURCES = frozenset({
    'scripts/derive_report.py', 'scripts/refresh_editor.py',
    'scripts/build_editor_input.py', 'scripts/normalize_review_outputs.py',
    'scripts/editor_decisions.py', 'scripts/check_final_report.py', 'scripts/render_report_pdf.py',
    'scripts/build_cli_package.py', 'scripts/build_work_plugin.py',
    'scripts/finding_verification.py', 'scripts/verify_findings.py',
    'prompts/templates/editor_report.txt', 'schemas/editor_decisions.schema.json',
    'prompts/templates/finding_verifier.txt', 'schemas/finding_verification.schema.json',
})


def compatible_runtime(parent: Path, runtime: Path) -> list[str]:
    old, new = runtime_snapshot(parent), runtime_snapshot(runtime)
    changed = sorted(name for name in old.keys() | new.keys() if old.get(name) != new.get(name))
    upstream = [name for name in changed if name not in DOWNSTREAM_RESOURCES]
    if upstream:
        raise ValueError('Derived synthesis refused: upstream runtime changed: ' + ', '.join(upstream)
                         + '. Retain the accepted upstream runtime or rerun affected reviews; exact resume is unchanged.')
    return changed


def local_file(root: Path, name: str) -> Path:
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Missing or nonlocal derivation input: ' + name)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
        raise ValueError('Symlinked derivation inputs are not supported: ' + name)
    return path


def copy_file(root: Path, name: str, destination: Path) -> None:
    source = local_file(root, name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if digest(source) != digest(destination):
        raise ValueError('Derivation copy changed: ' + name)


def manuscript_file(root: Path, name: str, expected_hash: str) -> Path:
    """The recorded source PDF may be external; no other external inputs are allowed."""
    path = root / name
    if not path.is_file() or path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Missing or symlinked parent manuscript: ' + name)
    if digest(path) != expected_hash:
        raise ValueError('Parent manuscript hash differs from accepted settings.')
    return path


def input_snapshot(repo, paths):
    files = runtime_snapshot(repo)
    for directory in (repo / 'inputs', paths.parsed_dir, paths.reviews_dir,
                      paths.selection_dir, paths.prompts_dir, paths.work_root / 'parent_receipts'):
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                name = path.relative_to(repo).as_posix()
                files[name] = digest(local_file(repo, name))
    for path in (paths.bundle_path, paths.editor_input_path,
                 paths.editor_dir / 'coverage_ledger.json', paths.editor_dir / 'evidence_checks.json'):
        if path.is_file():
            files[path.relative_to(repo).as_posix()] = digest(path)
    return files


def derive(args, runtime: Path) -> Path:
    parent, child = args.parent_workspace.resolve(), args.output_workspace.resolve()
    paper_id = args.paper_id
    if not paper_id or paper_id in {'.', '..'} or any(c in paper_id for c in '/\\:'):
        raise ValueError('Use the parent run\'s single-component paper ID.')
    if child.is_relative_to(parent) or parent.is_relative_to(child) or runtime.resolve().is_relative_to(child):
        raise ValueError('The new workspace must not contain or be inside the parent, or contain the running runtime.')
    if child.exists():
        raise ValueError('Derived workspace already exists; preserve it and choose a fresh destination.')
    if args.max_repair_calls < 0:
        raise ValueError('--max-repair-calls must be nonnegative')
    source_paths = paper_run_paths(parent, paper_id)
    # Check before acquiring the lease: do not create directories/receipts for legacy runs.
    manifest = read_run_manifest(source_paths.run_manifest_path)
    receipt_path = source_paths.work_root / 'resume_checkpoint.json'
    preflight_path = source_paths.work_root / 'preflight_receipt.json'
    if not manifest or manifest.get('status') != 'complete' or not receipt_path.is_file() or not preflight_path.is_file():
        raise ValueError('Derived synthesis requires a completed parent with current acceptance receipts; legacy evidence is diagnostic only.')
    changes = compatible_runtime(parent, runtime)
    execution_runtime = runtime_snapshot(runtime)
    with run_lease(source_paths.work_root):
        saved = read_json(receipt_path)
        checkpoint = ReviewCheckpoint(parent, source_paths, saved.get('settings', {}))
        checkpoint.load()
        expected = {r.name for r in checkpoint.reviewers if r.stage == 'review'}
        if set(checkpoint.data['accepted']) != expected or not checkpoint.data.get('report_sha256') or not checkpoint.data.get('editor_files'):
            raise ValueError('Parent does not have complete reviewer and editor acceptance receipts.')
        for name, setting in [('paper_id', 'paper_id'), ('backend', 'backend'), ('model', 'model'),
                              ('reviewer_editor_reasoning_effort', 'reasoning_effort')]:
            if manifest.get(name) != checkpoint.settings.get(setting):
                raise ValueError('Parent manifest differs from accepted upstream settings: ' + name)
        if set(manifest.get('selected_reviewers', [])) != expected:
            raise ValueError('Parent manifest differs from the accepted reviewer roster.')
        preflight = read_json(preflight_path)
        if preflight.get('settings') != checkpoint.settings:
            raise ValueError('Parent preflight and reviewer settings differ.')
        preflight_receipt(parent, source_paths, checkpoint.settings,
                          [r for r in checkpoint.reviewers if r.stage == 'preflight'], reuse=True)
        source_hash = checkpoint.settings.get('source_pdf_sha256')
        if manifest.get('source_pdf_sha256') != source_hash:
            raise ValueError('Parent manuscript hash differs from accepted settings.')
        source = manuscript_file(parent, manifest['source_pdf'], source_hash)
        # A copied completed workspace can retain the original absolute PDF path
        # in its accepted preprocessing receipt. Verify that exact reference too;
        # do not rewrite the receipt or permit arbitrary external checkpoint files.
        parsed_source = manuscript_file(parent, read_json(source_paths.parsed_dir / 'manifest.json')['source_pdf'], source_hash)
        manuscript_paths = {source.resolve(), parsed_source.resolve()}

        def parent_input(name):
            if (parent / name).resolve() in manuscript_paths:
                return manuscript_file(parent, name, source_hash)
            return local_file(parent, name)

        require_same_backend(args.backend or manifest.get('backend', 'codex'), manifest)
        args.backend = args.backend or manifest.get('backend', 'codex')
        args.model = args.model or checkpoint.settings['model']
        args.reasoning_effort = args.reasoning_effort or checkpoint.settings['reasoning_effort']
        if args.backend == 'claude':
            if args.reasoning_effort not in EFFORTS:
                raise ValueError('Claude requires reasoning effort low through max.')
            check_claude(runtime)
        parent_files = dict(checkpoint.data['files'])
        parent_files[source.relative_to(parent).as_posix() if source.is_relative_to(parent) else str(source)] = source_hash
        for path in [receipt_path, preflight_path, source_paths.run_manifest_path, source_paths.report_path,
                     *source_paths.reviews_dir.glob('*.json'), *source_paths.editor_dir.glob('*.json')]:
            parent_files[path.relative_to(parent).as_posix()] = digest(path)
        # Reject nonlocal receipt entries before creating anything in the child.
        for name in parent_files:
            parent_input(name)
        child.mkdir(parents=True, exist_ok=False)
        for name in execution_runtime:
            copy_file(runtime, name, child / name)
        (child / '.gitignore').write_text('*\n', encoding='utf-8')
        paths = paper_run_paths(child, paper_id)
        for directory in (source_paths.parsed_dir, source_paths.selection_dir, source_paths.prompts_dir):
            for path in directory.rglob('*'):
                if path.is_file():
                    name = path.relative_to(parent).as_posix()
                    copy_file(parent, name, child / name)
        for reviewer in checkpoint.reviewers:
            name = (source_paths.reviews_dir / reviewer.output).relative_to(parent).as_posix()
            copy_file(parent, name, child / name)
        source_name = 'inputs/source.pdf'
        (child / 'inputs').mkdir(exist_ok=True)
        shutil.copy2(source, child / source_name)
        manuscript_file(child, source_name, source_hash)
        for path in (receipt_path, preflight_path, source_paths.run_manifest_path, source_paths.report_path,
                     *source_paths.editor_dir.glob('*.json')):
            name = path.relative_to(parent).as_posix()
            copy_file(parent, name, paths.work_root / 'parent_receipts' / path.name)
        if any(digest(parent_input(name)) != value for name, value in parent_files.items()):
            raise ValueError('Parent changed while copying; child is incomplete.')
        if runtime_snapshot(runtime) != execution_runtime or runtime_snapshot(child) != execution_runtime:
            raise ValueError('Execution runtime changed while copying; child is incomplete.')
    for directory in (paths.editor_dir, paths.outputs_dir, paths.log_dir):
        directory.mkdir(parents=True, exist_ok=True)
    lineage = {'format': 1, 'kind': 'derived_synthesis', 'paper_id': paper_id,
               'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'preparing',
               'parent_workspace': str(parent), 'parent_report_sha256': checkpoint.data['report_sha256'],
               'parent_files': parent_files, 'upstream_settings': checkpoint.settings,
               'upstream_accepted': checkpoint.data['accepted'], 'changed_downstream_resources': changes,
               'runtime': runtime_snapshot(child), 'editor_settings': {
                   'backend': args.backend, 'model': args.model, 'reasoning_effort': args.reasoning_effort}}
    lineage_path = paths.work_root / 'derivation.json'
    atomic_write_json(lineage_path, lineage)
    child_manifest = {'paper_id': paper_id, 'run_kind': 'derived_synthesis', 'status': 'editor_pending',
                      'source_pdf': source_name, 'source_pdf_sha256': digest(child / source_name),
                      'backend': args.backend, 'model': args.model,
                      'reviewer_editor_reasoning_effort': args.reasoning_effort,
                      'selected_reviewers': sorted(expected), 'parent_workspace': str(parent),
                      'parent_report_sha256': checkpoint.data['report_sha256']}
    atomic_write_json(paths.run_manifest_path, child_manifest)
    try:
        with run_lease(paths.work_root):
            prepare_editor_input(paper_id, child, paths, checkpoint.reviewers)
            lineage['inputs'] = input_snapshot(child, paths)
            lineage['status'] = 'editor_pending'
            atomic_write_json(lineage_path, lineage)
            args.agent_timeout_minutes = 45
            run_editor(args, child, paths, paths.log_dir)
            if input_snapshot(child, paths) != lineage['inputs']:
                raise ValueError('Derived synthesis inputs changed; result is not accepted.')
            # Copied provenance can still refer to the original absolute PDF.
            # Setup verification alone cannot bind that evidence during execution.
            if any(digest(parent_input(name)) != value for name, value in parent_files.items()):
                raise ValueError('Parent inputs changed during derived synthesis; result is not accepted.')
            lineage.update(status='complete', completed_utc=datetime.now(timezone.utc).isoformat(),
                           report_sha256=digest(paths.report_path),
                           editor_files={p.name:digest(p) for p in paths.editor_dir.glob('*.json')})
            atomic_write_json(lineage_path, lineage)
            child_manifest.update(status='complete', completed_at_utc=lineage['completed_utc'],
                                  report=str(paths.report_path.relative_to(child)))
            atomic_write_json(paths.run_manifest_path, child_manifest)
    except BaseException as exc:
        lineage.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed', failure_type=type(exc).__name__)
        child_manifest.update(status=lineage['status'], failure_type=type(exc).__name__)
        atomic_write_json(lineage_path, lineage)
        atomic_write_json(paths.run_manifest_path, child_manifest)
        raise
    return paths.report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-workspace', type=Path, required=True)
    parser.add_argument('--output-workspace', type=Path, required=True)
    parser.add_argument('--paper-id', required=True)
    parser.add_argument('--backend', choices=['codex', 'claude'])
    parser.add_argument('--model')
    parser.add_argument('--reasoning-effort', choices=['none', 'low', 'medium', 'high', 'xhigh', 'max'])
    parser.add_argument('--max-repair-calls', type=int, default=1)
    args = parser.parse_args(argv)
    print('Derived report: ' + str(derive(args, Path(__file__).resolve().parents[1])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
