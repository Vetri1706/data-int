import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from grounding import chunk_sources, validate_candidates, rank_chunks, constraint_passes
from semantic_evidence import bind_review, review_records
from geography import preserve_geographic_scope
from test_grounding import document


class EvidenceReviewTests(unittest.IsolatedAsyncioTestCase):
    def setup_case(self):
        text = '# Delta Institute\n\nLocation: Chennai\nResearch: Aerospace Engineering\n'
        chunk = chunk_sources([document(text=text)])[0]
        contract = {'entity_type': 'institute', 'fields': [
            {'name': 'name', 'required': True}, {'name': 'location', 'required': True},
            {'name': 'specialization', 'required': True}], 'constraints': [], 'evidence_policy': {'min_sources': 1}}
        record = {'canonical_name': 'Delta Institute', 'name': 'Delta Institute', 'location': 'Chennai',
                  'specialization': 'Aerospace Engineering', 'chunk_id': chunk['chunk_id']}
        return chunk, contract, record

    async def test_heading_relations_require_a_separate_bound_review(self):
        chunk, contract, record = self.setup_case()
        values = {'canonical_name': 'Delta Institute', 'name': 'Delta Institute', 'location': 'Chennai', 'specialization': 'Aerospace Engineering'}
        model = AsyncMock(return_value=SimpleNamespace(content=json.dumps({'claims': [
            {'field_name': k, 'state': 'supported', 'observed_value': v, 'chunk_id': chunk['chunk_id'],
             'quote': chunk['text'], 'reason': 'Heading binds this institution to its own description'} for k, v in values.items()]})))
        before = validate_candidates([record], [chunk], contract)
        self.assertFalse(any(r['accepted'] for r in before))
        reviews, cache, calls = await review_records([record], [chunk], contract, model)
        result = validate_candidates([record], [chunk], contract, reviewed_claims=reviews)
        self.assertTrue(result[0]['accepted'])
        for ev in result[0]['provenance']['field_evidence']:
            self.assertEqual(ev['verbatim_quote'], chunk['text'][ev['char_start']:ev['char_end']])
        await review_records([record], [chunk], contract, model, cache)
        self.assertEqual(model.await_count, 1)

    def test_fabricated_quote_chunk_value_or_image_identity_never_binds(self):
        chunk, _, _ = self.setup_case()
        valid = {'state': 'supported', 'chunk_id': chunk['chunk_id'], 'quote': chunk['text'], 'observed_value': 'Chennai'}
        for change in [{'quote': 'Delta Institute is based in Chennai.'}, {'chunk_id': 'invented'}, {'observed_value': 'Mumbai'}]:
            self.assertIsNone(bind_review({**valid, **change}, 'Delta Institute', {'name': 'location'}, 'Chennai', {chunk['chunk_id']: chunk}))
        chunk['text'] = '![Delta Institute logo](https://example.com/logo.png)'
        self.assertIsNone(bind_review({**valid, 'quote': chunk['text'], 'observed_value': 'Delta Institute'}, 'Delta Institute', {'name': 'canonical_name'}, 'Delta Institute', {chunk['chunk_id']: chunk}))

    def test_deterministic_contradiction_cannot_be_overridden(self):
        chunk = chunk_sources([document(text='Acme is based in Mumbai. Beta is based in Chennai.')])[0]
        record = {'canonical_name': 'Acme', 'name': 'Acme', 'location': 'Chennai', 'chunk_id': chunk['chunk_id']}
        contract = {'fields': [{'name': 'name', 'required': True}, {'name': 'location', 'required': True}]}
        forged = {0: {'location': {'state': 'supported', 'reason': 'wrong model judgement', 'evidence': []}}}
        result = validate_candidates([record], [chunk], contract, reviewed_claims=forged)
        self.assertFalse(result[0]['accepted'])
        self.assertEqual(result[0]['claims']['location']['state'], 'contradicted')

    def test_model_support_for_historical_or_irrelevant_mentions_is_rejected(self):
        for text in ['Acme was based in Chennai in 2019.', 'Acme discussed Chennai at a conference.']:
            chunk = chunk_sources([document(text=text)])[0]
            raw = {'state': 'supported', 'chunk_id': chunk['chunk_id'], 'quote': text, 'observed_value': 'Chennai'}
            self.assertIsNone(bind_review(raw, 'Acme', {'name': 'location'}, 'Chennai', {chunk['chunk_id']: chunk}))

    def test_unsupported_does_not_mean_contradicted(self):
        text = 'Acme holds ISO 9001 certification.'
        chunk = chunk_sources([document(text=text)])[0]
        raw = {'state': 'contradicted', 'chunk_id': chunk['chunk_id'], 'quote': text, 'observed_value': 'ISO 9001'}
        self.assertIsNone(bind_review(raw, 'Acme', {'name': 'certification'}, 'ISO 27001', {chunk['chunk_id']: chunk}))

    def test_founding_date_does_not_invalidate_present_offerings(self):
        text = 'Delta Institute was established in 2007 and offers Aerospace Engineering.'
        chunk = chunk_sources([document(text=text)])[0]
        raw = {'state': 'supported', 'chunk_id': chunk['chunk_id'], 'quote': text, 'observed_value': 'Aerospace Engineering'}
        self.assertIsNotNone(bind_review(raw, 'Delta Institute', {'name': 'field_of_study'}, 'Aerospace Engineering', {chunk['chunk_id']: chunk}))

    def test_subject_constraint_excludes_a_supported_unrelated_discipline(self):
        import graph
        c = graph.normalize_data_contract({'fields': [{'name': 'field_of_study'}]},
            'Find research institutes in aerospace engineering in South India')
        topic = next(x for x in c['constraints'] if x['field'] == 'field_of_study')
        self.assertFalse(constraint_passes('Geophysical research', topic['operator'], topic['target_value']))
        self.assertTrue(constraint_passes('aerospace research and development', topic['operator'], topic['target_value']))

    def test_contract_constraints_have_fields_and_regions_are_not_literal_addresses(self):
        import graph
        c = graph.normalize_data_contract({'fields': [{'name': 'location'}], 'constraints': [
            {'field': 'research_focus', 'operator': 'contains', 'target_value': 'aerospace engineering', 'is_hard': True},
            {'field': 'location', 'operator': 'contains', 'target_value': 'South India', 'is_hard': True}]},
            'Find research institutes in aerospace engineering in South India', generated=True)
        self.assertTrue(any(f['name'] == 'research_focus' and f['required'] for f in c['fields']))
        location_rules = [x for x in c['constraints'] if x['field'] == 'location']
        self.assertEqual(len(location_rules), 1)
        self.assertEqual(location_rules[0]['operator'], 'in_region')

    def test_geographic_scope_survives_an_omitted_model_constraint(self):
        _, contract, _ = self.setup_case()
        preserve_geographic_scope(contract, 'Find aerospace research institutes in South India')
        self.assertEqual(contract['constraints'][0]['operator'], 'in_region')
        self.assertTrue(constraint_passes('Chennai, Tamil Nadu', 'in_region', 'south india'))
        self.assertFalse(constraint_passes('Kanpur, Uttar Pradesh', 'in_region', 'south india'))
        self.assertFalse(constraint_passes('unknown', 'in_region', 'south india'))

    def test_retrieval_covers_multiple_pages_before_directory_repetition(self):
        pages = [document('https://directory.example', text='Aerospace engineering research. ' * 200),
                 document('https://institute.example', text='Aerospace engineering laboratory at an institute.')]
        chunks = chunk_sources(pages)
        selected = rank_chunks(chunks, 'aerospace engineering research', {}, top_k=2)
        self.assertEqual(len({c['url'] for c in selected}), 2)
