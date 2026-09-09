from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import fitz

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_work_plugin import (  # noqa: E402
    PLUGIN_NAME, RUNTIME_PATH, build, check_bundle, make_private_marketplace, runtime_payload,
)
from check_final_report import report_failures  # noqa: E402
from work_plugin import MODES, ReviewRun, WorkError, doctor, main, parse_json, read_json, restore, write_json  # noqa: E402

PLUGIN = REPO / "plugins" / PLUGIN_NAME
SOURCE = PLUGIN / RUNTIME_PATH
TEMP = Path(tempfile.gettempdir()) / "reviewer-plugin-tests"


def empty_review(run, name, status="ok"):
    return {"reviewer": name, "paper_id": run.state["paper_id"], "run_status": status,
            "summary": "No material issue found in this synthetic test fixture.", "findings": [], "notes": []}


def finding(run, prefix="CLAIM", number=1, issue_type="manuscript_issue"):
    return {
        "id": f"{prefix}-{number:03d}", "category": "claim_consistency",
        "finding_summary": "The claimed increase conflicts with the reported decrease.",
        "issue_type": issue_type, "severity": "medium", "confidence": "high",
        "location": {"page": 1, "page_label": "1", "section": "Results",
                     "text_quote": "The estimate is -2.5 percent.", "precision": "exact"},
        "claim_text": "The estimate supports an increase.", "assessment": "no",
        "cannot_verify_reason": None, "evidence_summary": "The signed estimate is negative.",
        "source_objects": [{"id": "source-1", "type": "text", "label": "Results",
                            "path": f"work/{run.state['paper_id']}/parsed/pages/page_001.md",
                            "page": 1, "page_label": "1", "section": "Results",
                            "text_quote": "The estimate is -2.5 percent.", "url": None}],
        "claim_evidence_links": [{"claim_text": "The estimate supports an increase.",
                                  "source_object_ids": ["source-1"], "relation": "contradicts", "note": None}],
        "numeric_check": None, "suggested_fix": "Describe the signed estimate consistently."}


def selection(run, paper_type="mixed", confidence="high", selected=()):
    _, _, optional = run.split_reviewers()
    return {"paper_id": run.state["paper_id"], "paper_type": paper_type,
            "selection_confidence": confidence, "selection_mode": "applicability",
            "selected_optional_reviewers": [{"name": r.name, "reason": "Remit is present."}
                                             for r in optional if r.name in selected],
            "skipped_optional_reviewers": [{"name": r.name, "reason": "Entire remit is absent."}
                                            for r in optional if r.name not in selected], "notes": []}


def save_candidate(job, data):
    path = Path(job["candidate_file"])
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        write_json(path, data)


def synthetic_report(bundle, lite=False):
    # Test fixture, not an LLM review or a claim of scientific verification.
    text = "# Multi-Agent Paper Review Report\n\n"
    for heading in ("Executive Summary", "Highest-Priority Cross-Agent Findings",
                    "Suggested Revision Priorities", "Additional Findings"):
        text += f"## {heading}\n\n"
        text += ("This synthetic report exercises artifact validation only. The manuscript's signed estimate "
                 "must be described consistently, and any interpretation should stay within the evidence. " * 4) + "\n\n"
    text += "## Appendix: Review Scope and Limitations\n\n"
    text += "This is a synthetic workflow test, not a substantive scientific review. "
    if lite:
        text += "Lite mode uses a lower requested reasoning effort and is unbenchmarked. "
    text += "\n\n## Appendix: Traceability Map\n\n"
    text += "| Report section | Finding | Canonical ID | Source finding IDs |\n| --- | --- | --- | --- |\n"
    for item in bundle["canonical_findings"]:
        ids = ", ".join(f"{s['reviewer']}:{s['id']}" for s in item["source_findings"])
        text += f"| Additional Findings | Signed estimate | {item['canonical_id']} | {ids} |\n"
    return text


class WorkRunFixture:
    @classmethod
    def setUpClass(cls):
        TEMP.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="work-plugin-", dir=TEMP)
        cls.base = Path(cls.temporary.name)
        cls.pdf = cls.base / "paper with spaces.pdf"
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((72, 72), "A Synthetic Economics Paper\nAbstract\nThe estimate is -2.5 percent.\n"
                             "Results\nThis test preserves signs, decimal points, and page numbering.\n1")
            doc.save(cls.pdf)
        cls.template = cls.base / "template"
        ReviewRun.start(cls.template, SOURCE, cls.pdf, "full", "available")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.temporary_run = tempfile.TemporaryDirectory(prefix="case-", dir=self.base)
        self.folder = Path(self.temporary_run.name)
        self.root = self.folder / "run"
        shutil.copytree(self.template, self.root)
        self.run = ReviewRun(self.root, SOURCE)

    def tearDown(self):
        self.temporary_run.cleanup()

    def preflight(self, data=None):
        job = self.run.next_tasks()["jobs"][0]
        save_candidate(job, data or empty_review(self.run, job["task"]))
        result = self.run.accept(job["task"])
        self.assertEqual(result["status"], "accepted", result)
        return result

    def route(self, data=None):
        self.preflight()
        job = self.run.next_tasks()["jobs"][0]
        self.assertEqual(job["kind"], "selector")
        save_candidate(job, data or selection(self.run))
        result = self.run.accept(job["task"])
        self.assertEqual(result["status"], "accepted", result)


class WorkPluginTests(WorkRunFixture, unittest.TestCase):
    def test_real_preprocessing_and_no_nested_process(self):
        manifest = read_json(self.run.paths.parsed_dir / "manifest.json")
        self.assertEqual(manifest["summary"]["page_count"], 1)
        self.assertFalse(manifest["settings"]["ocr_used"])
        self.assertIn("-2.5", (self.run.paths.parsed_dir / "pages/page_001.md").read_text(encoding="utf-8"))
        with mock.patch("subprocess.run", side_effect=AssertionError("No model process allowed")):
            self.route()
            self.assertEqual(len(self.run.state["active_reviewers"]), 19)

    def test_preflight_barrier_and_inflight_not_duplicated(self):
        jobs = self.run.next_tasks(3)["jobs"]
        self.assertEqual([j["kind"] for j in jobs], ["preflight"])
        self.assertEqual(self.run.next_tasks(3)["jobs"], [])
        self.run.resume()
        self.assertEqual(self.run.next_tasks(3)["jobs"], [])

    def assert_invalid_candidate_retries(self, job, payload):
        candidate = Path(job["candidate_file"])
        candidate.write_bytes(payload)
        result = self.run.accept(job["task"])
        self.assertEqual(result["status"], "retry", result)
        self.assertEqual(candidate.read_bytes(), payload)
        self.assertIsNone(self.run.state["paused"])
        self.assertFalse(self.run.paths.report_path.exists())
        self.run = ReviewRun(self.root, SOURCE)
        self.assertEqual(self.run.task(job["task"])["attempts"][-1]["status"], "invalid")
        self.assertFalse(self.run.task(job["task"])["attempts"][-1].get("output"))
        self.assertNotIn(candidate.relative_to(self.root).as_posix(), self.run.state["sealed"])
        if job["kind"] == "selector":
            self.assertEqual(self.run.state["active_reviewers"], [])
            self.assertFalse(self.run.paths.selected_reviewers_config_path.exists())
        else:
            reviewer = next(r for r in self.run.reviewers if r.name == job["task"])
            output = self.run.paths.reviews_dir / reviewer.output
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(output.suffix + ".tmp").exists())
        retry = self.run.next_tasks()["jobs"][0]
        self.assertEqual(retry["task"], job["task"])
        self.assertEqual(retry["attempt"], 2)
        self.assertNotEqual(retry["candidate_file"], job["candidate_file"])
        valid = selection(self.run) if job["kind"] == "selector" else empty_review(self.run, job["task"])
        save_candidate(retry, valid)
        self.assertEqual(self.run.accept(retry["task"])["status"], "accepted")

    def test_duplicate_findings_are_rejected_without_losing_original_evidence(self):
        job = self.run.next_tasks()["jobs"][0]
        data = empty_review(self.run, job["task"])
        data["findings"] = [finding(self.run, "PARSER", issue_type="parser_artifact")]
        self.assertEqual(self.run.validate_review(data, job["task"]), [])
        payload = (json.dumps(data)[:-1] + ', "findings": []}').encode("utf-8")
        self.assert_invalid_candidate_retries(job, payload)

    def test_duplicate_nested_fields_are_rejected(self):
        job = self.run.next_tasks()["jobs"][0]
        data = empty_review(self.run, job["task"])
        data["findings"] = [finding(self.run, "PARSER", issue_type="parser_artifact")]
        payload = json.dumps(data).replace('"page": 1', '"page": 2, "page": 1', 1).encode("utf-8")
        self.assert_invalid_candidate_retries(job, payload)

    def test_router_duplicate_fields_do_not_promote_selection(self):
        self.preflight()
        job = self.run.next_tasks()["jobs"][0]
        payload = (json.dumps(selection(self.run))[:-1] + ', "selected_optional_reviewers": []}').encode("utf-8")
        self.assert_invalid_candidate_retries(job, payload)

    def test_oversized_integer_is_retried(self):
        job = self.run.next_tasks()["jobs"][0]
        self.assert_invalid_candidate_retries(job, b'{"findings":' + b"9" * 5000 + b"}")

    def test_excessively_nested_json_is_retried(self):
        job = self.run.next_tasks()["jobs"][0]
        self.assert_invalid_candidate_retries(job, b"[" * 1500 + b"0" + b"]" * 1500)

    def test_unpaired_surrogate_is_retried_before_writing_output(self):
        job = self.run.next_tasks()["jobs"][0]
        data = {**empty_review(self.run, job["task"]), "summary": "\ud800"}
        self.assert_invalid_candidate_retries(job, json.dumps(data).encode("utf-8"))

    def test_lite_malformed_json_exhausts_bounded_retries(self):
        self.run.state["mode"] = "lite"
        self.run.state["profile"] = MODES["lite"]
        self.run.task("parser_quality_auditor")["max_attempts"] = MODES["lite"]["max_attempts"]
        self.run.save()
        for expected in ("retry", "exhausted"):
            job = self.run.next_tasks()["jobs"][0]
            save_candidate(job, '{"findings": [], "findings": []}')
            self.assertEqual(self.run.accept(job["task"])["status"], expected)
        self.assertEqual(self.run.next_tasks()["status"], "paused")
        with self.assertRaises(WorkError):
            self.run.resume()
        self.assertEqual(len(self.run.task(job["task"])["attempts"]), 2)

    def test_injected_future_tasks_are_rejected_on_load_and_dispatch(self):
        for phase in ("preflight", "selection", "reviews"):
            if phase == "selection":
                self.preflight()
                self.run.advance()
            elif phase == "reviews":
                job = self.run.next_tasks()["jobs"][0]
                save_candidate(job, selection(self.run))
                self.run.accept(job["task"])
                self.run.advance()
            original = copy.deepcopy(self.run.state)
            for name, kind in (("grammar_auditor", "review"), ("editor", "editor")):
                if name in original["tasks"]:
                    continue
                with self.subTest(phase=phase, task=name):
                    self.run.state = copy.deepcopy(original)
                    self.run.add_task(name, kind)
                    self.run.save()
                    saved = self.run.state_path.read_bytes()
                    with self.assertRaises(WorkError) as caught:
                        ReviewRun(self.root, SOURCE)
                    self.assertEqual(caught.exception.code, "checkpoint_invalid")
                    with self.assertRaises(WorkError):
                        self.run.next_tasks(3)
                    self.assertEqual(self.run.state_path.read_bytes(), saved)
            self.run.state = original
            self.run.save()

    def test_malformed_checkpoint_shapes_return_friendly_errors_without_mutation(self):
        original = copy.deepcopy(self.run.state)
        cases = [("null", None), ("array", [])]
        for key, value in (("tasks", None), ("mode", []), ("phase", {}), ("web", []),
                           ("paper_id", 12), ("sealed", []), ("parsed_snapshot", []),
                           ("runtime_manifest", None), ("paused", []), ("paused", {"code": []}),
                           ("active_reviewers", [None]), ("coverage_limitations", [None])):
            cases.append((key, {**original, key: value}))
        parser = original["tasks"]["parser_quality_auditor"]
        for value in ([], None, {**parser, "attempts": None}, {**parser, "max_attempts": "3"},
                      {**parser, "max_attempts": True}, {**parser, "status": []},
                      {**parser, "status": "inflight", "attempts": [None]},
                      {**parser, "status": "inflight", "attempts": [{"candidate": None}]}):
            cases.append(("task", {**original, "tasks": {"parser_quality_auditor": value}}))
        for label, state in cases:
            with self.subTest(shape=label, state=state):
                write_json(self.run.state_path, state)
                saved = self.run.state_path.read_bytes()
                stdout, stderr = io.StringIO(), io.StringIO()
                argv = ["work_plugin.py", "--source", str(SOURCE), "status", "--workspace", str(self.root)]
                with mock.patch.object(sys, "argv", argv), redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(main(), 1)
                result = json.loads(stdout.getvalue())
                self.assertEqual(result["code"], "checkpoint_invalid")
                self.assertEqual(stderr.getvalue(), "")
                self.assertEqual(self.run.state_path.read_bytes(), saved)

    def test_parser_blocker_cannot_resume(self):
        data = empty_review(self.run, "parser_quality_auditor")
        data["findings"] = [finding(self.run, "PARSER", issue_type="parser_artifact")]
        data["findings"][0]["severity"] = "high"
        result = self.preflight(data)
        self.assertEqual(result["paused"]["code"], "parser_blocked")
        self.assertEqual(self.run.next_tasks()["status"], "paused")
        with self.assertRaises(WorkError):
            self.run.resume()

    def test_bad_identity_schema_and_retry_cap(self):
        for index in range(3):
            job = self.run.next_tasks()["jobs"][0]
            data = empty_review(self.run, job["task"])
            if index == 0:
                data["paper_id"] = "another-paper"
            elif index == 1:
                data["reviewer"] = "grammar_auditor"
            else:
                data["run_status"] = "failed"
            save_candidate(job, data)
            result = self.run.accept(job["task"])
            self.assertNotEqual(result["status"], "accepted")
        self.assertEqual(result["status"], "exhausted")
        with self.assertRaises(WorkError):
            self.run.resume()
        self.run.resume("parser_quality_auditor")
        self.assertEqual(self.run.next_tasks()["jobs"][0]["attempt"], 4)
        self.assertEqual(len(list((self.run.paths.work_root / "attempts/parser_quality_auditor").glob("*.json"))), 3)

    def test_invalid_json_and_incorrect_provenance(self):
        job = self.run.next_tasks()["jobs"][0]
        save_candidate(job, "```json\n{}\n```")
        self.assertEqual(self.run.accept(job["task"])["status"], "retry")
        job = self.run.next_tasks()["jobs"][0]
        data = empty_review(self.run, job["task"])
        data["findings"] = [finding(self.run, "PARSER", issue_type="parser_artifact")]
        data["findings"][0]["source_objects"][0]["path"] = "../private.txt"
        save_candidate(job, data)
        result = self.run.accept(job["task"])
        self.assertEqual(result["status"], "retry")
        self.assertTrue(any("traversal" in e for e in result["errors"]), result)

    def test_malformed_external_url_is_a_retry_not_a_stuck_task(self):
        job = self.run.next_tasks()["jobs"][0]
        data = empty_review(self.run, job["task"])
        data["findings"] = [finding(self.run, "PARSER", issue_type="parser_artifact")]
        source = data["findings"][0]["source_objects"][0]
        source.update({"type": "external", "path": None, "url": "https://[broken"})
        save_candidate(job, data)
        result = self.run.accept(job["task"])
        self.assertEqual(result["status"], "retry")
        self.assertTrue(any("provenance" in e for e in result["errors"]))

    def test_unfinished_checkpoint_cannot_claim_completion(self):
        self.run.state["phase"] = "complete"
        self.run.save()
        with self.assertRaises(WorkError):
            self.run.status()
        with self.assertRaises(WorkError):
            self.run.checkpoint(self.folder / "not-complete.zip")

    def test_checkpoint_rejects_unknown_task_paths(self):
        self.run.state["tasks"]["../outside"] = self.run.state["tasks"].pop("parser_quality_auditor")
        self.run.save()
        with self.assertRaises(WorkError):
            ReviewRun(self.root, SOURCE)

    def test_selector_requires_complete_roster_accounting(self):
        self.preflight()
        job = self.run.next_tasks()["jobs"][0]
        data = selection(self.run)
        data["skipped_optional_reviewers"].pop()
        save_candidate(job, data)
        self.assertEqual(self.run.accept(job["task"])["status"], "retry")

    def test_theory_guard_restores_theory_logic(self):
        self.route(selection(self.run, "theory"))
        self.assertEqual(len(self.run.state["active_reviewers"]), 9)
        self.assertIn("theory_logic_auditor", self.run.state["active_reviewers"])

    def test_lite_keeps_full_uncertain_coverage_but_serializes(self):
        self.run.state["mode"] = "lite"
        self.run.state["profile"] = MODES["lite"]
        self.run.save()
        self.route(selection(self.run, "empirical_causal", "medium"))
        self.assertEqual(len(self.run.state["active_reviewers"]), 19)
        jobs = self.run.next_tasks(50)["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["requested_reasoning_effort"], "high")
        self.assertEqual(self.run.next_tasks(50)["jobs"], [])

    def test_mixed_and_unknown_and_lower_confidence_expand_both_modes(self):
        from reviewer_routing import enforce_conservative_applicability
        _, mandatory, optional = self.run.split_reviewers()
        self.assertEqual(len(mandatory), 8)
        for mode in MODES:
            for paper_type, confidence in [("mixed", "high"), ("unknown", "high"),
                                           ("methods", "medium"), ("theory", "low")]:
                with self.subTest(mode=mode, paper_type=paper_type, confidence=confidence):
                    guarded = enforce_conservative_applicability(selection(self.run, paper_type, confidence), optional)
                    self.assertEqual({x["name"] for x in guarded["selected_optional_reviewers"]}, {r.name for r in optional})
                    self.assertEqual(guarded["skipped_optional_reviewers"], [])

    def test_no_new_dispatch_after_quota_but_completed_children_are_saved(self):
        self.route()
        jobs = self.run.next_tasks(3)["jobs"]
        self.assertEqual(len(jobs), 3)
        self.run.fail(jobs[0]["task"], "quota")
        save_candidate(jobs[1], empty_review(self.run, jobs[1]["task"]))
        result = self.run.accept(jobs[1]["task"])
        self.assertEqual(result["status"], "accepted")
        self.assertIsNotNone(result["paused"])
        self.assertEqual(self.run.next_tasks(3)["status"], "paused")
        self.run.resume()
        more = self.run.next_tasks(3)["jobs"]
        self.assertEqual(len(more), 2)
        self.assertNotIn(jobs[2]["task"], [job["task"] for job in more])

    def test_quota_pause_and_resume_do_not_repeat_accepted_work(self):
        self.preflight()
        job = self.run.next_tasks()["jobs"][0]
        self.run.fail(job["task"], "quota")
        self.assertEqual(self.run.next_tasks()["status"], "paused")
        self.run.resume()
        new_job = self.run.next_tasks()["jobs"][0]
        self.assertEqual(new_job["task"], "applicability_router")
        self.assertEqual(new_job["attempt"], 2)
        self.assertEqual(len(self.run.task("parser_quality_auditor")["attempts"]), 1)

    def test_missing_web_is_disclosed_not_falsely_verified(self):
        self.run.state["web"] = "unavailable"
        self.run.save()
        errors = self.run.validate_review(empty_review(self.run, "literature_auditor"), "literature_auditor")
        self.assertTrue(any("Web search" in e for e in errors))
        self.assertEqual(self.run.validate_review(empty_review(self.run, "literature_auditor", "cannot_verify"), "literature_auditor"), [])

    def test_changed_pdf_parsed_or_prompt_refuses_reuse(self):
        for path in [self.root / "inputs/paper.pdf", self.run.paths.parsed_dir / "pages/page_001.md",
                     self.run.paths.prompts_dir / "parser_quality_audit.txt"]:
            original = path.read_bytes()
            path.write_bytes(original + b"tampered")
            with self.assertRaises(WorkError):
                self.run.next_tasks()
            path.write_bytes(original)
        added = self.run.paths.parsed_dir / "extra.md"
        added.write_text("Unexpected evidence", encoding="utf-8")
        with self.assertRaises(WorkError):
            self.run.status()

    def test_fresh_start_refuses_existing_folder_and_dependencies(self):
        with self.assertRaisesRegex(WorkError, "already exists"):
            ReviewRun.start(self.root, SOURCE, self.pdf, "full", "available")
        with mock.patch("work_plugin.doctor", return_value={"status": "unavailable", "missing": ["pymupdf"]}):
            with self.assertRaisesRegex(WorkError, "Missing packages: pymupdf"):
                ReviewRun.start(self.folder / "no-deps", SOURCE, self.pdf, "full", "available")
        self.assertFalse((self.folder / "no-deps").exists())

    def test_encrypted_and_invalid_pdf_errors(self):
        locked = self.folder / "locked.pdf"
        with fitz.open(self.pdf) as doc:
            doc.save(locked, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="fixture-owner", user_pw="fixture-user")
        with self.assertRaisesRegex(WorkError, "password-protected"):
            ReviewRun.start(self.folder / "locked-run", SOURCE, locked, "full", "available")
        invalid = self.folder / "broken.pdf"
        invalid.write_bytes(b"not a PDF")
        with self.assertRaisesRegex(WorkError, "could not open"):
            ReviewRun.start(self.folder / "invalid-run", SOURCE, invalid, "full", "available")

    def test_portable_checkpoint_preserves_inflight_and_completed_stages(self):
        self.preflight()
        job = self.run.next_tasks()["jobs"][0]
        save_candidate(job, selection(self.run))
        archive = self.folder / "checkpoint.zip"
        self.run.checkpoint(archive)
        target = self.folder / "different location"
        restore(archive, target, SOURCE)
        resumed = ReviewRun(target, SOURCE)
        self.assertEqual(resumed.task("parser_quality_auditor")["status"], "accepted")
        self.assertEqual(resumed.task("applicability_router")["status"], "inflight")
        self.assertEqual(resumed.accept("applicability_router")["status"], "accepted")
        self.assertEqual(len(resumed.next_tasks(3)["jobs"]), 3)

    def test_restore_rejects_traversal_duplicates_and_modified_evidence(self):
        for entries in [[("../outside.txt", b"bad")], [("A", b"a"), ("a", b"b")]]:
            archive = self.folder / f"malicious-{len(entries)}.zip"
            with zipfile.ZipFile(archive, "w") as output:
                for name, data in entries:
                    output.writestr(name, data)
            with self.assertRaises(WorkError):
                restore(archive, self.folder / "restored", SOURCE)
        source_zip = self.folder / "original.zip"
        self.run.checkpoint(source_zip)
        modified = self.folder / "modified.zip"
        with zipfile.ZipFile(source_zip) as incoming, zipfile.ZipFile(modified, "w") as output:
            for name in incoming.namelist():
                output.writestr(name, b"changed" if name == "inputs/paper.pdf" else incoming.read(name))
        with self.assertRaises(WorkError):
            restore(modified, self.folder / "restored", SOURCE)
        self.assertFalse((self.folder / "restored").exists())

    def test_full_synthetic_pipeline_lossless_editor_retry_and_restore(self):
        self.route()
        saw_finding = False
        while True:
            jobs = self.run.next_tasks(3)["jobs"]
            if jobs[0]["kind"] == "editor":
                editor = jobs[0]
                break
            for job in jobs:
                data = empty_review(self.run, job["task"])
                if job["task"] == "claim_evidence_auditor":
                    reviewer = next(r for r in self.run.reviewers if r.name == job["task"])
                    data["findings"] = [finding(self.run, reviewer.id_prefix)]
                    saw_finding = True
                save_candidate(job, data)
                result = self.run.accept(job["task"])
                self.assertEqual(result["status"], "accepted", result)
        self.assertTrue(saw_finding)
        bundle = read_json(self.run.paths.bundle_path)
        self.assertEqual(len(bundle["canonical_findings"]), 1)
        editor_input = self.run.paths.editor_input_path.read_text(encoding="utf-8")
        self.assertIn("lossless", editor_input)
        self.assertNotIn(str(self.root), editor_input)
        self.assertIn("-2.5 percent", editor_input)
        save_candidate(editor, "Report saved.")
        self.assertEqual(self.run.accept("editor")["status"], "retry")
        self.assertFalse(self.run.paths.report_path.exists())
        editor = self.run.next_tasks()["jobs"][0]
        save_candidate(editor, synthetic_report(bundle))
        self.assertEqual(self.run.accept("editor")["status"], "accepted")
        self.assertEqual(self.run.next_tasks()["status"], "complete")
        archive = self.folder / "final-checkpoint.zip"
        self.run.checkpoint(archive)
        restored = restore(archive, self.folder / "final-restored", SOURCE)
        self.assertEqual(restored["status"], "complete")
        self.assertTrue(Path(restored["report"]).is_file())

    def test_empty_report_bundle_does_not_require_fabricated_ids(self):
        bundle = {"canonical_findings": []}
        self.assertEqual(report_failures(synthetic_report(bundle), bundle=bundle), [])
        nonempty = {"canonical_findings": [{"canonical_id": "CANON-001", "source_findings": []}]}
        self.assertTrue(report_failures(synthetic_report(bundle), bundle=nonempty))
        self.assertTrue(report_failures(synthetic_report(bundle), bundle={}))


class WorkJsonTests(unittest.TestCase):
    def test_strict_decoder_rejects_ambiguous_or_unserializable_values(self):
        for text in ('{"x": 1, "x": 2}', '{"x": {"y": 1, "y": 2}}',
                     '{"x": NaN}', '{"x": Infinity}', '{"x": 1e400}',
                     '{"x": "\\ud800"}', '{"\\udfff": "value"}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_json(text)

    def test_strict_decoder_preserves_valid_unicode_and_signed_numbers(self):
        data = {"evidence": "\u00f8 \U0001f4c4 -2.50 (12.50%)", "estimate": -2.5, "items": [None, True, 12]}
        self.assertEqual(parse_json(json.dumps(data, ensure_ascii=True)), data)
        self.assertEqual(parse_json(json.dumps(data, ensure_ascii=False)), data)


class WorkPackageTests(unittest.TestCase):
    def test_bundle_is_current_and_strictly_allowlisted(self):
        self.assertEqual(check_bundle(REPO, PLUGIN), [])
        names = runtime_payload(REPO)
        self.assertNotIn("scripts/review_paper.py", names)
        self.assertNotIn("scripts/select_reviewers.py", names)
        self.assertNotIn("scripts/refresh_editor.py", names)
        self.assertEqual(len(load_reviewers()), 20)

    def test_reproducible_zip_and_private_marketplace(self):
        TEMP.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="package-", dir=TEMP) as directory:
            folder = Path(directory)
            first, second = folder / "one.zip", folder / "two.zip"
            self.assertEqual(build(REPO, PLUGIN, check=True, archive=first), [])
            self.assertEqual(build(REPO, PLUGIN, check=True, archive=second), [])
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertIn(".codex-plugin/plugin.json", archive.namelist())
                self.assertFalse(any(name.startswith(("inputs/", "work/", "outputs/", ".env")) for name in archive.namelist()))
            marketplace = folder / "private"
            make_private_marketplace(REPO, PLUGIN, marketplace)
            catalog = read_json(marketplace / ".agents/plugins/marketplace.json")
            installed = marketplace / catalog["plugins"][0]["source"]["path"]
            self.assertEqual(check_bundle(REPO, installed), [])
            self.assertEqual(doctor(installed / RUNTIME_PATH)["status"], "ready")
            with self.assertRaises(ValueError):
                make_private_marketplace(REPO, PLUGIN, marketplace)


def load_reviewers():
    from reviewer_config import load_reviewers_config
    return load_reviewers_config(SOURCE / "config/reviewers.json")


if __name__ == "__main__":
    unittest.main()
