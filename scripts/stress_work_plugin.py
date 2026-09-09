"""Opt-in, offline stress tests of the packaged Work coordinator.

Synthetic PDFs and scripted model responses only. Does not modify the plugin,
install packages, make network calls, or execute a model. Nonzero exit means a
stress assertion failed; expected fail-closed responses count as passes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "plugins/economics-paper-reviewer/skills/review-paper/runtime"
sys.path.insert(0, str(SOURCE / "scripts"))
sys.path.insert(1, str(REPO))

import fitz  # noqa: E402
import work_plugin as runtime  # noqa: E402
from tests.test_work_plugin import empty_review, finding, selection, synthetic_report  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class StressRun:
    def __init__(self, output: Path, pages: int, only=None):
        require(not output.exists(), "Choose a new output directory; prior reports are preserved.")
        output.mkdir(parents=True)
        self.output, self.pages = output.resolve(), pages
        self.temporary = tempfile.TemporaryDirectory(prefix="reviewer-stress-")
        self.base = Path(self.temporary.name)
        self.counter = 0
        self.results = []
        self.only = set(only or [])
        self.fixtures = {}
        self.source_manifest = runtime.read_json(SOURCE / "bundle_manifest.json")
        require(Path(runtime.__file__).resolve().is_relative_to(SOURCE), "Test must exercise the bundled runtime.")
        pdf = self.base / "small synthetic paper.pdf"
        self.make_pdf(pdf, 1)
        self.template = self.base / "template"
        runtime.ReviewRun.start(self.template, SOURCE, pdf, "full", "available")

    def make_pdf(self, path, pages, mixed=False):
        with fitz.open() as document:
            for index in range(pages):
                page = document.new_page()
                label = f"Appendix A.{index + 1}" if index >= pages // 2 else f"Section {index + 1}"
                text = (f"Synthetic Economics Stress Paper\n{label}\n"
                        "The estimate is -2.5 percent (standard error 0.75).\n"
                        "The price is 12.50 and the interval is (-3.0, -2.0).\n"
                        "Table 1. Synthetic outcomes\nOutcome       Estimate       Standard error\n"
                        "Employment    -2.5           0.75\nHours          1.25          0.50\n"
                        "This is test evidence, not a real academic result.\n")
                page.insert_text((72, 72), text, fontsize=10)
                page.insert_text((290, 805), str(index + 1), fontsize=10)
                if mixed and index % 40 == 39:
                    pixmap = page.get_pixmap()
                    rectangle = page.rect
                    document.delete_page(index)
                    page = document.new_page(width=rectangle.width, height=rectangle.height)
                    page.insert_image(page.rect, pixmap=pixmap)
                elif mixed and index % 30 == 29:
                    page.set_rotation(90)
            document.save(path)

    def clone(self, label="case"):
        self.counter += 1
        root = self.base / f"{self.counter:03d}-{label}"
        shutil.copytree(self.template, root)
        return runtime.ReviewRun(root, SOURCE)

    def reload(self, run):
        return runtime.ReviewRun(run.root, SOURCE)

    def record(self, name, function, classification="supported"):
        if self.only and name not in self.only:
            return
        started = time.perf_counter()
        try:
            details = function() or {}
            result = {"name": name, "status": "pass", "details": details}
        except Exception as exc:
            result = {"name": name, "status": "fail", "error_type": type(exc).__name__, "error": str(exc)}
        result.update({"classification": classification, "seconds": round(time.perf_counter() - started, 3)})
        self.results.append(result)
        self.persist(intermediate=True)
        print(json.dumps(result, ensure_ascii=True), flush=True)

    def persist(self, intermediate=False):
        data = {"tested_runtime": str(Path(runtime.__file__).resolve()),
                "runtime_manifest_sha256": runtime.digest(SOURCE / "bundle_manifest.json"),
                "python": sys.version.split()[0], "synthetic_only": True,
                "fixtures": self.fixtures, "results": self.results,
                "passed": sum(r["status"] == "pass" for r in self.results),
                "failed": sum(r["status"] == "fail" for r in self.results)}
        destination = (self.output / "progress" / f"result-{len(self.results):03d}.json"
                       if intermediate else self.output / "results.json")
        runtime.write_json(destination, data)

    def submit(self, run, job, payload):
        candidate = Path(job["candidate_file"])
        if isinstance(payload, bytes):
            candidate.write_bytes(payload)
        else:
            runtime.write_json(candidate, payload)
        return run.accept(job["task"])

    def finish_router(self, run):
        job = run.next_tasks(3)["jobs"][0]
        require(self.submit(run, job, empty_review(run, job["task"]))["status"] == "accepted", "Preflight failed")
        job = run.next_tasks(3)["jobs"][0]
        require(self.submit(run, job, selection(run))["status"] == "accepted", "Routing failed")

    def candidate_case(self, payload_fn):
        run = self.clone("candidate")
        job = run.next_tasks()["jobs"][0]
        payload = payload_fn(run, job)
        response = self.submit(run, job, payload)
        require(response["status"] in {"retry", "exhausted"}, f"Malformed candidate was accepted: {response['status']}")
        require(self.reload(run).task(job["task"])["status"] != "inflight", "Invalid output left a stuck inflight attempt")
        return {"response_status": response["status"], "errors": response.get("errors", [])[:2]}

    def cli_candidate_case(self, payload_fn):
        run = self.clone("cli-candidate")
        job = run.next_tasks()["jobs"][0]
        Path(job["candidate_file"]).write_bytes(payload_fn(run, job))
        response = subprocess.run([sys.executable, str(SOURCE / "scripts/work_plugin.py"), "accept",
                                   "--workspace", str(run.root), "--task", job["task"]],
                                  capture_output=True, text=True, timeout=45)
        try:
            output = json.loads(response.stdout)
        except json.JSONDecodeError:
            output = {"stdout": response.stdout[:200]}
        state = self.reload(run).task(job["task"])["status"]
        require(state != "inflight" and "Traceback" not in response.stderr,
                f"Candidate stranded attempt: state={state}; exit={response.returncode}; "
                f"output={output}; traceback={'Traceback' in response.stderr}")
        return {"state": state, "exit": response.returncode}

    def corrupt_state(self, mutation):
        run = self.clone("state")
        changed = mutation(copy.deepcopy(run.state))
        runtime.write_json(run.state_path, changed)
        result = subprocess.run([sys.executable, str(SOURCE / "scripts/work_plugin.py"), "status",
                                 "--workspace", str(run.root)], capture_output=True, text=True, timeout=45)
        require(result.returncode != 0, "Corrupt checkpoint reported a usable status")
        require("Traceback" not in result.stderr, "Corrupt checkpoint produced a raw traceback instead of a friendly error")
        data = json.loads(result.stdout)
        require(data.get("status") == "error", f"Expected structured error: {data}")
        return {"code": data.get("code")}

    def injected_early_task(self):
        run = self.clone("early-task")
        run.add_task("grammar_auditor", "review")
        run.save()
        try:
            jobs = self.reload(run).next_tasks(3).get("jobs", [])
        except runtime.WorkError as exc:
            return {"rejected": exc.code}
        require(all(job["kind"] == "preflight" for job in jobs),
                "An extra configured reviewer in checkpoint state dispatched before parser preflight completed")

    def saved_response(self):
        run = self.clone("crash-write")
        job = run.next_tasks()["jobs"][0]
        runtime.write_json(Path(job["candidate_file"]), empty_review(run, job["task"]))
        with mock.patch.object(run, "save", side_effect=OSError("simulated write interruption")):
            try:
                run.accept(job["task"])
            except OSError:
                pass
        run = self.reload(run)
        require(run.task(job["task"])["status"] == "inflight", "Pre-interruption state was not retained")
        require(run.accept(job["task"])["status"] == "accepted", "Saved response could not be recovered")
        require(len(run.task(job["task"])["attempts"]) == 1, "Recovery consumed extra model work")

    def random_workflow(self, mode, seed):
        rng = random.Random(seed)
        run = self.clone(f"{mode}-seed-{seed}")
        run.state["mode"] = mode
        run.state["profile"] = runtime.MODES[mode]
        for task in run.state["tasks"].values():
            task["max_attempts"] = runtime.MODES[mode]["max_attempts"]
        run.save()
        inflight, reserved, injected = {}, set(), set()
        actions = 0
        while actions < 150:
            actions += 1
            run = self.reload(run)
            if run.state["paused"]:
                run.resume()
            dispatch = run.next_tasks(rng.choice([1, 2, 3, 100]))
            if dispatch["status"] == "complete":
                require(not inflight, "Completed despite pending children")
                break
            for job in dispatch.get("jobs", []):
                require(job["candidate_file"] not in reserved, "Duplicate candidate dispatch")
                reserved.add(job["candidate_file"])
                inflight[job["task"]] = job
            require(len(inflight) <= runtime.MODES[mode]["max_parallel"], "Concurrency cap was exceeded")
            require(inflight, "No progress and no running child")
            name = rng.choice(list(inflight))
            job = inflight.pop(name)
            if job["kind"] == "review" and len(injected) < 2 and name not in injected:
                injected.add(name)
                failure = "quota" if len(injected) == 1 else "transient"
                run.fail(name, failure)
                if failure == "quota":
                    require(run.next_tasks(3)["status"] == "paused", "Quota did not pause")
                continue
            if job["kind"] == "selector":
                response = selection(run)
            elif job["kind"] == "editor":
                response = synthetic_report(runtime.read_json(run.paths.bundle_path), lite=mode == "lite").encode("utf-8")
            else:
                response = empty_review(run, name)
            accepted = self.submit(run, job, response)
            require(accepted["status"] == "accepted", f"Valid simulated response failed: {accepted}")
            if actions in {7, 16}:
                archive = self.base / f"{run.root.name}-action-{actions}.zip"
                run.checkpoint(archive)
                restored = self.base / f"{run.root.name}-restored-{actions}"
                old_root = run.root
                runtime.restore(archive, restored, SOURCE)
                run = runtime.ReviewRun(restored, SOURCE)
                for remaining in inflight.values():
                    for key in ["candidate_file", "prompt_file", "schema_file"]:
                        if remaining.get(key):
                            remaining[key] = str(restored / Path(remaining[key]).relative_to(old_root))
        require(run.state["phase"] == "complete", "Randomized run did not finish")
        require(len(run.state["active_reviewers"]) == 19, "A reviewer was lost")
        require(all(task["status"] == "accepted" for task in run.state["tasks"].values()), "Missing accepted stage")
        return {"mode": mode, "seed": seed, "actions": actions, "attempts": len(reserved),
                "auditors": len(run.state["active_reviewers"])}

    def archive_case(self, members):
        self.counter += 1
        archive = self.base / f"bad-archive-{self.counter}.zip"
        target = self.base / f"bad-restored-{self.counter}"
        with zipfile.ZipFile(archive, "x") as output:
            for name, data, file_type in members:
                info = zipfile.ZipInfo(name)
                info.external_attr = file_type << 16
                output.writestr(info, data)
        try:
            runtime.restore(archive, target, SOURCE)
        except (runtime.WorkError, OSError, ValueError, KeyError):
            require(not target.exists(), "Bad archive left a claimed restored workspace")
            return {"rejected": True}
        raise AssertionError("Unsafe archive was restored")

    def large_pdf(self):
        pdf = self.base / "large mixed-layout paper.pdf"
        self.make_pdf(pdf, self.pages, mixed=True)
        initial_hash = runtime.digest(pdf)
        started = time.perf_counter()
        run = runtime.ReviewRun.start(self.base / "large-run", SOURCE, pdf, "full", "available")
        elapsed = time.perf_counter() - started
        manifest = runtime.read_json(run.paths.parsed_dir / "manifest.json")
        require(manifest["summary"]["page_count"] == self.pages, "Page count lost")
        require(len(list((run.paths.parsed_dir / "page_images").glob("*.png"))) == self.pages, "Page image missing")
        require(runtime.digest(pdf) == initial_hash, "Original source PDF changed")
        require(not manifest["settings"]["ocr_used"], "Unexpected OCR")
        for page_number in [1, min(2, self.pages), self.pages // 2 + 1]:
            content = (run.paths.parsed_dir / "pages" / f"page_{page_number:03d}.md").read_text(encoding="utf-8")
            require("-2.5" in content and "12.50" in content, "Signs/decimals not preserved")
        native_empty = [i + 1 for i in range(self.pages) if i % 40 == 39]
        require(set(native_empty).issubset(manifest["summary"]["ocr_recommended_pages"]), "Image-only page not flagged")
        samples = []
        for _ in range(3):
            before = time.perf_counter()
            run.status()
            samples.append(time.perf_counter() - before)
        artifact_bytes = sum(p.stat().st_size for p in run.paths.parsed_dir.rglob("*") if p.is_file())
        archive = self.base / "large-checkpoint.zip"
        run.checkpoint(archive)
        runtime.restore(archive, self.base / "large-restored", SOURCE)
        self.fixtures["large_pdf"] = {"pages": self.pages, "preprocessing_seconds": round(elapsed, 3),
                                      "parsed_bytes": artifact_bytes, "checkpoint_bytes": archive.stat().st_size,
                                      "status_seconds": [round(n, 3) for n in samples],
                                      "ocr_recommended_pages": manifest["summary"]["ocr_recommended_pages"]}
        return self.fixtures["large_pdf"]

    def large_evidence(self):
        run = self.clone("large-evidence")
        self.finish_router(run)
        large_marker = "synthetic-evidence-begin:" + "E" * 1_100_000 + ":synthetic-evidence-end"
        while True:
            try:
                jobs = run.next_tasks(3)["jobs"]
            except runtime.WorkError as exc:
                require(exc.code == "editor_input_too_large", f"Unexpected large-input failure: {exc.code}")
                break
            for job in jobs:
                require(job["kind"] == "review", "Oversized input was sent to editor")
                data = empty_review(run, job["task"])
                if job["task"] == "claim_evidence_auditor":
                    reviewer = next(r for r in run.reviewers if r.name == job["task"])
                    data["findings"] = [finding(run, reviewer.id_prefix)]
                    data["findings"][0]["evidence_summary"] = large_marker
                require(self.submit(run, job, data)["status"] == "accepted", "Large source finding lost")
        require(run.status()["status"] == "paused", "Oversized input did not pause")
        require(not run.paths.report_path.exists(), "Oversized input produced a misleading final report")
        archive = self.base / "large-evidence-checkpoint.zip"
        run.checkpoint(archive)
        target = self.base / "large-evidence-restored"
        runtime.restore(archive, target, SOURCE)
        restored = runtime.ReviewRun(target, SOURCE)
        reviewer = next(r for r in run.reviewers if r.name == "claim_evidence_auditor")
        data = runtime.read_json(restored.paths.reviews_dir / reviewer.output)
        require(data["findings"][0]["evidence_summary"] == large_marker, "Checkpoint truncated evidence")
        return {"evidence_chars": len(large_marker), "result": "paused without truncation"}

    def stale_parent(self):
        run = self.clone("duplicate-parent")
        other = self.reload(run)
        first = run.next_tasks()["jobs"]
        second = other.next_tasks()["jobs"]
        overlap = {j["candidate_file"] for j in first} & {j["candidate_file"] for j in second}
        return {"duplicate_dispatch": bool(overlap),
                "note": "Multiple coordinator writers are explicitly outside the documented single-parent contract."}

    def execute(self):
        # Malformed JSON that is likely to come from a failed or truncated model response.
        payloads = {
            "truncated_json": lambda r, j: b'{"reviewer":',
            "json_null": lambda r, j: b"null",
            "json_array": lambda r, j: b"[]",
            "invalid_utf8": lambda r, j: b"\xff\xfe\x80",
            "fenced_json": lambda r, j: b"```json\n{}\n```",
            "duplicate_findings_key": lambda r, j: json.dumps(empty_review(r, j["task"])).replace(
                '"findings": []', '"findings": ' + json.dumps([finding(r, "PARSER", issue_type="parser_artifact")])
                + ', "findings": []').encode(),
            "integer_conversion_limit": lambda r, j: b'{"findings":' + b"9" * 5000 + b"}",
            "deeply_nested_json": lambda r, j: b"[" * 1500 + b"0" + b"]" * 1500,
            "unpaired_unicode_surrogate": lambda r, j: json.dumps({**empty_review(r, j["task"]),
                                                                   "summary": "\ud800"}).encode(),
        }
        for name, function in payloads.items():
            method = self.cli_candidate_case if name in {"integer_conversion_limit", "deeply_nested_json", "unpaired_unicode_surrogate"} else self.candidate_case
            self.record("candidate/" + name, lambda function=function, method=method: method(function))
        mutations = {
            "top_level_null": lambda s: None,
            "top_level_array": lambda s: [],
            "tasks_null": lambda s: {**s, "tasks": None},
            "task_not_object": lambda s: {**s, "tasks": {"parser_quality_auditor": []}},
            "empty_attempts_inflight": lambda s: {**s, "tasks": {"parser_quality_auditor": {
                **s["tasks"]["parser_quality_auditor"], "status": "inflight"}}},
            "premature_complete": lambda s: {**s, "phase": "complete"},
            "invalid_mode": lambda s: {**s, "mode": "quick"},
            "invalid_task_name": lambda s: {**s, "tasks": {"../../elsewhere": s["tasks"]["parser_quality_auditor"]}},
        }
        for name, mutation in mutations.items():
            self.record("checkpoint/" + name, lambda mutation=mutation: self.corrupt_state(mutation))
        self.record("checkpoint/early_reviewer_injection", self.injected_early_task)
        self.record("recovery/interrupted_accept_write", self.saved_response)
        for mode in runtime.MODES:
            for seed in [7, 29, 83]:
                self.record(f"workflow/{mode}/seed-{seed}", lambda mode=mode, seed=seed: self.random_workflow(mode, seed))
        archive_cases = {
            "parent_traversal": [("../outside.txt", b"fixture", 0o100644)],
            "absolute_path": [("/outside.txt", b"fixture", 0o100644)],
            "windows_traversal": [("..\\outside.txt", b"fixture", 0o100644)],
            "case_collision": [("A.txt", b"a", 0o100644), ("a.txt", b"b", 0o100644)],
            "symlink": [("linked", b"../outside", 0o120777)],
            "file_directory_conflict": [("a", b"a", 0o100644), ("a/b", b"b", 0o100644)],
            "alternate_stream": [("work_state.json:stream", b"fixture", 0o100644)],
        }
        for name, members in archive_cases.items():
            self.record("archive/" + name, lambda members=members: self.archive_case(members))
        self.record("load/large_mixed_layout_pdf", self.large_pdf)
        self.record("load/oversized_lossless_editor_input", self.large_evidence)
        self.record("boundary/two_parent_writers", self.stale_parent, classification="outside_contract")
        require(runtime.read_json(SOURCE / "bundle_manifest.json") == self.source_manifest, "Plugin changed during stress test")
        require(self.results, "No matching stress cases selected")
        self.persist()
        report = ["# Work plugin stress-test results", "", f"Python: {sys.version.split()[0]}",
                  "Synthetic PDFs and simulated reviewer/editor outputs; no model calls or hosted Work test.", "",
                  "| Scenario | Result | Seconds |", "| --- | --- | --- |"]
        report += [f"| {r['name']} | {r['status']} | {r['seconds']} |" for r in self.results]
        report += ["", "## Failures", ""]
        for result in self.results:
            if result["status"] == "fail":
                report += [f"### {result['name']}", "", f"{result['error_type']}: {result['error']}", ""]
        report += ["## Scale measurements", "", "```json", json.dumps(self.fixtures, indent=2), "```", "",
                   "Multiple parent writers are outside the documented contract; their result is diagnostic, not a supported-workflow pass."]
        (self.output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        self.temporary.cleanup()
        return 1 if any(r["status"] == "fail" for r in self.results) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pages", type=int, default=120)
    parser.add_argument("--only", action="append", help="Run only this exact scenario name; repeat to select multiple cases.")
    args = parser.parse_args()
    if not 2 <= args.pages <= 150:
        parser.error("--pages must be between 2 and 150 for this bounded local stress test")
    return StressRun(args.output, args.pages, only=args.only).execute()


if __name__ == "__main__":
    raise SystemExit(main())
