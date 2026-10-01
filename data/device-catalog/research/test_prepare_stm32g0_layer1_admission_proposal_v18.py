import unittest
import prepare_stm32g0_layer1_admission_proposal_v18 as p

class TestG0Layer1ProposalV18(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,cls.csv,cls.s=p.build()
    def test_candidate_partition(self):
        self.assertEqual(self.s["candidate_exact_count"],359)
        self.assertEqual(self.s["layer2_backend_state"],
                         {"mapping_candidate":317,"no_mapping":42})
    def test_layer1_does_not_require_backend(self):
        self.assertFalse(self.s["backend_mapping_required_for_layer1_admission"])
        self.assertEqual(self.s["layer1_catalog_resolution"],{"normalized":359})
    def test_poststate_math(self):
        self.assertEqual(self.s["proposed_g0_catalog_exact_after"],406)
        self.assertEqual(self.s["whole_st_active_gap_after"],1587)
        self.assertEqual(self.s["production_exact_total_after_if_approved"],3042)
        self.assertAlmostEqual(self.s["whole_st_active_coverage_after_percent"],65.1209)
    def test_no_implicit_approval(self):
        self.assertFalse(self.s["production_write_authorized"])
        self.assertFalse(self.s["engineering_verified_claimed"])
        self.assertFalse(self.s["field_evidence_claimed"])

if __name__=="__main__": unittest.main()
