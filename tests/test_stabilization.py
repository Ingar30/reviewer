"""Acceptance-path regressions; synthetic sources, no manuscript fixtures/calls."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

from tests.test_evidence_gates import completed, REPO
from tests.test_evidence_contracts import arithmetic, quantity, bundle
from tests.test_reviewer_config import finding
from tests.mock_responses import editor_payload
from evidence_registry import build_registry
from reviewer_config import load_reviewers_config
from validate_review_json import validate_review_output
from editor_decisions import decision_errors, render


class AcceptanceRegressionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.parsed = self.root / 'work/paper-x/parsed'
        self.parsed.mkdir(parents=True)
        (self.parsed / 'manifest.json').write_text(json.dumps(
            {'source_pdf_sha256': 'a'*64, 'summary': {'page_count': 1}}))
        (self.parsed / 'page_index.json').write_text('[]')
        (self.parsed / 'page_001.md').write_text(
            'Both sources report 12. Inputs 2 and 3; reported total 6. '
            'Estimate -0.5; exponent 1e-3;\n21Our measurements are correlated.', encoding='utf-8')
        registry = build_registry(self.parsed)
        obj = next(o for o in registry['objects'] if o['path'] == 'page_001.md')
        self.source = dict(id='s', type='text', label=None, path='work/paper-x/parsed/page_001.md',
                           page=1, page_label=None, section=None, text_quote='Both sources report 12.',
                           url=None, object_id=obj['id'], correspondence='text', verification_note=None)
        self.data = completed()
        self.data['coverage'][0]['reason'] = 'All synthetic references checked.'
        self.data['findings'] = [finding(id='CROSSREF-001', numeric_check=None,
                                      source_objects=[self.source], claim_evidence_links=[])]
        self.schema = json.loads((REPO / 'schemas/reviewer_output.schema.json').read_text())
        self.reviewers = load_reviewers_config(REPO / 'config/reviewers.json')

    def errors(self):
        return validate_review_output(self.data, self.schema, self.reviewers, repo=self.root,
                                      expected_reviewer=self.data['reviewer'], paper_id='paper-x', require_complete=True)

    def test_cross_source_cannot_invent_quantity_under_valid_source_id(self):
        self.assertEqual(self.errors(), [])
        self.data['findings'][0]['numeric_check'] = dict(kind='cross_source', quantities=[quantity(12), quantity(99)],
            comparability='Same count in two passages', observed_discrepancy='12 versus 99',
            possible_explanation='Unknown', suggested_correction='Reconcile')
        self.assertTrue(self.errors())
        self.data['findings'][0]['numeric_check']['quantities'][1]['value'] = '12'
        self.assertEqual(self.errors(), [])

    def test_cross_source_polarity_labels_not_invented_numeric_codes(self):
        from numerical_checks import quantity_source_errors
        check = {'kind':'cross_source','quantities':[quantity('+'),quantity('\u2212')]}
        sources=[{'id':'s','correspondence':'text','text_quote':'Rule outputs (+) and (\u2212).'}]
        self.assertEqual(quantity_source_errors(check,sources),[])
        sources[0]['text_quote']='Estimates +3 and \u22122.'
        self.assertTrue(quantity_source_errors(check,sources))

    def test_unresolved_indispensable_input_not_unrelated_citation(self):
        item = self.data['findings'][0]
        item['numeric_check'] = arithmetic()
        self.source['text_quote'] = 'Inputs 2 and 3; reported total 6.'
        item['source_objects'].append({**self.source, 'id': 'background', 'correspondence': 'unresolved',
                                       'verification_note': 'Unrelated background not legible'})
        self.assertEqual(self.errors(), [])
        self.source.update(correspondence='unresolved', verification_note='Indispensable input not legible')
        self.assertTrue(self.errors())
        item.update(assessment='cannot_verify', cannot_verify_reason='Conditional on unreadable inputs')
        self.assertEqual(self.errors(), [])

    def test_sign_and_exponent_fragments_and_honest_visual_footnote(self):
        for quote in ('.5', '-3'):
            with self.subTest(quote=quote):
                self.source['text_quote'] = quote
                self.assertTrue(self.errors())
        for quote in ('-0.5', '1e-3'):
            self.source['text_quote'] = quote
            self.assertEqual(self.errors(), [])
        self.source['text_quote'] = 'Our measurements are correlated.'
        self.assertTrue(self.errors())  # No arbitrary stripping of footnote/subscript digits.
        self.source.update(correspondence='visual', verification_note='Page image inspected: 21 is a superscript footnote marker.')
        self.assertEqual(self.errors(), [])
        self.source.update(correspondence='text', text_quote=None)
        self.assertTrue(self.errors())

    def test_finished_but_unusable_preflight_is_not_permission_to_review(self):
        self.data.update(reviewer='parser_quality_auditor', findings=[], run_status='cannot_verify')
        self.data['completion']['evidence_limitations'] = ['No trustworthy representation or fallback']
        self.data['coverage'][0].update(status='cannot_verify', reason='No trustworthy representation or fallback')
        self.assertTrue(self.errors())
        self.data.update(run_status='ok')
        self.assertTrue(self.errors())  # Overall unavailable remit still blocks.
        self.data['coverage'][0].update(status='checked_no_issue', reason='Readable main text; one table unavailable; explicitly limited scope')
        self.assertEqual(self.errors(), [])

    def test_model_schema_does_not_invite_legacy_numbers_or_null_sampling_reasons(self):
        from jsonschema import Draft202012Validator
        self.data['coverage'][0].update(scope='sampled', reason=None)
        self.assertFalse(Draft202012Validator(self.schema).is_valid(self.data))
        self.assertTrue(self.errors())
        self.data['coverage'][0].update(scope='exhaustive')
        self.assertEqual(self.errors(), [])  # Retained exhaustive records need no invented reason.
        self.data['coverage'][0]['reason'] = 'All checked'
        self.data['findings'][0]['numeric_check'] = finding()['numeric_check']
        self.assertFalse(Draft202012Validator(self.schema).is_valid(self.data))
        self.assertTrue(self.errors())
        self.assertEqual(validate_review_output(self.data, self.schema, self.reviewers, repo=self.root), [])


class EditorialRegressionTests(unittest.TestCase):
    def test_empty_introduction_with_rendered_treatment_needs_no_filler(self):
        from check_final_report import report_failures
        from jsonschema import Draft202012Validator
        b = bundle()
        for introduction in ('', ' \n '):
            a = editor_payload(b)
            target = a['decisions'][0]['block_ids'][0]
            next(block for block in a['blocks'] if block['id'] == target)['markdown'] = introduction
            schema = json.loads((REPO / 'schemas/editor_decisions.schema.json').read_text())
            self.assertTrue(Draft202012Validator(schema).is_valid(a))
            self.assertEqual(decision_errors(a, b), [])
            text = render(a, b)
            self.assertIn(a['decisions'][0]['treatment'], text)
            self.assertEqual(report_failures(text, bundle=b, decisions=a), [])

    def test_empty_blocks_missing_treatments_and_invalid_evidence_still_fail(self):
        from check_final_report import report_failures
        b = bundle()
        for defect in ('empty_block', 'missing_treatment', 'unknown_finding', 'missing_block',
                       'unfaithful', 'unknown_url'):
            with self.subTest(defect=defect):
                a = editor_payload(b)
                decision = a['decisions'][0]
                target = next(block for block in a['blocks'] if block['id'] == decision['block_ids'][0])
                target['markdown'] = ''
                if defect == 'empty_block':
                    a['blocks'].append({'id':'empty', 'section':'Additional Findings', 'markdown':' \n '})
                elif defect == 'missing_treatment': decision['treatment'] = ' \n '
                elif defect == 'unknown_finding': decision['canonical_id'] = 'CANON-999'
                elif defect == 'missing_block': decision['block_ids'] = ['missing']
                elif defect == 'unfaithful': a['semantic_checks'][0]['verdict'] = 'unresolved'
                else: decision['treatment'] += ' Evidence: https://example.org/unsupported'
                if defect == 'unknown_url':
                    self.assertTrue(report_failures(render(a, b), bundle=b, decisions=a))
                else:
                    self.assertTrue(decision_errors(a, b))
                    with self.assertRaises(ValueError): render(a, b)

    def test_required_sections_cannot_be_headings_only_even_with_findings(self):
        from check_final_report import report_failures
        b = bundle()
        a = editor_payload(b)
        a['blocks'][0]['markdown'] = '### Summary'
        self.assertIn('empty report section: ## Executive Summary',
                      report_failures(render(a, b), bundle=b, decisions=a))

    def test_model_cannot_claim_human_or_independent_assessment(self):
        b = bundle()
        for assessor in ('human', 'independent_model'):
            a = editor_payload(b)
            a['semantic_checks'][0]['assessor'] = assessor
            self.assertTrue(decision_errors(a, b))

    def test_sections_and_tables_checked_in_treatments_too(self):
        b = bundle()
        for prose in ('## Injected section', '  ## Indented section', 'Replacement\n---', '| Area | Issue |'):
            for field in ('markdown', 'treatment'):
                a = editor_payload(b)
                (a['blocks'][0] if field == 'markdown' else a['decisions'][0])[field] = prose
                self.assertTrue(decision_errors(a, b), (field, prose))
        a = editor_payload(b)
        a['decisions'][0]['treatment'] = '| Area | Issue |\n| --- | --- |\n| Definition | Specify window |'
        self.assertEqual(decision_errors(a, b), [])
        self.assertIn('| --- | --- |', render(a, b))

    def test_partly_defined_measure_preserves_qualification(self):
        b = bundle()
        b['canonical_findings'][0]['finding_summary'] = 'The text defines claim filing, but not its observation window.'
        a = editor_payload(b)
        a['decisions'][0].update(disposition='narrowed', surviving_claim='Observation window missing',
            treatment='The paper defines the event as filing a claim. Specify its observation window.',
            qualifications=['Claim filing is already defined; do not call the event undefined.'])
        self.assertIn('defines the event as filing', render(a, b))
        a['decisions'][0]['treatment'] = 'The paper never defines the event.'
        a['semantic_checks'][0].update(verdict='not_faithful', reason='Source already defines filing; only window missing.')
        self.assertTrue(decision_errors(a, b))  # Enforcement, not automatic semantic detection.


class RepairIntegrationTests(unittest.TestCase):
    setUp = AcceptanceRegressionTests.setUp

    def run_reviewer(self, fix):
        from review_paper import run_reviewer_batch, RunResult, reviewer_output_errors
        work = self.parsed.parent
        prompts, reviews, logs = [work / name for name in ('prompts', 'reviews', 'logs')]
        for p in (prompts, reviews, logs): p.mkdir()
        schema = self.root / 'schemas/reviewer_output.schema.json'
        schema.parent.mkdir()
        schema.write_text(json.dumps(self.schema))
        reviewer = next(r for r in self.reviewers if r.name == 'crossref_auditor')
        (prompts / reviewer.prompt).write_text('Synthetic original task')
        output = reviews / reviewer.output
        calls, accepted = [], []
        def start(*args, **kwargs):
            calls.append(kwargs.get('prompt_override'))
            data = copy.deepcopy(self.data)
            if len(calls) == 1 or not fix:
                data['coverage'][0].update(scope='sampled', reason=None)
            output.write_text(json.dumps(data))
            return reviewer, SimpleNamespace(poll=lambda: 0), logs/'out', logs/'err', 0
        def accept(r, result, started):
            if not reviewer_output_errors(output, r, self.root, 'paper-x', schema):
                accepted.append(r.name)
        with mock.patch('review_paper.start_reviewer', side_effect=start), mock.patch(
            'review_paper.wait_reviewer', return_value=RunResult(reviewer.name, 0, logs/'out', logs/'err')):
            run_reviewer_batch([reviewer], self.root, prompts, reviews, schema, logs,
                               on_result=accept, max_repair_calls=2)
        self.assertEqual(len(calls), 2)
        self.assertIn('Sampled coverage must state its scope and limitations', calls[1])
        previous = json.loads((work/'repairs/01/previous.json').read_text())
        self.assertIsNone(previous['coverage'][0]['reason'])
        from stage_repair import reserve_repair
        self.assertIsNone(reserve_repair(work, reviewer.name, 8, output, ['still invalid'], 'original', self.root))
        return accepted

    def test_single_repair_can_complete_valid_review_without_rewriting_original(self):
        self.assertEqual(self.run_reviewer(True), ['crossref_auditor'])

    def test_failed_repair_never_gets_receipt_or_third_attempt(self):
        self.assertEqual(self.run_reviewer(False), [])

    def test_zero_and_shared_total_cap_reserve_before_call(self):
        from stage_repair import reserve_repair
        candidate = self.parsed.parent/'output.json'
        candidate.write_text('{"original":true}')
        self.assertIsNone(reserve_repair(self.parsed.parent,'reviewer',0,candidate,['error'],'prompt',self.root))
        self.assertIsNotNone(reserve_repair(self.parsed.parent,'reviewer',1,candidate,['error'],'prompt',self.root))
        self.assertIsNone(reserve_repair(self.parsed.parent,'editor',1,candidate,['error'],'prompt',self.root))

    def test_editor_repair_revalidates_and_preserves_rejected_draft(self):
        from pipeline_paths import paper_run_paths
        from review_paper import run_editor, RunResult
        paths = paper_run_paths(self.root, 'paper-x')
        paths.editor_dir.mkdir()
        paths.log_dir.mkdir()
        empty = {'paper_id':'paper-x','canonical_findings':[]}
        paths.bundle_path.write_text(json.dumps(empty))
        paths.editor_input_path.write_text('Synthetic editor prompt')
        schema = self.root/'schemas/editor_decisions.schema.json'
        schema.parent.mkdir()
        schema.write_bytes((REPO/'schemas/editor_decisions.schema.json').read_bytes())
        calls=[]
        started_at = 1_700_000_000.0
        def call(label, *args, **kwargs):
            if label=='editor':
                calls.append(kwargs['input_text'])
                artifact=editor_payload(empty)
                if len(calls)==1:artifact['blocks'][0]['markdown']='| Broken | Header |'
                output = paths.editor_dir/'editor_decisions.json'
                output.write_text(json.dumps(artifact))
                # Model elapsed execution explicitly: immediate Windows writes
                # can round below time.time() by one floating-point tick.
                os.utime(output, (started_at + len(calls), started_at + len(calls)))
            return RunResult(label,0,paths.log_dir/'out',paths.log_dir/'err')
        args=SimpleNamespace(backend='codex', model='unchanged', reasoning_effort='xhigh', agent_timeout_minutes=1,max_repair_calls=1)
        with mock.patch('review_paper.run_required',side_effect=call), mock.patch('review_paper.agent_exec_command',return_value=['mock']), \
                mock.patch('review_paper.time.time', return_value=started_at):
            run_editor(args,self.root,paths,paths.log_dir)
        self.assertEqual(len(calls),2)
        self.assertTrue(paths.report_path.exists())
        self.assertIn('matching delimiter row',calls[1])
        self.assertIn('Broken', (paths.work_root/'repairs/01/previous.json').read_text())

    def test_freshness_rejects_missing_and_older_output(self):
        from review_paper import require_fresh_file
        output = self.root/'freshness.json'
        with self.assertRaises(FileNotFoundError):
            require_fresh_file(output, 0, 'candidate')
        output.write_text('{}')
        written_at = output.stat().st_mtime
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            require_fresh_file(output, written_at + 1, 'candidate')
        require_fresh_file(output, written_at, 'candidate')
