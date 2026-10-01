"""Backend choices are local and deterministic; no provider calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backend_settings import SETTINGS_FILE, read_run_manifest, remember_backend, resolve_backend
import check_environment


class BackendSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="backend-choice-")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)

    def test_legacy_default_and_read_only_explicit_selection(self):
        self.assertEqual(resolve_backend(self.workspace), ("codex", "legacy default"))
        self.assertEqual(resolve_backend(self.workspace, "claude"), ("claude", "explicit choice"))
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_remembered_choice_explicit_override_and_existing_run_provenance(self):
        remember_backend(self.workspace, "claude")
        path = self.workspace / SETTINGS_FILE
        before = path.read_bytes()
        self.assertEqual(resolve_backend(self.workspace), ("claude", "workspace preference"))
        self.assertEqual(resolve_backend(self.workspace, "codex"), ("codex", "explicit choice"))
        self.assertEqual(resolve_backend(self.workspace, prior_manifest={}), ("codex", "saved run"))
        self.assertEqual(resolve_backend(self.workspace, prior_manifest={"backend": "codex"}),
                         ("codex", "saved run"))
        with self.assertRaisesRegex(ValueError, "Saved run uses --backend codex"):
            resolve_backend(self.workspace, "claude", {"backend": "codex"})
        self.assertEqual(path.read_bytes(), before)
        remember_backend(self.workspace, "codex")
        self.assertEqual(resolve_backend(self.workspace), ("codex", "workspace preference"))
        self.assertEqual([p.name for p in self.workspace.iterdir()], [SETTINGS_FILE])

    def test_malformed_or_unknown_preferences_do_not_silently_select_a_provider(self):
        path = self.workspace / SETTINGS_FILE
        for value in ("not json", "null", "[]", "{}", '{"format": 2, "backend": "claude"}',
                      '{"format": 1, "backend": "unknown"}'):
            with self.subTest(value=value):
                path.write_text(value)
                with self.assertRaisesRegex(ValueError, "Invalid backend preference"):
                    resolve_backend(self.workspace)
                # An explicit fresh-run choice can repair preferences, but reading
                # a known paper never depends on a preference for other papers.
                self.assertEqual(resolve_backend(self.workspace, "claude")[0], "claude")
                self.assertEqual(resolve_backend(self.workspace, prior_manifest={})[0], "codex")
        with self.assertRaisesRegex(ValueError, "unknown backend"):
            remember_backend(self.workspace, "unknown")

    def test_invalid_manifest_is_not_treated_as_a_fresh_codex_run(self):
        path = self.workspace / "run_manifest.json"
        self.assertIsNone(read_run_manifest(path))
        for value in ("not json", "[]", "null", '{"backend": "unknown"}'):
            path.write_text(value)
            with self.assertRaisesRegex(ValueError, "Cannot read saved backend"):
                read_run_manifest(path)
        path.write_text('{"model": "historical-codex-model"}')
        self.assertEqual(resolve_backend(self.workspace, prior_manifest=read_run_manifest(path))[0], "codex")

    def test_checkout_prerequisite_check_uses_preference_without_saving_or_fallback(self):
        remember_backend(self.workspace, "claude")
        before = (self.workspace / SETTINGS_FILE).read_bytes()
        with mock.patch.object(check_environment, "repo_root", return_value=self.workspace), \
                mock.patch.object(check_environment, "missing_modules", return_value=[]), \
                mock.patch.object(check_environment, "missing_paths", return_value=[]), \
                mock.patch.object(check_environment.shutil, "which", side_effect=AssertionError("Codex must not be probed")), \
                mock.patch("claude_backend.check_claude", side_effect=ValueError("Claude login missing")) as check, \
                mock.patch.object(sys, "argv", ["check_environment.py"]):
            self.assertEqual(check_environment.main(), 1)
        check.assert_called_once_with(self.workspace)
        self.assertEqual((self.workspace / SETTINGS_FILE).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
