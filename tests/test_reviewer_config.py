from __future__ import annotations

import json
import sys
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
TEMP_ROOT = REPO_ROOT / "work" / "test-tmp"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_final_report import GRAMMAR_APPENDIX_HEADING, TRACEABILITY_APPENDIX_HEADING, report_failures, external_source_urls  # noqa: E402
from check_shareable_repo import private_tracking_violations  # noqa: E402
from check_tracked_sensitive_names import suspicious_files  # noqa: E402
from evaluate_parser_repair import evaluate_plan  # noqa: E402
from evaluate_prior_runs import aggregate, selector_metrics  # noqa: E402
from render_prompts import append_parser_repair_note  # noqa: E402
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
from normalize_review_outputs import issue_class, normalize, should_merge  # noqa: E402
from preprocess_pdf import page_quality_summary, portable_path, should_append_raw_caption_continuation  # noqa: E402
from pipeline_paths import paper_run_paths  # noqa: E402
from refresh_editor import require_paths  # noqa: E402
from run_parser_repair_agent import (  # noqa: E402
    control_char_score,
    mojibake_score,
    repair_notes_markdown,
    repair_mojibake_text,
    repair_nul_codepoints,
    validate_artifact_filenames,
    validate_plan,
    write_repaired_artifacts,
)
from review_paper import (  # noqa: E402
    codex_exec_command,
    extract_editor_report_from_transcript,
    parser_quality_gate_findings,
    plausible_editor_report,
    recover_editor_report_if_needed,
    repairable_parser_findings,
    render_selector_prompt,
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


def strict_structured_output_schema_errors(schema: dict[str, object], path: str = "$") -> list[str]:
    errors: list[str] = []
    if schema.get("type") == "object" and isinstance(schema.get("properties"), dict):
        properties = schema["properties"]
        required = schema.get("required")
        if not isinstance(required, list):
            errors.append(f"{path}: required must list every property")
        else:
            missing = sorted(set(properties) - set(required))
            if missing:
                errors.append(f"{path}: required is missing {', '.join(missing)}")
        for name, child in properties.items():
            if isinstance(child, dict):
                errors.extend(strict_structured_output_schema_errors(child, f"{path}.{name}"))
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        errors.extend(strict_structured_output_schema_errors(schema["items"], f"{path}[]"))
    return errors


class ReviewerConfigTests(unittest.TestCase):
    def cleanup_path(self, path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except PermissionError:
            pass

    def cleanup_dir(self, path: Path) -> None:
        try:
            if path.exists():
                path.rmdir()
        except OSError:
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
                "institutional_context_auditor",
                "power_multiple_testing_auditor",
                "design_randomization_auditor",
                "economic_magnitude_auditor",
            ],
        )
        self.assertEqual([item.output for item in reviewers], [f"{item.name}.json" for item in reviewers])
        self.assertEqual(next(item for item in reviewers if item.name == "parser_quality_auditor").stage, "preflight")
        self.assertEqual(next(item for item in reviewers if item.name == "numerical_auditor").id_prefix, "NUM")
        self.assertTrue(next(item for item in reviewers if item.name == "literature_auditor").search)
        self.assertTrue(next(item for item in reviewers if item.name == "data_availability_replication_auditor").search)
        self.assertTrue(next(item for item in reviewers if item.name == "institutional_context_auditor").search)
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

    def test_repairable_parser_findings_returns_only_reported_parser_issues(self) -> None:
        data = review_output(
            [
                finding(id="PARSER-001", issue_type="parser_artifact", severity="medium"),
                finding(
                    id="PARSER-002",
                    issue_type="parser_artifact",
                    severity="high",
                    confidence="high",
                    assessment="no",
                ),
                finding(id="PARSER-003", issue_type="parser_artifact", severity="low"),
                finding(id="NUM-001", issue_type="manuscript_issue", severity="high"),
            ],
            reviewer_name="parser_quality_auditor",
        )

        self.assertEqual(
            [finding["id"] for finding in repairable_parser_findings(data)],
            ["PARSER-002", "PARSER-001"],
        )

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

    def test_codex_exec_command_can_override_reasoning(self) -> None:
        with mock.patch("review_paper.codex_command", return_value="codex"):
            self.assertEqual(
                codex_exec_command(reasoning_effort="xhigh", search=True),
                ["codex", "--search", "-c", 'model_reasoning_effort="xhigh"', "exec"],
            )
            self.assertEqual(codex_exec_command(), ["codex", "exec"])

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

    def test_should_merge_uses_source_object_overlap_with_related_claims(self) -> None:
        base = finding(
            claim_text="The table implies a large treatment effect.",
            source_objects=[
                {
                    "id": "SRC-T1",
                    "type": "table",
                    "label": "Table 1",
                    "path": "work/paper/parsed/tables/table_1.md",
                    "page": 5,
                    "page_label": "5",
                    "section": "Results",
                    "text_quote": "estimate",
                    "url": None,
                }
            ],
        )
        group = {
            "issue_class": "manuscript_issue",
            "source_reviewers": ["numerical_auditor"],
            "claim_text": base["claim_text"],
            "primary_quote": "estimate",
            "locations": [base["location"]],
            "source_objects": [{"source_object": base["source_objects"][0]}],
            "claim_evidence_links": [],
            "categories": [base["category"]],
        }
        related = finding(
            claim_text="Table 1 supports an economically meaningful effect.",
            source_objects=[base["source_objects"][0]],
        )

        self.assertTrue(should_merge(group, "claim_evidence_auditor", related, "manuscript_issue"))

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

    def test_editor_brief_keeps_up_to_eight_high_confidence_candidates(self) -> None:
        reviewer = reviewer_config("claim_evidence_auditor", "CEA")
        findings = []
        for index in range(1, 10):
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
                "issue_class_counts": {"manuscript_issue": 9},
                "severity_counts": {"high": 9},
            },
            "source_reviewer_outputs": [
                {"reviewer": "claim_evidence_auditor", "run_status": "ok", "finding_count": 9}
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

        self.assertIn("CANON-008", synthesis)
        self.assertNotIn("CANON-009", synthesis)
        self.assertIn("CANON-009", additional)

    def test_editor_brief_does_not_promote_lower_confidence_to_reach_minimum(self) -> None:
        reviewer = reviewer_config("claim_evidence_auditor", "CEA")
        findings = [
            {
                "canonical_id": "CANON-001",
                "issue_class": "manuscript_issue",
                "severity": "high",
                "confidence": "high",
                "assessment": "no",
                "source_reviewers": ["claim_evidence_auditor"],
                "source_findings": [{"reviewer": "claim_evidence_auditor", "id": "CEA-001"}],
                "claim_text": "High-confidence claim.",
                "primary_location": {"page": 1, "page_label": "1", "section": "Results"},
            },
            {
                "canonical_id": "CANON-002",
                "issue_class": "manuscript_issue",
                "severity": "high",
                "confidence": "medium",
                "assessment": "no",
                "source_reviewers": ["claim_evidence_auditor"],
                "source_findings": [{"reviewer": "claim_evidence_auditor", "id": "CEA-002"}],
                "claim_text": "Medium-confidence claim.",
                "primary_location": {"page": 2, "page_label": "2", "section": "Results"},
            },
        ]
        bundle = {
            "summary": {
                "issue_class_counts": {"manuscript_issue": 2},
                "severity_counts": {"high": 2},
            },
            "source_reviewer_outputs": [
                {"reviewer": "claim_evidence_auditor", "run_status": "ok", "finding_count": 2}
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

        self.assertIn("CANON-001", synthesis)
        self.assertNotIn("CANON-002", synthesis)
        self.assertIn("CANON-002", additional)

    def test_editor_report_recovery_uses_last_complete_transcript_report(self) -> None:
        report = "\n".join(
            [
                "# Multi-Agent Paper Review Report",
                "## Executive Summary",
                "summary",
                "## Review Configuration",
                "config",
                "## Highest-Priority Cross-Agent Findings",
                "findings",
                "## Suggested Revision Priorities",
                "priorities",
                "## Additional Findings",
                "additional",
                "body " + ("x" * 2100),
            ]
        )
        transcript = "\n".join(
            [
                "# Multi-Agent Paper Review Report",
                "## Executive Summary",
                "prompt skeleton only",
                "collab: SpawnAgent",
                "codex",
                report,
                "collab: CloseAgent",
                "codex",
                "Received.",
                "tokens used",
            ]
        )

        self.assertTrue(plausible_editor_report(report))
        self.assertEqual(extract_editor_report_from_transcript(transcript), report + "\n")

    def test_recover_editor_report_replaces_tiny_acknowledgement(self) -> None:
        report_path = self.config_path("tiny_editor_report.md")
        stderr_path = self.config_path("tiny_editor_report.stderr.log")
        recovered = "\n".join(
            [
                "# Multi-Agent Paper Review Report",
                "## Executive Summary",
                "summary",
                "## Review Configuration",
                "config",
                "## Highest-Priority Cross-Agent Findings",
                "findings",
                "## Suggested Revision Priorities",
                "priorities",
                "## Additional Findings",
                "additional",
                "body " + ("x" * 2100),
            ]
        )
        report_path.write_text("Received.", encoding="utf-8")
        stderr_path.write_text(f"codex\n{recovered}\ncollab: CloseAgent\nReceived.\n", encoding="utf-8")

        recover_editor_report_if_needed(report_path, stderr_path)

        self.assertEqual(report_path.read_text(encoding="utf-8"), recovered + "\n")

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

    def test_report_checker_requires_external_source_appendix_for_url_evidence(self) -> None:
        bundle = {
            "canonical_findings": [
                {
                    "canonical_id": "CANON-001",
                    "issue_class": "reference_integrity",
                    "source_findings": [{"reviewer": "reference_auditor", "id": "REF-001"}],
                    "source_objects": [
                        {
                            "source_object": {
                                "id": "SRC-001",
                                "url": "https://example.org/source",
                            }
                        }
                    ],
                }
            ]
        }
        base_report = "\n".join(
            [
                "# Multi-Agent Paper Review Report",
                "## Executive Summary",
                "CANON-001 reference_auditor:REF-001",
                "## Review Configuration",
                "reference_auditor ran.",
                "## Highest-Priority Cross-Agent Findings",
                "A source was checked at https://example.org/source.",
                "## Suggested Revision Priorities",
                "Revise the citation.",
                "## Additional Findings",
                "No additional findings.",
                f"{TRACEABILITY_APPENDIX_HEADING}",
                "| Report section | Finding | Canonical ID | Source finding IDs |",
                "| References | citation | CANON-001 | reference_auditor:REF-001 |",
            ]
        )
        fixed_report = base_report + "\n## Appendix: External Sources Cited In This Review\nhttps://example.org/source\n"

        failures = report_failures(base_report, bundle=bundle, min_chars=0)
        fixed = report_failures(fixed_report, bundle=bundle, min_chars=0)

        self.assertEqual(external_source_urls(bundle), {"https://example.org/source"})
        self.assertTrue(any("missing external-sources appendix" in failure for failure in failures))
        self.assertEqual(fixed, [])

    def test_report_checker_allows_uncited_bundle_external_urls(self) -> None:
        bundle = {
            "canonical_findings": [
                {
                    "canonical_id": "CANON-001",
                    "source_findings": [{"reviewer": "literature_auditor", "id": "LIT-001"}],
                    "source_objects": [
                        {
                            "source_object": {
                                "id": "SRC-001",
                                "url": "https://example.org/unused-source",
                            }
                        }
                    ],
                }
            ]
        }
        report = "\n".join(
            [
                "# Multi-Agent Paper Review Report",
                "## Executive Summary",
                "summary",
                "## Review Configuration",
                "literature_auditor ran.",
                "## Highest-Priority Cross-Agent Findings",
                "A source-informed issue was summarized without citing the URL.",
                "## Suggested Revision Priorities",
                "Revise the literature discussion.",
                "## Additional Findings",
                "No additional findings.",
                f"{TRACEABILITY_APPENDIX_HEADING}",
                "| Report section | Finding | Canonical ID | Source finding IDs |",
                "| Literature | citation | CANON-001 | literature_auditor:LIT-001 |",
            ]
        )

        self.assertEqual(report_failures(report, bundle=bundle, min_chars=0), [])

    def test_shareable_repo_check_allows_placeholders_only_in_private_dirs(self) -> None:
        paths = [
            "README.md",
            "inputs/README.md",
            "work/README.md",
            "outputs/README.md",
            "scripts/review_paper.py",
        ]

        self.assertEqual(private_tracking_violations(paths), [])

    def test_shareable_repo_check_rejects_private_artifacts(self) -> None:
        paths = [
            "inputs/paper.pdf",
            "work/paper1/reviews/numerical_auditor.json",
            "outputs/paper1/report.md",
            "data/raw/survey.csv",
            "data/paper/raw/table.csv",
        ]

        self.assertEqual(private_tracking_violations(paths), paths)

    def test_sensitive_name_check_flags_assignments_without_secret_values(self) -> None:
        root = self.config_path("sensitive_marker.txt").parent
        secret_file = root / "settings.py"
        normal_file = root / "notes.md"
        variable_name = "OPENAI_" + "API_KEY"
        secret_file.write_text(f"{variable_name} = 'do-not-print'\n", encoding="utf-8")
        normal_file.write_text("Key findings are summarized here.\n", encoding="utf-8")
        self.addCleanup(lambda: secret_file.exists() and secret_file.unlink())
        self.addCleanup(lambda: normal_file.exists() and normal_file.unlink())

        self.assertEqual(suspicious_files(root, ["settings.py", "notes.md"]), ["settings.py"])

    def test_prior_run_aggregate_scores_sections(self) -> None:
        results = [
            {
                "overall_score": 80.0,
                "preprocessing": {"score": 60.0},
                "caption_extraction": {"score": 100.0},
                "normalization": {"score": 90.0},
                "report_checking": {"score": 80.0},
                "selector_breadth": {"score": 70.0},
                "resume_readiness": {"score": 100.0},
            },
            {
                "overall_score": 100.0,
                "preprocessing": {"score": 100.0},
                "caption_extraction": {"score": 100.0},
                "normalization": {"score": 100.0},
                "report_checking": {"score": 100.0},
                "selector_breadth": {"score": 100.0},
                "resume_readiness": {"score": 100.0},
            },
        ]

        summary = aggregate(results)

        self.assertEqual(summary["paper_count"], 2)
        self.assertEqual(summary["overall_score"], 90.0)
        self.assertEqual(summary["section_scores"]["preprocessing"], 80.0)
        self.assertEqual(summary["section_scores"]["selector_breadth"], 85.0)

    def test_selector_metrics_penalizes_broad_pilot_zero_finding_selection(self) -> None:
        root = self.config_path("selector_marker.json").parent
        selection_dir = root / "selection"
        editor_dir = root / "editor"
        selection_dir.mkdir(exist_ok=True)
        editor_dir.mkdir(exist_ok=True)
        (selection_dir / "reviewer_selection.json").write_text(
            json.dumps(
                {
                    "paper_type": "mixed",
                    "selection_confidence": "high",
                    "selected_optional_reviewers": [
                        {"name": "numerical_auditor"},
                        {"name": "claim_evidence_auditor"},
                        {"name": "literature_auditor"},
                        {"name": "identification_auditor"},
                        {"name": "robustness_auditor"},
                        {"name": "sample_construction_auditor"},
                        {"name": "abstract_conclusion_consistency_auditor"},
                        {"name": "limitations_external_validity_auditor"},
                        {"name": "model_equation_auditor"},
                        {"name": "data_availability_replication_auditor"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (editor_dir / "normalized_bundle.json").write_text(
            json.dumps(
                {
                    "source_reviewer_outputs": [
                        {"reviewer": "data_availability_replication_auditor", "finding_count": 0}
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.addCleanup(lambda: (selection_dir / "reviewer_selection.json").exists() and (selection_dir / "reviewer_selection.json").unlink())
        self.addCleanup(lambda: (editor_dir / "normalized_bundle.json").exists() and (editor_dir / "normalized_bundle.json").unlink())

        metrics = selector_metrics(selection_dir, editor_dir)

        self.assertEqual(metrics["selected_optional_count"], 10)
        self.assertEqual(metrics["pilot_selected"], ["data_availability_replication_auditor"])
        self.assertEqual(metrics["zero_finding_selected_optional"], ["data_availability_replication_auditor"])
        self.assertEqual(metrics["score"], 86.0)

    def test_raw_caption_continuation_accepts_split_caption_but_not_notes(self) -> None:
        self.assertTrue(should_append_raw_caption_continuation("Table 1: Analysis when", "labels disagree"))
        self.assertTrue(should_append_raw_caption_continuation("Figure 2: Distribution of", "quality scores"))
        self.assertFalse(should_append_raw_caption_continuation("Table 1: Results", "Note: Standard errors"))
        self.assertFalse(should_append_raw_caption_continuation("Table 1: Results", "1.23 4.56 7.89"))
        self.assertFalse(should_append_raw_caption_continuation("Table 2: Model performances.", "in that it pushes"))

    def test_refresh_editor_require_paths_reports_missing_prerequisites(self) -> None:
        missing = self.config_path("missing_editor_prereq.json")

        with self.assertRaisesRegex(FileNotFoundError, "Editor refresh prerequisites"):
            require_paths({"normalized bundle": missing})

    def test_paper_run_paths_collects_runtime_locations(self) -> None:
        paths = paper_run_paths(REPO_ROOT, "paper-x")

        self.assertEqual(paths.parsed_dir, REPO_ROOT / "work" / "paper-x" / "parsed")
        self.assertEqual(paths.selected_reviewers_config_path.name, "selected_reviewers.json")
        self.assertEqual(paths.parser_repair_notes_path.name, "parser_repair_notes.md")
        self.assertEqual(paths.report_path, REPO_ROOT / "outputs" / "paper-x" / "report.md")

    def test_selector_prompt_contains_budget_and_pilot_gates(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "templates" / "reviewer_selection.txt").read_text(encoding="utf-8")

        self.assertIn("5 to 9 optional reviewers", prompt)
        self.assertIn("at most 2 pilot reviewers", prompt)
        self.assertIn("Use skipped_optional_reviewers", prompt)

    def test_preprocess_page_quality_summary_flags_low_text_and_order_instability(self) -> None:
        summary = page_quality_summary(
            [
                {
                    "pdf_page_number": 1,
                    "raw_text": "alpha\nbeta\ngamma\ndelta",
                    "normalized_text": "alpha\nbeta\ngamma\ndelta",
                    "likely_scanned": False,
                },
                {
                    "pdf_page_number": 2,
                    "raw_text": "a\nb\nc\nd\n",
                    "normalized_text": "\n".join(f"line {index} " + ("x" * 120) for index in range(10)),
                    "likely_scanned": False,
                },
            ]
        )

        self.assertEqual(summary["low_text_pages"], [1, 2])
        self.assertEqual(summary["suspicious_order_pages"], [2])
        self.assertIsNotNone(summary["raw_normalized_char_ratio_median"])

    def test_preprocess_page_quality_summary_separates_sparse_plausible_pages(self) -> None:
        summary = page_quality_summary(
            [
                {
                    "pdf_page_number": 3,
                    "raw_text": "Figure A.1: Screenshot of trading data\nNote: image-only evidence\n3",
                    "normalized_text": "Figure A.1: Screenshot of trading data\nNote: image-only evidence\n3",
                    "likely_scanned": False,
                }
            ]
        )

        self.assertEqual(summary["low_text_pages"], [])
        self.assertEqual(summary["sparse_plausible_pages"], [3])

    def test_portable_path_uses_absolute_path_when_outside_root(self) -> None:
        root = Path("C:/repo")
        inside = root / "work" / "paper"
        outside = Path("D:/other/work")

        self.assertEqual(portable_path(inside, root), "work/paper")
        self.assertEqual(portable_path(outside, root), str(outside))

    def test_parser_repair_plan_validation_and_notes(self) -> None:
        plan = {
            "paper_id": "paper-x",
            "run_status": "ok",
            "summary": "Prepared a parser repair overlay.",
            "repair_mode": "overlay",
            "repairs": [
                {
                    "parser_finding_id": "PARSER-001",
                    "issue_summary": "Table extraction is unreliable.",
                    "status": "repaired",
                    "action": "write_repaired_overlay_artifact",
                    "reviewer_guidance": "Use the repaired overlay CSV only after checking it against the page image.",
                    "preferred_source_paths": ["work/paper-x/repair/repaired_artifacts/table_1_repaired.csv"],
                    "avoid_source_paths": ["work/paper-x/parsed/tables/table_1.csv"],
                    "verification_steps": ["Compare the crop with the page image."],
                    "residual_risk": "Values still require visual verification.",
                    "repaired_artifacts": [
                        {
                            "filename": "table_1_repaired.csv",
                            "artifact_type": "table_csv",
                            "description": "Reviewer-safe reconstruction of Table 1.",
                            "content": "variable,value\nalpha,1\nbeta,2",
                            "source_paths": ["work/paper-x/parsed/page_images/page_001.png"],
                            "confidence": "medium",
                            "caveats": ["Reconstructed from page image evidence."],
                        }
                    ],
                }
            ],
            "reviewer_brief": "Use image fallback for Table 1.",
            "limitations": ["The overlay CSV does not replace deterministic table extraction."],
        }

        schema_path = REPO_ROOT / "schemas" / "parser_repair_plan.schema.json"
        self.assertEqual(validate_plan(plan, schema_path, "paper-x"), [])
        self.assertEqual(validate_artifact_filenames(plan), [])
        notes = repair_notes_markdown(plan)

        self.assertIn("PARSER-001", notes)
        self.assertIn("table_1_repaired.csv", notes)
        self.assertIn("work/paper-x/repair/repaired_artifacts/table_1_repaired.csv", notes)
        self.assertIn("The overlay CSV does not replace deterministic table extraction.", notes)

    def test_parser_repair_schema_is_strict_structured_output_compatible(self) -> None:
        schema = json.loads((REPO_ROOT / "schemas" / "parser_repair_plan.schema.json").read_text(encoding="utf-8"))

        self.assertEqual(strict_structured_output_schema_errors(schema), [])

    def test_parser_repair_plan_accepts_empty_repaired_artifacts(self) -> None:
        plan = {
            "paper_id": "paper-x",
            "run_status": "partial",
            "summary": "Prepared fallback guidance.",
            "repair_mode": "overlay",
            "repairs": [
                {
                    "parser_finding_id": "PARSER-002",
                    "issue_summary": "Page text is not in safe reading order.",
                    "status": "requires_reprocess",
                    "action": "requires_deterministic_preprocess_change",
                    "reviewer_guidance": "Use page images rather than normalized text for this table.",
                    "preferred_source_paths": ["work/paper-x/parsed/page_images/page_010.png"],
                    "avoid_source_paths": ["work/paper-x/parsed/pages/page_010.md"],
                    "verification_steps": ["Compare the normalized text with the page image."],
                    "residual_risk": "No faithful text overlay can be created from the parsed text.",
                    "repaired_artifacts": [],
                }
            ],
            "reviewer_brief": "Use page-image fallback for the affected table.",
            "limitations": ["Requires deterministic reprocessing for a real table repair."],
        }

        self.assertEqual(validate_plan(plan, REPO_ROOT / "schemas" / "parser_repair_plan.schema.json", "paper-x"), [])

    def test_parser_repair_writes_overlay_artifacts_and_manifest(self) -> None:
        output_dir = self.config_path("parser_repair_overlay_marker.txt").parent / "parser-repair-output"
        artifact_path = output_dir / "repaired_artifacts" / "table_1_repaired.csv"
        manifest_path = output_dir / "repair_manifest.json"
        self.addCleanup(self.cleanup_dir, output_dir)
        self.addCleanup(self.cleanup_dir, output_dir / "repaired_artifacts")
        self.addCleanup(lambda: manifest_path.exists() and manifest_path.unlink())
        self.addCleanup(lambda: artifact_path.exists() and artifact_path.unlink())
        plan = {
            "paper_id": "paper-x",
            "repair_mode": "overlay",
            "repairs": [
                {
                    "parser_finding_id": "PARSER-001",
                    "repaired_artifacts": [
                        {
                            "filename": "table_1_repaired.csv",
                            "artifact_type": "table_csv",
                            "description": "Reviewer-safe reconstruction of Table 1.",
                            "content": "variable,value\nalpha,1\nbeta,2\n",
                            "source_paths": ["work/paper-x/parsed/page_images/page_001.png"],
                            "confidence": "medium",
                            "caveats": ["Use only with the page image."],
                        }
                    ],
                }
            ],
        }

        manifest = write_repaired_artifacts(plan, output_dir, REPO_ROOT)

        self.assertEqual(artifact_path.read_text(encoding="utf-8"), "variable,value\nalpha,1\nbeta,2\n")
        self.assertEqual(manifest["artifact_count"], 1)
        self.assertEqual(manifest["artifacts"][0]["parser_finding_id"], "PARSER-001")
        self.assertIn("sha256", manifest["artifacts"][0])
        self.assertTrue(manifest_path.exists())

    def test_parser_repair_normalizes_overlay_mojibake(self) -> None:
        root = self.config_path("parser_repair_mojibake_marker.txt").parent
        source_path = root / "source_table.txt"
        output_dir = root / "parser-repair-mojibake-output"
        artifact_path = output_dir / "repaired_artifacts" / "table_1_repaired.csv"
        manifest_path = output_dir / "repair_manifest.json"
        self.addCleanup(self.cleanup_dir, output_dir)
        self.addCleanup(self.cleanup_dir, output_dir / "repaired_artifacts")
        self.addCleanup(lambda: manifest_path.exists() and manifest_path.unlink())
        self.addCleanup(lambda: artifact_path.exists() and artifact_path.unlink())
        self.addCleanup(lambda: source_path.exists() and source_path.unlink())
        source_path.write_text("Black × Discrimination -996.193∗∗∗\n", encoding="utf-8")
        plan = {
            "paper_id": "paper-x",
            "repair_mode": "overlay",
            "repairs": [
                {
                    "parser_finding_id": "PARSER-001",
                    "repaired_artifacts": [
                        {
                            "filename": "table_1_repaired.csv",
                            "artifact_type": "table_csv",
                            "description": "Reviewer-safe reconstruction of Table 1.",
                            "content": "row_label,column_1\nBlack Ã— Discrimination,-996.193âˆ—âˆ—âˆ—\n",
                            "source_paths": [str(source_path.relative_to(REPO_ROOT))],
                            "confidence": "medium",
                            "caveats": ["Use only with the source table."],
                        }
                    ],
                }
            ],
        }

        fixed, changed = repair_mojibake_text(plan["repairs"][0]["repaired_artifacts"][0]["content"])
        manifest = write_repaired_artifacts(plan, output_dir, REPO_ROOT)

        self.assertTrue(changed)
        self.assertLess(mojibake_score(fixed), mojibake_score("Black Ã— Discrimination,-996.193âˆ—âˆ—âˆ—"))
        self.assertIn("Black × Discrimination,-996.193∗∗∗", artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["quality_summary"]["normalized_mojibake_artifact_count"], 1)
        self.assertEqual(manifest["quality_summary"]["warning_count"], 0)
        self.assertTrue(manifest["artifacts"][0]["quality"]["normalized_mojibake"])
        self.assertEqual(manifest["artifacts"][0]["quality"]["mojibake_score_after"], 0)

    def test_parser_repair_normalizes_nul_codepoint_artifacts(self) -> None:
        root = self.config_path("parser_repair_control_marker.txt").parent
        output_dir = root / "parser-repair-control-output"
        artifact_path = output_dir / "repaired_artifacts" / "table_1_repaired.csv"
        manifest_path = output_dir / "repair_manifest.json"
        self.addCleanup(self.cleanup_dir, output_dir)
        self.addCleanup(self.cleanup_dir, output_dir / "repaired_artifacts")
        self.addCleanup(lambda: manifest_path.exists() and manifest_path.unlink())
        self.addCleanup(lambda: artifact_path.exists() and artifact_path.unlink())
        content = "row_label,column_1\nBlack \x00d7 Discrimination,-996.193\x002217\x002217\x002217\n"
        plan = {
            "paper_id": "paper-x",
            "repair_mode": "overlay",
            "repairs": [
                {
                    "parser_finding_id": "PARSER-001",
                    "repaired_artifacts": [
                        {
                            "filename": "table_1_repaired.csv",
                            "artifact_type": "table_csv",
                            "description": "Reviewer-safe reconstruction of Table 1.",
                            "content": content,
                            "source_paths": ["work/paper-x/parsed/tables/table_1.txt"],
                            "confidence": "medium",
                            "caveats": ["Use only with the source table."],
                        }
                    ],
                }
            ],
        }

        fixed, changed = repair_nul_codepoints(content)
        manifest = write_repaired_artifacts(plan, output_dir, REPO_ROOT)
        written = artifact_path.read_text(encoding="utf-8")

        self.assertTrue(changed)
        self.assertEqual(control_char_score(fixed), 0)
        self.assertIn("Black × Discrimination,-996.193∗∗∗", written)
        self.assertEqual(manifest["quality_summary"]["normalized_control_codepoint_artifact_count"], 1)
        self.assertEqual(manifest["quality_summary"]["warning_count"], 0)
        self.assertEqual(manifest["artifacts"][0]["quality"]["control_char_score_after"], 0)

    def test_parser_repair_evaluation_scores_coverage_and_guidance(self) -> None:
        parser_quality = {
            "findings": [
                {
                    "id": "PARSER-001",
                    "issue_type": "parser_artifact",
                    "severity": "medium",
                },
                {
                    "id": "PARSER-002",
                    "issue_type": "parser_artifact",
                    "severity": "low",
                },
            ]
        }
        plan = {
            "repairs": [
                {
                    "parser_finding_id": "PARSER-001",
                    "status": "repaired",
                    "action": "write_repaired_overlay_artifact",
                    "reviewer_guidance": "Use the repaired overlay artifact after checking it against the page image fallback.",
                    "preferred_source_paths": ["work/paper/repair/repaired_artifacts/table_1_repaired.csv"],
                }
            ]
        }

        metrics = evaluate_plan(parser_quality, plan)

        self.assertEqual(metrics["target_finding_count"], 1)
        self.assertEqual(metrics["covered_count"], 1)
        self.assertEqual(metrics["mitigated_count"], 1)
        self.assertEqual(metrics["score"], 100.0)

    def test_render_prompts_can_append_parser_repair_overlay(self) -> None:
        rendered = append_parser_repair_note("Audit:\n`work/paper/parsed`\n", "work/paper/repair/parser_repair_notes.md")

        self.assertIn("Parser repair overlay", rendered)
        self.assertIn("work/paper/repair/parser_repair_notes.md", rendered)
        self.assertIn("preferred fallback artifacts", rendered)

    def test_selector_prompt_can_include_parser_repair_overlay(self) -> None:
        prompt = render_selector_prompt(
            REPO_ROOT,
            "paper-x",
            REPO_ROOT / "work" / "paper-x" / "parsed",
            [reviewer_config("numerical_auditor", "NUM", selection_policy="optional")],
            REPO_ROOT / "schemas" / "reviewer_selection.schema.json",
            REPO_ROOT / "work" / "paper-x" / "repair" / "parser_repair_notes.md",
        )

        self.assertIn("Parser repair overlay available before reviewer selection", prompt)
        self.assertIn("parser_repair_notes.md", prompt)
        self.assertIn("verified fallback artifacts", prompt)


if __name__ == "__main__":
    unittest.main()
