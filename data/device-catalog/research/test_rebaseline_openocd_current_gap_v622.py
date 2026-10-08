import unittest

import rebaseline_openocd_current_gap_v622 as g


class TestOpenOCDCurrentGapRebaselineV622(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = g.build()

    def test_current_partition(self):
        self.assertEqual(self.summary["production_mapped_total"], 4054)
        self.assertEqual(self.summary["production_no_mapping_total"], 575)
        self.assertEqual(len(self.rows), 575)
        self.assertEqual(self.summary["tier_counts"], {
            "A_residual_same_series_existing_route": 8,
            "B_family_route_flash_capable_no_series_sibling": 102,
            "C_upstream_debug_target_without_flash_bank": 32,
            "D_no_direct_upstream_target_config": 433,
        })

    def test_a_residual_scope(self):
        self.assertEqual(
            self.summary["tier_family_counts"]["A_residual_same_series_existing_route"],
            {"STM32C0": 5, "STM32G4": 1, "STM32L4": 2},
        )

    def test_route_coverage(self):
        self.assertEqual(self.summary["active_openocd_route_exact_count"], 3975)
        self.assertEqual(self.summary["scoped_active_denominator"], 4550)
        self.assertAlmostEqual(self.summary["active_openocd_route_coverage_percent"], 87.3626)

    def test_frozen_unmoved_tiers(self):
        self.assertEqual(
            self.summary["tier_family_counts"]["C_upstream_debug_target_without_flash_bank"],
            {"STM32N6": 32},
        )
        self.assertEqual(
            self.summary["tier_family_counts"]["D_no_direct_upstream_target_config"],
            {"STM32C5": 172, "STM32H5": 190, "STM32WB0": 24, "STM32WL3": 47},
        )

    def test_governance(self):
        self.assertTrue(all(r["production_write_authorized"] == "false" for r in self.rows))
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))


if __name__ == "__main__":
    unittest.main()
