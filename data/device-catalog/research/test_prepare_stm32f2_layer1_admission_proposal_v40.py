import unittest
import prepare_stm32f2_layer1_admission_proposal_v40 as p

class TestSTM32F2Layer1AdmissionProposalV40(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()
        cls.by = {r["icpn"]: r for r in cls.rows}

    def test_partition(self):
        self.assertEqual(self.summary["proposal_addition_count"], 72)
        self.assertEqual(self.summary["backend_state_for_new_rows"], {"no_mapping": 72})
        self.assertFalse(self.summary["backend_scope_evaluated"])

    def test_poststate_math(self):
        self.assertEqual(self.summary["production_exact_prestate"], 4242)
        self.assertEqual(self.summary["production_f2_exact_prestate"], 33)
        self.assertEqual(self.summary["production_f2_exact_after_if_approved"], 105)
        self.assertEqual(self.summary["production_exact_after_if_approved"], 4314)
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"], 4235)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"], 315)
        self.assertAlmostEqual(self.summary["whole_st_active_coverage_after_if_approved_percent"], 93.0769)

    def test_exception_free_metadata(self):
        self.assertEqual(self.summary["metadata_exception_exact_icpns"], [])
        self.assertEqual(self.summary["direct_ordering_information_exact_count"], 72)

    def test_representative_metadata(self):
        self.assertEqual(self.by["STM32F205RGY6TR"]["package"], "WLCSP")
        self.assertEqual(self.by["STM32F205RGY6TR"]["pin_count"], "66")
        self.assertEqual(self.by["STM32F207IGH7"]["package"], "UFBGA")
        self.assertEqual(self.by["STM32F217ZGT6"]["pin_count"], "144")

    def test_no_capability_overclaim(self):
        self.assertFalse(self.summary["production_write_authorized"])
        self.assertFalse(self.summary["programming_profile_binding_claimed"])
        self.assertFalse(self.summary["programming_profile_scope_expanded"])
        self.assertFalse(self.summary["engineering_verified_claimed"])
        self.assertFalse(self.summary["field_evidence_claimed"])
        self.assertFalse(self.summary["ps_hil_claimed"])

if __name__ == "__main__":
    unittest.main()
