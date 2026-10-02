import unittest

import prepare_stm32f3_layer1_admission_proposal_v32 as p


class TestSTM32F3Layer1AdmissionProposalV32(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()

    def test_candidate_partition(self):
        self.assertEqual(self.summary["proposal_addition_count"], 182)
        self.assertEqual(self.summary["backend_state_for_new_rows"], {"no_mapping": 182})
        self.assertFalse(self.summary["backend_scope_evaluated"])
        self.assertEqual(len(self.rows), 182)

    def test_catalog_only_backend_boundary(self):
        self.assertFalse(self.summary["backend_mapping_required_for_layer1_admission"])
        self.assertEqual(self.summary["layer1_catalog_resolution"], {"normalized": 182})
        self.assertTrue(all(r["backend_mapping_state"] == "no_mapping" for r in self.rows))
        self.assertTrue(all(not r["openocd_target_config"] for r in self.rows))
        self.assertTrue(all(not r["existing_identifier"] for r in self.rows))
        self.assertTrue(all(not r["existing_identifier_kind"] for r in self.rows))

    def test_projected_poststate_math(self):
        self.assertEqual(self.summary["production_exact_prestate"], 3906)
        self.assertEqual(self.summary["production_f3_exact_prestate"], 10)
        self.assertEqual(self.summary["production_f3_exact_after_if_approved"], 192)
        self.assertEqual(self.summary["production_exact_after_if_approved"], 4088)
        self.assertEqual(self.summary["whole_st_active_intersection_prestate"], 3827)
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"], 4009)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"], 541)
        self.assertAlmostEqual(
            self.summary["whole_st_active_coverage_after_if_approved_percent"],
            88.1099,
        )

    def test_metadata_is_exception_free(self):
        self.assertEqual(self.summary["metadata_exception_exact_icpns"], [])
        self.assertTrue(all(not r["metadata_exception"] for r in self.rows))

    def test_representative_physical_metadata(self):
        by = {r["icpn"]: r for r in self.rows}
        self.assertEqual(by["STM32F301C8Y6TR"]["package"], "WLCSP")
        self.assertEqual(by["STM32F301C8Y6TR"]["pin_count"], "49")
        self.assertEqual(by["STM32F302VDH6"]["package"], "UFBGA")
        self.assertEqual(by["STM32F302VDH6"]["flash_size"], "384 KiB")
        self.assertEqual(by["STM32F378RCY6TR"]["pin_count"], "66")
        self.assertEqual(by["STM32F398VET6"]["flash_size"], "512 KiB")

    def test_no_implicit_capability_or_approval(self):
        self.assertFalse(self.summary["production_write_authorized"])
        self.assertFalse(self.summary["programming_profile_binding_claimed"])
        self.assertFalse(self.summary["programming_profile_scope_expanded"])
        self.assertFalse(self.summary["engineering_verified_claimed"])
        self.assertFalse(self.summary["field_evidence_claimed"])
        self.assertFalse(self.summary["ps_hil_claimed"])


if __name__ == "__main__":
    unittest.main()
