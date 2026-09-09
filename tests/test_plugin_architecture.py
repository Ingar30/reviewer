"""Core-to-package propagation and host-adapter parity (no model/network calls)."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from build_work_plugin import (CANONICAL_GUIDANCE, CANONICAL_SKILL, PACKAGE_FILES, PLUGIN_NAME, REPO_MARKETPLACE, RUNTIME_PATH,
                               build, build_release, canonical_files, check_bundle,
                               release_provenance, runtime_payload, runtime_scripts)
from render_prompts import render_review_prompts, render_selection_prompt
from review_paper import render_selector_prompt
from reviewer_config import load_reviewers_config, split_reviewers
from tests.test_work_plugin import WorkRunFixture, empty_review, save_candidate


class SharedWorkflowTests(WorkRunFixture, unittest.TestCase):
    def test_shared_prompt_rendering_matches_cli_byte_for_byte(self):
        values = {"paper_id": self.run.state["paper_id"],
                  "parsed_dir": self.run.rel(self.run.paths.parsed_dir),
                  "reviews_dir": self.run.rel(self.run.paths.reviews_dir),
                  "schema_path": "schemas/reviewer_output.schema.json",
                  "editor_bundle_path": self.run.rel(self.run.paths.bundle_path)}
        output = self.folder / "cli-prompts"
        command = [sys.executable, str(REPO / "scripts/render_prompts.py")]
        for key, value in values.items():
            command.extend(["--" + key.replace("_", "-"), value])
        command.extend(["--output-dir", str(output)])
        subprocess.run(command, cwd=REPO, capture_output=True, text=True, check=True)
        for path in output.iterdir():
            self.assertEqual(path.read_bytes(), (self.run.paths.prompts_dir / path.name).read_bytes())
        _, _, optional = split_reviewers(self.run.reviewers)
        shared = render_selection_prompt(REPO / "prompts/templates", values["paper_id"],
                                         values["parsed_dir"], "schemas/reviewer_selection.schema.json", optional)
        cli = render_selector_prompt(REPO, values["paper_id"], REPO / values["parsed_dir"],
                                     optional, REPO / "schemas/reviewer_selection.schema.json")
        self.assertEqual(shared, cli)

    def test_added_preflight_runs_before_routing_and_reaches_editor_roster(self):
        source = self.folder / "source"
        canonical = self.folder / "canonical"
        for relative in canonical_files(REPO):
            target = canonical / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        config = json.loads((canonical / "config/reviewers.json").read_text())
        config["reviewers"].append({**config["reviewers"][0], "name": "additional_preflight",
                                    "prompt": "additional_preflight.txt", "output": "additional_preflight.json",
                                    "id_prefix": "EXTRA"})
        (canonical / "config/reviewers.json").write_text(json.dumps(config), encoding="utf-8")
        (canonical / "prompts/templates/additional_preflight.txt").write_text("Audit {paper_id}.", encoding="utf-8")
        for relative, data in runtime_payload(canonical).items():
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        from work_plugin import ReviewRun, doctor
        run = ReviewRun.start(self.folder / "extra-run", source, self.pdf, "full", "available")
        self.assertEqual(doctor(source)["coverage"]["preflight"], 2)
        jobs = run.next_tasks(3)["jobs"]
        self.assertEqual({job["task"] for job in jobs}, {"parser_quality_auditor", "additional_preflight"})
        for index, job in enumerate(jobs):
            save_candidate(job, empty_review(run, job["task"]))
            self.assertEqual(run.accept(job["task"])["status"], "accepted")
            if index == 0:
                self.assertEqual(run.next_tasks(3)["jobs"], [])
        router = run.next_tasks()["jobs"][0]
        self.assertEqual(router["kind"], "selector")
        from tests.test_work_plugin import selection
        save_candidate(router, selection(run))
        run.accept(router["task"])
        selected = load_reviewers_config(run.paths.selected_reviewers_config_path)
        self.assertIn("additional_preflight", [r.name for r in selected])


class PackagePropagationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="reviewer-architecture-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        for relative in [*canonical_files(REPO), REPO_MARKETPLACE]:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        self.plugin = self.repo / "plugins" / PLUGIN_NAME
        for relative in PACKAGE_FILES:
            target = self.plugin / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / "plugins" / PLUGIN_NAME / relative, target)
        self.assertEqual(build(self.repo, self.plugin), [])

    def test_canonical_skill_config_schema_prompt_and_script_changes_propagate(self):
        for relative in (f"{CANONICAL_SKILL}/SKILL.md", "config/reviewers.json",
                         "schemas/reviewer_output.schema.json", "prompts/templates/claim_evidence_audit.txt",
                         "scripts/validate_review_json.py"):
            source = self.repo / relative
            source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertTrue(check_bundle(self.repo, self.plugin))
        self.assertEqual(build(self.repo, self.plugin), [])
        for relative, data in runtime_payload(self.repo).items():
            self.assertEqual((self.plugin / RUNTIME_PATH / relative).read_bytes(), data)

    def test_canonical_skill_is_a_reference_not_a_second_entrypoint(self):
        self.assertEqual((self.plugin / RUNTIME_PATH / CANONICAL_GUIDANCE).read_bytes(),
                         (self.repo / CANONICAL_SKILL / "SKILL.md").read_text(encoding="utf-8").encode("utf-8"))
        self.assertEqual([p.relative_to(self.plugin).as_posix() for p in self.plugin.rglob("SKILL.md")],
                         ["skills/review-paper/SKILL.md"])

    def test_new_pinned_core_dependency_is_checked_without_an_adapter_edit(self):
        requirements = self.repo / "requirements.txt"
        requirements.write_text(requirements.read_text() + "\nreviewer-missing-test-package==1.0\n", encoding="utf-8")
        build(self.repo, self.plugin)
        from work_plugin import doctor
        result = doctor(self.plugin / RUNTIME_PATH)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("reviewer-missing-test-package", result["missing"])

    def test_new_local_import_and_new_resource_follow_core_without_a_bundle_list_edit(self):
        helper = self.repo / "scripts/new_shared_helper.py"
        helper.write_text("VALUE = 1\n", encoding="utf-8")
        entry = self.repo / "scripts/work_plugin.py"
        entry.write_text(entry.read_text(encoding="utf-8") + "\nimport new_shared_helper\n", encoding="utf-8")
        (self.repo / "schemas/new.schema.json").write_text("{}\n", encoding="utf-8")
        self.assertEqual(build(self.repo, self.plugin), [])
        self.assertIn("new_shared_helper.py", runtime_scripts(self.repo))
        self.assertTrue((self.plugin / RUNTIME_PATH / "schemas/new.schema.json").is_file())

    def test_removed_generated_resource_is_retired_but_local_edits_are_preserved(self):
        relative = "schemas/retired.schema.json"
        source = self.repo / relative
        source.write_text("{}\n", encoding="utf-8")
        build(self.repo, self.plugin)
        source.unlink()
        target = self.plugin / RUNTIME_PATH / relative
        with redirect_stdout(io.StringIO()):
            self.assertEqual(build(self.repo, self.plugin), [])
        self.assertFalse(target.exists())
        source.write_text("{}\n", encoding="utf-8")
        build(self.repo, self.plugin)
        source.unlink()
        target.write_text("local edit", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "local edits"):
            build(self.repo, self.plugin)
        self.assertEqual(target.read_text(), "local edit")

    def test_cli_dependency_and_resource_escape_are_rejected(self):
        entry = self.repo / "scripts/work_plugin.py"
        entry.write_text(entry.read_text(encoding="utf-8") + "\nimport review_paper\n", encoding="utf-8")
        (self.repo / "scripts/review_paper.py").write_text("# forbidden launcher", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "excluded"):
            runtime_payload(self.repo)

    def git_fixture(self, *args, dirty="", tag_commit="a" * 40):
        if args[0] == "status":
            return dirty
        if args[0] == "ls-files":
            return "\n".join(path.relative_to(self.repo).as_posix() for path in self.repo.rglob("*") if path.is_file())
        return tag_commit if "--verify" in args else "a" * 40

    def test_release_gates_and_reproducible_receipt(self):
        tag = "v" + json.loads((self.plugin / ".codex-plugin/plugin.json").read_text())["version"]
        with mock.patch("build_work_plugin.git_output", side_effect=lambda _repo, *args: self.git_fixture(*args)):
            output = Path(self.temporary.name) / "release"
            archive = build_release(self.repo, self.plugin, output, tag)
            receipt = json.loads((output / "release.json").read_text())
            self.assertEqual(receipt["archive_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(receipt["commit"], "a" * 40)
            with zipfile.ZipFile(archive) as package:
                self.assertEqual(set(receipt["files"]), set(package.namelist()))
            with self.assertRaises(ValueError):
                build_release(self.repo, self.plugin, output, tag)
            with self.assertRaises(ValueError):
                release_provenance(self.repo, self.plugin, "v99.0.0")
        for options in ({"dirty": " M file"}, {"tag_commit": "b" * 40}):
            with mock.patch("build_work_plugin.git_output", side_effect=lambda _repo, *args: self.git_fixture(*args, **options)):
                with self.assertRaises(ValueError):
                    release_provenance(self.repo, self.plugin, tag)


if __name__ == "__main__":
    unittest.main()
