"""Optional launcher regressions; all Codex calls are mocked, no quota is used."""
from contextlib import chdir
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import fitz

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))
from build_cli_package import cli_payload
from economics_paper_reviewer import cli
from review_paper import codex_exec_command, codex_project_defaults
from backend_settings import SETTINGS_FILE, remember_backend


def fake_codex_environment(folder: Path, python: str = sys.executable) -> dict[str, str]:
    bin_dir = folder / "mock bin"
    bin_dir.mkdir(parents=True)
    script = bin_dir / "mock_codex.py"
    shutil.copyfile(REPO / "tests/mock_codex.py", script)
    if os.name == "nt":
        (bin_dir / "codex.cmd").write_text(f'@echo off\n"{python}" "{script}" %*\n', encoding="utf-8")
    else:
        command = bin_dir / "codex"
        command.write_text(f"#!/bin/sh\nexec {shlex.quote(python)} {shlex.quote(str(script))} \"$@\"\n")
        command.chmod(0o755)
    # A backend-selection regression must never reach an installed real Claude.
    # On Windows an invalid native-executable stub fails before authentication;
    # on POSIX the stub exits immediately. Neither can make a model request.
    blocked_claude = bin_dir / ("claude.exe" if os.name == "nt" else "claude")
    blocked_claude.write_text("Real Claude forbidden in offline test\n" if os.name == "nt"
                              else "#!/bin/sh\nexit 99\n")
    blocked_claude.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["REVIEWER_TEST_CALLS"] = str(folder / "mock calls")
    # If the double fails to resolve, abort the test instead of contacting real Codex.
    assert Path(shutil.which("codex.cmd" if os.name == "nt" else "codex", path=env["PATH"])).parent == bin_dir
    assert Path(shutil.which(blocked_claude.name, path=env["PATH"])) == blocked_claude
    return env


def synthetic_pdf(path: Path) -> None:
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((60, 65), "Synthetic economics paper for offline launcher validation", fontsize=14)
        page.insert_textbox(fitz.Rect(60, 100, 530, 700),
                            "Abstract\nThis is a synthetic test fixture, not a real paper.\n"
                            + "A reported value is -1.25 percent (N = 40). No causal claims are made.\n" * 12,
                            fontsize=11)
        doc.save(path)


def exercise_pipeline(command: list[str], folder: Path, env: dict[str, str], *, backend: str = "codex") -> dict:
    """Also usable against a locally installed wheel or uvx checkout invocation."""
    caller = folder / "unrelated directory with spaces"
    caller.mkdir(parents=True)
    pdf = caller / "paper with spaces.pdf"
    synthetic_pdf(pdf)
    workspace = caller / "persistent workspace"

    def run(args, *, expected=0, extra=None, choose_backend=False):
        backend_args = ["--backend", backend] if choose_backend else []
        result = subprocess.run(command + backend_args + args, cwd=caller, env={**env, **(extra or {})},
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        if (result.returncode == 0) != (expected == 0):
            raise AssertionError(result.stdout + "\n" + result.stderr)
        if "SENSITIVE_TEST_LOGIN_OUTPUT" in result.stdout + result.stderr:
            raise AssertionError("Login output leaked")
        return result

    run(["--help"])
    assert not workspace.exists()
    run(["--check"], choose_backend=True)
    assert not workspace.exists()
    args = ["--pdf", pdf.name, "--workspace", workspace.name]
    interrupted = run(args, expected=1, extra={"REVIEWER_TEST_STOP": "selection"}, choose_backend=backend != "codex")
    if backend == "claude":
        assert json.loads((workspace / SETTINGS_FILE).read_text())["backend"] == backend
    else:
        assert not (workspace / SETTINGS_FILE).exists()  # Legacy implicit Codex stays unchanged.
    # New-paper preferences must never switch an existing paper's provider.
    other_backend = "codex" if backend == "claude" else "claude"
    remember_backend(workspace, other_backend)
    refused = run(args + ["--backend", other_backend, "--resume-after-preflight"], expected=1)
    assert "Saved run uses --backend" in refused.stdout + refused.stderr
    paper_work = workspace / "work/paper-with-spaces"
    preflight = paper_work / "reviews/parser_quality_auditor.json"
    assert preflight.is_file(), interrupted.stdout + interrupted.stderr
    preflight_bytes, preflight_time = preflight.read_bytes(), preflight.stat().st_mtime_ns
    parsed = paper_work / "parsed/manifest.json"
    parsed_bytes, parsed_time = parsed.read_bytes(), parsed.stat().st_mtime_ns
    copied_pdf = next((workspace / "inputs/papers").rglob("*.pdf"))
    assert copied_pdf.read_bytes() == pdf.read_bytes()
    assert not (workspace / ".git").exists()
    changed_pdf = caller / "different paper.pdf"
    synthetic_pdf(changed_pdf)
    # Add bytes so the saved source hash cannot match, without changing fixtures in place.
    with changed_pdf.open("ab") as handle:
        handle.write(b"\n% changed fixture\n")
    refused = run(["--pdf", changed_pdf.name, "--workspace", workspace.name,
                   "--paper-id", "paper-with-spaces", "--resume-after-preflight"], expected=1)
    assert "source PDF hash differs" in refused.stdout + refused.stderr
    # Resume using the persistent copy: the original need not remain available.
    pdf.rename(pdf.with_suffix(".moved"))
    args = ["--pdf", str(copied_pdf), "--workspace", str(workspace), "--resume-after-preflight"]
    run(args, expected=1, extra={"REVIEWER_TEST_STOP": "editor"})
    assert preflight.read_bytes() == preflight_bytes and preflight.stat().st_mtime_ns == preflight_time
    assert parsed.read_bytes() == parsed_bytes and parsed.stat().st_mtime_ns == parsed_time
    assert len(list((paper_work / "reviews").glob("*.json"))) == 20
    review_hashes = {p.name: cli.sha256(p) for p in (paper_work / "reviews").glob("*.json")}
    run(["--workspace", str(workspace), "--refresh-editor", "--paper-id", "paper-with-spaces", "--run-editor"])
    report = workspace / "outputs/paper-with-spaces/report.md"
    assert "MOCK report" in report.read_text(encoding="utf-8")
    assert json.loads((paper_work / "run_manifest.json").read_text())["status"] == "complete"
    assert review_hashes == {p.name: cli.sha256(p) for p in (paper_work / "reviews").glob("*.json")}
    # A new process can still check/use the workspace after completion.
    run(["--workspace", str(workspace), "--paper-id", "paper-with-spaces", "--check"])
    assert json.loads((workspace / SETTINGS_FILE).read_text())["backend"] == other_backend
    calls = [json.loads(path.read_text()) for path in Path(env["REVIEWER_TEST_CALLS"]).glob("*.json")]
    executions = [call for call in calls if ("exec" if backend == "codex" else "--print") in call["args"]]
    assert len(executions) == 24, len(executions)  # preflight, failed selector, selector, 19, failed editor, editor
    default_model = codex_project_defaults(REPO)["model"] if backend == "codex" else "claude-opus-5-5"
    for call in executions:
        assert call["args"][call["args"].index("--model") + 1] == default_model
        if backend == "codex":
            assert "--skip-git-repo-check" in call["args"]
        else:
            assert call["args"][call["args"].index("--permission-mode") + 1] == "dontAsk"
            assert "--strict-mcp-config" in call["args"]
            assert "--dangerously-skip-permissions" not in call["args"]
        assert Path(call["cwd"]) == workspace
        assert not any(flag in call["args"] for flag in (
            "--dangerously-bypass-approvals-and-sandbox", "--full-auto", "--ignore-rules", "--ignore-user-config",
            "--sandbox", "--ask-for-approval", "--add-dir",
        ))
    return {"workspace": str(workspace), "report": str(report), "mock_exec_calls": len(executions),
            "preflight_reused": True, "reviews_reused_for_editor": True}


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="reviewer-uv-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()
        self.runtime = self.folder / "installation/economics_paper_reviewer/runtime"
        for name, data in cli_payload(REPO).items():
            target = self.runtime / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def test_resources_and_dependencies_are_canonical(self):
        names = cli.runtime_files(self.runtime)
        for name in names:
            self.assertEqual((self.runtime / name).read_bytes(), (REPO / name).read_text(encoding="utf-8").encode())
        self.assertNotIn("scripts/work_plugin.py", names)
        self.assertNotIn("scripts/build_work_plugin.py", names)
        self.assertIn(".codex/config.toml", names)
        self.assertIn(".agents/skills/paper-reviewer/SKILL.md", names)

    def test_workspace_runtime_is_never_silently_replaced(self):
        workspace = self.folder / "workspace"
        cli.prepare_workspace(workspace, self.runtime)
        cli.prepare_workspace(workspace, self.runtime)
        path = workspace / "prompts/templates/editor_report.txt"
        path.write_text("local edits")
        with self.assertRaisesRegex(ValueError, "changed or missing"):
            cli.prepare_workspace(workspace, self.runtime)
        self.assertEqual(path.read_text(), "local edits")

    def test_different_package_refuses_existing_workspace(self):
        workspace = self.folder / "workspace"
        cli.prepare_workspace(workspace, self.runtime)
        (workspace / cli.RECEIPT).write_text('{}')
        with self.assertRaisesRegex(ValueError, "original package/version"):
            cli.prepare_workspace(workspace, self.runtime)

    def test_nonempty_unowned_workspace_is_preserved(self):
        with self.assertRaisesRegex(ValueError, "must be empty"):
            cli.prepare_workspace(self.folder, self.runtime)

    def test_cache_and_install_locations_are_rejected(self):
        custom_cache = self.folder / "custom cache"
        custom_cache.mkdir()
        (custom_cache / "CACHEDIR.TAG").write_text("Signature: 8a477f597d28d172789f06886806bc55\n")
        with mock.patch.dict(os.environ, {"UV_CACHE_DIR": str(self.folder / "cache")}):
            for location in (self.folder / "cache/review", Path(sys.prefix) / "review",
                             self.runtime / "review", custom_cache / "review"):
                with self.subTest(location=location), self.assertRaisesRegex(ValueError, "outside Python"):
                    cli.prepare_workspace(location.resolve(), self.runtime)
                self.assertFalse(location.exists())

    def test_codex_missing_and_unauthenticated_diagnostics(self):
        with mock.patch.object(cli.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "No API key is required"):
                cli.check_codex(self.folder)
        with mock.patch.object(cli.shutil, "which", return_value="codex"), mock.patch.object(
            cli.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)
        ) as run:
            with self.assertRaisesRegex(ValueError, "codex login"):
                cli.check_codex(self.folder)
            self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
            self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_legacy_codex_command_is_unchanged_without_launcher(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("review_paper.codex_command", return_value="codex"):
            self.assertEqual(codex_exec_command(), ["codex", "exec"])

    def test_codex_double_blocks_real_claude(self):
        env = fake_codex_environment(self.folder)
        result = subprocess.run([sys.executable, str(REPO / "scripts/claude_backend.py"), "--check"],
                                cwd=self.folder, env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(Path(env["REVIEWER_TEST_CALLS"]).exists())

    def test_default_workspace_and_caller_relative_config(self):
        pdf = self.folder / "paper with spaces.pdf"
        synthetic_pdf(pdf)
        config = self.folder / "custom reviewers.json"
        config.write_bytes((REPO / "config/reviewers.json").read_bytes())
        with mock.patch.object(cli, "bundled_runtime", return_value=self.runtime), mock.patch.object(
            cli, "check_codex"
        ), chdir(self.folder), mock.patch.object(
            cli.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
        ) as run:
            self.assertEqual(cli.main(["--pdf", pdf.name, "--reviewers-config=" + config.name,
                                       "--model", "gpt-6-luna", "--reasoning-effort", "high"]), 0)
        workspace = self.folder / "reviewer-workspace"
        command = run.call_args.args[0]
        self.assertEqual(run.call_args.kwargs["cwd"], workspace)
        self.assertEqual(command.count("--model"), 1)
        self.assertIn("gpt-6-luna", command)
        self.assertIn("--reasoning-effort", command)
        self.assertEqual(command[command.index("--backend") + 1], "codex")
        self.assertEqual(run.call_args.kwargs["env"]["ECONOMICS_REVIEWER_PRESERVE_BACKEND_PREFERENCE"], "1")
        saved_config = Path(command[command.index("--reviewers-config") + 1])
        self.assertTrue(saved_config.is_relative_to(workspace))
        self.assertEqual(saved_config.read_bytes(), config.read_bytes())

    def test_editor_refresh_preserves_default_reasoning_without_project_trust(self):
        with mock.patch.object(cli, "bundled_runtime", return_value=self.runtime), mock.patch.object(
            cli, "check_codex"
        ), chdir(self.folder), mock.patch.object(
            cli.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
        ) as run:
            self.assertEqual(cli.main(["--refresh-editor", "--paper-id", "paper", "--run-editor"]), 0)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--reasoning-effort") + 1], "xhigh")

    def test_remembered_launcher_check_is_read_only_and_never_falls_back(self):
        workspace = self.folder / "reviewer-workspace"
        cli.prepare_workspace(workspace, self.runtime)
        remember_backend(workspace, "claude")
        before = (workspace / SETTINGS_FILE).read_bytes()
        with mock.patch.object(cli, "bundled_runtime", return_value=self.runtime), chdir(self.folder), \
                mock.patch.object(cli, "check_backend", side_effect=ValueError("Claude login missing")) as check:
            self.assertEqual(cli.main(["--check"]), 1)
        check.assert_called_once_with("claude", self.runtime)
        with mock.patch.object(cli, "bundled_runtime", return_value=self.runtime), chdir(self.folder), \
                mock.patch.object(cli, "check_backend") as check:
            self.assertEqual(cli.main(["--check", "--backend", "codex"]), 0)
        check.assert_called_once_with("codex", self.runtime)
        self.assertEqual((workspace / SETTINGS_FILE).read_bytes(), before)

    def test_launcher_legacy_run_wins_over_workspace_preference_before_authentication(self):
        workspace = self.folder / "reviewer-workspace"
        cli.prepare_workspace(workspace, self.runtime)
        remember_backend(workspace, "claude")
        manifest = workspace / "work/legacy/run_manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{}')
        with mock.patch.object(cli, "bundled_runtime", return_value=self.runtime), chdir(self.folder), \
                mock.patch.object(cli, "check_backend") as check:
            self.assertEqual(cli.main(["--check", "--paper-id", "legacy"]), 0)
            check.assert_called_once_with("codex", self.runtime)
            check.reset_mock()
            self.assertEqual(cli.main(["--check", "--paper-id", "legacy", "--backend", "claude"]), 1)
            check.assert_not_called()

    def test_new_paper_uses_remembered_backend_and_pins_it_before_child_launch(self):
        workspace = self.folder / "reviewer-workspace"
        cli.prepare_workspace(workspace, self.runtime)
        remember_backend(workspace, "claude")
        pdf = self.folder / "new paper.pdf"
        synthetic_pdf(pdf)

        def check(backend, runtime):
            self.assertEqual(backend, "claude")
            # Simulate another paper changing the default after this check.
            remember_backend(workspace, "codex")

        with mock.patch.object(cli, "bundled_runtime", return_value=self.runtime), chdir(self.folder), \
                mock.patch.object(cli, "check_backend", side_effect=check), \
                mock.patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(cli.main(["--pdf", pdf.name]), 0)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--backend") + 1], "claude")
        self.assertNotIn("--model", command)  # No Codex model injected into Claude.
        self.assertEqual(run.call_args.kwargs["env"]["ECONOMICS_REVIEWER_PRESERVE_BACKEND_PREFERENCE"], "1")
        self.assertEqual(json.loads((workspace / SETTINGS_FILE).read_text())["backend"], "codex")

    def test_pipeline_resume_and_persistence_with_only_codex_mocked(self):
        package = self.runtime.parent
        for name in ("__init__.py", "cli.py"):
            shutil.copyfile(REPO / "src/economics_paper_reviewer" / name, package / name)
        env = fake_codex_environment(self.folder)
        env["PYTHONPATH"] = str(package.parent)
        command = [sys.executable, "-c", "from economics_paper_reviewer.cli import main; raise SystemExit(main())"]
        exercise_pipeline(command, self.folder, env)


if __name__ == "__main__":
    unittest.main()
