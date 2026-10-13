#!/usr/bin/env python3
"""Offline-only contract for the recorded genuine 8-batch Microchip recovery."""
import json
from pathlib import Path
import unittest

ARCHIVE=Path(__file__).resolve().parent/'microchip-mcp-recovery-v2-observation-20261013.json'
SOURCE_SHA='9a00c71e262882687219fce322169435a36d45ac06d0a26bf146c4d6a5db83b0'
BATCH_IDS=frozenset(('8bit-0004','8bit-0005','8bit-0013','8bit-0048',
                     '8bit-0071','8bit-0072','8bit-0082','8bit-0105'))

def verify(p):
    assert p['schema_version']==1 and p['manufacturer']=='Microchip'
    assert p['original_dfp_index_sha256']==SOURCE_SHA
    assert p['source_live_run_id']==38373429583
    assert p['prior_pr']==829 and p['recovery_pr']==848
    assert p['old_full_first_pass_unique_candidates']==23276
    assert p['recovered_batches']==8
    assert p['recovered_positive_queries']==80
    assert p['recovered_zero_prefix_queries']==0
    assert p['recovered_unverified_queries']==0
    assert p['new_cross_source_distinct_candidates']==775
    assert p['new_final_source_linked_distinct_research_candidates']==24051
    assert (p['old_full_first_pass_unique_candidates']+
            p['new_cross_source_distinct_candidates']==
            p['new_final_source_linked_distinct_research_candidates'])
    assert (p['new_total_query_positive']+p['new_total_query_fuzzy_only']+
            p['new_total_query_not_found']+p['new_total_query_timeout_unverified']==
            p['planned_original_dfp_queries']==3198)
    assert (sum(p['observed_raw_lifecycle'].values())==24051 and
            p['observed_raw_lifecycle']['Active']==23801 and
            p['observed_raw_lifecycle']['Not Recommended For New Design']==250)
    assert set(p['original_zip_sha256'])==BATCH_IDS
    assert all(len(d)==64 and all(c in '0123456789abcdef' for c in d)
               for d in p['original_zip_sha256'].values())
    assert p['cross_source_raw_lifecycle_conflicts']==0
    assert p['recovery_original_raw_response_files_sha256_rechecked']==423
    assert p['global_active_denominator'] is None
    assert p['manufacturer_population_complete'] is False
    assert p['production_write_authorized'] is False
    assert p['programming_support_claimed'] is False
    assert p['not_found_is_eol_verdict'] is False
    return True

class RecoveryObservationTests(unittest.TestCase):
    def test_frozen_original_source_research_only_scope(self):
        self.assertTrue(verify(json.loads(ARCHIVE.read_text(encoding='utf-8'))))

    def test_reject_population_inflation_or_production_promotion(self):
        src=json.loads(ARCHIVE.read_text(encoding='utf-8'))
        for k,v in [('production_write_authorized',True),
                    ('global_active_denominator',24051),
                    ('recovered_positive_queries',70),
                    ('new_total_query_not_found',0),
                    ('recovery_original_raw_response_files_sha256_rechecked',0)]:
            with self.subTest(field=k),self.assertRaises(AssertionError):
                verify(dict(src,**{k:v}))

if __name__=='__main__':
    unittest.main()
