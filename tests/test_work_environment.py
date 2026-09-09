"""Isolated environment setup: no network, package installation, or model calls."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from prepare_work_environment import pinned_requirements, prepare, setup_command
from build_work_plugin import runtime_scripts
from build_cloud_test_kit import build_kit

READY = {"status": "ready", "version_differences": {}, "missing": []}
MISSING = {"status": "unavailable", "version_differences": {}, "missing": ["pymupdf"]}


class EnvironmentSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="reviewer-setup-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "plugin/skills/review-paper/runtime"
        self.source.mkdir(parents=True)
        (self.source / "requirements.txt").write_text("pymupdf==1.27.2.2\n", encoding="utf-8")
        self.target = self.root / "environment with spaces"

    def test_ready_environment_does_not_install_or_write(self):
        with mock.patch("prepare_work_environment.doctor", return_value=READY), \
                mock.patch("prepare_work_environment.setup_command") as command:
            result = prepare(self.source, self.target, allow_install=True)
        self.assertEqual(result["status"], "ready")
        self.assertFalse(result["installed"])
        self.assertFalse(self.target.exists())
        command.assert_not_called()
        self.assertIn("unverified", result["hosting"])

    def test_missing_or_different_packages_need_permission(self):
        for environment in [MISSING, {**READY, "version_differences": {"pymupdf": {"installed": "old"}}}]:
            with mock.patch("prepare_work_environment.doctor", return_value=environment), \
                    mock.patch("prepare_work_environment.setup_command") as command:
                self.assertEqual(prepare(self.source, self.target)["status"], "installation_permission_required")
                command.assert_not_called()
                self.assertFalse(self.target.exists())

    def test_authorized_setup_only_uses_new_venv_and_canonical_requirements(self):
        with mock.patch("prepare_work_environment.doctor", return_value=MISSING), \
                mock.patch("prepare_work_environment.setup_command", side_effect=["", "", json.dumps(READY)]) as command:
            result = prepare(self.source, self.target, allow_install=True)
        self.assertTrue(result["installed"])
        commands = [call.args[0] for call in command.call_args_list]
        self.assertEqual(commands[0], [sys.executable, "-I", "-m", "venv", "--copies", str(self.target)])
        self.assertTrue(Path(commands[1][0]).is_relative_to(self.target))
        self.assertIn("--only-binary=:all:", commands[1])
        self.assertIn(str(self.source / "requirements.txt"), commands[1])
        self.assertNotIn("--upgrade", commands[1])
        self.assertEqual(commands[2][-2:], [str(self.source / "scripts/work_plugin.py"), "doctor"])

    def test_existing_or_plugin_paths_are_never_modified(self):
        self.target.mkdir()
        marker = self.target / "preserve.txt"
        marker.write_text("user data", encoding="utf-8")
        for destination in [self.target, self.source / "new-env", self.source.parents[2] / "new-env", self.root]:
            with mock.patch("prepare_work_environment.doctor", return_value=MISSING), \
                    mock.patch("prepare_work_environment.setup_command") as command:
                with self.assertRaises(ValueError):
                    prepare(self.source, destination, allow_install=True)
                command.assert_not_called()
        self.assertEqual(marker.read_text(), "user data")

    def test_installer_directives_urls_unpinned_and_duplicate_requirements_are_rejected(self):
        for text in ["--extra-index-url https://example.invalid\n", "pymupdf>=1\n", "pkg @ https://example.invalid/a.whl\n",
                     "pkg==1\npkg==2\n", "# empty\n"]:
            (self.source / "requirements.txt").write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                pinned_requirements(self.source)

    def test_failed_setup_preserves_partial_environment_and_stops(self):
        with mock.patch("prepare_work_environment.doctor", return_value=MISSING), \
                mock.patch("prepare_work_environment.setup_command", side_effect=ValueError("network disabled")) as command:
            with self.assertRaises(ValueError):
                prepare(self.source, self.target, allow_install=True)
        self.assertTrue(self.target.is_dir())
        self.assertEqual(command.call_count, 1)

    def test_post_install_validation_failure_is_not_ready(self):
        with mock.patch("prepare_work_environment.doctor", return_value=MISSING), \
                mock.patch("prepare_work_environment.setup_command", side_effect=["", "", json.dumps(MISSING)]):
            with self.assertRaises(ValueError):
                prepare(self.source, self.target, allow_install=True)

    def test_command_failure_does_not_echo_pip_credentials(self):
        completed = subprocess.CompletedProcess([], 1, "private index", "private credentials")
        with mock.patch("prepare_work_environment.subprocess.run", return_value=completed):
            with self.assertRaises(ValueError) as raised:
                setup_command(["python", "-m", "pip"])
        self.assertNotIn("private", str(raised.exception))

    def test_new_entrypoint_is_bundled_and_no_cli_launcher_is_included(self):
        scripts = runtime_scripts(REPO)
        self.assertIn("prepare_work_environment.py", scripts)
        self.assertNotIn("review_paper.py", scripts)

    def test_cloud_kit_contains_exact_bundle_fixture_and_hash_receipt(self):
        destination = self.root / "cloud kit"
        result = build_kit(REPO, destination)
        self.assertFalse(result["cloud_execution_verified"])
        for name, expected in result["files"].items():
            self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), expected)
        with zipfile.ZipFile(destination / "economics-paper-reviewer.zip") as package:
            self.assertIn("skills/review-paper/runtime/scripts/prepare_work_environment.py", package.namelist())
            self.assertFalse(any(name.startswith(("inputs/", "work/", "outputs/")) for name in package.namelist()))
        with self.assertRaises(ValueError):
            build_kit(REPO, destination)

    def test_cloud_kit_refuses_stale_bundle_before_writing(self):
        destination = self.root / "stale kit"
        with mock.patch("build_cloud_test_kit.check_bundle", return_value=["stale"]):
            with self.assertRaises(ValueError):
                build_kit(REPO, destination)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
