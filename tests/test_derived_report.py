"""Child synthesis tests use a real pipeline with offline CLI doubles only."""
import json
from contextlib import chdir
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tests.test_uv_launcher import REPO, cli, cli_payload, fake_codex_environment, synthetic_pdf
from derive_report import compatible_runtime, derive
from resume_review import digest, runtime_snapshot


def hashes(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in root.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts}


class DerivedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='derived-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        cls.parent = cls.folder / 'parent'
        for name, content in cli_payload(REPO).items():
            p = cls.parent / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        (cls.parent / 'inputs').mkdir()
        synthetic_pdf(cls.parent / 'inputs/source.pdf')
        cls.env = fake_codex_environment(cls.folder)
        cls.env['ECONOMICS_REVIEWER_NON_GIT'] = '1'
        cls.env['PYTHONDONTWRITEBYTECODE'] = '1'
        result = subprocess.run([sys.executable, 'scripts/review_paper.py', '--pdf', 'inputs/source.pdf',
                                 '--paper-id', 'synthetic', '--max-repair-calls', '0'], cwd=cls.parent,
                                env=cls.env, capture_output=True, text=True, encoding='utf-8', timeout=180)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def setUp(self):
        self.case = self.folder / self._testMethodName
        self.case.mkdir()
        self.runtime = self.case / 'runtime'
        for name in runtime_snapshot(self.parent):
            p = self.runtime / name
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.parent / name, p)
        for name in ['LICENSE.md', 'requirements.txt', '.reviewer-workspace.json']:
            shutil.copy2(self.parent / name, self.runtime / name)
        self.args = SimpleNamespace(parent_workspace=self.parent, output_workspace=self.case / 'child',
            paper_id='synthetic', backend=None, model=None, reasoning_effort=None, max_repair_calls=0)

    def invoke(self):
        with mock.patch.dict(os.environ, self.env):
            return derive(self.args, self.runtime)

    def test_downstream_change_runs_only_editor_and_preserves_parent(self):
        before = hashes(self.parent)
        calls = len(list(Path(self.env['REVIEWER_TEST_CALLS']).glob('*.json')))
        p = self.runtime / 'prompts/templates/editor_report.txt'
        p.write_bytes(p.read_bytes() + b'\nPrefer compact narrative treatments.\n')
        report = self.invoke()
        self.assertIn('MOCK report', report.read_text(encoding='utf-8'))
        self.assertEqual(hashes(self.parent), before)
        self.assertEqual(len(list(Path(self.env['REVIEWER_TEST_CALLS']).glob('*.json'))), calls + 1)
        work = report.parents[2] / 'work/synthetic'
        lineage = json.loads((work / 'derivation.json').read_text())
        self.assertEqual(lineage['status'], 'complete')
        self.assertEqual(lineage['changed_downstream_resources'], ['prompts/templates/editor_report.txt'])
        self.assertEqual(lineage['report_sha256'], digest(report))
        self.assertFalse((work / 'resume_checkpoint.json').exists())
        receipt = work / 'parent_receipts/resume_checkpoint.json'
        self.assertEqual(receipt.read_bytes(), (self.parent / 'work/synthetic/resume_checkpoint.json').read_bytes())
        for p in (self.parent / 'work/synthetic/reviews').glob('*.json'):
            self.assertEqual(p.read_bytes(), (work / 'reviews' / p.name).read_bytes())

    def test_upstream_changes_and_unknown_resources_block_before_calls(self):
        before = hashes(self.parent)
        for name in ['prompts/templates/source_consistency_audit.txt', 'scripts/evidence_registry.py',
                     'config/reviewers.json', '.codex/config.toml', 'scripts/new_unknown.py']:
            with self.subTest(name=name):
                p = self.runtime / name
                old = p.read_bytes() if p.exists() else None
                p.write_bytes((old or b'') + b'\n# changed\n')
                try:
                    with mock.patch('derive_report.run_editor') as run:
                        with self.assertRaisesRegex(ValueError, 'upstream runtime changed'):
                            self.invoke()
                        run.assert_not_called()
                    self.assertFalse(self.args.output_workspace.exists())
                finally:
                    if old is None: p.unlink()
                    else: p.write_bytes(old)
        self.assertEqual(hashes(self.parent), before)

    def test_recorded_external_manuscript_reference_is_verified_not_rewritten(self):
        parent = self.case / 'external-parent'
        for name, content in cli_payload(REPO).items():
            p = parent / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        external = self.case / 'original.pdf'
        synthetic_pdf(external)
        result = subprocess.run([sys.executable, 'scripts/review_paper.py', '--pdf', str(external),
                                 '--paper-id', 'synthetic', '--max-repair-calls', '0'], cwd=parent,
                                env=self.env, capture_output=True, text=True, encoding='utf-8', timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # A retained workspace can have a local byte-identical source copy while
        # accepted preprocessing/checkpoint records still refer to the original.
        (parent / 'inputs').mkdir(exist_ok=True)
        shutil.copy2(external, parent / 'inputs/source.pdf')
        manifest_path = parent / 'work/synthetic/run_manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['source_pdf'] = 'inputs/source.pdf'
        manifest_path.write_text(json.dumps(manifest))
        self.args.parent_workspace = parent
        before = hashes(parent)
        original = external.read_bytes()
        calls = len(list(Path(self.env['REVIEWER_TEST_CALLS']).glob('*.json')))
        report = self.invoke()
        self.assertEqual(hashes(parent), before)
        self.assertEqual(external.read_bytes(), original)
        self.assertEqual(len(list(Path(self.env['REVIEWER_TEST_CALLS']).glob('*.json'))), calls + 1)
        work = report.parents[2] / 'work/synthetic'
        self.assertEqual((work / 'parent_receipts/resume_checkpoint.json').read_bytes(),
                         (parent / 'work/synthetic/resume_checkpoint.json').read_bytes())
        self.assertEqual((report.parents[2] / 'inputs/source.pdf').read_bytes(), original)
        lineage = json.loads((work / 'derivation.json').read_text())
        self.assertEqual(lineage['parent_files'][str(external)], digest(external))
        self.args.output_workspace = self.case / 'rejected-child'
        for path in (external, parent / 'inputs/source.pdf'):
            with self.subTest(path=path):
                path.write_bytes(original + b'changed')
                try:
                    with mock.patch('derive_report.run_editor') as run:
                        with self.assertRaises(ValueError): self.invoke()
                        run.assert_not_called()
                    self.assertFalse(self.args.output_workspace.exists())
                finally: path.write_bytes(original)
        self.assertEqual(hashes(parent), before)

        # An absolute source reference survives in copied provenance. It must
        # remain the accepted evidence throughout execution, not just at setup.
        from review_paper import run_editor
        def change_external_source(*args):
            run_editor(*args)  # Offline CLI double, with real assembly/checks.
            external.write_bytes(original + b'changed during editor')
        self.args.output_workspace = self.case / 'changed-source-child'
        try:
            with mock.patch('derive_report.run_editor', side_effect=change_external_source):
                with self.assertRaisesRegex(ValueError, 'Parent manuscript hash differs'):
                    self.invoke()
            lineage = json.loads((self.args.output_workspace / 'work/synthetic/derivation.json').read_text())
            self.assertEqual(lineage['status'], 'failed')
            self.assertNotIn('report_sha256', lineage)
        finally:
            external.write_bytes(original)
        self.assertEqual(hashes(parent), before)

    def test_tampered_evidence_outputs_and_reports_are_not_reused(self):
        for relative in ['inputs/source.pdf', 'work/synthetic/parsed/full_text.md',
                         'work/synthetic/reviews/numerical_auditor.json',
                         'outputs/synthetic/report.md', 'work/synthetic/selection/selected_reviewers.json']:
            with self.subTest(relative=relative):
                p = self.parent / relative
                old = p.read_bytes()
                p.write_bytes(old + b'\n ')
                try:
                    with mock.patch('derive_report.run_editor') as run:
                        with self.assertRaises(ValueError): self.invoke()
                        run.assert_not_called()
                    self.assertFalse(self.args.output_workspace.exists())
                finally:
                    p.write_bytes(old)

    def test_missing_and_legacy_receipts_are_not_manufactured(self):
        for name in ['resume_checkpoint.json', 'preflight_receipt.json']:
            p = self.parent / 'work/synthetic' / name
            old = p.read_bytes()
            try:
                p.rename(p.with_suffix('.saved'))
                with self.assertRaisesRegex(ValueError, 'current acceptance receipts'):
                    self.invoke()
                self.assertFalse(p.exists())
            finally:
                p.with_suffix('.saved').rename(p)
            if name == 'resume_checkpoint.json':
                d = json.loads(old); d['format'] = 1
                p.write_text(json.dumps(d))
                try:
                    with self.assertRaisesRegex(ValueError, 'legacy acceptance policy'): self.invoke()
                    self.assertEqual(json.loads(p.read_text())['format'], 1)
                finally: p.write_bytes(old)

    def test_failed_editor_preserves_parent_and_marks_child_incomplete(self):
        before = hashes(self.parent)
        with mock.patch('derive_report.run_editor', side_effect=RuntimeError('synthetic transport failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic transport failure'): self.invoke()
        self.assertEqual(hashes(self.parent), before)
        work = self.args.output_workspace / 'work/synthetic'
        self.assertEqual(json.loads((work / 'derivation.json').read_text())['status'], 'failed')
        self.assertEqual(json.loads((work / 'run_manifest.json').read_text())['status'], 'failed')
        self.assertFalse((work / 'resume_checkpoint.json').exists())

    def test_output_and_provider_guards_do_not_change_parent(self):
        before = hashes(self.parent)
        self.args.backend = 'claude'
        with self.assertRaisesRegex(ValueError, 'Saved run uses'): self.invoke()
        self.args.backend = None
        self.args.output_workspace = self.parent / 'child'
        with self.assertRaisesRegex(ValueError, 'inside the parent'): self.invoke()
        self.args.output_workspace = self.case / 'existing'
        self.args.output_workspace.mkdir()
        with self.assertRaisesRegex(ValueError, 'already exists'): self.invoke()
        self.assertEqual(hashes(self.parent), before)

    def test_manifest_settings_cannot_override_accepted_upstream(self):
        p = self.parent / 'work/synthetic/run_manifest.json'
        old = p.read_bytes()
        d = json.loads(old); d['model'] = 'unrecorded-model'
        p.write_text(json.dumps(d))
        try:
            with mock.patch('derive_report.run_editor') as run:
                with self.assertRaisesRegex(ValueError, 'accepted upstream settings'): self.invoke()
                run.assert_not_called()
            self.assertFalse(self.args.output_workspace.exists())
        finally: p.write_bytes(old)

    def test_child_evidence_change_cannot_be_marked_complete(self):
        before = hashes(self.parent)
        def mutate(args, repo, paths, log):
            p = paths.parsed_dir / 'full_text.md'
            p.write_bytes(p.read_bytes() + b'changed during editor')
        with mock.patch('derive_report.run_editor', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'inputs changed'): self.invoke()
        self.assertEqual(hashes(self.parent), before)
        d = json.loads((self.args.output_workspace / 'work/synthetic/derivation.json').read_text())
        self.assertEqual(d['status'], 'failed')
        self.assertNotIn('report_sha256', d)

    def test_launcher_creates_child_without_upgrading_parent_workspace(self):
        before = hashes(self.parent)
        calls = len(list(Path(self.env['REVIEWER_TEST_CALLS']).glob('*.json')))
        with mock.patch.object(cli, 'bundled_runtime', return_value=self.runtime), \
                mock.patch.dict(os.environ, self.env), chdir(self.case):
            self.assertEqual(cli.main(['--derive-from', str(self.parent), '--paper-id', 'synthetic',
                                       '--workspace', 'child', '--max-repair-calls', '0']), 0)
        self.assertEqual(hashes(self.parent), before)
        self.assertEqual(len(list(Path(self.env['REVIEWER_TEST_CALLS']).glob('*.json'))), calls + 1)
        self.assertTrue((self.case / 'child/outputs/synthetic/report.md').is_file())


if __name__ == '__main__':
    unittest.main()
