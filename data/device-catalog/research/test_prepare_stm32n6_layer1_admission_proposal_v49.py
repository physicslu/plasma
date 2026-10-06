import unittest

import prepare_stm32n6_layer1_admission_proposal_v49 as p


class TestSTM32N6Layer1AdmissionProposalV49(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()
        cls.by = {row["icpn"]: row for row in cls.rows}

    def test_partition(self):
        self.assertEqual(self.summary["proposal_addition_count"], 32)
        self.assertEqual(self.summary["backend_state_for_new_rows"], {"no_mapping": 32})
        self.assertFalse(self.summary["backend_scope_evaluated"])
        self.assertFalse(self.summary["backend_type_claimed"])

    def test_poststate_math_is_projection_only(self):
        self.assertEqual(self.summary["production_exact_prestate"], 4533)
        self.assertEqual(self.summary["production_source_count_prestate"], 26)
        self.assertEqual(self.summary["production_n6_exact_prestate"], 0)
        self.assertEqual(self.summary["production_n6_exact_after_if_approved"], 32)
        self.assertEqual(self.summary["production_source_count_after_if_approved"], 27)
        self.assertEqual(self.summary["production_exact_after_if_approved"], 4565)
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"], 4486)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"], 64)
        self.assertAlmostEqual(
            self.summary["whole_st_active_coverage_after_if_approved_percent"],
            98.5934,
        )

    def test_metadata_partition(self):
        self.assertEqual(
            self.summary["metadata_direct_ordering_information_exact_count"], 32
        )
        self.assertEqual(self.summary["metadata_bounded_exception_exact_count"], 0)
        self.assertEqual(self.summary["metadata_exception_exact_icpns"], [])

    def test_representative_rows(self):
        self.assertEqual(self.by["STM32N645Z0H3Q"]["pin_count"], "142")
        self.assertEqual(self.by["STM32N657A0H3QG"]["pin_count"], "169")
        self.assertEqual(self.by["STM32N657I0H3QTR"]["pin_count"], "178")
        self.assertEqual(self.by["STM32N657I0H3QTR"]["option_suffix"], "QTR")
        self.assertEqual(self.by["STM32N657X0H3Q"]["pin_count"], "264")
        self.assertEqual(self.by["STM32N657X0H3Q"]["flash_size"], "0-1 KiB")

    def test_external_memory_capability_boundary(self):
        self.assertTrue(self.summary["external_memory_programming_profile_boundary"])
        self.assertFalse(self.summary["production_write_authorized"])
        self.assertFalse(self.summary["backend_mapping_required_for_layer1_admission"])
        self.assertFalse(self.summary["programming_profile_binding_claimed"])
        self.assertFalse(self.summary["programming_profile_scope_expanded"])
        self.assertFalse(self.summary["engineering_verified_claimed"])
        self.assertFalse(self.summary["field_evidence_claimed"])
        self.assertFalse(self.summary["ps_hil_claimed"])
        self.assertTrue(all(row["backend_type"] == "" for row in self.rows))
        self.assertTrue(
            all(row["backend_mapping_state"] == "no_mapping" for row in self.rows)
        )
        self.assertTrue(
            all(row["openocd_target_config"] == "" for row in self.rows)
        )
        self.assertTrue(
            all(
                row["programming_profile_state"]
                == "unresolved_external_memory_programming_profile_boundary"
                for row in self.rows
            )
        )

if __name__ == "__main__":
    unittest.main()
