"""Submission preparation is local, canonical, reproducible and not publication."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import unittest
from unittest import mock
import zipfile

import fitz

from tests import test_plugin_architecture as architecture
from prepare_plugin_submission import DOCS, acceptance_cases, directory_errors, prepare
from build_work_plugin import PACKAGE_FILES, RUNTIME_PATH, runtime_payload

REPO = Path(__file__).resolve().parents[1]


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        architecture.PackagePropagationTests.setUp(self)
        for relative in [*("docs/" + name for name in DOCS), "docs/chatgpt_work_plugin_acceptance.md",
                         "scripts/prepare_plugin_submission.py", "scripts/build_cloud_test_kit.py",
                         "scripts/build_work_plugin.py"]:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        self.output = Path(self.temporary.name) / "submission"
        self.tag = "v" + json.loads((self.plugin / ".codex-plugin/plugin.json").read_text())["version"]

    def edit_manifest(self, change):
        path = self.plugin / ".codex-plugin/plugin.json"
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_directory_branding_and_metadata(self):
        self.assertEqual(directory_errors(self.plugin), [])
        for value in ("01.0.0", "0.1.0+codex.1", "0.1.0-01", "invalid"):
            self.edit_manifest(lambda m: m.update(version=value))
            self.assertTrue(directory_errors(self.plugin), value)
        self.edit_manifest(lambda m: m.update(version="1.2.3-rc.1"))
        self.assertEqual(directory_errors(self.plugin), [])
        self.edit_manifest(lambda m: m["interface"].update(logo="https://example.org/logo.svg"))
        self.assertTrue(directory_errors(self.plugin))

    def test_identity_and_metadata_changes_are_validated(self):
        self.edit_manifest(lambda m: m["interface"].update(developerName="Different Publisher", brandColor="#FFFFFF",
                                                          websiteURL="http://example.org"))
        errors = directory_errors(self.plugin)
        self.assertTrue(any("publisher" in e for e in errors))
        self.assertTrue(any("contrast" in e for e in errors))
        self.assertTrue(any("HTTPS" in e for e in errors))
        self.edit_manifest(lambda m: m["interface"].update(shortDescription="Trailing newline\n"))
        self.assertTrue(any("shortDescription" in e for e in directory_errors(self.plugin)))

    def test_unsafe_or_nonsquare_svg_rejected(self):
        logo = self.plugin / "assets/logo.svg"
        original = logo.read_text()
        for replacement in (original.replace('viewBox="0 0 256 256"', 'viewBox="0 0 256 128"'),
                            original.replace("</svg>", "<script>alert(1)</script></svg>")):
            logo.write_text(replacement, encoding="utf-8")
            self.assertTrue(directory_errors(self.plugin))

    def test_packet_is_allowlisted_and_receipts_match(self):
        receipt = prepare(self.repo, self.output)
        self.assertEqual(receipt["kind"], "development-candidate")
        self.assertFalse(receipt["submitted"])
        self.assertFalse(receipt["host_acceptance_verified_by_this_build"])
        for relative, digest in receipt["files"].items():
            self.assertEqual(hashlib.sha256((self.output / relative).read_bytes()).hexdigest(), digest)
        with zipfile.ZipFile(self.output / receipt["archive"]) as package:
            expected = set(PACKAGE_FILES) | {f"{RUNTIME_PATH}/{name}" for name in runtime_payload(self.repo)}
            self.assertEqual(set(package.namelist()), expected)
            self.assertNotIn("plugin_privacy.md", package.namelist())
        for fixture in (self.output / "fixtures").glob("*.pdf"):
            with fitz.open(fixture) as document:
                self.assertEqual(len(document), 1)
                self.assertTrue(document[0].get_text().strip())
                self.assertTrue(all(document[0].rect.contains(fitz.Rect(w[:4])) for w in document[0].get_text("words")))
        self.assertEqual(len(list((self.output / "fixtures").glob("*.pdf"))), 3)
        listing = json.loads((self.output / "listing.json").read_text())
        self.assertIsNone(listing["publisher_identity_verified"])
        self.assertIsNone(listing["countries"])
        self.assertIsNone(listing["owner_policy_approval"])
        guide = (self.output / "plugin_publication.md").read_text(encoding="utf-8")
        self.assertIn("https://github.com/Ingar30/reviewer/blob/main/docs/plugin_maintenance.md", guide)
        self.assertIn("](plugin_privacy.md)", guide)

    def test_listing_and_cases_follow_their_single_sources(self):
        self.edit_manifest(lambda m: m["interface"].update(shortDescription="Changed upstream description"))
        path = self.repo / "docs/chatgpt_work_plugin_acceptance.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Full warning;", "Upstream case change;"), encoding="utf-8")
        prepare(self.repo, self.output)
        self.assertEqual(json.loads((self.output / "listing.json").read_text())["shortDescription"], "Changed upstream description")
        cases = json.loads((self.output / "test-cases.json").read_text())
        self.assertIn("Upstream case change;", cases[0]["expected_behavior"])
        self.assertEqual([c["id"] for c in cases], ["P1", "P2", "P3", "P4", "P5", "N1", "N2", "N3"])
        path.write_text("# Missing cases", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "five positive"):
            acceptance_cases(self.repo)

    def test_no_overwrite_in_plugin_or_symlink_destination(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "new, unlinked"):
            prepare(self.repo, self.output)
        with self.assertRaisesRegex(ValueError, "outside the plugin"):
            prepare(self.repo, self.plugin / "packet")
        with mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(ValueError, "unlinked"):
                prepare(self.repo, Path(self.temporary.name) / "linked")

    def test_stale_runtime_and_missing_docs_prevent_creation(self):
        path = self.repo / "prompts/templates/claim_evidence_audit.txt"
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            prepare(self.repo, self.output)
        self.assertFalse(self.output.exists())
        path.write_bytes(original)
        (self.repo / "docs" / DOCS[0]).unlink()
        with self.assertRaises(OSError):
            prepare(self.repo, self.output)
        self.assertFalse(self.output.exists())

    def git_result(self, _repo, *args):
        return architecture.PackagePropagationTests.git_fixture(self, *args)

    def test_tagged_packet_keeps_existing_release_gate(self):
        with mock.patch("prepare_plugin_submission.git_output", side_effect=self.git_result), \
                mock.patch("build_work_plugin.git_output", side_effect=self.git_result):
            receipt = prepare(self.repo, self.output, release_tag=self.tag)
            self.assertEqual(receipt["kind"], "tagged-source")
            self.assertEqual(receipt["source"]["commit"], "a" * 40)
            self.assertEqual(receipt["archive_sha256"], receipt["source"]["archive_sha256"])
            self.assertTrue((self.output / "release.json").is_file())
            with self.assertRaisesRegex(ValueError, "Release tag"):
                prepare(self.repo, Path(self.temporary.name) / "wrong-tag", release_tag="v99.0.0")

    def test_untracked_submission_sources_cannot_be_a_release(self):
        with mock.patch("prepare_plugin_submission.git_output", return_value=""):
            with self.assertRaisesRegex(ValueError, "Submission tooling and documents must be tracked"):
                prepare(self.repo, self.output, release_tag=self.tag)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
