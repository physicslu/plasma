import unittest
import prepare_stm32c5_layer1_admission_proposal_v43 as p

class TestSTM32C5Layer1AdmissionProposalV43(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()
        cls.by = {r["icpn"]: r for r in cls.rows}

    def test_partition(self):
        self.assertEqual(self.summary["proposal_addition_count"], 172)
        self.assertEqual(self.summary["backend_state_for_new_rows"], {"no_mapping": 172})
        self.assertFalse(self.summary["backend_scope_evaluated"])

    def test_poststate_math(self):
        self.assertEqual(self.summary["production_exact_prestate"], 4314)
        self.assertEqual(self.summary["production_source_count_prestate"], 24)
        self.assertEqual(self.summary["production_c5_exact_prestate"], 0)
        self.assertEqual(self.summary["production_c5_exact_after_if_approved"], 172)
        self.assertEqual(self.summary["production_source_count_after_if_approved"], 25)
        self.assertEqual(self.summary["production_exact_after_if_approved"], 4486)
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"], 4407)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"], 143)
        self.assertAlmostEqual(self.summary["whole_st_active_coverage_after_if_approved_percent"], 96.8571)

    def test_metadata_partition(self):
        self.assertEqual(self.summary["metadata_direct_ordering_information_exact_count"], 170)
        self.assertEqual(self.summary["metadata_bounded_exception_exact_count"], 2)
        self.assertEqual(
            self.summary["metadata_exception_exact_icpns"],
            ["STM32C551CCT7", "STM32C551CCT7TR"],
        )
        self.assertEqual(self.summary["dfp_exact_variant_observed_count"], 139)
        self.assertEqual(self.summary["dfp_parent_only_count"], 33)

    def test_representative_rows(self):
        self.assertEqual(self.by["STM32C531FBU6TR"]["package"], "UFQFPN")
        self.assertEqual(self.by["STM32C531FBU6TR"]["pin_count"], "20")
        self.assertEqual(self.by["STM32C542RCT3"]["flash_size"], "256 KiB")
        self.assertEqual(self.by["STM32C562KEU3TR"]["temperature_grade"], "-40 to 125 C")
        self.assertEqual(self.by["STM32C593ZGT6"]["pin_count"], "144")
        self.assertEqual(self.by["STM32C5A3KGU3TR"]["flash_size"], "1024 KiB")

    def test_exact_temp7_exceptions(self):
        for icpn in ("STM32C551CCT7", "STM32C551CCT7TR"):
            self.assertEqual(
                self.by[icpn]["metadata_exception"],
                "C551_TEMP7_EXACT_ESTORE_EXCEPTION",
            )
            self.assertEqual(
                self.by[icpn]["verification_status"],
                "verified_direct_st_exact_product_metadata_override",
            )

    def test_no_capability_overclaim(self):
        self.assertFalse(self.summary["production_write_authorized"])
        self.assertFalse(self.summary["backend_mapping_required_for_layer1_admission"])
        self.assertFalse(self.summary["programming_profile_binding_claimed"])
        self.assertFalse(self.summary["programming_profile_scope_expanded"])
        self.assertFalse(self.summary["engineering_verified_claimed"])
        self.assertFalse(self.summary["field_evidence_claimed"])
        self.assertFalse(self.summary["ps_hil_claimed"])
        self.assertTrue(all(r["backend_mapping_state"] == "no_mapping" for r in self.rows))
        self.assertTrue(all(r["openocd_target_config"] == "" for r in self.rows))

if __name__ == "__main__":
    unittest.main()
