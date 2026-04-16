from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
TEMP_ROOT = REPO_ROOT / "work" / "test-tmp"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from normalize_review_outputs import issue_class, normalize  # noqa: E402
from reviewer_config import ReviewerConfig, load_reviewers_config  # noqa: E402
from validate_review_json import semantic_errors  # noqa: E402


def write_config(path: Path, reviewers: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"reviewers": reviewers}), encoding="utf-8")


def reviewer(
    name: str,
    *,
    output: str | None = None,
    prompt: str | None = None,
    enabled: bool = True,
    role: str = "manuscript",
) -> dict[str, object]:
    return {
        "name": name,
        "prompt": prompt or f"{name}.txt",
        "output": output or f"{name}.json",
        "id_prefix": name.upper(),
        "search": False,
        "enabled": enabled,
        "normalization_role": role,
    }


def reviewer_config(name: str = "numerical_auditor", prefix: str = "NUM") -> ReviewerConfig:
    return ReviewerConfig(
        name=name,
        prompt=f"{name}.txt",
        output=f"{name}.json",
        id_prefix=prefix,
        search=False,
        enabled=True,
        normalization_role="manuscript",
    )


def finding(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "NUM-001",
        "category": "rounding_error",
        "issue_type": "manuscript_issue",
        "severity": "medium",
        "confidence": "high",
        "location": {
            "page": 1,
            "page_label": "1",
            "section": "Results",
            "text_quote": "reported 10%",
            "precision": "exact",
        },
        "claim_text": "The value is 10%.",
        "assessment": "no",
        "cannot_verify_reason": None,
        "evidence_summary": "The table reports 12%.",
        "source_objects": [
            {
                "id": "SRC-001",
                "type": "table",
                "label": "Table 1",
                "path": "work/paper/parsed/tables/table_1.md",
                "page": 1,
                "page_label": "1",
                "section": "Results",
                "text_quote": "12%",
                "url": None,
            }
        ],
        "claim_evidence_links": [
            {
                "claim_text": "The value is 10%.",
                "source_object_ids": ["SRC-001"],
                "relation": "contradicts",
                "note": "Table reports 12%.",
            }
        ],
        "numeric_check": {
            "reported_value": "10%",
            "expected_value": "12%",
            "method": "direct table comparison",
            "inputs": ["Table 1"],
            "recomputation_notes": "No arithmetic needed.",
        },
        "suggested_fix": "Use 12%.",
    }
    base.update(overrides)
    return base


def review_output(findings: list[dict[str, object]], reviewer_name: str = "numerical_auditor") -> dict[str, object]:
    return {
        "reviewer": reviewer_name,
        "paper_id": "paper-x",
        "run_status": "ok",
        "summary": "summary",
        "findings": findings,
        "notes": [],
    }


class ReviewerConfigTests(unittest.TestCase):
    def config_path(self, name: str) -> Path:
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        path = TEMP_ROOT / name
        if path.exists():
            path.unlink()
        self.addCleanup(lambda: path.exists() and path.unlink())
        return path

    def test_default_config_loads_enabled_reviewers(self) -> None:
        reviewers = load_reviewers_config(REPO_ROOT / "config" / "reviewers.json")

        self.assertEqual(
            [item.name for item in reviewers],
            [
                "crossref_auditor",
                "numerical_auditor",
                "claim_evidence_auditor",
                "literature_auditor",
                "reference_auditor",
            ],
        )
        self.assertEqual([item.output for item in reviewers], [f"{item.name}.json" for item in reviewers])
        self.assertEqual(next(item for item in reviewers if item.name == "numerical_auditor").id_prefix, "NUM")
        self.assertTrue(next(item for item in reviewers if item.name == "literature_auditor").search)
        self.assertEqual(next(item for item in reviewers if item.name == "crossref_auditor").normalization_role, "crossref")

    def test_disabled_reviewers_are_skipped_by_default(self) -> None:
        path = self.config_path("disabled_reviewers.json")
        write_config(path, [reviewer("enabled_agent"), reviewer("disabled_agent", enabled=False)])

        enabled = load_reviewers_config(path)
        all_reviewers = load_reviewers_config(path, enabled_only=False)

        self.assertEqual([item.name for item in enabled], ["enabled_agent"])
        self.assertEqual([item.name for item in all_reviewers], ["enabled_agent", "disabled_agent"])

    def test_duplicate_outputs_are_rejected(self) -> None:
        path = self.config_path("duplicate_outputs.json")
        write_config(path, [reviewer("agent_a", output="same.json"), reviewer("agent_b", output="same.json")])

        with self.assertRaisesRegex(ValueError, "Duplicate reviewer output"):
            load_reviewers_config(path)

    def test_duplicate_id_prefixes_are_rejected(self) -> None:
        path = self.config_path("duplicate_prefixes.json")
        left = reviewer("agent_a")
        right = reviewer("agent_b")
        right["id_prefix"] = left["id_prefix"]
        write_config(path, [left, right])

        with self.assertRaisesRegex(ValueError, "Duplicate reviewer id_prefix"):
            load_reviewers_config(path)

    def test_invalid_normalization_role_is_rejected(self) -> None:
        path = self.config_path("invalid_role.json")
        write_config(path, [reviewer("agent_a", role="novelty")])

        with self.assertRaisesRegex(ValueError, "normalization_role"):
            load_reviewers_config(path)

    def test_issue_class_uses_manifest_role(self) -> None:
        finding = {"category": "outdated_working_paper", "assessment": "yes"}
        reference = ReviewerConfig(
            name="published_version_auditor",
            prompt="published_version_audit.txt",
            output="published_version_auditor.json",
            id_prefix="PVA",
            search=True,
            enabled=True,
            normalization_role="reference",
        )
        manuscript = ReviewerConfig(
            name="robustness_auditor",
            prompt="robustness_audit.txt",
            output="robustness_auditor.json",
            id_prefix="ROB",
            search=False,
            enabled=True,
            normalization_role="manuscript",
        )

        self.assertEqual(issue_class(reference, finding), "bibliography_maintenance")
        self.assertEqual(issue_class(manuscript, finding), "manuscript_issue")

    def test_semantic_errors_reject_bad_id_and_duplicates(self) -> None:
        data = review_output([finding(id="BAD-001"), finding(id="BAD-001")])

        errors = semantic_errors(data, [reviewer_config()])

        self.assertTrue(any("must match NUM-###" in error for error in errors))
        self.assertTrue(any("duplicates another finding id" in error for error in errors))

    def test_semantic_errors_require_cannot_verify_reason(self) -> None:
        data = review_output(
            [
                finding(
                    id="NUM-001",
                    category="cannot_verify",
                    issue_type="cannot_verify",
                    assessment="cannot_verify",
                    numeric_check=None,
                    cannot_verify_reason=None,
                )
            ]
        )

        errors = semantic_errors(data, [reviewer_config()])

        self.assertTrue(any("cannot_verify_reason is required" in error for error in errors))

    def test_semantic_errors_require_numeric_check_for_numerical_findings(self) -> None:
        data = review_output([finding(numeric_check=None)])

        errors = semantic_errors(data, [reviewer_config()])

        self.assertTrue(any("numeric_check is required" in error for error in errors))

    def test_semantic_errors_accept_exact_artifact_location_without_page(self) -> None:
        data = review_output(
            [
                finding(
                    location={
                        "page": None,
                        "page_label": None,
                        "section": "manifest summary",
                        "text_quote": "table_count: 0",
                        "precision": "exact",
                    }
                )
            ]
        )

        errors = semantic_errors(data, [reviewer_config()])

        self.assertFalse(any("precision=exact" in error for error in errors))

    def test_semantic_errors_validate_claim_evidence_links(self) -> None:
        data = review_output(
            [
                finding(
                    claim_evidence_links=[
                        {
                            "claim_text": "The value is 10%.",
                            "source_object_ids": ["MISSING"],
                            "relation": "contradicts",
                            "note": "Missing source object.",
                        }
                    ]
                )
            ]
        )

        errors = semantic_errors(data, [reviewer_config()])

        self.assertTrue(any("undeclared source object ids" in error for error in errors))

    def test_normalize_preserves_structured_contract_fields(self) -> None:
        reviews_dir = self.config_path("reviews_marker.json").parent / "reviews"
        reviews_dir.mkdir(exist_ok=True)
        reviewer = reviewer_config()
        (reviews_dir / reviewer.output).write_text(json.dumps(review_output([finding()])), encoding="utf-8")
        self.addCleanup(lambda: (reviews_dir / reviewer.output).exists() and (reviews_dir / reviewer.output).unlink())

        bundle = normalize("paper-x", reviews_dir, [reviewer])
        group = bundle["canonical_findings"][0]

        self.assertEqual(group["confidence"], "high")
        self.assertEqual(group["source_objects"][0]["source_object"]["id"], "SRC-001")
        self.assertEqual(group["claim_evidence_links"][0]["link"]["relation"], "contradicts")
        self.assertEqual(group["numeric_checks"][0]["numeric_check"]["expected_value"], "12%")


if __name__ == "__main__":
    unittest.main()
