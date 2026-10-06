import unittest

import prepare_stm32wb0_layer1_admission_proposal_v52 as p


class TestSTM32WB0Layer1AdmissionProposalV52(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()
        cls.by = {row["icpn"]: row for row in cls.rows}

    def test_partition(self):
        self.assertEqual(self.summary["proposal_addition_count"], 24)
        self.assertEqual(self.summary["backend_state_for_new_rows"], {"no_mapping": 24})
        self.assertFalse(self.summary["backend_scope_evaluated"])
        self.assertFalse(self.summary["backend_type_claimed"])

    def test_poststate_math_is_projection_only(self):
        self.assertEqual(self.summary["production_exact_prestate"], 4565)
        self.assertEqual(self.summary["production_source_count_prestate"], 27)
        self.assertEqual(self.summary["production_wb0_exact_prestate"], 0)
        self.assertEqual(self.summary["production_wb0_exact_after_if_approved"], 24)
        self.assertEqual(self.summary["production_source_count_after_if_approved"], 28)
        self.assertEqual(self.summary["production_exact_after_if_approved"], 4589)
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"], 4510)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"], 40)
        self.assertAlmostEqual(
            self.summary["whole_st_active_coverage_after_if_approved_percent"],
            99.1209,
        )

    def test_metadata_partition(self):
        self.assertEqual(
            self.summary["metadata_direct_ordering_information_exact_count"], 24
        )
        self.assertEqual(self.summary["metadata_bounded_exception_exact_count"], 0)
        self.assertEqual(self.summary["metadata_exception_exact_icpns"], [])
        self.assertEqual(self.summary["network_coprocessor_exact_count"], 4)
        self.assertTrue(self.summary["network_coprocessor_semantic_preserved"])
        self.assertTrue(self.summary["package_dependent_physical_pin_count_preserved"])

    def test_representative_rows(self):
        self.assertEqual(self.by["STM32WB05KNV6TR"]["flash_size"], "N/A (network coprocessor)")
        self.assertEqual(self.by["STM32WB05KNV6TR"]["pin_count"], "32")
        self.assertEqual(self.by["STM32WB05TZF7TR"]["pin_count"], "36")
        self.assertEqual(self.by["STM32WB06CCF6TR"]["pin_count"], "49")
        self.assertEqual(self.by["STM32WB06CCF6TR"]["package"], "WLCSP")
        self.assertEqual(self.by["STM32WB07CCV7TR"]["pin_count"], "48")
        self.assertEqual(self.by["STM32WB09TEF6TR"]["flash_size"], "512 KiB")

    def test_capability_boundary(self):
        self.assertFalse(self.summary["production_write_authorized"])
        self.assertFalse(self.summary["backend_mapping_required_for_layer1_admission"])
        self.assertFalse(self.summary["programming_profile_binding_claimed"])
        self.assertFalse(self.summary["programming_profile_scope_expanded"])
        self.assertFalse(self.summary["engineering_verified_claimed"])
        self.assertFalse(self.summary["field_evidence_claimed"])
        self.assertFalse(self.summary["ps_hil_claimed"])
        self.assertTrue(all(row["backend_type"] == "" for row in self.rows))
        self.assertTrue(all(row["backend_mapping_state"] == "no_mapping" for row in self.rows))
        self.assertTrue(all(row["openocd_target_config"] == "" for row in self.rows))
        self.assertTrue(all(row["programming_profile_state"] == "unresolved" for row in self.rows))


if __name__ == "__main__":
    unittest.main()
