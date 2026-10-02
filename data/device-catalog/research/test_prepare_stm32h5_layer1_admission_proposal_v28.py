import unittest

import prepare_stm32h5_layer1_admission_proposal_v28 as p


class TestSTM32H5Layer1AdmissionProposalV28(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()

    def test_candidate_partition(self):
        self.assertEqual(self.summary["proposal_addition_count"], 190)
        self.assertEqual(
            self.summary["backend_state_counts"],
            {"mapping_candidate": 0, "no_mapping": 190},
        )
        self.assertEqual(len(self.rows), 190)

    def test_layer1_does_not_require_backend(self):
        self.assertFalse(self.summary["backend_mapping_required_for_layer1_admission"])
        self.assertEqual(self.summary["layer1_catalog_resolution"], {"normalized": 190})
        self.assertTrue(all(r["backend_mapping_state"] == "no_mapping" for r in self.rows))
        self.assertTrue(all(not r["openocd_target_config"] for r in self.rows))

    def test_projected_poststate_math(self):
        self.assertEqual(self.summary["production_exact_prestate"], 3716)
        self.assertEqual(self.summary["production_exact_after_if_approved"], 3906)
        self.assertEqual(self.summary["whole_st_active_intersection_prestate"], 3637)
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"], 3827)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"], 723)
        self.assertAlmostEqual(
            self.summary["whole_st_active_coverage_after_if_approved_percent"],
            84.1099,
        )

    def test_exact_exceptions_remain_bounded(self):
        self.assertEqual(
            self.summary["metadata_exception_exact_icpns"],
            [
                "STM32H5E4ZJJ6",
                "STM32H5E4ZJJ7Q",
                "STM32H5E4ZKJ6",
            ],
        )
        exception_rows = [r for r in self.rows if r["metadata_exception"]]
        self.assertEqual(len(exception_rows), 3)

    def test_no_implicit_capability_or_approval(self):
        self.assertFalse(self.summary["production_write_authorized"])
        self.assertFalse(self.summary["programming_profile_binding_claimed"])
        self.assertFalse(self.summary["programming_profile_scope_expanded"])
        self.assertFalse(self.summary["engineering_verified_claimed"])
        self.assertFalse(self.summary["field_evidence_claimed"])
        self.assertFalse(self.summary["ps_hil_claimed"])


if __name__ == "__main__":
    unittest.main()
