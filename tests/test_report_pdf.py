from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import fitz

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from render_report_pdf import PDFExportError, inline, normalized, render_report_pdf, table_cells
from work_plugin import ReviewRun, WorkError, read_json, restore
from tests.test_work_plugin import SOURCE, WorkRunFixture, empty_review, save_candidate, synthetic_report


class ReportPDFTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="reviewer-pdf-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "report.md"
        self.pdf = self.root / "report.pdf"

    def tearDown(self):
        self.temporary.cleanup()

    def render(self, text):
        self.source.write_text(text, encoding="utf-8")
        original = self.source.read_bytes()
        result = render_report_pdf(self.source, self.pdf)
        self.assertEqual(self.source.read_bytes(), original)
        with fitz.open(self.pdf) as document:
            self.assertEqual(document.embfile_get("report.md"), original)
            self.assertEqual(document.page_count, result["pages"])
            extracted = "".join(page.get_text() for page in document)
        self.assertTrue(result["text_verified"])
        self.assertEqual(result["source_sha256"], hashlib.sha256(original).hexdigest())
        return result, extracted

    def test_unicode_numbers_links_and_literal_math_survive(self):
        result, text = self.render(
            "# Complete review\n\nNæss: α = −2.5%, p < 0.05; CI [-4.1, -0.9].\n\n"
            "**Evidence** and *qualification*: `x_i = -2.5`. $\\beta$ stays literal.\n\n"
            "[Source](https://example.org/paper_(2026))\n\n"
            "- Do not infer the missing estimate.\n\n"
            "```text\n<unsafe> & -1.00\n```\n")
        for expected in ("Næss", "α = −2.5%", "[-4.1, -0.9]", "$\\beta$", "<unsafe>", "-1.00"):
            self.assertIn(normalized(expected), normalized(text))
        with fitz.open(self.pdf) as doc:
            self.assertIn("https://example.org/paper_(2026)", [link.get("uri") for p in doc for link in p.get_links()])

    def test_long_table_and_every_traceability_id_survive_pagination(self):
        # Exercise long-form output and row boundaries: no silent page truncation.
        evidence = "The effect is -2.5 percent, not +2.5 percent. Preserve the caveat and source location. "
        source = "# Full report\n\n" + evidence * 50 + "\n\n## Traceability\n\n"
        source += "| ID | Evidence | Source |\n| --- | --- | --- |\n"
        for i in range(90):
            source += f"| CANON-{i:03d} | {evidence * 4} | claim_evidence_auditor:CLAIM-{i:03d} |\n"
        source += "\n## Last section\n\nEND OF COMPLETE REPORT.\n"
        result, text = self.render(source)
        self.assertGreater(result["pages"], 10)
        for i in range(90):
            self.assertIn(f"CANON-{i:03d}", normalized(text))
            self.assertIn(f"claim_evidence_auditor:CLAIM-{i:03d}", normalized(text))
        self.assertIn("END OF COMPLETE REPORT.", text)

    def test_table_pipes_and_unexpected_columns_preserved(self):
        self.assertEqual(table_cells(r"| `a|b` | c\|d |"), ["`a|b`", r"c\|d"])
        _, text = self.render("# Table\n\n| A | B |\n| --- | --- |\n| `a|b` | c\\|d |\n| x | y | EXTRA |\n")
        for value in ("a|b", "c|d", "EXTRA"):
            self.assertIn(value, text)

    def test_html_images_and_unsafe_links_are_not_loaded(self):
        rendered = inline('<img src="file:///private.png"> [run](javascript:alert)')
        self.assertNotIn("<img", rendered)
        self.assertNotIn("href=", rendered)
        _, text = self.render('# Offline report\n\n<img src="https://invalid.example/private.png">\n\n'
                              '![Figure](file:///private.png)\n\n[run](javascript:alert)\n')
        self.assertIn("private.png", normalized(text))
        self.assertIn("javascript:alert", normalized(text))

    def test_existing_and_empty_outputs_fail_without_overwrite(self):
        self.source.write_text("# Source", encoding="utf-8")
        self.pdf.write_bytes(b"existing user file")
        with self.assertRaises(PDFExportError):
            render_report_pdf(self.source, self.pdf)
        self.assertEqual(self.pdf.read_bytes(), b"existing user file")
        self.source.write_text("", encoding="utf-8")
        empty_output = self.root / "empty.pdf"
        with self.assertRaises(PDFExportError):
            render_report_pdf(self.source, empty_output)
        self.assertFalse(empty_output.exists())

    def test_missing_text_fails_closed(self):
        self.source.write_text("# Report\n\nCritical evidence -2.5%.", encoding="utf-8")
        with mock.patch("fitz.Page.get_text", return_value="missing content"):
            with self.assertRaises(PDFExportError):
                render_report_pdf(self.source, self.pdf)
        self.assertFalse(self.pdf.exists())

    def test_page_limit_fails_without_truncated_output(self):
        self.source.write_text("# Report\n\n" + ("Long evidence. " * 2000), encoding="utf-8")
        with mock.patch("render_report_pdf.MAX_PAGES", 1):
            with self.assertRaises(PDFExportError):
                render_report_pdf(self.source, self.pdf)
        self.assertFalse(self.pdf.exists())


class PDFDeliveryTests(WorkRunFixture, unittest.TestCase):
    def test_validated_export_retry_reuse_and_checkpoint(self):
        with self.assertRaises(WorkError) as early:
            self.run.export_pdf()
        self.assertEqual(early.exception.code, "report_not_complete")
        self.route()
        while True:
            jobs = self.run.next_tasks(3)["jobs"]
            if jobs[0]["kind"] == "editor":
                save_candidate(jobs[0], synthetic_report(read_json(self.run.paths.bundle_path)))
                self.assertEqual(self.run.accept("editor")["status"], "accepted")
                break
            for job in jobs:
                save_candidate(job, empty_review(self.run, job["task"]))
                self.assertEqual(self.run.accept(job["task"])["status"], "accepted")
        self.assertEqual(self.run.next_tasks()["status"], "complete")
        before = self.run.status()["tasks"]
        with mock.patch("render_report_pdf.render_report_pdf", side_effect=PDFExportError("test layout failure")):
            with self.assertRaises(WorkError) as failed:
                self.run.export_pdf()
        self.assertEqual(failed.exception.code, "pdf_export_failed")
        self.assertEqual(self.run.status()["status"], "complete")
        self.assertEqual(self.run.status()["tasks"], before)
        self.assertIsNone(self.run.status()["report_pdf"])
        first = self.run.export_pdf()
        self.assertEqual(first["status"], "pdf_ready")
        pdf = Path(first["report_pdf"])
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        self.assertTrue(self.run.export_pdf()["reused"])
        self.assertEqual(self.run.status()["tasks"], before)
        checkpoint = self.folder / "with-pdf.zip"
        self.run.checkpoint(checkpoint)
        restored = self.folder / "restored"
        result = restore(checkpoint, restored, SOURCE)
        self.assertEqual(hashlib.sha256(Path(result["report_pdf"]).read_bytes()).hexdigest(), digest)
        self.assertTrue(ReviewRun(restored, SOURCE).export_pdf()["reused"])
        pdf.write_bytes(b"changed")
        with self.assertRaises(WorkError):
            self.run.export_pdf()
