"""Bounded shadow verification tests use explicit synthetic assessor judgments."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evidence_registry import build_registry
from finding_verification import prepare, verification_errors
from strict_json import parse_json
from tests.test_evidence_contracts import arithmetic, quantity
from numerical_checks import evaluate


class VerificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.parsed = self.root / "work/p/parsed"
        (self.parsed / "pages").mkdir(parents=True)
        (self.parsed / "pages/page_001.md").write_text("Synthetic estimate: 5, not 6.")
        (self.parsed / "manifest.json").write_text(json.dumps({"source_pdf_sha256": "a"*64, "summary": {"page_count":1}}))
        (self.parsed / "page_index.json").write_text("[]")
        registry = build_registry(self.parsed)
        self.oid = next(o["id"] for o in registry["objects"] if o["path"] == "pages/page_001.md")
        self.bundle = self.root / "bundle.json"
        self.bundle.write_text(json.dumps({"paper_id":"p", "canonical_findings":[
            {"canonical_id":"CANON-001", "severity":"high", "finding_summary":"Synthetic discrepancy"}]}))
        self.packet_path = self.root / "packet.json"
        self.packet = prepare(self.bundle, ["CANON-001"], self.packet_path)
        self.data = {"version":1, "paper_id":"p", "status":"complete", "limitations":[],
            "packet_sha256":hashlib.sha256(json.dumps(self.packet,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            "results":[{"canonical_id":"CANON-001", "outcome":"confirmed", "reason":"Synthetic source comparison",
                "strongest_alternative":"Checked whether a different denominator explains it",
                "observation":"Displayed values differ", "diagnosis":"Cause not identified", "remedy":"Reconcile narrowly",
                "surviving_claim":None, "editor_fidelity":"faithful", "editor_reason":"MOCK faithful qualified treatment",
                "evidence":[{"object_id":self.oid,"page":1,"quote":"Synthetic estimate: 5, not 6.","correspondence":"text","note":None}]}]}

    def errors(self):
        return verification_errors(self.data,self.packet,self.root)

    def test_all_four_outcomes_preserve_original_candidate(self):
        original = self.packet_path.read_bytes()
        for outcome in ("confirmed","narrowed","unsupported","unresolved"):
            self.data["results"][0].update(outcome=outcome,surviving_claim="Narrow observation" if outcome=="narrowed" else None)
            self.assertEqual(self.errors(),[])
        self.assertEqual(original,self.packet_path.read_bytes())

    def test_failed_or_contradictory_verifier_never_confirms(self):
        self.data["status"]="failed"
        self.assertTrue(self.errors())
        self.data["status"]="complete"
        self.data["results"].append({**copy.deepcopy(self.data["results"][0]),"outcome":"unsupported"})
        self.assertTrue(self.errors())

    def test_unavailable_source_remains_unresolved(self):
        result = self.data["results"][0]
        result["evidence"][0].update(correspondence="unresolved",quote=None,note="Retained page cannot establish the comparison")
        self.assertTrue(self.errors())
        result["outcome"]="unresolved"
        self.assertEqual(self.errors(),[])
        result["evidence"]=[]
        self.assertEqual(self.errors(),[])

    def test_packet_identity_and_budget_cannot_change_silently(self):
        self.data["packet_sha256"]="wrong"
        self.assertTrue(self.errors())
        for ids in ([],["CANON-001"]*2,[f"CANON-{i:03d}" for i in range(6)]):
            with self.assertRaises(ValueError):prepare(self.bundle,ids,self.root/'new.json')
        with self.assertRaises(FileExistsError):prepare(self.bundle,["CANON-001"],self.packet_path)

    def test_shared_decoder_rejects_malicious_ambiguous_artifacts(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":"\\ud800"}'):
            with self.assertRaises((ValueError,UnicodeError)):parse_json(text)

    def test_dimensional_ratio_is_not_forced_to_be_a_percentage(self):
        data=arithmetic()
        data.update(operation="ratio",quantities=[quantity(20,unit="words"),quantity(2,unit="minutes")],
                    reported=quantity(11,unit="words/minute"),computed_value="10")
        self.assertEqual(evaluate(data)["status"],"arithmetic_discrepancy")
        data=arithmetic();data["reported"]["unit"]="unrelated unit"
        self.assertEqual(evaluate(data)["status"],"unresolved")


if __name__ == "__main__":
    unittest.main()
