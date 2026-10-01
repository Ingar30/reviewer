"""Offline benchmark protocol/runner/scoring regression tests; no model calls."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import benchmark_models as benchmark
import benchmark_scoring as scoring
from review_paper import RunResult


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="rb-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.work = self.source / "work/paper-a"
        self.pdf = self.root / "source paper.pdf"
        self.pdf.write_bytes(b"synthetic test-only PDF identity; no real paper or review")
        benchmark.write(self.work / "parsed/manifest.json", {
            "paper_id": "paper-a", "source_pdf_sha256": benchmark.digest(self.pdf),
            "summary": {"page_count": 1},
        })
        (self.work / "parsed/full_text.md").write_text("Synthetic parsed fixture only.")
        benchmark.write(self.work / "reviews/parser_quality_auditor.json", {
            "reviewer": "parser_quality_auditor", "paper_id": "paper-a", "run_status": "ok",
            "summary": "MOCK parser preflight", "findings": [], "notes": [],
        })
        self.config = {"format": 1, "repeats": 2, "schedule_seed": 17,
                       "profiles": [
                           {"id": "sol", "backend": "codex", "model": "gpt-6-sol", "effort": "xhigh"},
                           {"id": "opus", "backend": "claude", "model": "claude-opus-5-5", "effort": "xhigh"}],
                       "cases": [{"id": "case-a", "workspace": "source", "paper_id": "paper-a",
                                  "pdf": "source paper.pdf", "roles": ["numerical_auditor", "claim_evidence_auditor"]}]}
        self.config_path = self.root / "config.json"
        benchmark.write(self.config_path, self.config)
        self.plan_path = self.root / "benchmark/plan.json"

    def prepare(self):
        return benchmark.prepare(self.config_path, self.plan_path.parent)

    def fake_run(self, label, command, cwd, log_dir, input_text, timeout_seconds):
        self.assertNotIn("--dangerously-skip-permissions", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertNotIn("--ignore-rules", command)
        role = "numerical_auditor" if 'reviewer = "numerical_auditor"' in input_text else "claim_evidence_auditor"
        payload = {"reviewer": role, "paper_id": "paper-a", "run_status": "ok", "summary": "MOCK", "findings": [], "notes": []}
        log_dir.mkdir(parents=True)
        stdout, stderr = log_dir / "benchmark.stdout.log", log_dir / "benchmark.stderr.log"
        if "--print" in command:
            benchmark.write(stdout, {"type": "result", "subtype": "success", "is_error": False,
                                    "structured_output": payload,
                                    "usage": {"input_tokens": 10, "cache_read_input_tokens": 20,
                                              "cache_creation_input_tokens": 30, "output_tokens": 40}})
        else:
            self.assertIn("--json", command)
            self.assertIn("--skip-git-repo-check", command)
            benchmark.write(Path(command[command.index("--output-last-message") + 1]), payload)
            stdout.write_text(json.dumps({"type": "turn.completed", "usage": {
                "input_tokens": 60, "cached_input_tokens": 20, "output_tokens": 40}}) + "\n")
        stderr.write_text("model: gpt-6-sol\nreasoning effort: xhigh\nsandbox: read-only\n")
        self.assertEqual({p.name for p in (cwd / "work/paper-a/reviews").glob("*.json")},
                         {"parser_quality_auditor.json"} | ({role + ".json"} if "--print" not in command else set()))
        return RunResult(label, 0, stdout, stderr)

    def mocked_job(self, job):
        with mock.patch.object(benchmark, "run_command", side_effect=self.fake_run), \
                mock.patch.object(benchmark, "check_claude", return_value="2.1.280"), \
                mock.patch("review_paper.codex_command", return_value="OFFLINE"), \
                mock.patch("claude_backend.claude_command", return_value="OFFLINE"), \
                mock.patch.object(benchmark.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "MOCK CLI", "")):
            return benchmark.run_job(self.plan_path, job["id"], allow_live=True)

    def test_prepare_is_repeatable_balanced_and_never_calls_a_cli(self):
        before = benchmark.snapshot(self.source)
        with mock.patch.object(benchmark.subprocess, "run", side_effect=AssertionError("No CLI during preparation")):
            plan = self.prepare()
            other = benchmark.prepare(self.config_path, self.root / "second plan")
        self.assertEqual(plan["planned_model_calls"], 8)
        self.assertEqual(plan["jobs"], other["jobs"])
        self.assertEqual(before, benchmark.snapshot(self.source))
        self.assertFalse((self.plan_path.parent / "runs").exists())
        self.assertFalse(any("benchmark_models.py" in name for name in plan["runtime_files"]))

    def test_prepare_rejects_changed_pdf(self):
        self.pdf.write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.prepare()
        self.assertFalse(self.plan_path.parent.exists())

    def test_existing_plan_and_unsafe_identifiers_are_rejected(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "not overwritten"):
            self.prepare()
        with self.assertRaises(ValueError):
            benchmark.identifier("../outside")

    def test_no_live_execution_without_explicit_flag(self):
        with mock.patch.object(benchmark, "run_command", side_effect=AssertionError("No CLI")):
            with self.assertRaisesRegex(ValueError, "consumes quota"):
                benchmark.run_job(self.plan_path, "j001")
        self.assertFalse(self.plan_path.parent.exists())

    def test_run_refuses_input_or_runtime_drift_before_any_model_call(self):
        plan = self.prepare()
        with mock.patch.object(benchmark, "runtime_hashes", return_value={}):
            with self.assertRaisesRegex(ValueError, "changed since"):
                benchmark.run_job(self.plan_path, plan["jobs"][0]["id"], allow_live=True)
        (self.work / "parsed/full_text.md").write_text("changed")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            benchmark.run_job(self.plan_path, plan["jobs"][0]["id"], allow_live=True)

    def test_mocked_both_backends_keep_identical_prompts_inputs_and_refuse_reruns(self):
        plan = self.prepare()
        before = benchmark.snapshot(self.source)
        selected = [j for j in plan["jobs"] if j["role"] == "numerical_auditor" and j["repeat"] == 1]
        records = [self.mocked_job(job) for job in selected]
        self.assertEqual({r["status"] for r in records}, {"complete"})
        self.assertEqual({r["usage"]["status"] for r in records}, {"reported"})
        self.assertEqual(len({r["prompt_sha256"] for r in records}), 1)
        self.assertEqual(before, benchmark.snapshot(self.source))
        with self.assertRaisesRegex(ValueError, "already attempted"):
            self.mocked_job(selected[0])
        packet = self.root / "packet"
        exported = benchmark.collect(self.plan_path, packet)
        self.assertEqual(exported["complete"], 2)
        self.assertEqual(exported["samples"], 8)
        self.assertNotIn('"profile"', (packet / "blind/samples.json").read_text())
        self.assertTrue((packet / "operator-key.json").exists())
        with self.assertRaisesRegex(ValueError, "do not overwrite"):
            benchmark.collect(self.plan_path, packet)

    def test_failed_calls_and_usage_remain_visible_and_are_not_retried(self):
        plan = self.prepare()
        job = next(j for j in plan["jobs"] if j["profile"] == "sol")
        normal_fake = self.fake_run
        def failed_run(*args, **kwargs):
            result = normal_fake(*args, **kwargs)
            return RunResult(result.label, 1, result.stdout_path, result.stderr_path)
        self.fake_run = failed_run
        with self.assertRaisesRegex(ValueError, "Agent failed"):
            self.mocked_job(job)
        result = benchmark.read(self.plan_path.parent / "runs" / job["id"] / "result.json")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["usage"]["output"], 40)
        with self.assertRaisesRegex(ValueError, "already attempted"):
            self.mocked_job(job)
        packet = self.root / "failed packet"
        benchmark.collect(self.plan_path, packet)
        statuses = [s["status"] for s in benchmark.read(packet / "blind/samples.json")]
        self.assertEqual(statuses.count("failed"), 1)
        self.assertEqual(statuses.count("not-run"), 7)

    def test_reference_ledger_is_frozen_and_exported_without_leaking_to_jobs(self):
        references = self.root / "reference.json"
        benchmark.write(references, {"issues": [{"status": "provisional", "case": "case-a"}]})
        self.config["reference_issues"] = "reference.json"
        benchmark.write(self.config_path, self.config)
        plan = self.prepare()
        self.assertEqual(plan["reference_issues"]["provisional"], 1)
        self.mocked_job(plan["jobs"][0])
        self.assertFalse(list((self.plan_path.parent / "runs").rglob("reference.json")))
        packet = self.root / "reference packet"
        benchmark.collect(self.plan_path, packet)
        self.assertEqual(references.read_bytes(), (packet / "blind/reference-issues.json").read_bytes())
        benchmark.write(references, {"issues": []})
        with self.assertRaisesRegex(ValueError, "Reference ledger changed"):
            self.mocked_job(plan["jobs"][1])

    def test_codex_usage_is_not_double_counted_and_missing_is_unknown(self):
        log = self.root / "usage.log"
        event = {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 30,
                                                         "reasoning_output_tokens": 20}}
        log.write_text(json.dumps(event) + "\n")
        result = benchmark.usage_from_log("codex", log)
        self.assertEqual((result["input_uncached"], result["input_cached"], result["output"]), (20, 80, 30))
        log.write_text(json.dumps(event) + "\n" + json.dumps(event))
        self.assertEqual(benchmark.usage_from_log("codex", log)["status"], "ambiguous-or-incomplete")
        log.write_text("truncated {")
        self.assertIsNone(benchmark.usage_from_log("codex", log)["output"])
        log.write_text("null")
        self.assertIsNone(benchmark.usage_from_log("codex", log)["output"])

    def test_claude_cache_write_read_and_uncached_are_separate(self):
        log = self.root / "usage.log"
        benchmark.write(log, {"usage": {"input_tokens": 10, "cache_read_input_tokens": 20,
                                        "cache_creation_input_tokens": 30, "output_tokens": 40}, "total_cost_usd": 0.1})
        result = benchmark.usage_from_log("claude", log)
        self.assertEqual(result["input_total"], 60)
        self.assertEqual(result["input_cache_write"], 30)
        self.assertEqual(result["provider_cost_usd_estimate_not_subscription_bill"], 0.1)


class ScoringTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="rb-score-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        benchmark.write(self.root / "samples.json", [
            {"sample_id": "s1", "case": "case-a", "role": "numerical_auditor", "status": "complete"},
            {"sample_id": "s2", "case": "case-a", "role": "numerical_auditor", "status": "failed"}])
        benchmark.write(self.root / "s1.json", {"findings": [{"id": f"f{i}"} for i in range(4)]})
        benchmark.write(self.root / "key.json", {
            "s1": {"job": {"profile": "sol", "repeat": 1}, "result": {}},
            "s2": {"job": {"profile": "opus", "repeat": 1}, "result": {}}})
        benchmark.write(self.root / "reference.json", {"issues": [
            {"case": "case-a", "issue_key": "known", "roles": ["numerical_auditor"], "weight": 3,
             "status": "confirmed", "source": "synthetic source p1"},
            {"case": "case-a", "issue_key": "missed", "roles": ["numerical_auditor"], "weight": 1,
             "status": "confirmed", "source": "synthetic source p2"},
            {"case": "case-a", "issue_key": "not-ground-truth", "status": "provisional"}]})
        self.rows = [{"sample_id": "s1", "finding_id": f"f{i}", "verdict": verdict, "issue_key": issue,
                      "evidence_correct": "true", "actionability": "2", "source_check_notes": "Synthetic checked location p1"}
                     for i, (verdict, issue) in enumerate([
                         ("confirmed", "known"), ("confirmed", "known"), ("false_positive", "wrong"), ("unresolved", "uncertain")])]
        self.write_ratings()

    def write_ratings(self):
        with (self.root / "ratings.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.rows[0].keys())
            writer.writeheader()
            writer.writerows(self.rows)

    def score(self):
        return scoring.score(self.root, self.root / "reference.json", self.root / "key.json")

    def test_deduplication_precision_bounds_recall_and_failures(self):
        result = self.score()
        cell = result["cells"][0]
        self.assertEqual(cell["confirmed_unique"], 1)
        self.assertEqual(cell["precision_resolved"], 0.5)
        self.assertAlmostEqual(cell["precision_lower_bound"], 1 / 3)
        self.assertEqual(cell["known_issue_recall"], 0.5)
        self.assertEqual(cell["weighted_known_issue_recall"], 0.75)
        self.assertEqual(result["profiles"]["opus"]["completion_rate_attempted"], 0)
        self.assertEqual(result["profiles"]["sol"]["matched_complete_cells"], 0)
        self.assertEqual(result["unconfirmed_reference_issues_excluded"], 1)

    def test_incomplete_adjudication_does_not_generate_scores(self):
        self.rows[0]["verdict"] = ""
        self.write_ratings()
        with self.assertRaisesRegex(ValueError, "Finish source checking"):
            self.score()

    def test_missing_rating_is_rejected(self):
        self.rows.pop()
        self.write_ratings()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.score()

    def test_matched_cells_include_empty_reviews_without_inventing_perfect_precision(self):
        samples = benchmark.read(self.root / "samples.json")
        samples[1]["status"] = "complete"
        benchmark.write(self.root / "samples.json", samples)
        benchmark.write(self.root / "s2.json", {"findings": []})
        result = self.score()
        sol, opus = result["profiles"]["sol"], result["profiles"]["opus"]
        self.assertEqual(sol["matched_complete_cells"], 1)
        self.assertEqual(sol["precision_resolved_macro"]["mean"], 0.5)
        self.assertEqual(opus["known_issue_recall_macro"]["mean"], 0)
        self.assertIsNone(opus["precision_resolved_macro"]["mean"])
        self.assertEqual(opus["precision_resolved_macro"]["defined_cells"], 0)

    def test_changing_frozen_reference_ledger_is_rejected(self):
        benchmark.write(self.root / "packet.json", {
            "reference_sha256": benchmark.digest(self.root / "reference.json")})
        self.score()
        benchmark.write(self.root / "reference.json", {"issues": []})
        with self.assertRaisesRegex(ValueError, "differs from the frozen"):
            self.score()

    def test_conflicting_verdicts_for_duplicate_issue_are_rejected(self):
        self.rows[1]["verdict"] = "false_positive"
        self.write_ratings()
        with self.assertRaisesRegex(ValueError, "Conflicting verdicts"):
            self.score()

    def test_novel_valid_issues_count_for_precision_without_inventing_recall(self):
        self.rows[0]["issue_key"] = "novel"
        self.rows[1]["issue_key"] = "novel"
        self.write_ratings()
        cell = self.score()["cells"][0]
        self.assertEqual(cell["confirmed_unique"], 1)
        self.assertEqual(cell["known_issue_recall"], 0)


if __name__ == "__main__":
    unittest.main()
