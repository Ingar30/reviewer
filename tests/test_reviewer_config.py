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

from check_final_report import GRAMMAR_APPENDIX_HEADING, TRACEABILITY_APPENDIX_HEADING, report_failures  # noqa: E402
from build_editor_input import (  # noqa: E402
    ADDITIONAL_FINDINGS_SECTION,
    GRAMMAR_APPENDIX_SECTION,
    HIGHEST_PRIORITY_SECTION,
    PARSER_SECTION,
    REFERENCE_SECTION,
    editor_brief_markdown,
    finding_score,
    route_finding,
)
from normalize_review_outputs import issue_class, normalize  # noqa: E402
from review_paper import (  # noqa: E402
    parser_quality_gate_findings,
    selected_reviewers_from_selection,
    validate_selection_output,
)
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
    selection_policy: str = "mandatory",
) -> dict[str, object]:
    return {
        "name": name,
        "prompt": prompt or f"{name}.txt",
        "output": output or f"{name}.json",
        "id_prefix": name.upper(),
        "search": False,
        "enabled": enabled,
        "normalization_role": role,
        "selection_policy": selection_policy,
    }


def reviewer_config(
    name: str = "numerical_auditor",
    prefix: str = "NUM",
    role: str = "manuscript",
    selection_policy: str = "mandatory",
) -> ReviewerConfig:
    return ReviewerConfig(
        name=name,
        prompt=f"{name}.txt",
        output=f"{name}.json",
        id_prefix=prefix,
        search=False,
        enabled=True,
        normalization_role=role,
        stage="review",
        selection_policy=selection_policy,
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


def review_output(
    findings: list[dict[str, object]],
    reviewer_name: str = "numerical_auditor",
    run_status: str = "ok",
) -> dict[str, object]:
    return {
        "reviewer": reviewer_name,
        "paper_id": "paper-x",
        "run_status": run_status,
        "summary": "summary",
        "findings": findings,
        "notes": [],
    }


class ReviewerConfigTests(unittest.TestCase):
    def cleanup_path(self, path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except PermissionError:
            pass

    def config_path(self, name: str) -> Path:
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        path = TEMP_ROOT / name
        self.cleanup_path(path)
        self.addCleanup(self.cleanup_path, path)
        return path

    def test_default_config_loads_enabled_reviewers(self) -> None:
        reviewers = load_reviewers_config(REPO_ROOT / "config" / "reviewers.json")

        self.assertEqual(
            [item.name for item in reviewers],
            [
                "parser_quality_auditor",
                "crossref_auditor",
                "numerical_auditor",
                "claim_evidence_auditor",
                "literature_auditor",
                "reference_auditor",
                "grammar_auditor",
                "identification_auditor",
                "robustness_auditor",
                "sample_construction_auditor",
                "abstract_conclusion_consistency_auditor",
                "limitations_external_validity_auditor",
                "model_equation_auditor",
                "data_availability_replication_auditor",
            ],
        )
        self.assertEqual([item.output for item in reviewers], [f"{item.name}.json" for item in reviewers])
        self.assertEqual(next(item for item in reviewers if item.name == "parser_quality_auditor").stage, "preflight")
        self.assertEqual(next(item for item in reviewers if item.name == "numerical_auditor").id_prefix, "NUM")
        self.assertTrue(next(item for item in reviewers if item.name == "literature_auditor").search)
        self.assertEqual(next(item for item in reviewers if item.name == "crossref_auditor").normalization_role, "crossref")
        self.assertEqual(next(item for item in reviewers if item.name == "grammar_auditor").normalization_role, "copyedit")
        self.assertEqual(next(item for item in reviewers if item.name == "crossref_auditor").selection_policy, "mandatory")
        self.assertEqual(next(item for item in reviewers if item.name == "numerical_auditor").selection_policy, "optional")

    def test_disabled_reviewers_are_skipped_by_default(self) -> None:
        path = self.config_path("disabled_reviewers.json")
        write_config(path, [reviewer("enabled_agent"), reviewer("disabled_agent", enabled=False)])

        enabled = load_reviewers_config(path)
        all_reviewers = load_reviewers_config(path, enabled_only=False)

        self.assertEqual([item.name for item in enabled], ["enabled_agent"])
        self.assertEqual([item.name for item in all_reviewers], ["enabled_agent", "disabled_agent"])
        self.assertEqual(enabled[0].stage, "review")

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

    def test_invalid_stage_is_rejected(self) -> None:
        path = self.config_path("invalid_stage.json")
        item = reviewer("agent_a")
        item["stage"] = "later"
        write_config(path, [item])

        with self.assertRaisesRegex(ValueError, "stage"):
            load_reviewers_config(path)

    def test_invalid_selection_policy_is_rejected(self) -> None:
        path = self.config_path("invalid_selection_policy.json")
        item = reviewer("agent_a")
        item["selection_policy"] = "sometimes"
        write_config(path, [item])

        with self.assertRaisesRegex(ValueError, "selection_policy"):
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
            stage="review",
            selection_policy="mandatory",
        )
        manuscript = ReviewerConfig(
            name="robustness_auditor",
            prompt="robustness_audit.txt",
            output="robustness_auditor.json",
            id_prefix="ROB",
            search=False,
            enabled=True,
            normalization_role="manuscript",
            stage="review",
            selection_policy="mandatory",
        )
        copyedit = ReviewerConfig(
            name="grammar_auditor",
            prompt="grammar_audit.txt",
            output="grammar_auditor.json",
            id_prefix="GRAM",
            search=False,
            enabled=True,
            normalization_role="copyedit",
            stage="review",
            selection_policy="mandatory",
        )

        self.assertEqual(issue_class(reference, finding), "bibliography_maintenance")
        self.assertEqual(issue_class(manuscript, finding), "manuscript_issue")
        self.assertEqual(issue_class(copyedit, finding), "copyedit_issue")

    def test_schema_accepts_copyedit_issue(self) -> None:
        schema = json.loads((REPO_ROOT / "schemas" / "reviewer_output.schema.json").read_text(encoding="utf-8"))
        data = review_output(
            [
                finding(
                    id="GRAM-001",
                    category="grammar",
                    issue_type="copyedit_issue",
                    claim_text="This sentence are awkward.",
                    assessment="no",
                    evidence_summary="The subject and verb do not agree.",
                    source_objects=[
                        {
                            "id": "SRC-001",
                            "type": "text",
                            "label": "Page 1 text",
                            "path": "work/paper/parsed/pages/page_001.md",
                            "page": 1,
                            "page_label": "1",
                            "section": "Introduction",
                            "text_quote": "This sentence are awkward.",
                            "url": None,
                        }
                    ],
                    claim_evidence_links=[],
                    numeric_check=None,
                    suggested_fix="This sentence is awkward.",
                )
            ],
            reviewer_name="grammar_auditor",
        )

        issue_types = schema["properties"]["findings"]["items"]["properties"]["issue_type"]["enum"]
        semantic = semantic_errors(data, [reviewer_config("grammar_auditor", "GRAM", "copyedit")])

        self.assertIn("copyedit_issue", issue_types)
        self.assertEqual(semantic, [])

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

    def test_semantic_errors_allow_parser_artifacts_without_numeric_check(self) -> None:
        data = review_output(
            [
                finding(
                    issue_type="parser_artifact",
                    category="structured_table_missing",
                    assessment="yes",
                    numeric_check=None,
                )
            ]
        )

        errors = semantic_errors(data, [reviewer_config()])

        self.assertFalse(any("numeric_check is required" in error for error in errors))

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

    def test_parser_quality_gate_blocks_only_high_confidence_blockers(self) -> None:
        high_blocker = finding(
            id="PARSER-001",
            issue_type="parser_artifact",
            severity="high",
            confidence="high",
            assessment="no",
        )
        medium_warning = finding(
            id="PARSER-002",
            issue_type="parser_artifact",
            severity="medium",
            confidence="high",
            assessment="no",
        )
        high_medium_confidence_warning = finding(
            id="PARSER-003",
            issue_type="parser_artifact",
            severity="high",
            confidence="medium",
            assessment="no",
        )
        low_finding = finding(
            id="PARSER-004",
            issue_type="parser_artifact",
            severity="low",
            confidence="high",
            assessment="no",
        )

        blockers, warnings = parser_quality_gate_findings(
            review_output(
                [high_blocker, medium_warning, high_medium_confidence_warning, low_finding],
                reviewer_name="parser_quality_auditor",
            )
        )

        self.assertEqual([finding["id"] for finding in blockers], ["PARSER-001"])
        self.assertEqual([finding["id"] for finding in warnings], ["PARSER-002", "PARSER-003"])

    def test_validate_selection_output_rejects_unknown_mandatory_and_duplicate_reviewers(self) -> None:
        mandatory = [
            reviewer_config("crossref_auditor", "CROSSREF"),
            reviewer_config("reference_auditor", "REF", "reference"),
        ]
        optional = [
            ReviewerConfig(
                name="identification_auditor",
                prompt="identification_audit.txt",
                output="identification_auditor.json",
                id_prefix="ID",
                search=False,
                enabled=True,
                normalization_role="manuscript",
                stage="review",
                selection_policy="optional",
            )
        ]
        selection = {
            "paper_id": "paper-x",
            "paper_type": "empirical_causal",
            "selection_confidence": "high",
            "selected_optional_reviewers": [
                {"name": "identification_auditor", "reason": "Causal paper."},
                {"name": "identification_auditor", "reason": "Duplicate."},
                {"name": "crossref_auditor", "reason": "Mandatory."},
                {"name": "unknown_auditor", "reason": "Unknown."},
            ],
            "skipped_optional_reviewers": [],
            "notes": [],
        }

        errors = validate_selection_output(selection, "paper-x", mandatory, optional)

        self.assertTrue(any("duplicated" in error for error in errors))
        self.assertTrue(any("mandatory" in error for error in errors))
        self.assertTrue(any("not an enabled optional reviewer" in error for error in errors))

    def test_selected_reviewers_from_selection_combines_mandatory_and_optional(self) -> None:
        mandatory = [reviewer_config("crossref_auditor", "CROSSREF")]
        optional = [
            ReviewerConfig(
                name="identification_auditor",
                prompt="identification_audit.txt",
                output="identification_auditor.json",
                id_prefix="ID",
                search=False,
                enabled=True,
                normalization_role="manuscript",
                stage="review",
                selection_policy="optional",
            ),
            ReviewerConfig(
                name="model_equation_auditor",
                prompt="model_equation_audit.txt",
                output="model_equation_auditor.json",
                id_prefix="MODEL",
                search=False,
                enabled=True,
                normalization_role="manuscript",
                stage="review",
                selection_policy="optional",
            ),
        ]
        selection = {
            "selected_optional_reviewers": [
                {"name": "model_equation_auditor", "reason": "Model-heavy paper."}
            ]
        }

        selected = selected_reviewers_from_selection(selection, mandatory, optional)

        self.assertEqual([reviewer.name for reviewer in selected], ["crossref_auditor", "model_equation_auditor"])

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

    def test_normalize_preserves_copyedit_issue_class(self) -> None:
        reviews_dir = self.config_path("copyedit_reviews_marker.json").parent / "reviews"
        reviews_dir.mkdir(exist_ok=True)
        reviewer = reviewer_config("grammar_auditor", "GRAM", "copyedit")
        data = review_output(
            [
                finding(
                    id="GRAM-001",
                    category="typo",
                    issue_type="copyedit_issue",
                    numeric_check=None,
                    suggested_fix="Correct the typo.",
                )
            ],
            reviewer_name="grammar_auditor",
        )
        (reviews_dir / reviewer.output).write_text(json.dumps(data), encoding="utf-8")
        self.addCleanup(lambda: (reviews_dir / reviewer.output).exists() and (reviews_dir / reviewer.output).unlink())

        bundle = normalize("paper-x", reviews_dir, [reviewer])

        self.assertEqual(bundle["canonical_findings"][0]["issue_class"], "copyedit_issue")
        self.assertEqual(bundle["summary"]["issue_class_counts"]["copyedit_issue"], 1)

    def test_editor_brief_priority_scoring_and_routing(self) -> None:
        high_manuscript = {
            "canonical_id": "CANON-001",
            "issue_class": "manuscript_issue",
            "severity": "high",
            "confidence": "high",
            "assessment": "no",
            "source_reviewers": ["claim_evidence_auditor", "numerical_auditor"],
            "source_findings": [
                {"reviewer": "claim_evidence_auditor", "id": "CEA-001"},
                {"reviewer": "numerical_auditor", "id": "NUM-001"},
            ],
            "claim_text": "The main claim is overstated.",
            "primary_location": {"page": 1, "page_label": "1", "section": "Abstract", "text_quote": "claim"},
        }
        copyedit = {
            **high_manuscript,
            "canonical_id": "CANON-002",
            "issue_class": "copyedit_issue",
            "source_reviewers": ["grammar_auditor"],
            "source_findings": [{"reviewer": "grammar_auditor", "id": "GRAM-001"}],
        }
        parser = {
            **high_manuscript,
            "canonical_id": "CANON-003",
            "issue_class": "parser_artifact",
            "source_reviewers": ["parser_quality_auditor"],
            "source_findings": [{"reviewer": "parser_quality_auditor", "id": "PARSER-001"}],
        }
        reference = {
            **high_manuscript,
            "canonical_id": "CANON-004",
            "issue_class": "reference_integrity",
            "source_reviewers": ["reference_auditor"],
            "source_findings": [{"reviewer": "reference_auditor", "id": "REF-001"}],
        }
        low_manuscript = {
            **high_manuscript,
            "canonical_id": "CANON-005",
            "severity": "low",
            "confidence": "low",
            "source_reviewers": ["claim_evidence_auditor"],
            "source_findings": [{"reviewer": "claim_evidence_auditor", "id": "CEA-002"}],
        }

        self.assertGreater(finding_score(high_manuscript), finding_score(copyedit))
        self.assertEqual(route_finding(high_manuscript)[0], HIGHEST_PRIORITY_SECTION)
        self.assertEqual(route_finding(copyedit)[0], GRAMMAR_APPENDIX_SECTION)
        self.assertEqual(route_finding(parser)[0], PARSER_SECTION)
        self.assertEqual(route_finding(reference)[0], REFERENCE_SECTION)
        self.assertEqual(route_finding(low_manuscript)[0], ADDITIONAL_FINDINGS_SECTION)

    def test_editor_brief_guides_concise_configuration_and_traceability(self) -> None:
        reviewer = reviewer_config("claim_evidence_auditor", "CEA")
        crossref = reviewer_config("crossref_auditor", "CROSSREF", role="crossref", selection_policy="mandatory")
        grammar = reviewer_config("grammar_auditor", "GRAM", role="copyedit", selection_policy="mandatory")
        bundle = {
            "summary": {
                "issue_class_counts": {"manuscript_issue": 2, "copyedit_issue": 1},
                "severity_counts": {"high": 1, "low": 2},
            },
            "source_reviewer_outputs": [
                {"reviewer": "claim_evidence_auditor", "run_status": "ok", "finding_count": 1},
                {"reviewer": "crossref_auditor", "run_status": "partial", "finding_count": 1},
                {"reviewer": "grammar_auditor", "run_status": "ok", "finding_count": 1},
            ],
            "canonical_findings": [
                {
                    "canonical_id": "CANON-001",
                    "issue_class": "manuscript_issue",
                    "severity": "high",
                    "confidence": "high",
                    "assessment": "no",
                    "source_reviewers": ["claim_evidence_auditor"],
                    "source_findings": [{"reviewer": "claim_evidence_auditor", "id": "CEA-001"}],
                    "claim_text": "A central claim is not supported.",
                    "primary_location": {"page": 1, "page_label": "1", "section": "Abstract", "text_quote": "claim"},
                },
                {
                    "canonical_id": "CANON-002",
                    "issue_class": "manuscript_issue",
                    "severity": "low",
                    "confidence": "high",
                    "assessment": "partial",
                    "source_reviewers": ["crossref_auditor"],
                    "source_findings": [{"reviewer": "crossref_auditor", "id": "CROSSREF-001"}],
                    "claim_text": "A minor cross-reference is imprecise.",
                    "primary_location": {"page": 2, "page_label": "2", "section": "Results", "text_quote": "claim"},
                },
                {
                    "canonical_id": "CANON-003",
                    "issue_class": "copyedit_issue",
                    "severity": "low",
                    "confidence": "high",
                    "assessment": "partial",
                    "source_reviewers": ["grammar_auditor"],
                    "source_findings": [{"reviewer": "grammar_auditor", "id": "GRAM-001"}],
                    "claim_text": "A sentence has a typo.",
                    "primary_location": {"page": 3, "page_label": "3", "section": "Conclusion", "text_quote": "typo"},
                },
            ],
        }

        brief = editor_brief_markdown(
            "paper-x",
            bundle,
            [crossref, grammar, reviewer],
            {
                "claim_evidence_auditor": review_output([], "claim_evidence_auditor"),
                "crossref_auditor": review_output([], "crossref_auditor", "partial"),
                "grammar_auditor": review_output([], "grammar_auditor"),
            },
            {
                "paper_type": "empirical_causal",
                "selection_confidence": "high",
                "selected_optional_reviewers": [
                    {"name": "claim_evidence_auditor", "reason": "Important displayed-evidence claims."}
                ],
            },
        )

        self.assertIn("# Deterministic Editor Brief", brief)
        self.assertIn("Review Configuration Guidance", brief)
        self.assertIn("empirical_causal", brief)
        self.assertIn("Important displayed-evidence claims.", brief)
        self.assertIn("claim_evidence_auditor", brief)
        self.assertIn("Findings Recommended For Cross-Agent Synthesis", brief)
        self.assertIn("Additional Findings Candidates", brief)
        self.assertIn("Traceability Map Rows", brief)
        self.assertIn("CROSSREF-001", brief)
        self.assertIn("GRAM-001", brief)
        self.assertNotIn("Agent-by-Agent Finding Index", brief)
        self.assertIn("CANON-001", brief)

    def test_editor_brief_caps_highest_priority_candidates(self) -> None:
        reviewer = reviewer_config("claim_evidence_auditor", "CEA")
        findings = []
        for index in range(1, 7):
            findings.append(
                {
                    "canonical_id": f"CANON-{index:03d}",
                    "issue_class": "manuscript_issue",
                    "severity": "high",
                    "confidence": "high",
                    "assessment": "no",
                    "source_reviewers": ["claim_evidence_auditor"],
                    "source_findings": [{"reviewer": "claim_evidence_auditor", "id": f"CEA-{index:03d}"}],
                    "claim_text": f"High priority claim {index}.",
                    "primary_location": {"page": index, "page_label": str(index), "section": "Results"},
                }
            )
        bundle = {
            "summary": {
                "issue_class_counts": {"manuscript_issue": 6},
                "severity_counts": {"high": 6},
            },
            "source_reviewer_outputs": [
                {"reviewer": "claim_evidence_auditor", "run_status": "ok", "finding_count": 6}
            ],
            "canonical_findings": findings,
        }

        brief = editor_brief_markdown(
            "paper-x",
            bundle,
            [reviewer],
            {"claim_evidence_auditor": review_output([], "claim_evidence_auditor")},
        )

        synthesis = brief.split("## Findings Recommended For Cross-Agent Synthesis", 1)[1].split(
            "## Additional Findings Candidates", 1
        )[0]
        additional = brief.split("## Additional Findings Candidates", 1)[1].split("## Section Routing Guidance", 1)[0]

        self.assertIn("CANON-005", synthesis)
        self.assertNotIn("CANON-006", synthesis)
        self.assertIn("CANON-006", additional)

    def test_report_checker_requires_grammar_appendix_when_copyedit_exists(self) -> None:
        bundle = {
            "canonical_findings": [
                {
                    "canonical_id": "CANON-001",
                    "issue_class": "copyedit_issue",
                    "source_findings": [{"reviewer": "grammar_auditor", "id": "GRAM-001"}],
                }
            ]
        }
        base_report = "\n".join(
            [
                "# Multi-Agent Paper Review Report",
                "## Executive Summary",
                "CANON-001 grammar_auditor:GRAM-001",
                "## Review Configuration",
                "grammar_auditor ran.",
                "## Highest-Priority Cross-Agent Findings",
                "No substantive issues.",
                "## Suggested Revision Priorities",
                "Revise grammar appendix items.",
                "## Additional Findings",
                "No additional findings.",
            ]
        )

        failures = report_failures(base_report, bundle=bundle, min_chars=0)
        fixed = report_failures(
            base_report
            + f"\n{GRAMMAR_APPENDIX_HEADING}\n"
            + "| Location | Current text | Issue | Suggested correction |\n"
            + "| Page 1 | text | typo | correction |\n"
            + f"\n{TRACEABILITY_APPENDIX_HEADING}\n"
            + "| Report section | Finding | Canonical ID | Source finding IDs |\n"
            + "| Grammar | typo | CANON-001 | grammar_auditor:GRAM-001 |\n",
            bundle=bundle,
            min_chars=0,
        )

        self.assertTrue(any("missing grammar appendix heading" in failure for failure in failures))
        self.assertEqual(fixed, [])


if __name__ == "__main__":
    unittest.main()
