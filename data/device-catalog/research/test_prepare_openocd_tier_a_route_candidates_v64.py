import unittest

import prepare_openocd_tier_a_route_candidates_v64 as p


class TestOpenOCDTierARouteCandidatesV64(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,cls.csv_text,cls.summary=p.build()

    def test_count_and_family_partition(self):
        self.assertEqual(self.summary["candidate_exact_count"],389)
        self.assertEqual(self.summary["family_counts"],{
            "STM32C0":17,
            "STM32F2":72,
            "STM32F3":172,
            "STM32F4":3,
            "STM32F7":62,
            "STM32G0":42,
            "STM32G4":1,
            "STM32H7":14,
            "STM32L1":2,
            "STM32L4":3,
            "STM32U3":1,
        })

    def test_no_identifier_synthesis(self):
        self.assertFalse(self.summary["identifier_synthesis_performed"])
        self.assertFalse(self.summary["existing_identifier_binding_claimed"])
        self.assertTrue(all(r["existing_identifier_proposed"]=="" for r in self.rows))
        self.assertTrue(all(r["existing_identifier_kind_proposed"]=="" for r in self.rows))

    def test_all_are_route_candidates_only(self):
        self.assertTrue(all(r["current_mapping_status"]=="no_mapping" for r in self.rows))
        self.assertTrue(all(r["candidate_openocd_target_config"] for r in self.rows))
        self.assertTrue(all(
            r["candidate_evidence_state"]=="same_series_single_consistent_openocd_target_config"
            for r in self.rows
        ))
        self.assertTrue(all(r["programming_profile_state"]=="unresolved" for r in self.rows))
        self.assertTrue(all(r["production_write_authorized"]=="false" for r in self.rows))

    def test_projection(self):
        self.assertEqual(self.summary["current_active_openocd_route_exact_count"],3594)
        self.assertEqual(self.summary["projected_route_exact_count_if_all_qualified"],3983)
        self.assertEqual(self.summary["projected_remaining_gap_if_all_qualified"],567)
        self.assertAlmostEqual(
            self.summary["projected_route_coverage_percent_if_all_qualified"],87.5385
        )

    def test_capability_boundary(self):
        for key in (
            "production_write_authorized",
            "identifier_synthesis_performed",
            "existing_identifier_binding_claimed",
            "programming_profile_binding_claimed",
            "programming_verified_claimed",
            "engineering_verified_claimed",
            "hil_verified_claimed",
        ):
            self.assertFalse(self.summary[key])


if __name__=="__main__":
    unittest.main()
