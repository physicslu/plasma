import unittest

import prepare_stm32c0_layer1_admission_proposal_v55 as p


class TestSTM32C0Layer1AdmissionProposalV55(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()
        cls.by = {row["icpn"]: row for row in cls.rows}

    def test_partition(self):
        self.assertEqual(self.summary["proposal_addition_count"], 17)
        self.assertEqual(self.summary["backend_state_for_new_rows"], {"no_mapping": 17})
        self.assertFalse(self.summary["backend_scope_evaluated"])
        self.assertFalse(self.summary["backend_type_claimed"])

    def test_poststate_math_is_projection_only(self):
        self.assertEqual(self.summary["production_exact_prestate"], 4589)
        self.assertEqual(self.summary["production_source_count_prestate"], 28)
        self.assertEqual(self.summary["production_c0_exact_prestate"], 209)
        self.assertEqual(self.summary["production_c0_exact_after_if_approved"], 226)
        self.assertEqual(self.summary["production_source_count_after_if_approved"], 28)
        self.assertEqual(self.summary["production_exact_after_if_approved"], 4606)
        self.assertEqual(
            self.summary["catalog_backend_partition_after_if_approved"],
            {"mapped": 3673, "no_mapping": 933},
        )
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"], 4527)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"], 23)
        self.assertAlmostEqual(
            self.summary["whole_st_active_coverage_after_if_approved_percent"],
            99.4945,
        )

    def test_metadata_and_lifecycle_delta(self):
        self.assertEqual(
            self.summary["metadata_direct_ordering_information_exact_count"], 17
        )
        self.assertEqual(self.summary["metadata_bounded_exception_exact_count"], 0)
        self.assertEqual(self.summary["metadata_exception_exact_icpns"], [])
        self.assertEqual(self.summary["lifecycle_delta_exact_icpns"], ["STM32C091KBT3"])

    def test_representative_rows(self):
        self.assertEqual(self.by["STM32C011D6Y6TR"]["package"], "WLCSP")
        self.assertEqual(self.by["STM32C011D6Y6TR"]["pin_count"], "12")
        self.assertEqual(self.by["STM32C051D8Y6TR"]["pin_count"], "15")
        self.assertEqual(self.by["STM32C071FBY6TR"]["pin_count"], "19")
        self.assertEqual(self.by["STM32C071R8I6N"]["option_suffix"], "N")
        self.assertEqual(self.by["STM32C091KBT3"]["temperature_grade"], "-40 to 125 C")
        self.assertEqual(self.by["STM32C092ECY3TR"]["pin_count"], "24")

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
