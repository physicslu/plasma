import unittest

import prepare_stm32h7_layer1_admission_proposal_v58 as p


class TestSTM32H7Layer1AdmissionProposalV58(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()
        cls.by = {row["icpn"]: row for row in cls.rows}

    def test_partition(self):
        self.assertEqual(self.summary["proposal_addition_count"], 14)
        self.assertEqual(self.summary["backend_state_for_new_rows"], {"no_mapping": 14})
        self.assertFalse(self.summary["backend_scope_evaluated"])
        self.assertFalse(self.summary["existing_family_backend_mapping_inherited"])
        self.assertFalse(self.summary["backend_type_claimed"])

    def test_poststate_math_is_projection_only(self):
        self.assertEqual(self.summary["production_exact_prestate"], 4606)
        self.assertEqual(self.summary["production_source_count_prestate"], 28)
        self.assertEqual(self.summary["production_h7_exact_prestate"], 191)
        self.assertEqual(self.summary["production_h7_exact_after_if_approved"], 205)
        self.assertEqual(self.summary["production_source_count_after_if_approved"], 28)
        self.assertEqual(self.summary["production_exact_after_if_approved"], 4620)
        self.assertEqual(
            self.summary["catalog_backend_partition_after_if_approved"],
            {"mapped": 3673, "no_mapping": 947},
        )
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"], 4541)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"], 9)
        self.assertAlmostEqual(
            self.summary["whole_st_active_coverage_after_if_approved_percent"],
            99.8022,
        )

    def test_metadata_partition(self):
        self.assertEqual(
            self.summary["metadata_direct_ordering_information_exact_count"], 14
        )
        self.assertEqual(self.summary["metadata_bounded_exception_exact_count"], 0)
        self.assertEqual(self.summary["metadata_exception_exact_icpns"], [])

    def test_representative_rows(self):
        self.assertEqual(self.by["STM32H730ABI6Q"]["pin_count"], "169")
        self.assertEqual(self.by["STM32H730ABI6Q"]["option_suffix"], "Q")
        self.assertEqual(self.by["STM32H743IIT6TR"]["option_suffix"], "TR")
        self.assertEqual(self.by["STM32H7A3QIY6QTR"]["pin_count"], "132")
        self.assertEqual(self.by["STM32H7A3QIY6QTR"]["package"], "WLCSP")
        self.assertEqual(self.by["STM32H7B3LIH6Q"]["pin_count"], "225")

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
        self.assertTrue(all(row["existing_identifier"] == "" for row in self.rows))
        self.assertTrue(all(row["existing_identifier_kind"] == "" for row in self.rows))
        self.assertTrue(all(row["openocd_target_config"] == "" for row in self.rows))
        self.assertTrue(all(row["programming_profile_state"] == "unresolved" for row in self.rows))


if __name__ == "__main__":
    unittest.main()
