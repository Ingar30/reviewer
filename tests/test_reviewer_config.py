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

from check_final_report import (  # noqa: E402
    GRAMMAR_APPENDIX_HEADING,
    TRACEABILITY_APPENDIX_HEADING,
    external_source_urls,
    report_failures,
    urls_in_text,
)
from check_environment import REQUIRED_MODULES  # noqa: E402
from check_shareable_repo import private_tracking_violations  # noqa: E402
from check_tracked_sensitive_names import suspicious_files  # noqa: E402
from evaluate_prior_runs import aggregate, selector_metrics  # noqa: E402
from build_editor_input import (  # noqa: E402
    ADDITIONAL_FINDINGS_SECTION,
    BIBLIOGRAPHY_APPENDIX_SECTION,
    GRAMMAR_APPENDIX_SECTION,
    HIGHEST_PRIORITY_SECTION,
    MAX_EDITOR_INPUT_BYTES,
    PARSER_SECTION,
    REFERENCE_SECTION,
    bounded_editor_input,
    editor_input_document,
    editor_brief_markdown,
    finding_score,
    requires_body_coverage,
    route_finding,
)
from normalize_review_outputs import group_merge_score, issue_class, normalize, numeric_signature, should_merge  # noqa: E402
from preprocess_pdf import (  # noqa: E402
    FIGURE_CAPTION_RE,
    TABLE_CAPTION_RE,
    align_positioned_glyph_repairs,
    apply_reconciled_geometric_page_label_artifacts,
    apply_text_repairs,
    attach_captions_to_auto_tables,
    caption_column_bounds,
    caption_table_quality,
    caption_match,
    choose_normalized_text,
    disallowed_control_character_codes,
    extract_crossrefs,
    extract_citations,
    extract_reference_list,
    extract_sections,
    figure_render_crop_bbox,
    infer_page_label_from_words,
    is_heading,
    join_text_chunks_preserving_hyphens,
    label_only_table_title,
    merge_reference_line_fragments,
    native_blocks_are_column_major,
    normalize_page_label,
    normalize_page_text,
    page_quality_summary,
    page_label_ordinal,
    page_label_layout_artifacts,
    parse_captioned_table_rows,
    portable_path,
    positioned_numbered_headings,
    positioned_text_repair_plan,
    repaired_word_records,
    reconcile_geometric_page_labels,
    remove_layout_artifact_text,
    repeated_layout_artifacts,
    rect_overlap_ratio,
    save_tables,
    should_append_caption_continuation,
    should_append_raw_caption_continuation,
    supported_caption_match,
    split_trailing_table_cells,
    structure_captioned_table_rows,
    table_candidate_is_excluded,
    table_region_below_caption,
    valid_crossref_label,
)
from pipeline_paths import paper_run_paths  # noqa: E402
from refresh_editor import require_paths  # noqa: E402
from review_paper import (  # noqa: E402
    REASONING_EFFORT_CHOICES,
    REVIEWER_SELECTION_MODE,
    codex_exec_command,
    enforce_conservative_applicability,
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
                "source_consistency_auditor",
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
                "theory_logic_auditor",
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
        self.assertEqual(
            next(item for item in reviewers if item.name == "source_consistency_auditor").selection_policy,
            "mandatory",
        )
        self.assertEqual(
            next(item for item in reviewers if item.name == "claim_evidence_auditor").selection_policy,
            "mandatory",
        )
        self.assertEqual(
            next(item for item in reviewers if item.name == "literature_auditor").selection_policy,
            "mandatory",
        )
        self.assertEqual(
            next(
                item
                for item in reviewers
                if item.name == "abstract_conclusion_consistency_auditor"
            ).selection_policy,
            "mandatory",
        )
        self.assertEqual(
            next(item for item in reviewers if item.name == "model_equation_auditor").selection_policy,
            "mandatory",
        )
        self.assertEqual(next(item for item in reviewers if item.name == "numerical_auditor").selection_policy, "optional")
        self.assertEqual(
            next(item for item in reviewers if item.name == "theory_logic_auditor").selection_policy,
            "optional",
        )
        self.assertEqual(REVIEWER_SELECTION_MODE, "applicability")
        self.assertNotIn("minimal", REASONING_EFFORT_CHOICES)
        selection_schema = json.loads(
            (REPO_ROOT / "schemas" / "reviewer_selection.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            selection_schema["properties"]["selection_mode"]["enum"],
            ["applicability"],
        )
        self.assertIn("selection_mode", selection_schema["required"])

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
            "selection_mode": "applicability",
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
            "selection_mode": "applicability",
            "selected_optional_reviewers": [],
            "skipped_optional_reviewers": [],
            "notes": [],
        }

        errors = validate_selection_output(selection, "paper-x", [], optional)

        self.assertTrue(any("neither selected nor skipped" in error for error in errors))

    def test_validate_selection_output_allows_full_conditional_roster(self) -> None:
        optional = [
            reviewer_config(f"optional_{index}", f"OPT{index}", selection_policy="optional")
            for index in range(14)
        ]
        selection = {
            "paper_id": "paper-x",
            "paper_type": "mixed",
            "selection_confidence": "high",
            "selection_mode": "applicability",
            "selected_optional_reviewers": [
                {"name": reviewer.name, "reason": "Distinct material cue."}
                for reviewer in optional
            ],
            "skipped_optional_reviewers": [],
            "notes": [],
        }

        errors = validate_selection_output(selection, "paper-x", [], optional)

        self.assertEqual(errors, [])

    def test_conservative_applicability_expands_uncertain_selection(self) -> None:
        optional = [
            reviewer_config("numerical_auditor", "NUM", selection_policy="optional"),
            reviewer_config("theory_logic_auditor", "THEORY", selection_policy="optional"),
        ]
        selection = {
            "paper_id": "paper-x",
            "paper_type": "empirical_causal",
            "selection_confidence": "medium",
            "selection_mode": "applicability",
            "selected_optional_reviewers": [
                {"name": "numerical_auditor", "reason": "The paper reports estimates."}
            ],
            "skipped_optional_reviewers": [
                {"name": "theory_logic_auditor", "reason": "No formal model was found."}
            ],
            "notes": [],
        }

        guarded = enforce_conservative_applicability(selection, optional)

        self.assertEqual(
            [item["name"] for item in guarded["selected_optional_reviewers"]],
            ["numerical_auditor", "theory_logic_auditor"],
        )
        self.assertEqual(guarded["skipped_optional_reviewers"], [])
        self.assertIn("expanded an uncertain classification", guarded["notes"][-1])
        self.assertEqual(len(selection["selected_optional_reviewers"]), 1)

    def test_conservative_applicability_requires_theory_specialist(self) -> None:
        optional = [
            reviewer_config("numerical_auditor", "NUM", selection_policy="optional"),
            reviewer_config("theory_logic_auditor", "THEORY", selection_policy="optional"),
        ]
        selection = {
            "paper_id": "paper-x",
            "paper_type": "theory",
            "selection_confidence": "high",
            "selection_mode": "applicability",
            "selected_optional_reviewers": [],
            "skipped_optional_reviewers": [
                {"name": "numerical_auditor", "reason": "No material quantitative claims."},
                {"name": "theory_logic_auditor", "reason": "Incorrectly skipped."},
            ],
            "notes": [],
        }

        guarded = enforce_conservative_applicability(selection, optional)

        self.assertEqual(
            [item["name"] for item in guarded["selected_optional_reviewers"]],
            ["theory_logic_auditor"],
        )
        self.assertEqual(
            [item["name"] for item in guarded["skipped_optional_reviewers"]],
            ["numerical_auditor"],
        )

    def test_validate_selection_output_rejects_legacy_modes(self) -> None:
        selection = {
            "paper_id": "paper-x",
            "paper_type": "theory",
            "selection_confidence": "high",
            "selection_mode": "static",
            "selected_optional_reviewers": [],
            "skipped_optional_reviewers": [],
            "notes": [],
        }

        errors = validate_selection_output(selection, "paper-x", [], [])

        self.assertTrue(any("must be 'applicability'" in error for error in errors))

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
                    model="test-model", reasoning_effort="max", search=True
                ),
                [
                    "codex",
                    "--search",
                    "--model",
                    "test-model",
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
        output = review_output([finding()], run_status="partial")
        output["summary"] = "The reviewer could not verify one appendix result."
        output["notes"] = ["Appendix source was unavailable.", "No files were edited."]
        (reviews_dir / reviewer.output).write_text(json.dumps(output), encoding="utf-8")
        self.addCleanup(lambda: (reviews_dir / reviewer.output).exists() and (reviews_dir / reviewer.output).unlink())

        bundle = normalize("paper-x", reviews_dir, [reviewer])
        group = bundle["canonical_findings"][0]
        reviewer_output = bundle["source_reviewer_outputs"][0]

        self.assertEqual(group["confidence"], "high")
        self.assertEqual(group["source_objects"][0]["source_object"]["id"], "SRC-001")
        self.assertEqual(group["claim_evidence_links"][0]["link"]["relation"], "contradicts")
        self.assertEqual(group["numeric_checks"][0]["numeric_check"]["expected_value"], "12%")
        self.assertEqual(group["source_finding_details"][0]["id"], "NUM-001")
        self.assertEqual(
            group["source_finding_details"][0]["finding_summary"],
            "The reported percentage conflicts with Table 1.",
        )
        self.assertEqual(
            reviewer_output["summary"],
            "The reviewer could not verify one appendix result.",
        )
        self.assertEqual(reviewer_output["notes"], ["Appendix source was unavailable."])
        self.assertEqual(bundle["summary"]["process_notes_removed"], 1)
        self.assertEqual(
            group["source_finding_details"][0]["claim_text"],
            "The value is 10%.",
        )

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

    def test_shared_source_object_does_not_force_semantic_merge(self) -> None:
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
        distinct = finding(
            finding_summary="Table 1 does not define the analysis sample.",
            claim_text="Table 1 reports estimates for the full sample.",
            source_objects=[base["source_objects"][0]],
        )

        self.assertFalse(should_merge(group, "claim_evidence_auditor", distinct, "manuscript_issue"))

    def test_should_merge_clear_cross_reviewer_paraphrases(self) -> None:
        base = finding(
            finding_summary="The paper does not establish that expressive opposition causes more backlash than deterrence.",
            claim_text="Backlash is driven more by expressive opposition than by deterrence.",
        )
        group = {
            "issue_class": "manuscript_issue",
            "source_reviewers": ["claim_evidence_auditor"],
            "finding_summary": base["finding_summary"],
            "claim_text": base["claim_text"],
            "primary_quote": "expressive opposition rather than deterrence",
            "primary_location": base["location"],
            "locations": [base["location"]],
            "source_objects": [],
            "claim_evidence_links": [],
            "categories": [base["category"]],
        }
        paraphrase = finding(
            id="ROB-001",
            finding_summary="The evidence cannot show that expressive opposition is a larger driver of backlash than deterrence.",
            claim_text="Expressive opposition drives backlash more than deterrence does.",
        )

        self.assertTrue(should_merge(group, "robustness_auditor", paraphrase, "manuscript_issue"))
        self.assertFalse(
            should_merge(group, "claim_evidence_auditor", paraphrase, "manuscript_issue")
        )

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

    def test_should_not_merge_conflicting_explicit_corrections(self) -> None:
        def group_for(summary: str) -> dict[str, object]:
            base = finding(finding_summary=summary, claim_text=summary)
            return {
                "issue_class": "manuscript_issue",
                "source_reviewers": ["numerical_auditor"],
                "finding_summary": summary,
                "claim_text": summary,
                "primary_location": base["location"],
                "locations": [base["location"]],
                "source_objects": [],
                "claim_evidence_links": [],
                "categories": [base["category"]],
            }

        conflicts = [
            (
                "The coefficient should be \u22120.12, not +0.12.",
                "The coefficient should be +0.12, not \u22120.12.",
            ),
            (
                "The regression excludes 1,009 respondents without explanation.",
                "The regression excludes 2,009 respondents without explanation.",
            ),
            (
                "Column 1 reverses the coefficient sign.",
                "Column 2 reverses the coefficient sign.",
            ),
            (
                "Column 1 reports a negative coefficient.",
                "Column 1 reports a positive coefficient.",
            ),
            (
                "The corrected response rate is 5%, not 10%.",
                "The corrected response rate is 5%, not 15%.",
            ),
            (
                "The manuscript reports 5%; the corrected value is 10%.",
                "The manuscript reports 10%; the corrected value is 5%.",
            ),
            (
                "Table S8 uses the wrong treatment-arm label.",
                "Table S9 uses the wrong treatment-arm label.",
            ),
        ]
        for index, (left, right) in enumerate(conflicts, start=1):
            with self.subTest(index=index):
                candidate = finding(
                    id=f"CEA-{index:03d}",
                    finding_summary=right,
                    claim_text=right,
                )
                self.assertFalse(
                    should_merge(
                        group_for(left),
                        "claim_evidence_auditor",
                        candidate,
                        "manuscript_issue",
                    )
                )

        same_correction = finding(
            id="CEA-100",
            finding_summary="The reported coefficient is -0.12 but should be +0.12.",
            claim_text="The reported coefficient is -0.12 but should be +0.12.",
        )
        self.assertTrue(
            should_merge(
                group_for("The coefficient is -0.12 but should be +0.12."),
                "claim_evidence_auditor",
                same_correction,
                "manuscript_issue",
            )
        )

        percent_wording = finding(
            id="CEA-101",
            finding_summary=(
                "The text reports 57.2 percent agreement, but Figure 4 displays 27 percent."
            ),
            claim_text="The reported agreement rate is 57.2 percent.",
        )
        self.assertTrue(
            should_merge(
                group_for("The text reports 57.2% agreement, but Figure 4 displays 27%."),
                "claim_evidence_auditor",
                percent_wording,
                "manuscript_issue",
            )
        )
        formula_wording = finding(
            id="NUM-101",
            finding_summary=(
                "The manuscript reports coefficients on log(1+kW) as percentage changes in kW, "
                "so its 8%, 13%, 10%, 6%, and 12% statements use the wrong scale."
            ),
            claim_text="The five coefficients imply changes of 8%, 13%, 10%, 6%, and 12%.",
        )
        self.assertTrue(
            should_merge(
                group_for(
                    "The manuscript interprets coefficients on log(1+kW) as percentage changes "
                    "in kW, although those coefficients require baseline kW for conversion."
                ),
                "model_equation_auditor",
                formula_wording,
                "manuscript_issue",
            )
        )
        model_identifier = finding(
            id="MODEL-102",
            finding_summary=(
                "The 2SLS coefficient is -1.03 in the prose but should be -1.11."
            ),
            claim_text="The 2SLS coefficient is -1.03 rather than -1.11.",
        )
        self.assertTrue(
            should_merge(
                group_for(
                    "The prose reports -1.03 for the 2SLS coefficient, but the table gives -1.11."
                ),
                "model_equation_auditor",
                model_identifier,
                "manuscript_issue",
            )
        )

    def test_numeric_signature_ignores_identifier_digits_and_keeps_terminal_values(self) -> None:
        self.assertEqual(
            numeric_signature("The 2SLS and 3D checks report -1.11."),
            [("1.11", "-")],
        )
        self.assertEqual(numeric_signature("The reported share is 27%."), [("27%", None)])

    def test_sparse_semantic_overlap_needs_independent_support(self) -> None:
        unrelated_base = finding(
            finding_summary=(
                "The manuscript excludes cantons that later adopted expropriation reforms "
                "and interprets the larger estimate as the effect of private rights absent "
                "reform, although reform status is a post-1815, potentially endogenous event."
            ),
            claim_text=(
                "Restricting the RDD sample to cantons that did not implement expropriation "
                "reforms identifies the effect of private rights in the absence of "
                "institutional adjustment."
            ),
        )
        unrelated_group = {
            "issue_class": "manuscript_issue",
            "source_reviewers": ["design_randomization_auditor"],
            "finding_summary": unrelated_base["finding_summary"],
            "claim_text": unrelated_base["claim_text"],
            "primary_location": unrelated_base["location"],
            "locations": [unrelated_base["location"]],
            "source_objects": [],
            "claim_evidence_links": [],
            "categories": [unrelated_base["category"]],
        }
        clustering_finding = finding(
            id="ROB-004",
            finding_summary=(
                "The reform-effect and reform-by-private-rights significance claims lack "
                "inference clustered at the canton level where reforms are assigned."
            ),
            claim_text=(
                "Expropriation reforms increased water-energy generation, and the positive "
                "effect is entirely driven by private-rights cantons."
            ),
        )
        self.assertFalse(
            should_merge(
                unrelated_group,
                "robustness_auditor",
                clustering_finding,
                "manuscript_issue",
            )
        )

        true_base = finding(
            finding_summary=(
                "The post-event analysis and Table 7 cluster standard errors at the "
                "district-year level even though both treatments are assigned at the canton level."
            ),
            claim_text=(
                "District-year clustering provides assignment-consistent inference for the "
                "canton-level water-rights and reform treatments."
            ),
        )
        true_group = {
            **unrelated_group,
            "finding_summary": true_base["finding_summary"],
            "claim_text": true_base["claim_text"],
            "primary_location": true_base["location"],
            "locations": [true_base["location"]],
        }
        true_paraphrase = finding(
            id="ID-007",
            finding_summary=(
                "Panel and reform regressions cluster at district-year even though institutional "
                "exposure is assigned at canton and outcomes repeat over time, so their reported "
                "inference does not allow treatment-level or serial dependence."
            ),
            claim_text=(
                "The reported uncertainty for the panel event studies and Table 7 supports "
                "statistically reliable conclusions about canton-level institutional treatments."
            ),
        )
        self.assertTrue(
            should_merge(
                true_group,
                "identification_auditor",
                true_paraphrase,
                "manuscript_issue",
            )
        )

    def test_group_merge_rejects_a_weak_single_anchor_bridge(self) -> None:
        anchors = [
            {
                "reviewer": "abstract_conclusion_consistency_auditor",
                "issue_class": "manuscript_issue",
                "page": 7,
                "finding_summary": (
                    "The conclusion turns an effect of information about fewer audits on stated "
                    "responses into claims about actual audit reductions."
                ),
                "claim_text": (
                    "Reduced audit activity itself lowers public trust and secures public support."
                ),
            },
            {
                "reviewer": "claim_evidence_auditor",
                "issue_class": "manuscript_issue",
                "page": 7,
                "finding_summary": (
                    "The policy conclusion generalizes an information-treatment effect to the "
                    "effect of maintaining actual audit levels."
                ),
                "claim_text": (
                    "Maintaining normal audit levels is important for securing public support."
                ),
            },
        ]
        group = {
            "issue_class": "manuscript_issue",
            "source_reviewers": [anchor["reviewer"] for anchor in anchors],
            "_merge_anchors": anchors,
        }
        tradeoff_finding = finding(
            id="MAG-003",
            finding_summary=(
                "The manuscript favors maintaining normal audit capacity without measuring the "
                "policy trade-offs or support threshold needed to justify that prescription."
            ),
            claim_text=(
                "The treatment effects demonstrate that maintaining normal audit levels is "
                "important to secure public support."
            ),
            location={
                "page": 7,
                "page_label": "7",
                "section": "Conclusion",
                "text_quote": "maintaining normal audit levels",
                "precision": "exact",
            },
        )

        self.assertIsNone(
            group_merge_score(
                group,
                "economic_magnitude_auditor",
                tradeoff_finding,
                "manuscript_issue",
            )
        )

    def test_group_merge_rejects_conflict_with_any_existing_anchor(self) -> None:
        anchors = [
            {
                "reviewer": "claim_evidence_auditor",
                "issue_class": "manuscript_issue",
                "page": 4,
                "finding_summary": "The reported response rate of 5% is incorrect.",
                "claim_text": "The response rate is 5%.",
            },
            {
                "reviewer": "numerical_auditor",
                "issue_class": "manuscript_issue",
                "page": 4,
                "finding_summary": "The reported response rate is 5%, but it should be 10%.",
                "claim_text": "The response rate is 5%, not 10%.",
            },
        ]
        group = {
            "issue_class": "manuscript_issue",
            "source_reviewers": [anchor["reviewer"] for anchor in anchors],
            "_merge_anchors": anchors,
        }
        candidate = finding(
            id="SOURCE-001",
            finding_summary="The reported response rate is 5%, but it should be 15%.",
            claim_text="The response rate is 5%, not 15%.",
            location={
                "page": 4,
                "page_label": "4",
                "section": "Results",
                "text_quote": "response rate",
                "precision": "exact",
            },
        )

        self.assertIsNone(
            group_merge_score(
                group,
                "source_consistency_auditor",
                candidate,
                "manuscript_issue",
            )
        )

    def test_page_less_anchor_cannot_bridge_different_known_pages(self) -> None:
        summary = "The reported treatment-effect sign conflicts with the displayed coefficient."
        group = {
            "issue_class": "manuscript_issue",
            "source_reviewers": ["numerical_auditor", "claim_evidence_auditor"],
            "_merge_anchors": [
                {
                    "reviewer": "numerical_auditor",
                    "issue_class": "manuscript_issue",
                    "page": 1,
                    "finding_summary": summary,
                    "claim_text": "The treatment effect is positive.",
                },
                {
                    "reviewer": "claim_evidence_auditor",
                    "issue_class": "manuscript_issue",
                    "page": None,
                    "finding_summary": summary,
                    "claim_text": "The treatment effect is positive.",
                },
            ],
        }
        candidate = finding(
            id="MODEL-001",
            finding_summary=summary,
            claim_text="The treatment effect is positive.",
            location={
                "page": 2,
                "page_label": "2",
                "section": "Results",
                "text_quote": "positive treatment effect",
                "precision": "exact",
            },
        )

        self.assertIsNone(
            group_merge_score(
                group,
                "model_equation_auditor",
                candidate,
                "manuscript_issue",
            )
        )

    def test_normalize_keeps_shared_quote_issues_separate_and_is_order_stable(self) -> None:
        reviews_dir = self.config_path("precision_normalizer_marker.json").parent / "precision-reviews"
        reviews_dir.mkdir(exist_ok=True)
        reviewers = [
            reviewer_config("claim_evidence_auditor", "CEA"),
            reviewer_config("abstract_conclusion_consistency_auditor", "CONSIST"),
            reviewer_config("limitations_external_validity_auditor", "VALID"),
        ]
        shared_location = {
            "page": 1,
            "page_label": "1",
            "section": "Abstract",
            "text_quote": "Both approaches support the headline conclusion.",
            "precision": "exact",
        }
        shared_source = {
            **finding()["source_objects"][0],
            "path": "work/paper/parsed/pages/page_001.md",
            "page": 1,
        }
        findings = [
            finding(
                id="CEA-001",
                finding_summary="The historical index is described as direct discrimination even though it is only a proxy for the local racial environment.",
                claim_text="The historical index measures discrimination directly.",
                location=shared_location,
                source_objects=[shared_source],
            ),
            finding(
                id="CONSIST-001",
                finding_summary="The paper presents the historical discrimination index as direct exposure despite defining it as a proxy for the local environment.",
                claim_text="The historical index identifies direct discrimination exposure.",
                location=shared_location,
                source_objects=[shared_source],
            ),
            finding(
                id="VALID-001",
                finding_summary="The study generalizes from selected military pilots to all highly skilled Black Americans.",
                claim_text="The pilot evidence applies to all highly skilled Black Americans.",
                location=shared_location,
                source_objects=[shared_source],
            ),
        ]
        for config, item in zip(reviewers, findings):
            (reviews_dir / config.output).write_text(
                json.dumps(review_output([item], config.name)), encoding="utf-8"
            )
            self.addCleanup(self.cleanup_path, reviews_dir / config.output)
        self.addCleanup(self.cleanup_dir, reviews_dir)

        forward = normalize("paper-x", reviews_dir, reviewers)
        reverse = normalize("paper-x", reviews_dir, list(reversed(reviewers)))

        def clusters(bundle: dict[str, object]) -> list[tuple[str, ...]]:
            return sorted(
                tuple(sorted(source["id"] for source in group["source_findings"]))
                for group in bundle["canonical_findings"]
            )

        self.assertEqual(
            clusters(forward),
            [("CEA-001", "CONSIST-001"), ("VALID-001",)],
        )
        self.assertEqual(clusters(reverse), clusters(forward))
        details = forward["canonical_findings"][0]["source_finding_details"]
        self.assertEqual(
            {detail["id"] for detail in details}, {"CEA-001", "CONSIST-001"}
        )

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
        bibliography = {
            **high_manuscript,
            "canonical_id": "CANON-006",
            "issue_class": "bibliography_maintenance",
            "source_reviewers": ["reference_auditor"],
            "source_findings": [{"reviewer": "reference_auditor", "id": "REF-002"}],
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
        self.assertEqual(route_finding(bibliography)[0], BIBLIOGRAPHY_APPENDIX_SECTION)
        self.assertEqual(route_finding(low_manuscript)[0], ADDITIONAL_FINDINGS_SECTION)
        self.assertFalse(requires_body_coverage(parser))

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
                {
                    "reviewer": "crossref_auditor",
                    "run_status": "partial",
                    "finding_count": 1,
                    "summary": "Appendix coverage was incomplete.",
                    "notes": [],
                },
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
                "selection_mode": "applicability",
                "selected_optional_reviewers": [
                    {"name": "claim_evidence_auditor", "reason": "Important displayed-evidence claims."}
                ],
            },
        )

        self.assertIn("# Deterministic Editor Brief", brief)
        self.assertIn("Review Configuration Guidance", brief)
        self.assertIn("empirical_causal", brief)
        self.assertIn("Important displayed-evidence claims.", brief)
        self.assertIn("Appendix coverage was incomplete.", brief)
        self.assertIn("claim_evidence_auditor", brief)
        self.assertIn("Machine-Ranked Candidate Findings (Advisory Only)", brief)
        self.assertIn("retrieval aids, not a final priority list", brief)
        self.assertNotIn("| Canonical ID | Score |", brief)
        self.assertNotIn("| Canonical ID | Severity | Confidence | Agents |", brief)
        self.assertIn("Additional Findings Candidates", brief)
        self.assertIn("Traceability Map Rows", brief)
        self.assertIn("CROSSREF-001", brief)
        self.assertIn("GRAM-001", brief)
        self.assertNotIn("Agent-by-Agent Finding Index", brief)
        self.assertIn("CANON-001", brief)

    def test_editor_brief_records_applicability_roster_and_required_body_coverage(self) -> None:
        optional = reviewer_config(
            "claim_evidence_auditor", "CEA", selection_policy="optional"
        )
        finding_item = {
            "canonical_id": "CANON-001",
            "issue_class": "manuscript_issue",
            "severity": "medium",
            "confidence": "high",
            "assessment": "no",
            "source_reviewers": ["claim_evidence_auditor"],
            "source_findings": [
                {"reviewer": "claim_evidence_auditor", "id": "CEA-001"}
            ],
            "finding_summary": "A central claim names the wrong denominator.",
            "claim_text": "The result applies to all assigned participants.",
            "primary_location": {"page": 2, "page_label": "2", "section": "Results"},
        }
        bundle = {
            "summary": {
                "issue_class_counts": {"manuscript_issue": 1},
                "severity_counts": {"medium": 1},
            },
            "source_reviewer_outputs": [
                {"reviewer": optional.name, "run_status": "ok", "finding_count": 1}
            ],
            "canonical_findings": [finding_item],
        }
        selection = {
            "selection_mode": "applicability",
            "paper_type": "empirical_causal",
            "selection_confidence": "high",
            "selected_optional_reviewers": [
                {
                    "name": optional.name,
                    "reason": "The paper reports central treatment-effect claims.",
                }
            ],
        }

        brief = editor_brief_markdown(
            "paper-x",
            bundle,
            [optional],
            {optional.name: review_output([], optional.name)},
            selection,
        )

        self.assertIn("Applicability routing classified the paper", brief)
        self.assertIn("skipped only when their entire remit is clearly absent", brief)
        self.assertIn("Required Body Coverage Audit", brief)
        self.assertIn("CANON-001", brief)
        self.assertTrue(requires_body_coverage(finding_item))
        self.assertFalse(requires_body_coverage({**finding_item, "severity": "low"}))

    def test_editor_brief_preserves_legacy_selection_provenance(self) -> None:
        optional = reviewer_config(
            "numerical_auditor", "NUM", selection_policy="optional"
        )
        bundle = {
            "summary": {"issue_class_counts": {}, "severity_counts": {}},
            "source_reviewer_outputs": [
                {"reviewer": optional.name, "run_status": "ok", "finding_count": 0}
            ],
            "canonical_findings": [],
        }
        selection = {
            "selection_mode": "static",
            "paper_type": "unknown",
            "selection_confidence": "high",
            "selected_optional_reviewers": [
                {"name": optional.name, "reason": "Legacy exhaustive run."}
            ],
        }

        static_brief = editor_brief_markdown(
            "paper-x",
            bundle,
            [optional],
            {optional.name: review_output([], optional.name)},
            selection,
        )
        dynamic_brief = editor_brief_markdown(
            "paper-x",
            bundle,
            [optional],
            {optional.name: review_output([], optional.name)},
            {**selection, "selection_mode": "dynamic", "paper_type": "theory"},
        )

        self.assertIn("legacy exhaustive run", static_brief)
        self.assertIn("legacy dynamically routed run", dynamic_brief)
        self.assertIn("`theory`", dynamic_brief)

    def test_editor_input_uses_bundle_and_provenance_without_raw_json_duplication(self) -> None:
        optional = reviewer_config(
            "claim_evidence_auditor", "CEA", selection_policy="optional"
        )
        review_path = Path("work/paper-x/reviews/custom-review-output.json")
        raw_review = review_output([], optional.name)
        raw_review["notes"] = ["RAW_ONLY_SENTINEL"]
        bundle = {
            "paper_id": "paper-x",
            "summary": {"issue_class_counts": {}, "severity_counts": {}},
            "source_reviewer_outputs": [
                {"reviewer": optional.name, "run_status": "ok", "finding_count": 0}
            ],
            "canonical_findings": [],
        }
        args = {
            "paper_id": "paper-x",
            "editor_prompt_text": "Editor prompt",
            "bundle_path": Path("work/paper-x/editor/normalized_bundle.json"),
            "bundle_json": bundle,
            "reviews_dir": Path("work/paper-x/reviews"),
            "reviewers": [optional],
            "review_paths": [review_path],
            "review_json_by_name": {optional.name: raw_review},
            "selection_json": None,
        }

        document = editor_input_document(**args, compact_bundle=False)

        self.assertIn("Validated Reviewer Output Provenance", document)
        self.assertIn(review_path.as_posix(), document)
        self.assertIn(
            f"| {optional.name} | {review_path.as_posix()} | ok | 0 |",
            document,
        )
        self.assertNotIn("RAW_ONLY_SENTINEL", document)
        self.assertNotIn("Original Configured Reviewer Outputs", document)

        expanded_bundle = {
            **bundle,
            "transport_padding": [
                {"alpha": index, "beta": "evidence" * 8} for index in range(120)
            ],
        }
        expanded_args = {**args, "bundle_json": expanded_bundle}
        pretty = editor_input_document(**expanded_args, compact_bundle=False)
        compact = editor_input_document(**expanded_args, compact_bundle=True)
        pretty_size = len(pretty.encode("utf-8"))
        compact_size = len(compact.encode("utf-8"))
        self.assertLess(compact_size, pretty_size)

        bounded, serialization, byte_count = bounded_editor_input(
            expanded_args, max_bytes=(pretty_size + compact_size) // 2
        )
        self.assertEqual(serialization, "minified")
        self.assertEqual(byte_count, len(bounded.encode("utf-8")))
        self.assertLess(byte_count, MAX_EDITOR_INPUT_BYTES)
        with self.assertRaisesRegex(ValueError, "will not truncate evidence"):
            bounded_editor_input(expanded_args, max_bytes=compact_size - 1)

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

        synthesis = brief.split("## Machine-Ranked Candidate Findings (Advisory Only)", 1)[1].split(
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

        synthesis = brief.split("## Machine-Ranked Candidate Findings (Advisory Only)", 1)[1].split(
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
                "## Highest-Priority Cross-Agent Findings",
                "findings",
                "## Suggested Revision Priorities",
                "priorities",
                "## Additional Findings",
                "additional",
                "## Appendix: Review Scope and Limitations",
                "scope",
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

    def test_report_checker_accepts_new_and_legacy_review_scope_headings(self) -> None:
        report = "\n".join(
            [
                "# Multi-Agent Paper Review Report",
                "## Executive Summary",
                "Summary for CANON-001.",
                "## Highest-Priority Cross-Agent Findings",
                "Finding.",
                "## Suggested Revision Priorities",
                "Priority.",
                "## Additional Findings",
                "Additional.",
                "## Appendix: Review Scope and Limitations",
                "Scope.",
            ]
        )

        self.assertEqual(report_failures(report, min_chars=0), [])
        self.assertEqual(
            report_failures(
                report.replace(
                    "## Appendix: Review Scope and Limitations",
                    "## Review Configuration",
                ),
                min_chars=0,
            ),
            [],
        )
        failures = report_failures(
            report.replace("## Appendix: Review Scope and Limitations\nScope.", ""),
            min_chars=0,
        )
        self.assertTrue(any("missing review-scope heading" in failure for failure in failures))

    def test_editor_prompt_encodes_general_cplus_priority_rules(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "templates" / "editor_report.txt").read_text(
            encoding="utf-8"
        )

        self.assertIn("confirmed correction", prompt)
        self.assertIn("material qualification", prompt)
        self.assertIn("exploratory suggestion", prompt)
        self.assertIn("Minimum adequate correction", prompt)
        self.assertIn("Appendix: Review Scope and Limitations", prompt)
        self.assertIn("Appendix: Parser and Preprocessing Limitations", prompt)
        self.assertIn("limitation of evidence available to this review", prompt)
        self.assertNotIn("shares not summing", prompt.lower())
        self.assertNotIn("shift in beliefs", prompt.lower())

    def test_numerical_prompt_requires_source_faithful_adding_up_checks(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "templates" / "numerical_audit.txt").read_text(
            encoding="utf-8"
        )

        self.assertIn("accounting and adding-up identities", prompt)
        self.assertIn("same sample, denominator, timing, and specification", prompt)
        self.assertIn("never infer a balancing component, value, or sign", prompt)

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

    def test_report_checker_preserves_balanced_parentheses_in_urls(self) -> None:
        url = "https://doi.org/10.1016/0047-2727(72)90010-2"
        bundle = {
            "canonical_findings": [
                {
                    "canonical_id": "CANON-001",
                    "source_findings": [{"reviewer": "literature_auditor", "id": "LIT-001"}],
                    "source_objects": [{"source_object": {"id": "SRC-001", "url": url}}],
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
                f"The source is [{url}]({url}).",
                "## Suggested Revision Priorities",
                "Revise the literature discussion.",
                "## Additional Findings",
                "No additional findings.",
                TRACEABILITY_APPENDIX_HEADING,
                "| Report section | Finding | Canonical ID | Source finding IDs |",
                "| Literature | citation | CANON-001 | literature_auditor:LIT-001 |",
                "## Appendix: External Sources Cited In This Review",
                f"| Source | URL |\n| DOI | {url} |",
            ]
        )

        self.assertEqual(urls_in_text(report), {url})
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

    def test_uppercase_unpunctuated_caption_is_typographically_bounded(self) -> None:
        figure = caption_match("figure", "FIGURE 1 Vignette experiment: Skills")
        table = caption_match("table", "TABLE A1 Main estimates")

        self.assertIsNotNone(figure)
        self.assertEqual(figure.group("label"), "1")
        self.assertEqual(figure.group("title"), "Vignette experiment: Skills")
        self.assertIsNotNone(table)
        self.assertEqual(table.group("label"), "A1")
        self.assertIsNone(caption_match("figure", "Figure 1 shows the estimates"))

    def test_citation_inventory_excludes_references_and_keeps_later_appendix(self) -> None:
        pages = [
            {
                'pdf_page_number': 1,
                'page_label': '1',
                'normalized_text': (
                    'Becker (1973, 1974) motivates the design.\n'
                    'Canonical models (Becker, 1973, 1974) motivate it.\n'
                    'References\n'
                    'Smith (2020). A cited paper.\n'
                ),
            },
            {
                'pdf_page_number': 2,
                'page_label': '2',
                'normalized_text': (
                    'Jones (2021). Another cited paper.\n'
                    'Appendix A. Checks\n'
                    'Brown (2022) motivates this check.\n'
                ),
            },
        ]

        matches = [item['match'] for item in extract_citations(pages)]

        self.assertEqual(
            set(matches),
            {'Becker (1973, 1974)', '(Becker, 1973, 1974)', 'Brown (2022)'},
        )

    def test_repeated_chart_categories_are_not_section_headings(self) -> None:
        self.assertFalse(is_heading('2 Groups 3 Groups'))
        self.assertFalse(is_heading('N 2,715 2,529'))
        self.assertFalse(
            is_heading(
                'A US daily newspapers B Weekly news source C Digital share of'
            )
        )
        self.assertFalse(is_heading('R E S E A R C H A R T I C L E'))
        self.assertFalse(is_heading('I. P. L. Png, University of Example'))
        self.assertFalse(is_heading('EDITED BY'))
        self.assertFalse(is_heading('G V ='))
        self.assertFalse(
            is_heading(
                'Appendix C Table C2, the results are similar to those reported in the text'
            )
        )
        self.assertFalse(
            is_heading(
                '1 Uniqueness Factor 1 indicates that it is a suitable and trustworthy measure for analysis'
            )
        )

    def test_front_matter_order_divergence_is_flagged_without_global_overflagging(self) -> None:
        common = {
            'raw_text': 'substantive text ' * 100,
            'normalized_text': 'substantive text ' * 100,
            'likely_scanned': False,
            'normalized_text_strategy': 'coordinate_sorted',
            'raw_sorted_similarity': 0.3,
        }

        summary = page_quality_summary(
            [
                {'pdf_page_number': 1, **common},
                {'pdf_page_number': 2, **common},
            ]
        )

        self.assertEqual(summary['reading_order_review_pages'], [1])

    def test_suspect_native_table_can_still_receive_matching_caption(self) -> None:
        captions = [
            {
                'page': 2,
                'label': '1',
                'caption': 'Table 1: Main estimates',
                'caption_source': 'positioned_lines',
                'caption_bbox': [10, 100, 300, 120],
                'crop_bbox': [10, 90, 300, 300],
            }
        ]
        auto_tables = [
            {
                'page': 2,
                'bbox': [20, 130, 290, 280],
                'status': 'auto_extracted_suspect',
            }
        ]

        self.assertEqual(attach_captions_to_auto_tables(captions, auto_tables), {0})
        self.assertEqual(auto_tables[0]['table_label'], '1')

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
        self.assertFalse(
            should_append_raw_caption_continuation(
                "Table 1: Effects (main sample", "Notes: Standard errors"
            )
        )
        self.assertFalse(
            should_append_caption_continuation(
                "Figure 1: Effects (main sample", "Notes: Standard errors", 8.0
            )
        )
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

    def test_label_only_figure_requires_source_note_on_same_page(self) -> None:
        match = FIGURE_CAPTION_RE.match("Figure A.16")
        self.assertIsNotNone(match)
        assert match is not None
        self.assertTrue(
            supported_caption_match(
                "figure", match, ["Figure A.16", "Notes: Source and sample details."], 0
            )
        )
        self.assertFalse(
            supported_caption_match(
                "figure", match, ["Figure A.16", "A prose sentence follows."], 0
            )
        )
        titled = FIGURE_CAPTION_RE.match("Figure A.16: Verified title")
        assert titled is not None
        self.assertTrue(supported_caption_match("figure", titled, ["Figure A.16: Verified title"], 0))

    def test_label_only_table_requires_aligned_same_block_title(self) -> None:
        match = TABLE_CAPTION_RE.match("Table 1")
        self.assertIsNotNone(match)
        assert match is not None
        label = {
            "text": "Table 1",
            "bbox": [41, 55, 67, 62],
            "block_index": 1,
            "font_size": 6.4,
            "is_bold": True,
        }
        title = {
            "text": "Main post-treatment outcomes.",
            "bbox": [41, 64, 260, 71],
            "block_index": 1,
            "font_size": 6.4,
            "is_bold": False,
        }

        self.assertTrue(supported_caption_match("table", match, [label, title], 0))
        self.assertFalse(supported_caption_match("table", match, ["Table 1", title["text"]], 0))
        self.assertFalse(
            supported_caption_match(
                "table", match, [label, {**title, "block_index": 2}], 0
            )
        )
        self.assertEqual(
            label_only_table_title(
                [{**label, "text": "Table 1: Inline caption title"}, title], 0
            ),
            "",
        )

    def test_same_row_caption_title_uses_geometry_without_bold_font(self) -> None:
        match = FIGURE_CAPTION_RE.match('FIGURE 1')
        assert match is not None
        lines = [
            {
                'text': 'FIGURE 1',
                'bbox': [40, 209, 88, 218],
                'block_index': 3,
                'font_size': 8.5,
                'is_bold': False,
            },
            {
                'text': 'Vignette experiment: Skills.',
                'bbox': [96, 209, 300, 218],
                'block_index': 3,
                'font_size': 8.5,
                'is_bold': False,
            },
        ]

        self.assertTrue(supported_caption_match('figure', match, lines, 0))

    def test_same_block_caption_wrap_preserves_complete_title(self) -> None:
        self.assertTrue(
            should_append_caption_continuation(
                "Table A.13: Impact of Wingmen Origins on 1950 Location",
                "Choice",
                14.5,
                same_block_wrap=True,
            )
        )
        self.assertTrue(
            should_append_caption_continuation(
                "Table 5: Outcomes (1990s", "Index to Public Records)", 14.5
            )
        )
        self.assertTrue(
            should_append_caption_continuation(
                "Figure A.17: Background characteristics: Experiment",
                "2 (YouGov)",
                14.5,
                same_block_wrap=True,
            )
        )
        self.assertFalse(
            should_append_caption_continuation(
                "Figure 1: Complete title", "2 4 6 8", 14.5
            )
        )
        self.assertFalse(
            should_append_caption_continuation(
                "Table 1: Complete results.",
                "Unrelated prose",
                14.5,
                same_block_wrap=True,
            )
        )

    def test_landscape_caption_uses_full_page_width(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=800, height=600)
        try:
            self.assertEqual(caption_column_bounds(page, [80, 100, 300, 120]), (24.0, 776.0))
        finally:
            doc.close()

    def test_rotated_figure_uses_explicit_full_page_crop_fallback(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.set_rotation(90)
        try:
            crop, strategy = figure_render_crop_bbox(page, [100, 250, 500, 612])
            self.assertEqual(crop, [0.0, 0.0, 792.0, 612.0])
            self.assertEqual(strategy, 'full_page_rotated_fallback')
        finally:
            doc.close()

    def test_reference_fragments_merge_across_artificial_column_threshold(self) -> None:
        lines = [
            {"text": "Colson, R. (2011).", "bbox": [72, 236, 169, 248], "block_index": 0},
            {"text": "Eminent domain: A comparative perspective.", "bbox": [179, 236, 420, 248], "block_index": 0},
            {"text": "Journal of Economic History.", "bbox": [430, 236, 540, 248], "block_index": 0},
        ]

        merged = merge_reference_line_fragments(lines, 612)

        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0]["text"],
            "Colson, R. (2011). Eminent domain: A comparative perspective. Journal of Economic History.",
        )

    def test_reference_boundaries_skip_headers_and_page_footnotes(self) -> None:
        def line(text: str, y: float, *, block: int = 0) -> dict[str, object]:
            return {
                "text": text,
                "bbox": [72.0, y, 520.0, y + 10.0],
                "block_index": block,
                "is_page_footer": False,
            }

        pages = [
            {
                "pdf_page_number": 1,
                "page_label": "1",
                "page_width": 612.0,
                "page_height": 792.0,
                "positioned_lines": [
                    line("Journal running header", 35),
                    line("References", 100),
                    line("Alpha, A., 2020. First study.", 125),
                    line("Beta, B., 2021. Second study.", 150),
                    line("13 See e.g. the supplementary source.", 680),
                    line("footnote continuation", 695),
                ],
                "normalized_text": "",
            },
            {
                "pdf_page_number": 2,
                "page_label": "2",
                "page_width": 612.0,
                "page_height": 792.0,
                "positioned_lines": [
                    line("Journal running header", 35),
                    line("Gamma, G., 2022. Third study.", 100),
                    line("Figures", 180),
                    line("Figure 1: Results", 210),
                ],
                "normalized_text": "",
            },
        ]

        references = extract_reference_list(pages)

        self.assertEqual(len(references), 3)
        self.assertEqual([item["text"] for item in references], [
            "Alpha, A., 2020. First study.",
            "Beta, B., 2021. Second study.",
            "Gamma, G., 2022. Third study.",
        ])

    def test_page_label_decodes_explicit_utf16_pdf_token(self) -> None:
        self.assertEqual(normalize_page_label("<FEFF0030>"), "0")
        self.assertEqual(normalize_page_label("<FEFF0041002E0031>"), "A.1")
        self.assertEqual(normalize_page_label("<NOTHEX>"), "<NOTHEX>")

    def test_page_label_uses_isolated_geometric_footer_candidate(self) -> None:
        words = [
            [421, 79, 426, 91, '2', 0, 0, 0],
            [293, 800, 302, 808, '02', 1, 0, 0],
        ]

        self.assertEqual(infer_page_label_from_words(words, 595, 842), '02')

    def test_geometric_page_labels_require_consecutive_document_sequence(self) -> None:
        records = [
            {
                'page_label': label,
                'page_label_source': 'geometric_footer_or_header',
                'rejected_page_label_candidate': None,
            }
            for label in ('01', '02', '03')
        ]
        isolated = [
            {
                'page_label': label,
                'page_label_source': 'geometric_footer_or_header',
                'rejected_page_label_candidate': None,
            }
            for label in ('183', '8', 'i')
        ]

        reconcile_geometric_page_labels(records)
        reconcile_geometric_page_labels(isolated)

        self.assertEqual([item['page_label'] for item in records], ['01', '02', '03'])
        self.assertEqual([item['page_label'] for item in isolated], [None, None, None])
        self.assertEqual(isolated[0]['rejected_page_label_candidate'], '183')
        self.assertEqual(page_label_ordinal('XIV'), ('roman', 14))

    def test_repeated_layout_artifacts_require_geometry_and_recurrence(self) -> None:
        pages = []
        for page_index in range(3):
            blocks = [
                [50, 30, 545, 42, f'Journal 2024 page {page_index + 1}', 0, 0],
                [50, 90, 545, 700, 'Substantive body text', 1, 0],
                [250, 760, 280, 770, str((page_index + 1) * 15), 3, 0],
            ]
            if page_index < 2:
                blocks.append([570, 20, 580, 700, 'Repeated license notice', 2, 0])
            else:
                blocks.append([570, 100, 580, 500, 'Unique axis label', 2, 0])
            pages.append(
                {
                    'page_index': page_index,
                    'page_width': 600,
                    'page_height': 800,
                    'blocks': blocks,
                }
            )

        artifacts = repeated_layout_artifacts(pages)

        self.assertEqual(
            {item['reason'] for item in artifacts[0]},
            {'repeated_header', 'repeated_vertical_margin'},
        )
        self.assertEqual(
            {item['reason'] for item in artifacts[2]}, {'repeated_header'}
        )
        self.assertNotIn('Unique axis label', str(artifacts))
        self.assertFalse(
            any(
                item['source_text'].strip().isdigit()
                for page_items in artifacts.values()
                for item in page_items
            )
        )
        cleaned = remove_layout_artifact_text(
            'Journal 2024 page 1\nSubstantive body text\nRepeated license notice',
            artifacts[0],
        )
        self.assertEqual(cleaned.strip(), 'Substantive body text')

    def test_pdf_page_label_token_is_removed_only_at_page_edge(self) -> None:
        blocks = [
            [300, 705, 312, 717, '52\n', 19, 0],
            [70, 300, 82, 312, '52\n', 20, 0],
        ]
        words = [
            [526, 701, 540, 712, 'the', 18, 6, 17],
            [300, 705, 312, 717, '52', 19, 0, 0],
            [88, 715, 118, 725, 'market', 18, 7, 0],
        ]

        artifacts = page_label_layout_artifacts(
            blocks, words, '52', 'pdf_label', 612, 792
        )

        self.assertEqual([item['block_number'] for item in artifacts], [19])
        self.assertEqual(artifacts[0]['reason'], 'pdf_page_label_token')
        self.assertEqual(
            page_label_layout_artifacts(
                blocks, [], '52', 'text_edge', 612, 792
            ),
            [],
        )
        self.assertEqual(
            remove_layout_artifact_text(
                'able to beat the                                      52\n   market',
                artifacts,
            ),
            'able to beat the\nmarket',
        )

    def test_only_reconciled_geometric_page_labels_are_removed(self) -> None:
        records = []
        for page_number, label in enumerate(('01', '02', '03', '183'), start=1):
            artifact = page_label_layout_artifacts(
                [[300, 750, 312, 765, f'{label}\n', 2, 0]],
                [
                    [70, 700, 110, 712, 'body', 1, 0, 0],
                    [300, 750, 312, 765, label, 2, 0, 0],
                ],
                label,
                'geometric_footer_or_header',
                612,
                792,
            )
            records.append(
                {
                    'pdf_page_number': page_number,
                    'page_label': label,
                    'page_label_source': 'geometric_footer_or_header',
                    'rejected_page_label_candidate': None,
                    'normalized_text': f'body\n{label}\n',
                    'excluded_layout_artifact_count': 0,
                    'excluded_layout_artifact_reasons': [],
                    '_pending_geometric_page_label_artifacts': artifact,
                }
            )

        reconcile_geometric_page_labels(records)
        provenance = []
        apply_reconciled_geometric_page_label_artifacts(records, provenance)

        self.assertEqual([record['page_label'] for record in records], ['01', '02', '03', None])
        self.assertEqual([record['normalized_text'] for record in records[:3]], ['body\n'] * 3)
        self.assertEqual(records[3]['normalized_text'], 'body\n183\n')
        self.assertEqual(len(provenance), 3)
        self.assertTrue(
            all('_pending_geometric_page_label_artifacts' not in record for record in records)
        )

    def test_page_label_cleanup_finishes_reordered_recurring_footer(self) -> None:
        recurring_footer = {
            'reason': 'repeated_footer',
            'source_text': 'Frontiers in Psychology\n01\nfrontiersin.org\n',
        }
        page_label = {
            'reason': 'pdf_page_label_word',
            'source_text': '01',
            'label_text': '01',
            'previous_word': 'Psychology',
            'next_word': 'frontiersin.org',
        }

        cleaned = remove_layout_artifact_text(
            'body\nFrontiers in Psychology\nfrontiersin.org\n01\n',
            [recurring_footer],
        )
        cleaned = remove_layout_artifact_text(cleaned, [page_label])

        self.assertEqual(cleaned.strip(), 'body')

    def test_embedded_pdf_page_label_word_preserves_its_mixed_text_block(self) -> None:
        blocks = [
            [50, 700, 360, 732, 'Note text.\n53\n', 14, 0],
        ]
        words = [
            [270, 696, 276, 708, '53', 13, 4, 2],
            [266, 707, 326, 717, 'autocorrelation', 13, 15, 9],
            [300, 705, 312, 717, '53', 14, 1, 0],
            [329, 707, 336, 717, 'in', 13, 15, 10],
        ]

        artifacts = page_label_layout_artifacts(
            blocks, words, '53', 'pdf_label', 612, 792
        )

        self.assertEqual(artifacts[0]['reason'], 'pdf_page_label_word')
        self.assertEqual(artifacts[0]['block_number'], 14)
        self.assertFalse(artifacts[0]['exclude_entire_block'])
        self.assertEqual(
            remove_layout_artifact_text(
                'about autocorrelation53 in returns; -10.53 and 53.0', artifacts
            ),
            'about autocorrelation in returns; -10.53 and 53.0',
        )

    def test_page_label_context_preserves_numeric_cells_and_footnote_markers(self) -> None:
        numeric_artifact = page_label_layout_artifacts(
            [[303, 705, 309, 717, '7\n', 8, 0]],
            [
                [497, 700, 540, 709, 'confidence', 6, 11, 16],
                [303, 705, 309, 717, '7', 8, 0, 0],
                [89, 712, 97, 721, 'in', 6, 12, 0],
            ],
            '7',
            'pdf_label',
            612,
            792,
        )
        self.assertEqual(
            remove_layout_artifact_text(
                'Control mean 37.7\nHigh confidence\n 7 in their ability',
                numeric_artifact,
            ),
            'Control mean 37.7\nHigh confidence\nin their ability',
        )

        end_artifact = page_label_layout_artifacts(
            [[303, 760, 309, 772, '1\n', 20, 0]],
            [
                [100, 740, 145, 752, 'material', 19, 2, 3],
                [303, 760, 309, 772, '1', 20, 0, 0],
            ],
            '1',
            'pdf_label',
            612,
            792,
        )
        self.assertEqual(
            remove_layout_artifact_text(
                '1Hsieh et al. (2019) footnote\n1\nOther material\n1\n',
                end_artifact,
            ),
            '1Hsieh et al. (2019) footnote\n1\nOther material\n',
        )

    def test_soft_hyphen_is_removed_only_from_normalized_text(self) -> None:
        self.assertEqual(normalize_page_text('inter\u00adnational'), 'international\n')

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
        self.assertEqual(summary['unresolved_control_glyph_count'], 1)
        self.assertEqual(summary['unresolved_control_glyph_codes'], ['U+0002'])
        self.assertEqual(summary['unresolved_control_glyphs'][0]['font_family'], 'PICUP10')
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

    def test_parser_quality_prompt_uses_new_parser_provenance(self) -> None:
        prompt = (
            REPO_ROOT / 'prompts' / 'templates' / 'parser_quality_audit.txt'
        ).read_text(encoding='utf-8')

        self.assertIn('unresolved_control_glyph_pages', prompt)
        self.assertIn('layout_artifacts.json', prompt)
        self.assertIn('rejected_geometric_page_label_pages', prompt)
        self.assertIn('unlabeled_candidate', prompt)
        self.assertIn('table_candidate_count', prompt)

    def test_selector_prompt_contains_conservative_applicability_gates(self) -> None:
        prompt = (REPO_ROOT / "prompts" / "templates" / "reviewer_selection.txt").read_text(encoding="utf-8")

        self.assertIn("Set `selection_mode` to `applicability`", prompt)
        self.assertIn("There is no reviewer-count target or cap", prompt)
        self.assertIn("positive, high-confidence evidence", prompt)
        self.assertIn("select every conditional specialist", prompt)
        self.assertIn("wrapper enforces this rule deterministically", prompt)
        self.assertIn("theory_logic_auditor", prompt)
        self.assertIn("mandatory model_equation_auditor separately checks", prompt)
        self.assertIn("List every catalog reviewer exactly once", prompt)
        theory_prompt = (
            REPO_ROOT / "prompts" / "templates" / "theory_logic_audit.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("assumption-to-result validity", theory_prompt)
        self.assertIn("distinct from model_equation_auditor", theory_prompt)
        self.assertIn("never reconstruct a sign, symbol, or formula", theory_prompt)
        contract = (
            REPO_ROOT / "prompts" / "templates" / "reviewer_contract.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("empty findings array", contract)
        self.assertIn("do not stretch the remit", contract)
        self.assertIn("Audit independently", contract)
        self.assertIn("Do not inspect, quote, or rely on another substantive reviewer", contract)
        self.assertIn("downstream normalization and editing", contract)

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
            {"text": "Notes: Robust standard errors.", "bbox": [70, 170, 530, 182], "is_page_footer": False},
        ]

        region = table_region_below_caption(page, lines, [60, 70, 540, 88])

        self.assertIsNotNone(region)
        self.assertIn("Treatment -0.547*** 0.219**", region["raw_lines"])
        self.assertNotIn("Notes: Robust standard errors.", region["raw_lines"])
        self.assertLess(region["crop_bbox"][3], 170)

    def test_table_region_stops_before_separated_prose_after_numeric_rows(self) -> None:
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
            {
                "text": "The discussion resumes with a complete prose sentence.",
                "bbox": [70, 181, 530, 193],
                "is_page_footer": False,
            },
        ]

        region = table_region_below_caption(page, lines, [60, 70, 540, 88])

        self.assertIsNotNone(region)
        self.assertNotIn(lines[-1]["text"], region["raw_lines"])
        self.assertLess(region["crop_bbox"][3], 181)

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
        self.assertTrue(table_candidate_is_excluded(candidate, [figure]))
        self.assertFalse(table_candidate_is_excluded(candidate, [adjacent]))
        self.assertTrue(table_candidate_is_excluded(None, [figure]))
        self.assertFalse(table_candidate_is_excluded(None, []))

    @mock.patch("preprocess_pdf.save_captioned_tables", return_value=[])
    @mock.patch("preprocess_pdf.attach_captions_to_auto_tables", return_value=set())
    @mock.patch("preprocess_pdf.save_auto_tables", return_value=[])
    @mock.patch("preprocess_pdf.extract_captioned_items")
    def test_positioned_figure_regions_are_excluded_from_auto_tables(
        self,
        extract_items: mock.Mock,
        save_auto: mock.Mock,
        _attach: mock.Mock,
        _save_captioned: mock.Mock,
    ) -> None:
        extract_items.side_effect = [
            [],
            [
                {
                    "page": 3,
                    "caption_source": "positioned_lines",
                    "crop_bbox": [10.0, 20.0, 300.0, 400.0],
                },
                {
                    "page": 4,
                    "caption_source": "positioned_lines_visual_anchor",
                    "crop_bbox": [12.0, 24.0, 302.0, 402.0],
                },
            ],
        ]

        save_tables(mock.Mock(), Path("paper.pdf"), Path("tables"), REPO_ROOT, 200)

        self.assertEqual(
            save_auto.call_args.args[5],
            {
                3: [[10.0, 20.0, 300.0, 400.0]],
                4: [[12.0, 24.0, 302.0, 402.0]],
            },
        )

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
