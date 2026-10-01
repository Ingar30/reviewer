"""Selective recovery uses offline process doubles, never real model calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_uv_launcher import REPO, cli, cli_payload, fake_codex_environment, synthetic_pdf
from tests.test_claude_backend import fake_claude_environment
from resume_review import run_lease
from review_paper import run_command
from backend_settings import SETTINGS_FILE, remember_backend


def exercise_selective_resume(folder, backend, command=None, runtime=None):
    env = fake_claude_environment(folder) if backend == "claude" else fake_codex_environment(folder)
    caller = folder / "unrelated with spaces"
    caller.mkdir()
    pdf = caller / "paper with spaces.pdf"
    synthetic_pdf(pdf)
    workspace = caller / "persistent workspace"
    if runtime is not None:
        cli.prepare_workspace(workspace, runtime)
        command = [sys.executable, str(workspace / "scripts/review_paper.py")]
        args = ["--pdf", str(pdf), "--backend", backend]
        cwd = workspace
        env["ECONOMICS_REVIEWER_NON_GIT"] = "1"
    else:
        args = ["--pdf", pdf.name, "--backend", backend, "--workspace", str(workspace)]
        cwd = caller

    def run(extra=(), stop=None, success=True):
        result = subprocess.run([*command, *args, *extra], cwd=cwd,
                                env={**env, **({"REVIEWER_TEST_STOP": stop} if stop else {})},
                                text=True, encoding="utf-8", capture_output=True, timeout=180)
        if (result.returncode == 0) != success:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout + result.stderr

    def executions():
        return [json.loads(p.read_text()) for p in Path(env["REVIEWER_TEST_CALLS"]).glob("*.json")
                if ("--print" if backend == "claude" else "exec") in json.loads(p.read_text())["args"]]

    config = json.loads((REPO / "config/reviewers.json").read_text())["reviewers"]
    first = next(r["name"] for r in config if r.get("stage", "review") == "review" and r.get("enabled", True))
    run(stop=first, success=False)
    assert json.loads((workspace / SETTINGS_FILE).read_text())["backend"] == backend
    # Remember the initial explicit choice, then recover without a backend flag.
    # Even if another paper changed the workspace preference, this run stays put.
    index = args.index("--backend")
    del args[index:index + 2]
    other_backend = "codex" if backend == "claude" else "claude"
    remember_backend(workspace, other_backend)
    work = workspace / "work/paper-with-spaces"
    checkpoint = work / "resume_checkpoint.json"
    data = json.loads(checkpoint.read_text())
    assert len(data["accepted"]) == 3, data["accepted"]
    saved = {p: p.read_bytes() for p in (work / "reviews").glob("*.json")}
    logs = {p: p.read_bytes() for p in (work / "logs").glob("*.log")}
    count = len(executions())
    # Changes fail closed, before a billable model invocation or log overwrite.
    assert "differs" in run(["--resume-incomplete", "--model", "different-model"], success=False)
    for path in (pdf, workspace / "prompts/templates/editor_report.txt", next(iter(saved))):
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"\n")
            run(["--resume-incomplete"], success=False)
        finally:
            path.write_bytes(original)
    assert len(executions()) == count
    # Retain the successful siblings even though another member of the batch failed.
    run(["--resume-incomplete"], stop="editor", success=False)
    assert all(p.read_bytes() == content for p, content in saved.items())
    assert all(p.read_bytes() == content for p, content in logs.items())
    assert len(json.loads(checkpoint.read_text())["accepted"]) == 19
    before_editor = len(executions())
    run(["--resume-incomplete"])
    assert len(executions()) == before_editor + 1
    report = workspace / "outputs/paper-with-spaces/report.md"
    assert "MOCK report" in report.read_text()
    before = len(executions())
    run(["--resume-incomplete"])
    assert len(executions()) == before  # A completed checkpoint costs no call.
    assert all(p.read_bytes() == content for p, content in saved.items())
    assert json.loads((workspace / SETTINGS_FILE).read_text())["backend"] == other_backend
    return {"backend": backend, "model_calls": before, "retained_siblings": 3,
            "workspace": str(workspace), "validation": "mocked only"}


class SelectiveResumeTests(unittest.TestCase):
    def test_both_backends_reuse_completed_stages_without_uv(self):
        for backend in ("codex", "claude"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory(prefix="resume-test-") as temp:
                folder = Path(temp)
                runtime = folder / "installation/runtime"
                for name, data in cli_payload(REPO).items():
                    path = runtime / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                exercise_selective_resume(folder, backend, runtime=runtime)

    def test_lease_released_and_duplicate_process_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            with run_lease(path):
                with self.assertRaisesRegex(RuntimeError, "Another pipeline"):
                    with run_lease(path):
                        self.fail("Duplicate lease accepted")
            with run_lease(path):
                pass

    def test_timeout_keeps_streamed_output(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            result = run_command("timeout", [sys.executable, "-c",
                "import time; print('retained before timeout', flush=True); time.sleep(30)"],
                folder, folder, timeout_seconds=5)
            self.assertEqual(result.returncode, 124)
            self.assertIn("retained before timeout", result.stdout_path.read_text())

    @unittest.skipUnless(os.name == "nt", "Windows process-tree regression")
    def test_timeout_stops_owned_grandchild(self):
        import ctypes
        from ctypes import wintypes
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            child_pid = folder / "child.pid"
            code = ("import subprocess,sys,time; from pathlib import Path; "
                    "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                    "Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(60)")
            result = run_command("tree-timeout", [sys.executable, "-c", code, str(child_pid)],
                                 folder, folder, timeout_seconds=10)
            self.assertEqual(result.returncode, 124)
            self.assertTrue(child_pid.is_file(), "Parent never launched the child fixture")
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x00100000, False, int(child_pid.read_text()))
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 0), 0,
                                     "Owned child is still running after wrapper timeout")
                finally:
                    kernel.CloseHandle(handle)
            else:
                self.assertEqual(ctypes.get_last_error(), 87)  # Process no longer exists.


if __name__ == "__main__":
    unittest.main()
