"""Claude transport tests are offline: no real Claude/Codex request is allowed."""
import json
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from build_cli_package import cli_payload
import claude_backend as backend
from review_paper import agent_exec_command, run_command, start_reviewer, wait_reviewer
from reviewer_config import ReviewerConfig
from tests.test_uv_launcher import exercise_pipeline


def fake_claude_environment(folder: Path) -> dict[str, str]:
    """Swap only executable lookup/launch; exercise the real adapter and pipeline.

    The launch double uses Python (a native .exe on Windows), not cmd.exe: JSON
    argv quoting follows the same native-process path as the required Claude exe.
    A test-only sitecustomize propagates this guard to every child Python process.
    """
    guard = folder / "offline process guard"
    guard.mkdir(parents=True)
    shutil.copyfile(REPO / "tests/mock_claude.py", guard / "mock_claude.py")
    (guard / "sitecustomize.py").write_text('''import os, shutil, subprocess, sys
from pathlib import Path
original_which = shutil.which
original_popen = subprocess.Popen
sentinel = "REVIEWER_OFFLINE_CLAUDE"
def which(command, *args, **kwargs):
    if str(command).lower() in ("claude", "claude.exe", "claude.cmd"):
        return sentinel
    if str(command).lower() in ("codex", "codex.exe", "codex.cmd"):
        raise AssertionError("Codex is forbidden in the Claude test")
    return original_which(command, *args, **kwargs)
class Popen(original_popen):
    def __init__(self, args, *positional, **kwargs):
        if isinstance(args, (list, tuple)):
            if args[0] == sentinel:
                args = [sys.executable, str(Path(__file__).with_name("mock_claude.py")), *args[1:]]
            elif Path(str(args[0])).stem.lower() in ("claude", "codex"):
                raise AssertionError("Real model executable forbidden in offline test")
        super().__init__(args, *positional, **kwargs)
shutil.which = which
subprocess.Popen = Popen
''', encoding="utf-8")
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_")):
            del env[name]
    env["PYTHONPATH"] = str(guard)
    env["REVIEWER_TEST_CALLS"] = str(folder / "mock calls")
    return env


class ClaudeBackendTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="reviewer-claude-")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def test_native_cli_missing_diagnostic(self):
        with mock.patch.object(backend.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "No API key is required"):
                backend.check_claude(self.folder)

    def test_usage_and_auth_errors_are_actionable_without_echoing_provider_text(self):
        path = self.folder / "provider.stdout.log"
        for message, expected in (
            ("You've hit your session limit · resets 1:50pm (Europe/Oslo) SECRET", "usage limit"),
            ("401 OAuth access token invalid SECRET", "claude auth login"),
            ("Maximum turn limit reached SECRET", "unsuccessful call"),
            ("Unexpected provider failure SECRET", "unsuccessful call"),
        ):
            path.write_text(json.dumps({"type": "result", "subtype": "success",
                                        "is_error": True, "result": message}), encoding="utf-8")
            hint = backend.claude_failure_hint(path)
            self.assertIn(expected, hint)
            self.assertIn(str(path), hint)
            self.assertNotIn("SECRET", hint)
        path.write_text("not JSON", encoding="utf-8")
        self.assertIsNone(backend.claude_failure_hint(path))

    def check_status(self, account, *, version="2.1.280", status=0):
        responses = [subprocess.CompletedProcess([], 0, version, ""),
                     subprocess.CompletedProcess([], status, json.dumps(account), "SECRET")]
        with mock.patch.object(backend, "claude_command", return_value="claude"), \
                mock.patch.object(backend.subprocess, "run", side_effect=responses) as run:
            result = backend.check_claude(self.folder)
            self.assertEqual(len(run.call_args_list), 2)
            self.assertEqual(run.call_args_list[1].args[0], ["claude", "auth", "status", "--json"])
            return result

    def test_router_and_editor_nonzero_exit_explain_stdout_quota_error(self):
        envelope = {"type": "result", "subtype": "success", "is_error": True,
                    "result": "You've hit your session limit SECRET"}
        code = "import json, sys; print(json.dumps(" + repr(envelope) + ")); sys.exit(1)"
        for label in ("reviewer-selector", "editor"):
            terminal = io.StringIO()
            with contextlib.redirect_stdout(terminal):
                result = run_command(label, [sys.executable, "-c", code], self.folder, self.folder)
            self.assertEqual(result.returncode, 1)
            for text in (terminal.getvalue(), result.stderr_path.read_text(encoding="utf-8")):
                self.assertIn("usage limit", text)
                self.assertIn(str(result.stdout_path), text)
                self.assertNotIn("SECRET", text)
            self.assertEqual(json.loads(result.stdout_path.read_text()), envelope)

    def test_reviewer_exit_or_error_envelope_preserves_output_and_explains_quota(self):
        reviewer = ReviewerConfig("offline", "prompt.txt", "review.json", "OFF", False,
                                  True, "manuscript", "review", "mandatory")
        (self.folder / reviewer.prompt).write_text("offline prompt", encoding="utf-8")
        output = self.folder / reviewer.output
        output.write_text("previous accepted review", encoding="utf-8")
        envelope = {"type": "result", "subtype": "success", "is_error": True,
                    "result": "You've hit your session limit SECRET"}
        for exit_code in (0, 1):
            code = ("import json, sys; sys.stdin.read(); print(json.dumps(" + repr(envelope)
                    + ")); sys.exit(" + str(exit_code) + ")")
            terminal = io.StringIO()
            with mock.patch("review_paper.agent_exec_command", return_value=[sys.executable, "-c", code]), \
                    contextlib.redirect_stdout(terminal):
                job = start_reviewer(reviewer, self.folder, self.folder, self.folder,
                                     REPO / "schemas/reviewer_output.schema.json", self.folder, backend="claude")
                result = wait_reviewer(*job, timeout_seconds=30)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(output.read_text(), "previous accepted review")
            for text in (terminal.getvalue(), result.stderr_path.read_text(encoding="utf-8")):
                self.assertIn("usage limit", text)
                self.assertNotIn("SECRET", text)

    def test_subscription_auth_without_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.check_status({"loggedIn": True, "authMethod": "claude.ai"}), "2.1.280")

    def test_old_cli_stops_before_auth_or_inference(self):
        with self.assertRaisesRegex(ValueError, "2.1.280"):
            self.check_status({}, version="2.1.126")

    def test_missing_auth_and_api_billing_are_rejected_without_leaking_status(self):
        for status in ({"loggedIn": False, "secret": "NEVER_ECHO"},
                       {"loggedIn": True, "authMethod": "api_key", "secret": "NEVER_ECHO"}):
            with self.subTest(status=status["loggedIn"]), self.assertRaises(ValueError) as caught:
                self.check_status(status)
            self.assertNotIn("NEVER_ECHO", str(caught.exception))

    def test_provider_overrides_do_not_silently_bill_api(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "NEVER_ECHO"}, clear=True):
            with self.assertRaisesRegex(ValueError, "API/provider overrides") as caught:
                self.check_status({"loggedIn": True, "authMethod": "claude.ai"})
            self.assertNotIn("NEVER_ECHO", str(caught.exception))

    def test_permissions_and_canonical_schema(self):
        with mock.patch.object(backend, "claude_command", return_value="claude"):
            schema = REPO / "schemas/reviewer_output.schema.json"
            for search in (False, True):
                command = backend.claude_exec_command(schema_path=schema, search=search)
                self.assertEqual(command[command.index("--model") + 1], "claude-opus-5-5")
                self.assertEqual(command[command.index("--permission-mode") + 1], "dontAsk")
                self.assertEqual("--allowedTools" in command, search)
                tools = command[command.index("--tools") + 1].split(",")
                self.assertEqual(set(tools), {"Read", "Glob", "Grep"} | ({"WebSearch", "WebFetch"} if search else set()))
                self.assertEqual(json.loads(command[command.index("--json-schema") + 1]), json.loads(schema.read_text()))
                self.assertNotIn("--bare", command)
                self.assertNotIn("--dangerously-skip-permissions", command)

    def test_none_effort_rejected(self):
        with self.assertRaisesRegex(ValueError, "not none"):
            backend.claude_exec_command(reasoning_effort="none")

    def test_legacy_codex_transport_unchanged(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("review_paper.codex_command", return_value="codex"):
            self.assertEqual(agent_exec_command(output_path=Path("out.json"), schema_path=Path("schema.json")),
                             ["codex", "exec", "--output-schema", "schema.json", "--output-last-message", "out.json", "-"])

    def test_backend_mismatch_and_legacy_manifest(self):
        backend.require_same_backend("codex", {"model": "gpt-5.6-sol"})
        backend.require_same_backend("claude", {"backend": "claude"})
        for current, prior in (("codex", {"backend": "claude"}), ("claude", {"model": "old"})):
            with self.assertRaisesRegex(ValueError, "Saved run uses"):
                backend.require_same_backend(current, prior)

    def test_failed_malformed_denied_or_missing_output_never_overwrites_saved_artifact(self):
        output = self.folder / "review.json"
        output.write_text("previous validated output")
        stdout = self.folder / "stdout.log"
        good = {"type": "result", "subtype": "success", "is_error": False}
        for payload in ({}, [], {**good, "is_error": True}, {**good, "subtype": "error_max_turns"},
                        {**good, "permission_denials": [{"tool_name": "Read"}]}, good,
                        {**good, "structured_output": {"reviewer": "wrong"}}):
            stdout.write_text(json.dumps(payload))
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                backend.save_claude_output(stdout, output, REPO / "schemas/reviewer_output.schema.json")
            self.assertEqual(output.read_text(), "previous validated output")
        stdout.write_text("not JSON")
        with self.assertRaises(ValueError):
            backend.save_claude_output(stdout, output)

    def test_structured_and_editor_outputs_preserve_unicode_and_metadata(self):
        stdout = self.folder / "stdout.log"
        output = self.folder / "report.md"
        response = {"type": "result", "subtype": "success", "is_error": False,
                    "result": "# Report\n\nEvidence: −1.25; ø.", "modelUsage": {"claude-opus-5-5": {"inputTokens": 12}}}
        stdout.write_text(json.dumps(response), encoding="utf-8")
        original = stdout.read_bytes()
        backend.save_claude_output(stdout, output)
        self.assertEqual(output.read_text(encoding="utf-8"), response["result"] + "\n")
        self.assertEqual(stdout.read_bytes(), original)
        self.assertFalse(output.with_suffix(".md.pending").exists())

    def test_full_mocked_pipeline_packaged_resources_resume_and_editor_refresh(self):
        package = self.folder / "installation/economics_paper_reviewer"
        for name, data in cli_payload(REPO).items():
            target = package / "runtime" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for name in ("__init__.py", "cli.py"):
            shutil.copyfile(REPO / "src/economics_paper_reviewer" / name, package / name)
        env = fake_claude_environment(self.folder)
        env["PYTHONPATH"] += os.pathsep + str(package.parent)
        command = [sys.executable, "-c", "from economics_paper_reviewer.cli import main; raise SystemExit(main())"]
        result = exercise_pipeline(command, self.folder, env, backend="claude")
        manifest = json.loads((Path(result["workspace"]) / "work/paper-with-spaces/run_manifest.json").read_text())
        self.assertEqual(manifest["backend"], "claude")
        self.assertEqual(manifest["reused_preflight"]["model"], "claude-opus-5-5")
        self.assertEqual(manifest["refreshed_editor"]["backend"], "claude")


if __name__ == "__main__":
    unittest.main()
