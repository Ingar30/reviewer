"""A prose cross-reference is not another structured disposition or source mapping."""
import copy
import unittest
from tests.test_evidence_contracts import bundle
from tests.mock_responses import editor_payload
from editor_decisions import render, decision_errors
from check_final_report import traceability_failures


class TraceabilityIdentityTests(unittest.TestCase):
    def setUp(self):
        self.bundle=bundle()
        self.bundle['canonical_findings'].append({**copy.deepcopy(self.bundle['canonical_findings'][0]),
            'canonical_id':'CANON-002','source_findings':[{'reviewer':'crossref_auditor','id':'CROSSREF-001'}]})
        self.artifact=editor_payload(self.bundle)

    def test_known_ids_in_explanatory_prose_do_not_create_rows_or_mappings(self):
        self.artifact['decisions'][0]['reason']='Related to CANON-002 and crossref_auditor:CROSSREF-001; distinct evidence.'
        self.assertEqual(decision_errors(self.artifact,self.bundle),[])
        self.assertEqual(traceability_failures(render(self.artifact,self.bundle),self.bundle),[])

    def test_actual_duplicates_unknown_ids_and_wrong_columns_still_fail(self):
        text=render(self.artifact,self.bundle)
        row=next(line for line in text.splitlines() if '| CANON-001 |' in line)
        for bad in (text+'\n'+row, text.replace('| CANON-001 |','| CANON-001 CANON-002 |'),
                    text.replace('| CANON-001 |','| CANON-999 |'),
                    text.replace('numerical_auditor:NUM-001','crossref_auditor:CROSSREF-001'),
                    text.replace('| CANON-001 |','| No ID |')):
            with self.subTest(bad=bad): self.assertTrue(traceability_failures(bad,self.bundle))
        duplicate=copy.deepcopy(self.bundle); duplicate['canonical_findings'].append(duplicate['canonical_findings'][0])
        self.assertTrue(traceability_failures(text,duplicate))

    def test_unknown_prose_ids_and_body_ids_still_fail(self):
        self.artifact['decisions'][0]['reason']='See CANON-999.'
        self.assertTrue(traceability_failures(render(self.artifact,self.bundle),self.bundle))
        self.artifact['decisions'][0]['reason']='Ordinary explanation.'
        self.artifact['blocks'][0]['markdown']+=' CANON-002'
        self.assertTrue(traceability_failures(render(self.artifact,self.bundle),self.bundle))

    def test_source_in_reason_cannot_replace_required_source_column(self):
        source_id = "numerical_auditor:NUM-001"
        self.artifact["decisions"][0]["reason"] = f"Source discussed: {source_id}."
        text = render(self.artifact, self.bundle)
        self.assertEqual(traceability_failures(text, self.bundle), [])
        missing_source = text.replace(f"| {source_id} |", "| No source supplied |")
        self.assertNotEqual(missing_source, text)
        self.assertIn(source_id, missing_source)
        self.assertIn(
            f"missing source finding identifier from CANON-001 row: {source_id}",
            traceability_failures(missing_source, self.bundle),
        )


if __name__=='__main__': unittest.main()
