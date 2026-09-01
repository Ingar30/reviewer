from __future__ import annotations

import json
import sys
import unittest
from unittest import mock
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
TEMP_ROOT = REPO_ROOT / "work" / "test-tmp"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_final_report import GRAMMAR_APPENDIX_HEADING, TRACEABILITY_APPENDIX_HEADING, report_failures, external_source_urls  # noqa: E402
from check_environment import REQUIRED_MODULES  # noqa: E402
from check_shareable_repo import private_tracking_violations  # noqa: E402
from check_tracked_sensitive_names import suspicious_files  # noqa: E402
from evaluate_prior_runs import aggregate, selector_metrics  # noqa: E402
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
from preprocess_pdf import (  # noqa: E402
    FIGURE_CAPTION_RE,
    TABLE_CAPTION_RE,
    align_positioned_glyph_repairs,
    apply_text_repairs,
    attach_captions_to_auto_tables,
    caption_table_quality,
    choose_normalized_text,
    disallowed_control_character_codes,
    extract_crossrefs,
    extract_reference_list,
    extract_sections,
    is_heading,
    join_text_chunks_preserving_hyphens,
    native_blocks_are_column_major,
    normalize_page_label,
    page_quality_summary,
    parse_captioned_table_rows,
    portable_path,
    positioned_numbered_headings,
    positioned_text_repair_plan,
    repaired_word_records,
    rect_overlap_ratio,
    should_append_caption_continuation,
    should_append_raw_caption_continuation,
    split_trailing_table_cells,
    structure_captioned_table_rows,
    table_region_below_caption,
    valid_crossref_label,
)
from pipeline_paths import paper_run_paths  # noqa: E402
from refresh_editor import require_paths  # noqa: E402
from review_paper import (  # noqa: E402
    codex_exec_command,
    extract_editor_report_from_transcript,
    finding_label,
    parser_quality_gate_findings,
    plausible_editor_report,
    recover_editor_report_if_needed,
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
        "finding_summary": "The reported percentage conflicts with Table 1.",
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

    def test_environment_check_requires_only_runtime_dependencies(self) -> None:
        self.assertEqual(
            REQUIRED_MODULES,
            ["fitz", "pdfplumber", "pandas", "jsonschema", "tabulate"],
        )

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

    def test_semantic_errors_validate_local_source_provenance(self) -> None:
        paper_id = "provenance-test"
        parsed_dir = REPO_ROOT / "work" / paper_id / "parsed"
        source_path = parsed_dir / "pages" / "page_001.md"
        manifest_path = parsed_dir / "manifest.json"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("verified source", encoding="utf-8")
        manifest_path.write_text(
            json.dumps({"summary": {"page_count": 2}}), encoding="utf-8"
        )
        self.addCleanup(self.cleanup_dir, REPO_ROOT / "work" / paper_id)
        self.addCleanup(self.cleanup_dir, parsed_dir)
        self.addCleanup(self.cleanup_dir, source_path.parent)
        self.addCleanup(self.cleanup_path, manifest_path)
        self.addCleanup(self.cleanup_path, source_path)

        item = finding(
            source_objects=[
                {
                    **finding()["source_objects"][0],
                    "path": f"work/{paper_id}/parsed/pages/page_001.md",
                    "page": 1,
                }
            ]
        )
        data = review_output([item])
        data["paper_id"] = paper_id

        self.assertEqual(semantic_errors(data, [reviewer_config()], repo=REPO_ROOT), [])

        item["source_objects"][0]["path"] = (
            f"work/{paper_id}/parsed/pages/page_001.md; work/{paper_id}/parsed/manifest.json"
        )
        errors = semantic_errors(data, [reviewer_config()], repo=REPO_ROOT)
        self.assertTrue(any("one file" in error for error in errors))

        item["source_objects"][0]["path"] = "README.md"
        errors = semantic_errors(data, [reviewer_config()], repo=REPO_ROOT)
        self.assertTrue(any("must stay under" in error for error in errors))

        source = item["source_objects"][0]
        source["type"] = "external"
        source["path"] = f"work/{paper_id}/parsed/pages/page_001.md"
        source["url"] = "https://example.com/source"
        errors = semantic_errors(data, [reviewer_config()], repo=REPO_ROOT)
        self.assertTrue(any("path must be null for external evidence" in error for error in errors))

        source["path"] = None
        source["url"] = None
        errors = semantic_errors(data, [reviewer_config()], repo=REPO_ROOT)
        self.assertTrue(any("url is required for external evidence" in error for error in errors))

        source["type"] = "text"
        source["url"] = "https://example.com/source"
        errors = semantic_errors(data, [reviewer_config()], repo=REPO_ROOT)
        self.assertTrue(any("path is required for parsed manuscript evidence" in error for error in errors))
        self.assertTrue(any("url must be null for parsed manuscript evidence" in error for error in errors))

    def test_parser_quality_gate_blocks_only_high_confidence_blockers(self) -> None:
        high_blocker = finding(
            id="PARSER-001",
            issue_type="parser_artifact",
            severity="high",
            confidence="high",
            assessment="yes",
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

    def test_validate_selection_output_requires_complete_optional_accounting(self) -> None:
        optional = [
            reviewer_config(
                "identification_auditor", "ID", selection_policy="optional"
            )
        ]
        selection = {
            "paper_id": "paper-x",
            "paper_type": "empirical_causal",
            "selection_confidence": "high",
            "selected_optional_reviewers": [],
            "skipped_optional_reviewers": [],
            "notes": [],
        }

        errors = validate_selection_output(selection, "paper-x", [], optional)

        self.assertTrue(any("neither selected nor skipped" in error for error in errors))

    def test_validate_selection_output_enforces_roster_and_pilot_caps(self) -> None:
        optional = [
            reviewer_config(f"optional_{index}", f"OPT{index}", selection_policy="optional")
            for index in range(14)
        ]
        selection = {
            "paper_id": "paper-x",
            "paper_type": "mixed",
            "selection_confidence": "high",
            "selected_optional_reviewers": [
                {"name": reviewer.name, "reason": "Distinct material cue."}
                for reviewer in optional
            ],
            "skipped_optional_reviewers": [],
            "notes": [],
        }

        errors = validate_selection_output(selection, "paper-x", [], optional)

        self.assertTrue(any("count exceeds 13" in error for error in errors))

        pilot_names = [
            "data_availability_replication_auditor",
            "institutional_context_auditor",
            "power_multiple_testing_auditor",
            "design_randomization_auditor",
            "economic_magnitude_auditor",
        ]
        pilots = [
            reviewer_config(name, f"PILOT{index}", selection_policy="optional")
            for index, name in enumerate(pilot_names)
        ]
        selection["selected_optional_reviewers"] = [
            {"name": reviewer.name, "reason": "Distinct material cue."} for reviewer in pilots
        ]
        errors = validate_selection_output(selection, "paper-x", [], pilots)
        self.assertTrue(any("pilot reviewer count exceeds 4" in error for error in errors))

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

    def test_codex_exec_command_can_override_model_and_reasoning(self) -> None:
        with mock.patch("review_paper.codex_command", return_value="codex"):
            self.assertEqual(
                codex_exec_command(
                    model="gpt-5.6-terra", reasoning_effort="max", search=True
                ),
                [
                    "codex",
                    "--search",
                    "--model",
                    "gpt-5.6-terra",
                    "-c",
                    'model_reasoning_effort="max"',
                    "exec",
                ],
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

    def test_should_not_merge_unrelated_numeric_findings_on_same_page(self) -> None:
        base = finding(
            category="numeric_error",
            finding_summary="The response-rate percentage is calculated incorrectly.",
            claim_text="The response rate is 39.6 percent.",
        )
        group = {
            "issue_class": "manuscript_issue",
            "source_reviewers": ["numerical_auditor"],
            "finding_summary": base["finding_summary"],
            "claim_text": base["claim_text"],
            "primary_quote": "39.6 percent",
            "locations": [base["location"]],
            "source_objects": [],
            "claim_evidence_links": [],
            "categories": [base["category"]],
        }
        unrelated = finding(
            id="NUM-002",
            category="numeric_error",
            finding_summary="A log coefficient is interpreted as an exact percentage change.",
            claim_text="The coefficient of 0.411 means an exact 41.1 percent increase.",
        )

        self.assertFalse(should_merge(group, "claim_evidence_auditor", unrelated, "manuscript_issue"))

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
                "A copyediting issue requires correction.",
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
                "A reference-integrity issue requires correction.",
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

    def test_report_checker_rejects_wrong_traceability_mapping_and_invented_url(self) -> None:
        bundle = {
            "canonical_findings": [
                {
                    "canonical_id": "CANON-001",
                    "source_findings": [{"reviewer": "numerical_auditor", "id": "NUM-001"}],
                },
                {
                    "canonical_id": "CANON-002",
                    "source_findings": [{"reviewer": "claim_evidence_auditor", "id": "CEA-001"}],
                },
            ]
        }
        report = "\n".join(
            [
                "# Multi-Agent Paper Review Report",
                "## Executive Summary",
                "A correction is needed. https://invented.example/source",
                "## Review Configuration",
                "The configured reviewers ran.",
                "## Highest-Priority Cross-Agent Findings",
                "One issue is material.",
                "## Suggested Revision Priorities",
                "Correct the claim.",
                "## Additional Findings",
                "No additional findings.",
                TRACEABILITY_APPENDIX_HEADING,
                "| Report section | Finding | Canonical ID | Source finding IDs |",
                "| Priority | first | CANON-001 | claim_evidence_auditor:CEA-001 |",
                "| Additional | second | CANON-002 | numerical_auditor:NUM-001 |",
            ]
        )

        failures = report_failures(report, bundle=bundle, min_chars=0)

        self.assertTrue(any("wrong canonical row" in failure for failure in failures))
        self.assertTrue(any("not present in reviewer evidence" in failure for failure in failures))

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
        self.assertEqual(metrics["score"], 92.0)

    def test_raw_caption_continuation_accepts_split_caption_but_not_notes(self) -> None:
        self.assertTrue(should_append_raw_caption_continuation("Table 1: Analysis when", "labels disagree"))
        self.assertTrue(should_append_raw_caption_continuation("Figure 2: Distribution of", "quality scores"))
        self.assertTrue(
            should_append_raw_caption_continuation(
                "Figure B.1: Validation across", "12,192 decisions and 32 codes"
            )
        )
        self.assertTrue(
            should_append_caption_continuation(
                "Figure B.1: Validation across", "12,192 decisions and 32 codes", 11.5
            )
        )
        self.assertFalse(should_append_raw_caption_continuation("Table 1: Results", "Note: Standard errors"))
        self.assertFalse(should_append_raw_caption_continuation("Table 1: Results", "1.23 4.56 7.89"))
        self.assertFalse(should_append_raw_caption_continuation("Table 2: Model performances.", "in that it pushes"))

    def test_caption_labels_accept_appendix_forms_with_or_without_periods(self) -> None:
        for text in ("Table A1: Overview", "Table A.1: Overview"):
            self.assertEqual(TABLE_CAPTION_RE.match(text).group("label"), text.split()[1][:-1])
        for text in ("Figure A31: Results", "Figure B.5: Results"):
            self.assertIsNotNone(FIGURE_CAPTION_RE.match(text))

        for kind in ("Table", "Figure", "Section", "Appendix", "Equation"):
            self.assertTrue(valid_crossref_label(kind, "A1"))
            self.assertTrue(valid_crossref_label(kind, "A.1"))

    def test_page_label_decodes_explicit_utf16_pdf_token(self) -> None:
        self.assertEqual(normalize_page_label("<FEFF0030>"), "0")
        self.assertEqual(normalize_page_label("<FEFF0041002E0031>"), "A.1")
        self.assertEqual(normalize_page_label("<NOTHEX>"), "<NOTHEX>")

    def test_positioned_text_repairs_are_font_and_coordinate_grounded(self) -> None:
        raw_dict = {
            "blocks": [
                {
                    "lines": [
                        {
                            "spans": [
                                {
                                    "font": "CMEX10",
                                    "size": 11.0,
                                    "chars": [
                                        {"c": "\x00", "bbox": [10, 10, 15, 21], "origin": [10, 19]},
                                        {"c": "\x01", "bbox": [20, 10, 25, 21], "origin": [20, 19]},
                                        {"c": "h", "bbox": [30, 10, 35, 21], "origin": [30, 19]},
                                        {"c": "i", "bbox": [40, 10, 45, 21], "origin": [40, 19]},
                                        {"c": "(", "bbox": [50, 10, 55, 21], "origin": [50, 19]},
                                    ],
                                }
                            ]
                        },
                        {
                            "spans": [
                                {
                                    "font": "NimbusRomNo9L-Regu",
                                    "size": 10.0,
                                    "chars": [
                                        {"c": "R", "bbox": [25, 30, 30, 40], "origin": [25, 38]},
                                        {"c": "\u00b4", "bbox": [31, 30, 34, 40], "origin": [31, 38]},
                                        {"c": "e", "bbox": [30.5, 30, 35, 40], "origin": [30.5, 38]},
                                    ],
                                }
                            ]
                        },
                        {
                            "spans": [
                                {
                                    "font": "NimbusRomNo9L-Regu",
                                    "size": 10.0,
                                    "chars": [
                                        {"c": "I", "bbox": [35, 45, 39, 55], "origin": [35, 53]},
                                        {"c": "\u02dc", "bbox": [39.5, 45, 43, 55], "origin": [39.5, 53]},
                                        {"c": "n", "bbox": [39, 45, 44, 55], "origin": [39, 53]},
                                    ],
                                }
                            ]
                        },
                        {
                            "spans": [
                                {
                                    "font": "PiCUP10",
                                    "size": 10.0,
                                    "chars": [
                                        {"c": "\x02", "bbox": [40, 30, 45, 40], "origin": [40, 38]}
                                    ],
                                }
                            ]
                        },
                        {
                            "spans": [
                                {
                                    "font": "NimbusRomNo9L-Regu",
                                    "size": 10.0,
                                    "chars": [
                                        {"c": "h", "bbox": [60, 50, 65, 60], "origin": [60, 58]}
                                    ],
                                }
                            ]
                        },
                        {
                            "spans": [
                                {
                                    "font": "CMEX10",
                                    "size": 10.0,
                                    "chars": [
                                        {"c": "X", "bbox": [70, 70, 75, 80], "origin": [70, 78]},
                                        {"c": " ", "bbox": [76, 70, 80, 80], "origin": [76, 78]},
                                        {"c": "", "bbox": [81, 70, 81, 80], "origin": [81, 78]},
                                    ],
                                }
                            ]
                        },
                    ]
                }
            ]
        }

        repairs, summary = positioned_text_repair_plan(raw_dict)
        positioned, positioned_count = align_positioned_glyph_repairs(
            summary["_native_positioned_text"],
            summary["_native_positioned_text"],
            summary["_native_positioned_repairs"],
        )
        repaired = apply_text_repairs(positioned, repairs)
        words, word_count = repaired_word_records(
            [
                [30, 10, 35, 21, "h", 0, 0, 0],
                [60, 50, 65, 60, "h", 0, 3, 0],
            ],
            repairs,
            summary["_coordinate_glyph_repairs"],
        )

        self.assertEqual(repaired, "()[]{\nR\u00e9\nI\u00f1\n\x02\nh\nX \n")
        self.assertEqual(positioned_count, 5)
        self.assertEqual([word[4] for word in words], ["[", "h"])
        self.assertEqual(word_count, 1)
        self.assertEqual(summary["known_font_glyph_repair_count"], 5)
        self.assertEqual(summary["positioned_font_glyph_repair_count"], 5)
        self.assertEqual(summary["positioned_accent_composition_count"], 2)
        self.assertEqual(summary["unresolved_math_glyph_count"], 2)
        self.assertEqual(
            summary["unresolved_math_glyph_codes"],
            ["CMEX10:U+0020", "CMEX10:U+0058"],
        )
        self.assertEqual(disallowed_control_character_codes(repaired), ["U+0002"])

    def test_structured_line_join_preserves_observed_hyphens(self) -> None:
        self.assertEqual(
            join_text_chunks_preserving_hyphens(["Sentence-", "BERT embeddings"]),
            "Sentence-BERT embeddings",
        )
        self.assertEqual(
            join_text_chunks_preserving_hyphens(["example sum-", "maries"]),
            "example sum-maries",
        )

    def test_section_inventory_pairs_position_verified_number_and_title(self) -> None:
        positioned_lines = [
            {"text": "2", "bbox": [307, 253, 313, 266], "is_bold": True},
            {"text": "Background", "bbox": [325, 253, 390, 266], "is_bold": True},
            {"text": "2.1", "bbox": [307, 275, 321, 286], "is_bold": True},
            {"text": "Manual Evaluation", "bbox": [332, 275, 430, 286], "is_bold": True},
            {"text": "3.4.1", "bbox": [307, 350, 329, 361], "is_bold": True},
            {"text": "LSA and Doc2vec", "bbox": [340, 350, 423, 361], "is_bold": True},
            {"text": "5", "bbox": [90, 107, 95, 117], "is_bold": False},
        ]
        page = {
            "pdf_page_number": 2,
            "normalized_text": (
                "2\nBackground\nBody text.\n2.1\nManual Evaluation\nMore text.\n"
                "3.4.1\nLSA and Doc2vec\nDetails.\n"
            ),
            "positioned_lines": positioned_lines,
        }

        candidates = positioned_numbered_headings(positioned_lines)
        sections = extract_sections([page])

        expected = ["2 Background", "2.1 Manual Evaluation", "3.4.1 LSA and Doc2vec"]
        self.assertEqual([item["heading"] for item in candidates], expected)
        self.assertEqual([item["heading"] for item in sections], expected)

    def test_crossref_inventory_handles_series_and_cross_page_word_break(self) -> None:
        pages = [
            {
                "pdf_page_number": 7,
                "page_label": "7",
                "normalized_text": "See Sections 3.1 and 3.2. Examples appear in Ap-\n",
                "raw_text": "",
            },
            {
                "pdf_page_number": 8,
                "page_label": "8",
                "normalized_text": "Figure 4: Results\npendix A. Their scores follow.\n",
                "raw_text": "",
            },
        ]

        crossrefs = extract_crossrefs(pages)
        indexed = {(item["page"], item["kind"].lower(), item["label"]): item for item in crossrefs}

        self.assertIn((7, "sections", "3.1"), indexed)
        self.assertIn((7, "sections", "3.2"), indexed)
        self.assertEqual(indexed[(7, "appendix", "A")]["source"], "cross_page_hyphenated_reference")

    def test_parser_warning_label_uses_finding_summary(self) -> None:
        self.assertEqual(
            finding_label(
                {
                    "id": "PARSER-001",
                    "finding_summary": "Equation delimiters are unresolved.",
                    "claim_text": "Equation delimiters are preserved.",
                }
            ),
            "PARSER-001: Equation delimiters are unresolved.",
        )

    def test_refresh_editor_require_paths_reports_missing_prerequisites(self) -> None:
        missing = self.config_path("missing_editor_prereq.json")

        with self.assertRaisesRegex(FileNotFoundError, "Editor refresh prerequisites"):
            require_paths({"normalized bundle": missing})

    def test_paper_run_paths_collects_runtime_locations(self) -> None:
        paths = paper_run_paths(REPO_ROOT, "paper-x")

        self.assertEqual(paths.parsed_dir, REPO_ROOT / "work" / "paper-x" / "parsed")
        self.assertEqual(paths.selected_reviewers_config_path.name, "selected_reviewers.json")
        self.assertEqual(paths.report_path, REPO_ROOT / "outputs" / "paper-x" / "report.md")
        self.assertEqual(paths.run_manifest_path, REPO_ROOT / "work" / "paper-x" / "run_manifest.json")

    def test_selector_prompt_contains_budget_and_pilot_gates(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "templates" / "reviewer_selection.txt").read_text(encoding="utf-8")

        self.assertIn("7 to 13 optional reviewers", prompt)
        self.assertIn("up to 4 pilot reviewers", prompt)
        self.assertIn("treat this audit as distinct", prompt)
        self.assertIn("Numerical and robustness review are not substitutes", prompt)
        self.assertIn("whenever a manuscript reports and interprets a substantive experiment", prompt)
        self.assertIn("not redundant", prompt)
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

    def test_preprocess_quality_flags_ocr_and_reading_order_review(self) -> None:
        summary = page_quality_summary(
            [
                {
                    "pdf_page_number": 7,
                    "raw_text": "short native text",
                    "normalized_text": "short native text",
                    "likely_scanned": False,
                    "ocr_recommended": True,
                    "two_column_detected": True,
                    "landscape": False,
                    "raw_sorted_similarity": 0.5,
                    "unresolved_math_glyph_count": 1,
                }
            ]
        )

        self.assertEqual(summary["ocr_recommended_pages"], [7])
        self.assertEqual(summary["two_column_pages"], [7])
        self.assertEqual(summary["reading_order_review_pages"], [7])
        self.assertEqual(summary["unresolved_math_glyph_pages"], [7])

    def test_two_column_normalization_uses_verified_native_column_order(self) -> None:
        blocks = [
            [60, 50, 280, 300, "left column", 0, 0],
            [315, 50, 535, 300, "right column", 1, 0],
        ]

        self.assertTrue(native_blocks_are_column_major(blocks, 595))
        text, strategy = choose_normalized_text(
            "left column\nright column",
            "left right interleaved",
            blocks,
            595,
            True,
        )
        self.assertEqual(text, "left column\nright column")
        self.assertEqual(strategy, "native_content_order_two_column")

    def test_two_column_normalization_rejects_native_column_reentry(self) -> None:
        blocks = [
            [60, 50, 280, 100, "left one", 0, 0],
            [315, 50, 535, 100, "right", 1, 0],
            [60, 120, 280, 180, "left two", 2, 0],
        ]

        self.assertFalse(native_blocks_are_column_major(blocks, 595))
        text, strategy = choose_normalized_text("native", "sorted", blocks, 595, True)
        self.assertEqual(text, "sorted")
        self.assertEqual(strategy, "coordinate_sorted")

    def test_landscape_normalization_prefers_native_order_when_sorting_is_unstable(self) -> None:
        raw = "Figure B.5\nPanel A\nSupport tariffs\nPanel B\nOppose tariffs"
        sorted_text = "Support Panel Oppose B.5 tariffs Figure Panel tariffs A B"

        text, strategy = choose_normalized_text(
            raw,
            sorted_text,
            [],
            792,
            False,
            landscape=True,
        )

        self.assertEqual(text, raw)
        self.assertEqual(strategy, "native_content_order_landscape")

    def test_normalization_prefers_repaired_native_text_when_sorted_alignment_fails(self) -> None:
        text, strategy = choose_normalized_text(
            "native with []",
            "sorted with hi",
            [],
            595,
            False,
            {
                "positioned_font_glyph_repair_count": 2,
                "raw_positioned_glyph_repair_applied_count": 2,
                "sorted_positioned_glyph_repair_applied_count": 0,
            },
        )

        self.assertEqual(text, "native with []")
        self.assertEqual(strategy, "native_content_order_font_fidelity")

        quality = page_quality_summary(
            [
                {
                    "pdf_page_number": 9,
                    "raw_text": "native with []",
                    "normalized_text": "native with []",
                    "likely_scanned": False,
                    "normalized_text_strategy": strategy,
                    "raw_sorted_similarity": 0.6,
                }
            ]
        )
        self.assertEqual(quality["font_fidelity_order_fallback_pages"], [9])
        self.assertEqual(quality["reading_order_review_pages"], [9])

    def test_heading_filter_rejects_chart_and_body_fragments(self) -> None:
        self.assertFalse(is_heading("0.87 Prefer more tangible assets Tax on consumers 0.39"))
        self.assertFalse(is_heading("x. By the principle of state-wise dominance"))
        self.assertFalse(is_heading("EP EP"))
        self.assertTrue(is_heading("4 Results"))
        self.assertTrue(is_heading("IV. Robustness Checks"))

    def test_table_cells_preserve_signs_percentages_and_pairs(self) -> None:
        label, cells = split_trailing_table_cells(
            "Estimated effects −0.68 94.8%*** (0.21)*** (5, 1)"
        )

        self.assertEqual(label, "Estimated effects")
        self.assertEqual(cells, ["−0.68", "94.8%***", "(0.21)***", "(5, 1)"])

        spaced_label, spaced_cells = split_trailing_table_cells("Treatment 6.2 % 100 %")
        self.assertEqual(spaced_label, "Treatment")
        self.assertEqual(spaced_cells, ["6.2 %", "100 %"])

        header_label, header_cells = split_trailing_table_cells("Model Loss Acc. F1")
        self.assertEqual(header_label, "Model Loss Acc. F1")
        self.assertEqual(header_cells, [])

        missing_label, missing_cells = split_trailing_table_cells("LSA - 0.726 0.755")
        self.assertEqual(missing_label, "LSA")
        self.assertEqual(missing_cells, ["-", "0.726", "0.755"])

    def test_table_region_prefers_numeric_rows_below_caption_and_stops_at_note(self) -> None:
        page = mock.Mock()
        page.rect = fitz.Rect(0, 0, 600, 800)
        lines = [
            {"text": "(1) (2)", "bbox": [220, 105, 380, 115], "is_page_footer": False},
            {
                "text": "Treatment -0.547*** 0.219**",
                "bbox": [70, 125, 530, 137],
                "is_page_footer": False,
            },
            {
                "text": "Constant 0.319*** 0.044***",
                "bbox": [70, 145, 530, 157],
                "is_page_footer": False,
            },
            {"text": "Note: Robust standard errors.", "bbox": [70, 170, 530, 182], "is_page_footer": False},
        ]

        region = table_region_below_caption(page, lines, [60, 70, 540, 88])

        self.assertIsNotNone(region)
        self.assertIn("Treatment -0.547*** 0.219**", region["raw_lines"])
        self.assertNotIn("Note: Robust standard errors.", region["raw_lines"])
        self.assertLess(region["crop_bbox"][3], 170)

    def test_reference_inventory_uses_hanging_indents_and_stops_at_appendix(self) -> None:
        page = {
            "pdf_page_number": 9,
            "page_label": "9",
            "page_width": 595.0,
            "positioned_lines": [
                {"text": "References", "bbox": [72, 490, 130, 502], "is_page_footer": False},
                {"text": "Ada Author and Ben Writer. 2024.", "bbox": [72, 512, 290, 523], "is_page_footer": False},
                {"text": "A careful paper.", "bbox": [83, 524, 180, 535], "is_page_footer": False},
                {"text": "Cara Scholar. 2025. Another paper.", "bbox": [72, 545, 290, 556], "is_page_footer": False},
                {"text": "Appendix A. Materials", "bbox": [307, 566, 520, 577], "is_page_footer": False},
            ],
        }

        references = extract_reference_list([page])

        self.assertEqual(len(references), 2)
        self.assertIn("A careful paper", references[0]["text"])
        self.assertEqual(references[1]["text"], "Cara Scholar. 2025. Another paper.")

    def test_reference_inventory_keeps_wide_single_column_continuations(self) -> None:
        page = {
            "pdf_page_number": 25,
            "page_label": "25",
            "page_width": 595.0,
            "positioned_lines": [
                {"text": "References", "bbox": [71, 650, 162, 662], "is_page_footer": False},
                {"text": "Ada Author (2024): A long title ending with", "bbox": [71, 686, 524, 698], "is_page_footer": False},
                {"text": "the journal name and page range.", "bbox": [83, 710, 524, 722], "is_page_footer": False},
                {"text": "Ben Writer (2025): Another paper.", "bbox": [71, 740, 524, 752], "is_page_footer": False},
                {"text": "A Additional Figures and Tables", "bbox": [71, 770, 361, 782], "is_page_footer": False},
            ],
        }

        references = extract_reference_list([page])

        self.assertEqual(len(references), 2)
        self.assertIn("journal name and page range", references[0]["text"])

    def test_caption_table_parser_stops_before_following_section(self) -> None:
        rows = parse_captioned_table_rows(
            [
                "Table 4: Treatments and sample sizes",
                "Baseline 993 1,023",
                "3.2 Implementation and Sample",
                "The experiment was conducted in three studies.",
            ]
        )
        status, flags = caption_table_quality(rows)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_text"], "Baseline 993 1,023")
        self.assertEqual(status, "caption_text_needs_visual_verification")
        self.assertEqual(flags, [])

    def test_caption_table_parser_promotes_exact_semantic_headers(self) -> None:
        rows = parse_captioned_table_rows(
            [
                "Model Ex. 1 Ex. 2 Ex. 3",
                "Baseline 0.24 -0.68 0.32",
                "Alternative 0.46 -0.54 0.28",
            ]
        )

        columns, csv_rows, structured_rows, promoted = structure_captioned_table_rows(rows)

        self.assertTrue(promoted)
        self.assertEqual(columns, ["Model", "Ex. 1", "Ex. 2", "Ex. 3"])
        self.assertEqual(len(structured_rows), 2)
        self.assertEqual(csv_rows[0], ["Baseline", "0.24", "-0.68", "0.32"])

    def test_native_table_candidate_inside_figure_is_suppressed_by_overlap_rule(self) -> None:
        candidate = [80.0, 54.0, 282.0, 226.0]
        figure = [67.0, 42.0, 295.0, 251.0]
        adjacent = [300.0, 42.0, 550.0, 251.0]

        self.assertEqual(rect_overlap_ratio(candidate, figure), 1.0)
        self.assertEqual(rect_overlap_ratio(candidate, adjacent), 0.0)

    def test_auto_table_keeps_matching_caption_and_unmatched_fallback(self) -> None:
        captions = [
            {
                "page": 2,
                "label": "1",
                "caption": "Table 1: Main estimates",
                "caption_source": "word_lines",
                "caption_bbox": [10, 100, 300, 120],
                "crop_bbox": [10, 90, 300, 300],
            },
            {
                "page": 3,
                "label": "2",
                "caption": "Table 2: Robustness",
                "caption_source": "word_lines",
                "caption_bbox": [10, 100, 300, 120],
                "crop_bbox": [10, 90, 300, 300],
            },
        ]
        auto_tables = [
            {
                "page": 2,
                "bbox": [20, 130, 290, 280],
                "status": "auto_extracted_needs_visual_verification",
            }
        ]

        matched = attach_captions_to_auto_tables(captions, auto_tables)

        self.assertEqual(matched, {0})
        self.assertEqual(auto_tables[0]["table_label"], "1")
        self.assertEqual(auto_tables[0]["caption"], "Table 1: Main estimates")

    def test_portable_path_uses_absolute_path_when_outside_root(self) -> None:
        root = Path("C:/repo")
        inside = root / "work" / "paper"
        outside = Path("D:/other/work")

        self.assertEqual(portable_path(inside, root), "work/paper")
        self.assertEqual(portable_path(outside, root), str(outside))

if __name__ == "__main__":
    unittest.main()
