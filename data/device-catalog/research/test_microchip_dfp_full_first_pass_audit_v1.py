#!/usr/bin/env python3
"""Research-only consistency guards for the full archived Microchip DFP sweep."""
import json
from pathlib import Path
import unittest

AUDIT = Path(__file__).resolve().parent / 'microchip-dfp-full-first-pass-audit-20261013.json'
PINNED = '9a00c71e262882687219fce322169435a36d45ac06d0a26bf146c4d6a5db83b0'

def check(x):
    assert x['manufacturer']=='Microchip' and x['schema_version']==1
    assert x['original_dfp_index_sha256']==PINNED
    assert x['planned_batches']==321 and x['planned_dfp_queries']==3198
    assert x['batch_archives_with_valid_capture_attestation']==313
    assert x['batches_quarantined_due_to_missing_attestation_after_worker_timeouts']==8
    assert x['batch_archives_with_valid_capture_attestation']+x['batches_quarantined_due_to_missing_attestation_after_worker_timeouts']==321
    assert x['complete_positive_exact_prefix_queries']==2753
    assert x['fully_replayed_zero_exact_prefix_queries']==68
    assert x['manufacturer_not_found_failed_queries']==297
    assert x['timeout_missing_batch_query_results']==80
    assert sum(x[k] for k in ('complete_positive_exact_prefix_queries','fully_replayed_zero_exact_prefix_queries','manufacturer_not_found_failed_queries','timeout_missing_batch_query_results'))==3198
    assert x['verified_original_source_response_links']==23427
    assert x['verified_original_distinct_source_files']==3009
    assert x['unique_exact_prefix_candidates_without_conflicts']==23276
    assert sum(x['raw_lifecycle_counts_nonconflicted'].values())==23276
    assert x['raw_lifecycle_counts_nonconflicted']['Active']==23047
    assert x['raw_lifecycle_counts_nonconflicted']['Not Recommended For New Design']==229
    assert x['raw_lifecycle_conflicts']==0
    for source_field,target in [('positive','complete_positive_exact_prefix_queries'),('fuzzy_only','fully_replayed_zero_exact_prefix_queries'),('not_found','manufacturer_not_found_failed_queries'),('missing','timeout_missing_batch_query_results')]:
        assert sum(l[source_field] for l in x['lanes'].values())==x[target]
    assert x['original_vendor_active_population_complete'] is False
    assert x['unknown_global_active_denominator'] is None
    assert x['production_write_authorized'] is False
    assert x['programming_support_claimed'] is False
    return True

class ResearchAuditTests(unittest.TestCase):
    def test_pinned_source_first_pass_and_nonproduction_boundary(self):
        self.assertTrue(check(json.loads(AUDIT.read_text(encoding='utf-8'))))
    def test_forged_number_or_privilege_is_rejected(self):
        source=json.loads(AUDIT.read_text(encoding='utf-8'))
        for field,value in [('production_write_authorized',True),('programming_support_claimed',True),('unknown_global_active_denominator',23276),('raw_lifecycle_conflicts',1),('complete_positive_exact_prefix_queries',3198),('verified_original_source_response_links',2)]:
            with self.subTest(field=field), self.assertRaises(AssertionError):
                check(dict(source,**{field:value}))

if __name__=='__main__':
    unittest.main()
