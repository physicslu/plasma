#!/usr/bin/env python3
"""Immutable manufacturer ordering boundary review is not Production admission."""
import copy
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'microchip-dfp-ordering-boundary-review-v1.json'
SHA='9a00c71e262882687219fce322169435a36d45ac06d0a26bf146c4d6a5db83b0'

def validate(x):
    assert x['manufacturer']=='Microchip' and x['schema_version']==1
    assert x['original_dfp_index_sha256']==SHA
    assert x['original_vendor_run_id']==38348043707
    assert x['original_vendor_artifact_id']==11790626653
    assert x['device_support_names_are_orderable_skus'] is False
    assert x['research_coverage_does_not_prove_commercial_population'] is True
    assert x['production_write_authorized'] is False
    assert x['manufacturer_population_complete'] is False
    assert x['global_active_denominator'] is None
    assert x['exact_ordering_code_verified_count']==0
    records=x['records']
    assert len(records)==23
    ids=[r['dfp_device_name'] for r in records]
    assert len(ids)==len(set(ids))
    assert len([r for r in records if r['observed_capture_state']=='complete_fuzzy_only'])==9
    assert len([r for r in records if r['observed_capture_state']=='mcp_not_found'])==14
    assert len([r for r in records if r['research_type_classification']=='secondary_core_device_id'])==5
    assert len([r for r in records if r['research_type_classification']=='wireless_module_family'])==8
    for r in records:
        assert r['production_admission'] is False
        assert r['exact_ordering_code_verified'] is False
        assert r['source_batch_id'] in {
            '8bit-0001','16bit-0046','32bit-pic-sam-0021',
            '32bit-pic-sam-0041','wireless-0002',
            'wireless-0003','wireless-0004'}
        assert r['suggested_catalog_handling'] in {
            'manufacturer_module_separate_from_icpn',
            'programming_profile_candidate_not_commercial_orderable_sku',
            'manual_manufacturer_ordering_identity_review'}
        url=r['official_evidence_url']
        if url is not None:
            p=urlparse(url)
            assert p.scheme=='https' and p.hostname in {
                'onlinedocs.microchip.com','www.microchip.com'}
        if r['research_type_classification']=='secondary_core_device_id':
            assert r['dfp_device_name'].endswith('S1')
            assert r['related_parent_or_soc_device']==r['dfp_device_name'][:-2]
    return True

class BoundaryReviewTests(unittest.TestCase):
    def test_original_source_bound_23_exceptions(self):
        self.assertTrue(validate(json.loads(DATA.read_text(encoding='utf-8'))))
    def test_never_publish_fuzzy_module_identity_as_orderable_icpn(self):
        a=json.loads(DATA.read_text(encoding='utf-8'))
        for mutate in (
            lambda x:x.update(global_active_denominator=1397),
            lambda x:x.update(production_write_authorized=True),
            lambda x:x['records'][0].update(exact_ordering_code_verified=True),
            lambda x:x['records'].pop(),
            lambda x:x['records'][0].update(official_evidence_url='https://evil.test/'),
        ):
            b=copy.deepcopy(a)
            mutate(b)
            with self.assertRaises((AssertionError,KeyError)):
                validate(b)

if __name__=='__main__':
    unittest.main()
