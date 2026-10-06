import unittest
import prepare_stm32wl3_layer1_admission_proposal_v46 as p

class TestSTM32WL3Layer1AdmissionProposalV46(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()
        cls.by = {r["icpn"]: r for r in cls.rows}

    def test_partition(self):
        self.assertEqual(self.summary["proposal_addition_count"], 47)
        self.assertEqual(self.summary["backend_state_for_new_rows"], {"no_mapping": 47})
        self.assertFalse(self.summary["backend_scope_evaluated"])

    def test_poststate_math(self):
        self.assertEqual(self.summary["production_exact_prestate"], 4486)
        self.assertEqual(self.summary["production_source_count_prestate"], 25)
        self.assertEqual(self.summary["production_wl3_exact_prestate"], 0)
        self.assertEqual(self.summary["production_wl3_exact_after_if_approved"], 47)
        self.assertEqual(self.summary["production_source_count_after_if_approved"], 26)
        self.assertEqual(self.summary["production_exact_after_if_approved"], 4533)
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"], 4454)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"], 96)
        self.assertAlmostEqual(self.summary["whole_st_active_coverage_after_if_approved_percent"], 97.8901)

    def test_metadata_partition(self):
        self.assertEqual(self.summary["metadata_direct_ordering_information_exact_count"], 45)
        self.assertEqual(self.summary["metadata_bounded_exception_exact_count"], 2)
        self.assertEqual(
            self.summary["metadata_exception_exact_icpns"],
            ["STM32WL31C8V6", "STM32WL31CBV6"],
        )

    def test_representative_rows(self):
        self.assertEqual(self.by["STM32WL30K8V6"]["pin_count"], "32")
        self.assertEqual(self.by["STM32WL31C8V6"]["pin_count"], "48")
        self.assertEqual(self.by["STM32WL33CCV7ATR"]["flash_size"], "256 KiB")
        self.assertEqual(self.by["STM32WL33CCV7ATR"]["option_suffix"], "ATR")
        self.assertEqual(self.by["STM32WL3RKBV6X"]["option_suffix"], "X")

    def test_exact_pin_exceptions(self):
        for icpn in ("STM32WL31C8V6", "STM32WL31CBV6"):
            self.assertEqual(
                self.by[icpn]["metadata_exception"],
                "WL31_C_PIN48_EXACT_PRODUCT_EXCEPTION",
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
