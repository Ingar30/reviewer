"""Synthetic reliability regressions. No model calls or manuscript fixtures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from review_paper import codex_exec_command, enforce_preflight_gate
from reviewer_config import load_reviewers_config
from validate_review_json import semantic_errors
from validate_review_json import validate_review_output
from review_acceptance import acceptance_errors
from resume_review import ReviewCheckpoint, POLICY_VERSION
from review_paper import RunResult
from tests.test_reviewer_config import finding, review_output, reviewer_config


class ReproducedGateTests(unittest.TestCase):
    def test_empty_failed_preflight_cannot_authorize_review(self):
        preflight = load_reviewers_config(REPO / "config/reviewers.json")[0]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "preflight.json"
            path.write_text(json.dumps(review_output([], preflight.name, "failed")))
            with self.assertRaisesRegex((ValueError, RuntimeError), "complet|failed"):
                enforce_preflight_gate(preflight, path)

    def test_null_only_numeric_check_is_not_a_recomputation(self):
        empty = dict(reported_value=None, expected_value=None, method=None,
                     inputs=[], recomputation_notes=None)
        errors = semantic_errors(review_output([finding(numeric_check=empty)]), [reviewer_config()])
        self.assertTrue(any("numeric_check" in e for e in errors), errors)

    def test_non_search_role_explicitly_disables_inherited_search(self):
        with mock.patch("review_paper.codex_command", return_value="codex"):
            command = codex_exec_command(search=False)
        self.assertIn('web_search="disabled"', command)


def completed(status="ok", state="complete"):
    data = review_output([], reviewer_name="crossref_auditor", run_status=status)
    data["completion"] = {"version": 1, "state": state,
        "scope_description": "Cross-reference targets and uses in the synthetic paper",
        "checks_completed": ["Compared every reference target with its use"],
        "missing_checks": [], "evidence_limitations": []}
    data["coverage"] = [{"item_id": "assigned_remit", "source_object_ids": [], "claim": None,
        "check_performed": "Compared every synthetic target", "status": "checked_no_issue", "reason": "All synthetic targets checked",
        "finding_ids": [], "attempted": True, "importance": "central", "scope": "exhaustive"}]
    return data


class CompletionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.schema = json.loads((REPO / "schemas/reviewer_output.schema.json").read_text())
        self.reviewers = load_reviewers_config(REPO / "config/reviewers.json")

    def test_completed_unavailable_evidence_and_inapplicable_remit(self):
        data = completed("cannot_verify")
        data["completion"]["evidence_limitations"] = ["Attempted appendix target check; scan is illegible"]
        self.assertEqual(acceptance_errors(data), [])
        self.assertEqual(acceptance_errors(completed(state="not_applicable")), [])

    def test_unattempted_required_check_cannot_be_labeled_evidence_limitation(self):
        data = completed("cannot_verify")
        data["completion"]["missing_checks"] = ["Appendix targets not checked"]
        data["completion"]["evidence_limitations"] = ["Time ran out"]
        self.assertTrue(acceptance_errors(data))

    def test_failed_partial_and_legacy_never_complete(self):
        for status in ("failed", "partial"):
            self.assertTrue(acceptance_errors(completed(status)))
        data = completed()
        del data["completion"]
        self.assertTrue(acceptance_errors(data))
        self.assertEqual(validate_review_output(data, self.schema, self.reviewers, repo=self.root), [])
        self.assertTrue(validate_review_output(data, self.schema, self.reviewers, repo=self.root, require_complete=True))

    def checkpoint(self, data):
        from pipeline_paths import paper_run_paths
        c = ReviewCheckpoint.__new__(ReviewCheckpoint)
        c.repo = self.root
        c.paths = paper_run_paths(self.root, "paper-x")
        c.paths.reviews_dir.mkdir(parents=True, exist_ok=True)
        c.path = c.paths.work_root / "resume_checkpoint.json"
        c.schema = self.schema
        c.reviewers = self.reviewers
        c.settings = {"paper_id": "paper-x"}
        c.data = {"accepted": {}, "files": {}}
        c.files = lambda: {}
        reviewer = next(r for r in self.reviewers if r.name == "crossref_auditor")
        path = c.paths.reviews_dir / reviewer.output
        path.write_text(json.dumps(data))
        return c, reviewer, path

    def test_exit_zero_failed_and_partial_outputs_not_receipted(self):
        for status in ("failed", "partial"):
            with self.subTest(status=status):
                c, reviewer, path = self.checkpoint(completed(status))
                before = path.read_bytes()
                c.accept(reviewer, RunResult("test", 0, path, path), 0)
                self.assertEqual(c.data["accepted"], {})
                self.assertEqual(path.read_bytes(), before)

    def test_malformed_stale_and_interrupted_output_not_receipted(self):
        import time
        for kind in ("malformed", "stale", "interrupted"):
            c, reviewer, path = self.checkpoint(completed())
            if kind == "malformed":
                path.write_text('{"unfinished":')
            result = RunResult("test", 124 if kind == "interrupted" else 0, path, path)
            c.accept(reviewer, result, time.time() + 10 if kind == "stale" else 0)
            self.assertEqual(c.data["accepted"], {})

    def test_completed_output_is_receipted_but_tampering_fails_reuse(self):
        c, reviewer, path = self.checkpoint(completed())
        c.data.update(format=2, acceptance_policy=POLICY_VERSION, settings=c.settings, files={})
        c.reviewers = [reviewer]
        c.accept(reviewer, RunResult("test", 0, path, path), 0)
        self.assertIn(reviewer.name, c.data["accepted"])
        path.write_text(path.read_text() + "\n")
        with mock.patch.object(c, "files", return_value={}):
            with self.assertRaisesRegex(ValueError, "accepted review changed"):
                c.load()

    def test_input_changes_during_audit_prevent_acceptance(self):
        c, reviewer, path = self.checkpoint(completed())
        c.files = lambda: {"synthetic-evidence": "changed"}
        c.accept(reviewer, RunResult("test", 0, path, path), 0)
        self.assertEqual(c.data["accepted"], {})

    def test_editor_artifact_tampering_prevents_completed_reuse(self):
        c, reviewer, path = self.checkpoint(completed())
        c.reviewers = []
        c.data.update(format=2, acceptance_policy=POLICY_VERSION, settings=c.settings)
        c.paths.editor_dir.mkdir(parents=True)
        for name in ("editor_decisions.json", "editor_receipt.json", "normalized_bundle.json",
                     "coverage_ledger.json", "evidence_checks.json"):
            (c.paths.editor_dir / name).write_text("{}")
        c.paths.outputs_dir.mkdir(parents=True)
        c.paths.report_path.write_text("synthetic report")
        c.complete()
        (c.paths.editor_dir / "editor_decisions.json").write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, "editorial decisions"):
            c.load()

    def test_legacy_checkpoint_cannot_bypass_new_policy(self):
        c, reviewer, path = self.checkpoint(completed())
        c.data.update(format=1, settings=c.settings)
        c.save()
        with self.assertRaisesRegex(ValueError, "legacy acceptance policy"):
            c.load()

    def test_same_second_prior_output_is_archived_before_launch(self):
        from review_paper import archive_previous_output, require_fresh_file
        path = self.root / "candidate.json"
        path.write_text('{"prior":true}')
        archive_previous_output(path, self.root / "logs")
        self.assertFalse(path.exists())
        self.assertEqual(next((self.root / "logs").iterdir()).read_text(), '{"prior":true}')
        with self.assertRaises(FileNotFoundError):
            require_fresh_file(path, 0, "zero-exit candidate without a new output")

    def test_editor_refresh_archives_under_long_windows_workspace(self):
        from refresh_editor import archive_editor_products
        # Source files remain well below MAX_PATH, but the previous nested UUID
        # archive added enough length to fail on Windows without long-path support.
        work = self.root / ("workspace " + "x" * max(1, 180 - len(str(self.root)) - 11))
        editor = work / "editor"
        editor.mkdir(parents=True)
        original = editor / "normalized_bundle.json"
        original.write_bytes(b'{"synthetic":"preserve these bytes"}')
        for _ in range(2):
            archived = archive_editor_products(work / "report.md", editor, editor / "input.md", work / "logs")
            self.assertEqual((archived / (original.name + ".previous")).read_bytes(), original.read_bytes())
        self.assertEqual(len(list((work / "logs").glob("**/*.previous"))), 2)

    def test_selective_resume_leaves_room_for_long_reviewer_log_names(self):
        from types import SimpleNamespace
        work = self.root / ("workspace " + "x" * max(1, 180 - len(str(self.root)) - 11))
        c = ReviewCheckpoint.__new__(ReviewCheckpoint)
        c.paths = SimpleNamespace(log_dir=work / "logs", reviews_dir=work / "reviews",
                                  report_path=work / "report.md")
        c.reviewers = []
        c.data = {"accepted": {}}
        folders = [c.attempt_dir(), c.attempt_dir()]
        self.assertNotEqual(*folders)
        for folder in folders:
            log = folder / "abstract_conclusion_consistency_auditor.stdout.log"
            log.write_text("synthetic resume output")
            self.assertEqual(log.read_text(), "synthetic resume output")


if __name__ == "__main__":
    unittest.main()
