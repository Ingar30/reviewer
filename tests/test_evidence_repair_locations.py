"""Acceptance-path footnote diagnostics, without inferring replacement text."""
import json
import unittest

from tests import test_stabilization
from evidence_registry import build_registry, review_evidence_checks


class LocatedEvidenceTests(unittest.TestCase):
    errors = test_stabilization.AcceptanceRegressionTests.errors
    def setUp(self):
        test_stabilization.AcceptanceRegressionTests.setUp(self)
        self.page = self.parsed / 'page_001.md'
        self.page.write_text('21The measurements are correlated.\n'
                             'The fee deters respondents from investing.19\n'
                             'Estimate -0.5; exponent 1e-3; x_2; revenue 15%; not supported.',
                             encoding='utf-8')
        self.image = self.parsed / 'page_001.png'
        # A small actual PNG; visual content is not machine-adjudicated.
        import base64
        self.image.write_bytes(base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1sAAAAASUVORK5CYII='))
        self.registry = build_registry(self.parsed)
        self.source['object_id'] = next(o['id'] for o in self.registry['objects'] if o['path']=='page_001.md')

    def test_footnote_shapes_require_explicit_visual_inspection_not_digit_stripping(self):
        for quote in ('The measurements are correlated.', 'deters respondents from investing'):
            self.source.update(text_quote=quote, correspondence='text', verification_note=None)
            errors = self.errors()
            self.assertEqual(len(errors), 1)
            for label in ('reviewer/stage=crossref_auditor', 'finding=CROSSREF-001', 'source=s',
                          'field=findings.0.source_objects.0', self.source['object_id'],
                          'page_001.md', 'page_001.png', 'not yet inspected'):
                self.assertIn(label, errors[0])
            original = self.page.read_bytes()
            self.source.update(correspondence='visual', verification_note=
                'Synthetic inspection assertion: page_001.png shows a raised footnote label, not part of the quotation.')
            self.assertEqual(self.errors(), [])
            check = review_evidence_checks(self.data, self.root)[0]
            self.assertEqual(check['correspondence'], 'visual_assessment_required')
            self.assertNotEqual(check['correspondence'], 'matched_text_not_adjudicated')
            self.assertEqual(self.page.read_bytes(), original)
            self.source['verification_note'] = ''
            self.assertTrue(self.errors())

    def test_meaning_changing_fragments_still_fail_in_acceptance(self):
        for quote in ('0.5', '.5', '-3', 'e-3', '2', '15', '5%',
                      'The measurements are uncorrelated.', 'deters respondents from saving'):
            with self.subTest(quote=quote):
                self.source['text_quote'] = quote
                self.assertTrue(self.errors())
        for quote in ('-0.5', '1e-3', 'x_2', '15%', 'not supported.'):
            self.source['text_quote'] = quote
            self.assertEqual(self.errors(), [])

    def test_wrong_page_tamper_and_missing_registry_remain_located_failures(self):
        self.source['text_quote'] = 'The measurements are correlated.'
        self.image.write_bytes(b'changed')
        self.assertNotIn('visual candidates', ' '.join(self.errors()))
        self.source.update(correspondence='visual', verification_note='Inspected page image', page=2)
        self.assertTrue(self.errors())
        self.source['page'] = 1
        self.page.write_text('changed', encoding='utf-8')
        self.assertIn('Registered source artifact changed', ' '.join(self.errors()))
        (self.parsed/'source_registry.json').write_text('{invalid', encoding='utf-8')
        errors = ' '.join(self.errors())
        for label in ('CROSSREF-001', 'source=s', 'source_registry', 'page_001.md'):
            self.assertIn(label, errors if label != 'source_registry' else errors.lower().replace(' ', '_'))
