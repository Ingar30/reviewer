"""Source correspondence, safe arithmetic, editorial decisions and coverage."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evidence_registry import build_registry, check_source, corresponding_text, quote_corresponds, safe_artifact
from numerical_checks import evaluate, numeric_errors, quantity_source_errors
from editor_decisions import decision_errors, render
from review_coverage import coverage_errors
from tests.mock_responses import editor_payload
from tests.test_evidence_gates import completed


class SourceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "pages").mkdir()
        (self.root / "pages/page_001.md").write_text("A line-wrap com\u00ad\nparison: -2.50% < x_1.", encoding="utf-8")
        (self.root / "page.png").write_bytes(b"synthetic image placeholder")
        (self.root / "manifest.json").write_text(json.dumps({"source_pdf_sha256": "a"*64,"summary":{"page_count":1}}))
        (self.root / "page_index.json").write_text(json.dumps([{"pdf_page_number":1,"normalized_text_path":"work/p/parsed/pages/page_001.md"}]))
        self.registry = build_registry(self.root)
        obj = next(o for o in self.registry["objects"] if o["path"] == "pages/page_001.md")
        self.source = {"id":"s", "object_id":obj["id"], "path":"work/p/parsed/pages/page_001.md",
                       "page":1,"type":"text","correspondence":"text","text_quote":"comparison: -2.50% < x_1."}

    def check(self):
        return check_source(self.source,self.root,self.registry,paper_id="p")

    def test_whitespace_line_wrap_not_sign_decimal_percent_or_subscript(self):
        result = self.check()
        self.assertFalse(result["errors"])
        self.assertEqual(result["relevance"], "not_assessed")
        self.assertEqual(result["criticism_support"], "not_assessed")
        for quote in ("2.50% < x_1.", "-250% < x_1.", "-2.50 < x_1.", "-2.50% < x1."):
            self.source["text_quote"] = "comparison: " + quote
            self.assertTrue(self.check()["errors"])

    def test_visible_minus_at_a_line_break_is_not_word_hyphenation(self):
        self.assertNotEqual(corresponding_text("x-\ny"), corresponding_text("xy"))
        self.assertNotEqual(corresponding_text("alpha-\nbeta"), corresponding_text("alphabeta"))
        for quote in ("2.50%", "50%", "x", "1"):
            self.assertFalse(quote_corresponds(quote, "-2.50% < x_1"))
        self.assertTrue(quote_corresponds("-2.50%", "Estimate: -2.50% < x_1"))

    def test_missing_ids_wrong_pdf_invalid_page_and_tampered_artifact(self):
        original = copy.deepcopy(self.source)
        for key, value in (("object_id",None),("page",2),("path","work/other/parsed/pages/page_001.md")):
            self.source = {**original,key:value}
            self.assertTrue(self.check()["errors"])
        self.source = original
        self.registry["source_pdf_sha256"]="b"*64
        self.assertTrue(self.check()["errors"])
        self.registry["source_pdf_sha256"]="a"*64
        (self.root/"pages/page_001.md").write_text("changed")
        self.assertTrue(self.check()["errors"])

    def test_visual_evidence_is_not_a_fabricated_text_match(self):
        self.source.update(correspondence="visual",text_quote="not extractable",verification_note="Region visually inspected; equation sign uncertain")
        result=self.check()
        self.assertFalse(result["errors"])
        self.assertEqual(result["correspondence"],"visual_assessment_required")

    def test_traversal_absolute_and_symlink_escapes(self):
        for path in ("../outside", "/absolute", "C:/outside", "pages/../../outside"):
            with self.assertRaises(ValueError):safe_artifact(self.root,path)
        try:(self.root/"escape").symlink_to(self.root.parent,target_is_directory=True)
        except OSError:self.skipTest("Symlink privilege unavailable")
        with self.assertRaises(ValueError):safe_artifact(self.root,"escape/other")

    def test_external_url_syntax_never_establishes_retrieval(self):
        result=check_source({"type":"external","id":"ext","url":"https://example.org"},self.root,self.registry,paper_id="p")
        self.assertFalse(result["located"])
        self.assertEqual(result["correspondence"],"url_only")


def quantity(value, *, scale="number", half="0", unit="count"):
    return dict(value=str(value),source_id="s",unit=unit,sample="same-sample",denominator="same-population",
                context="Synthetic comparable quantities",scale=scale,rounding_half_width=half)


def arithmetic():
    return dict(kind="arithmetic",operation="sum",quantities=[quantity(2),quantity(3)],
                reported=quantity(6),computed_value="5",tolerance="0",observed_discrepancy="5 is not 6",
                possible_explanation="Unknown",suggested_correction="Reconcile the displayed sum")


class NumericalTests(unittest.TestCase):
    def test_registered_source_link_does_not_license_invented_input_values(self):
        check = arithmetic()
        sources = [{"id":"s", "correspondence":"text", "text_quote":"Inputs 2 and 3; reported total 6."}]
        self.assertEqual(quantity_source_errors(check, sources), [])
        check["quantities"][0]["value"] = "200"
        check["computed_value"] = "203"
        self.assertTrue(quantity_source_errors(check, sources))
        check["quantities"] = [quantity("2.50", scale="percent")]
        check["reported"] = quantity("2.50", scale="percent")
        sources[0]["text_quote"] = "The estimate is -2.50%."
        self.assertTrue(quantity_source_errors(check, sources))
        for q in [*check["quantities"], check["reported"]]: q["value"] = "-2.50"
        self.assertEqual(quantity_source_errors(check, sources), [])
        check["reported"]["scale"] = "proportion"
        self.assertTrue(quantity_source_errors(check, sources))

    def test_true_error_and_rounding_compatible_values(self):
        check=arithmetic()
        self.assertEqual(evaluate(check)["status"],"arithmetic_discrepancy")
        check["quantities"]=[quantity(2,half="0.5"),quantity(3,half="0.5")]
        self.assertEqual(evaluate(check)["status"],"rounding_compatible")
        self.assertTrue(numeric_errors(check,{"s"},cannot_verify=False))

    def test_sample_denominator_and_percent_scale_mismatches(self):
        for key in ("sample","denominator"):
            check=arithmetic();check["quantities"][0][key]="another"
            self.assertEqual(evaluate(check)["status"],"unresolved")
        check=arithmetic();check["quantities"][0]["scale"]="percent"
        self.assertEqual(evaluate(check)["status"],"unresolved")

    def test_percentage_points_differ_from_relative_percentage(self):
        check=arithmetic();check.update(operation="percentage_points",quantities=[quantity(15,scale="percent",unit="share"),quantity(.10,scale="proportion",unit="share")],reported=quantity(5,scale="percent",unit="share"),computed_value="5")
        self.assertEqual(evaluate(check)["status"],"rounding_compatible")
        check.update(operation="percent_change",computed_value="50",reported=quantity(50,scale="percent",unit="share"))
        self.assertEqual(evaluate(check)["status"],"rounding_compatible")

    def test_unsupported_malicious_nonfinite_and_zero_denominator(self):
        for op in ("regression", "__import__('os').system('whoami')", "../../payload"):
            check=arithmetic();check["operation"]=op
            self.assertEqual(evaluate(check)["status"],"unresolved")
        for value in ("NaN","Infinity","1e999999", True):
            check=arithmetic();check["quantities"][0]["value"]=value
            self.assertEqual(evaluate(check)["status"],"unresolved")
        check=arithmetic();check.update(operation="ratio",quantities=[quantity(1),quantity(0)])
        self.assertEqual(evaluate(check)["status"],"unresolved")

    def test_underdetermined_cannot_be_a_verified_error(self):
        check={"kind":"underdetermined","question":"Mean of ratios or ratio of means?","quantities":[],
               "missing_information":["Individual denominators"],"status":"unresolved"}
        self.assertTrue(numeric_errors(check,set(),cannot_verify=False))
        self.assertFalse(numeric_errors(check,set(),cannot_verify=True))


def bundle():
    return {"paper_id":"p", "canonical_findings":[{"canonical_id":"CANON-001","severity":"high",
        "issue_class":"manuscript_issue","finding_summary":"The comparisons may use different samples",
        "source_findings":[{"reviewer":"numerical_auditor","id":"NUM-001"}]}]}


class EditorialTests(unittest.TestCase):
    def test_ids_and_headings_without_substantive_treatment_fail(self):
        b=bundle();a=editor_payload(b);a["decisions"][0]["treatment"]=""
        self.assertTrue(decision_errors(a,b))

    def test_generic_or_strengthened_treatment_fails_explicit_semantic_verdict(self):
        b=bundle();a=editor_payload(b)
        for treatment in ("Consider improving this section.","The paper uses inconsistent estimates."):
            a["decisions"][0]["treatment"]=treatment
            verdict=[{"canonical_id":"CANON-001","assessor":"independent_model","verdict":"not_faithful",
                      "reason":"Mocked assessor: the possible sample difference was erased or asserted as a proven error"}]
            self.assertTrue(decision_errors(a,b,semantic_verdicts=verdict,trusted_assessor="independent_model"))

    def test_missing_duplicate_dangling_and_cyclic_dispositions(self):
        b=bundle();a=editor_payload(b)
        a["decisions"]=[];self.assertTrue(decision_errors(a,b))
        a=editor_payload(b);a["decisions"].append(copy.deepcopy(a["decisions"][0]));self.assertTrue(decision_errors(a,b))
        a=editor_payload(b);a["decisions"][0].update(disposition="merged",block_ids=[],treatment="",destination="CANON-999")
        self.assertTrue(decision_errors(a,b))
        b["canonical_findings"].append({**b["canonical_findings"][0],"canonical_id":"CANON-002"})
        a=editor_payload(b)
        for index,d in enumerate(a["decisions"]):d.update(disposition="merged",block_ids=[],treatment="",destination=f"CANON-{2-index:03d}")
        self.assertTrue(decision_errors(a,b))

    def test_source_based_rejection_and_qualified_merge_are_accounted_for(self):
        b=bundle();a=editor_payload(b)
        a["decisions"][0].update(disposition="rejected",block_ids=[],treatment="",reason="Synthetic appendix explicitly defines separate samples")
        self.assertEqual(decision_errors(a,b),[])
        self.assertIn("rejected: Synthetic appendix",render(a,b))
        b["canonical_findings"].append({**b["canonical_findings"][0],"canonical_id":"CANON-002"})
        a=editor_payload(b);a["decisions"][1].update(disposition="merged",block_ids=[],treatment="",destination="CANON-001",
            retained_evidence=["Both source passages"],qualifications=["May differ; not a demonstrated inconsistency"])
        self.assertEqual(decision_errors(a,b),[])
        self.assertEqual(render(a,b),render(copy.deepcopy(a),copy.deepcopy(b)))


class CoverageTests(unittest.TestCase):
    def test_source_linked_absent_claim_does_not_require_invented_text(self):
        data = completed()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source_registry.json").write_text(json.dumps({"objects": [
                {"id": "OBJ-synthetic", "path": "pages/page_001.md", "kind": "text_span", "page": 1}
            ]}), encoding="utf-8")
            record = {"item_id": "claim:absent_design", "claim": None,
                      "source_object_ids": ["OBJ-synthetic"], "finding_ids": [],
                      "check_performed": "Checked the synthetic methods and results for assigned interventions",
                      "status": "not_applicable", "reason": "This synthetic study only predicts existing outcomes",
                      "attempted": True, "importance": "central", "scope": "exhaustive"}
            data["coverage"].append(record)
            self.assertEqual(coverage_errors(data, root), [])
            for state in ["checked_no_issue", "cannot_verify", "not_checked"]:
                with self.subTest(state=state):
                    record["status"] = state
                    self.assertTrue(coverage_errors(data, root))
            record["status"] = "not_applicable"
            for field, value in [("attempted", False), ("reason", None),
                                 ("source_object_ids", []), ("source_object_ids", ["unknown"]),
                                 ("check_performed", ""), ("item_id", "invented"), ("claim", "")]:
                with self.subTest(field=field, value=value):
                    old = record[field]
                    record[field] = value
                    self.assertTrue(coverage_errors(data, root))
                    record[field] = old
            # A scope exclusion cannot substitute for a central-claim audit.
            data["reviewer"] = "claim_evidence_auditor"
            self.assertTrue(coverage_errors(data, root))
            data["completion"]["state"] = "not_applicable"
            self.assertEqual(coverage_errors(data, root), [])

    def test_sampled_scope_still_requires_a_reason(self):
        data = completed()
        with tempfile.TemporaryDirectory() as temp:
            record = data["coverage"][0]
            record.update(scope="sampled", reason=None)
            self.assertTrue(coverage_errors(data, Path(temp)))
            record["reason"] = "Peripheral examples sampled; all required central checks attempted separately"
            self.assertEqual(coverage_errors(data, Path(temp)), [])

    def test_required_checks_not_attempted_and_unknown_ids(self):
        data=completed()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.assertEqual(coverage_errors(data,root),[])
            data["coverage"][0].update(status="cannot_verify",attempted=False,reason="Ran out of time")
            self.assertTrue(coverage_errors(data,root))
            data["coverage"][0].update(status="not_checked")
            self.assertTrue(coverage_errors(data,root))
            data["coverage"][0]["item_id"]="invented"
            self.assertTrue(coverage_errors(data,root))
