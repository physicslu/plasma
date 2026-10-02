import unittest

import prepare_stm32f7_layer1_admission_proposal_v36 as p


class TestSTM32F7Layer1AdmissionProposalV36(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()
        cls.by = {row["icpn"]: row for row in cls.rows}

    def test_candidate_partition(self):
        self.assertEqual(self.summary["proposal_addition_count"], 154)
        self.assertEqual(self.summary["backend_state_for_new_rows"], {"no_mapping": 154})
        self.assertFalse(self.summary["backend_scope_evaluated"])
        self.assertEqual(len(self.rows), 154)

    def test_catalog_only_backend_boundary(self):
        self.assertFalse(self.summary["backend_mapping_required_for_layer1_admission"])
        self.assertEqual(self.summary["layer1_catalog_resolution"], {"normalized": 154})
        self.assertTrue(all(r["backend_mapping_state"] == "no_mapping" for r in self.rows))
        self.assertTrue(all(not r["openocd_target_config"] for r in self.rows))
        self.assertTrue(all(not r["existing_identifier"] for r in self.rows))
        self.assertTrue(all(not r["existing_identifier_kind"] for r in self.rows))

    def test_projected_poststate_math(self):
        self.assertEqual(self.summary["production_exact_prestate"], 4088)
        self.assertEqual(self.summary["production_f7_exact_prestate"], 19)
        self.assertEqual(self.summary["production_f7_exact_after_if_approved"], 173)
        self.assertEqual(self.summary["production_exact_after_if_approved"], 4242)
        self.assertEqual(self.summary["whole_st_active_intersection_prestate"], 4009)
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"], 4163)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"], 387)
        self.assertAlmostEqual(
            self.summary["whole_st_active_coverage_after_if_approved_percent"],
            91.4945,
        )

    def test_bounded_f750_metadata_overrides(self):
        self.assertEqual(
            set(self.summary["metadata_override_exact_icpns"]),
            {"STM32F750V8T6", "STM32F750V8T7", "STM32F750Z8T6"},
        )
        self.assertEqual(self.summary["direct_ordering_information_exact_count"], 151)
        self.assertEqual(self.summary["exact_product_override_count"], 3)
        for icpn in self.summary["metadata_override_exact_icpns"]:
            self.assertEqual(
                self.by[icpn]["metadata_exception"],
                "F750_X8_EXACT_PRODUCT_METADATA_OVERRIDE",
            )

    def test_representative_physical_metadata(self):
        self.assertEqual(self.by["STM32F723ZCI6"]["package"], "UFBGA")
        self.assertEqual(self.by["STM32F723ZCI6"]["pin_count"], "144")
        self.assertEqual(self.by["STM32F746ZEY6TR"]["package"], "WLCSP")
        self.assertEqual(self.by["STM32F746ZEY6TR"]["pin_count"], "143")
        self.assertEqual(self.by["STM32F765IIK6"]["flash_size"], "2048 KiB")
        self.assertEqual(self.by["STM32F769AIY6TR"]["pin_count"], "180")

    def test_no_implicit_capability_or_approval(self):
        self.assertFalse(self.summary["production_write_authorized"])
        self.assertFalse(self.summary["programming_profile_binding_claimed"])
        self.assertFalse(self.summary["programming_profile_scope_expanded"])
        self.assertFalse(self.summary["engineering_verified_claimed"])
        self.assertFalse(self.summary["field_evidence_claimed"])
        self.assertFalse(self.summary["ps_hil_claimed"])


if __name__ == "__main__":
    unittest.main()
