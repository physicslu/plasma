import unittest

import prepare_st_final_layer1_admission_proposal_v61 as p


class TestSTFinalLayer1AdmissionProposalV61(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,cls.csv_text,cls.summary=p.build()
        cls.by={r["icpn"]:r for r in cls.rows}

    def test_final_nine(self):
        self.assertEqual(self.summary["proposal_addition_count"],9)
        self.assertEqual(self.summary["family_addition_counts"],{
            "STM32F4":3,"STM32L1":2,"STM32L4":3,"STM32U3":1
        })
        self.assertEqual(self.summary["metadata_ready_exact_count"],9)
        self.assertEqual(self.summary["metadata_blocked_exact_count"],0)

    def test_projection_closes_locked_denominator(self):
        self.assertEqual(self.summary["production_exact_after_if_approved"],4629)
        self.assertEqual(self.summary["production_source_count_after_if_approved"],28)
        self.assertEqual(self.summary["catalog_backend_partition_after_if_approved"],{
            "mapped":3673,"no_mapping":956
        })
        self.assertEqual(self.summary["whole_st_active_intersection_after_if_approved"],4550)
        self.assertEqual(self.summary["whole_st_active_gap_after_if_approved"],0)
        self.assertEqual(self.summary["whole_st_active_coverage_after_if_approved_percent"],100.0)

    def test_family_poststates(self):
        self.assertEqual(self.summary["family_production_after_if_approved"],{
            "STM32F4":387,
            "STM32L1":146,
            "STM32L4":449,
            "STM32U3":107,
        })

    def test_opaque_suffixes_not_interpreted_as_backend(self):
        for icpn in (
            "STM32F405OGY6VTR","STM32F405OGY6WTR","STM32F437VIT6WTR",
            "STM32L151VDT7X","STM32L151VDY6XTR",
        ):
            self.assertEqual(self.by[icpn]["backend_mapping_state"],"no_mapping")
            self.assertEqual(self.by[icpn]["openocd_target_config"],"")
            self.assertEqual(self.by[icpn]["programming_profile_state"],"unresolved")

    def test_capability_boundary(self):
        self.assertFalse(self.summary["production_write_authorized"])
        self.assertFalse(self.summary["backend_scope_evaluated"])
        self.assertFalse(self.summary["existing_family_backend_mapping_inherited"])
        self.assertFalse(self.summary["backend_type_claimed"])
        self.assertFalse(self.summary["programming_profile_binding_claimed"])
        self.assertFalse(self.summary["programming_profile_scope_expanded"])
        self.assertFalse(self.summary["engineering_verified_claimed"])
        self.assertFalse(self.summary["field_evidence_claimed"])
        self.assertFalse(self.summary["ps_hil_claimed"])
        self.assertTrue(all(r["backend_mapping_state"]=="no_mapping" for r in self.rows))


if __name__=="__main__":
    unittest.main()
