"""Concise no-findings reports must pass without padding or model retries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from check_final_report import report_failures, MIN_REPORT_CHARS
from review_paper import plausible_editor_report, recover_editor_report_if_needed


def empty_bundle():
    return {"canonical_findings": [], "source_reviewer_outputs": [
        {"reviewer": "fixture_auditor", "run_status": "ok", "finding_count": 0}
    ]}


def concise_report():
    return """# Multi-Agent Paper Review Report

## Executive Summary
This synthetic test document contains no substantive claims to evaluate.

## Highest-Priority Cross-Agent Findings
No corrections were identified.

## Suggested Revision Priorities
No revisions are required for this test fixture.

## Additional Findings
No additional findings were identified.

## Appendix: Review Scope and Limitations
The audit covered the available text. There were no methods, references or
quantitative results to evaluate; this is not evidence of scholarly quality.

## Appendix: Traceability Map
No findings to map.
"""


class EmptyReportTests(unittest.TestCase):
    def test_successful_empty_report_passes_recovery_and_final_check(self):
        report = concise_report()
        self.assertLess(len(report), MIN_REPORT_CHARS)
        self.assertTrue(plausible_editor_report(report, bundle=empty_bundle()))
        self.assertEqual(report_failures(report, bundle=empty_bundle()), [])
        with tempfile.TemporaryDirectory() as folder:
            report_path, log = Path(folder) / "report.md", Path(folder) / "editor.stderr.log"
            report_path.write_text(report, encoding="utf-8")
            log.write_text("", encoding="utf-8")
            before = (report_path.read_bytes(), report_path.stat().st_mtime_ns)
            recover_editor_report_if_needed(report_path, log, bundle=empty_bundle())
            self.assertEqual((report_path.read_bytes(), report_path.stat().st_mtime_ns), before)

    def test_missing_failed_incomplete_or_nonempty_evidence_keeps_length_floor(self):
        bundles = [None, {}, {"canonical_findings": []},
                   {"canonical_findings": [], "source_reviewer_outputs": []}]
        for field, value in (("run_status", "failed"), ("run_status", "cannot_verify"),
                             ("run_status", None), ("finding_count", 1), ("finding_count", None)):
            bundle = empty_bundle()
            bundle["source_reviewer_outputs"][0][field] = value
            bundles.append(bundle)
        bundle = empty_bundle()
        bundle["canonical_findings"] = [{"canonical_id": "CANON-001"}]
        bundles.append(bundle)
        for bundle in bundles:
            with self.subTest(bundle=bundle):
                self.assertFalse(plausible_editor_report(concise_report(), bundle=bundle))
                self.assertTrue(any("too short" in error for error in report_failures(concise_report(), bundle=bundle)))

    def test_explicit_minimum_is_not_waived(self):
        self.assertTrue(any("too short" in error for error in report_failures(
            concise_report(), bundle=empty_bundle(), min_chars=MIN_REPORT_CHARS)))

    def test_empty_report_still_requires_content_scope_and_traceability(self):
        invalid = ["Received.", "# Multi-Agent Paper Review Report\n",
                   concise_report().replace("No corrections were identified.", ""),
                   concise_report().replace("## Appendix: Review Scope and Limitations", "## Other"),
                   concise_report().replace("## Appendix: Traceability Map", "## Other"),
                   concise_report().replace("No findings to map.", ""),
                   concise_report() + "\nCANON-001\n",
                   concise_report() + "\nhttps://unsupported.example/source\n"]
        for report in invalid:
            with self.subTest(report=report):
                self.assertTrue(report_failures(report, bundle=empty_bundle()))

    def test_no_findings_cli_uses_same_rule_and_honours_override(self):
        with tempfile.TemporaryDirectory() as folder:
            report, bundle = Path(folder) / "report.md", Path(folder) / "bundle.json"
            report.write_text(concise_report(), encoding="utf-8")
            bundle.write_text(json.dumps(empty_bundle()), encoding="utf-8")
            command = [sys.executable, str(REPO / "scripts/check_final_report.py"),
                       "--input", str(report), "--bundle", str(bundle)]
            passed = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            failed = subprocess.run(command + ["--min-chars", "2000"], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("too short", failed.stdout)


if __name__ == "__main__":
    unittest.main()
