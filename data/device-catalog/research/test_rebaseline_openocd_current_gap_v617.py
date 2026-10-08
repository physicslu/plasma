import unittest
import rebaseline_openocd_current_gap_v617 as g

class TestOpenOCDCurrentGapRebaselineV617(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = g.build()

    def test_current_partition(self):
        self.assertEqual(self.summary["production_mapped_total"], 4037)
        self.assertEqual(self.summary["production_no_mapping_total"], 592)
        self.assertEqual(len(self.rows), 592)
        self.assertEqual(sum(self.summary["tier_counts"].values()), 592)

    def test_route_coverage(self):
        self.assertEqual(self.summary["active_openocd_route_exact_count"], 3958)
        self.assertEqual(self.summary["scoped_active_denominator"], 4550)
        self.assertAlmostEqual(self.summary["active_openocd_route_coverage_percent"], 86.9890)

    def test_fail_closed_classification(self):
        self.assertEqual(len({r["icpn"] for r in self.rows}), 592)
        self.assertTrue(all(r["production_write_authorized"] == "false" for r in self.rows))
        self.assertTrue(all(r["programming_profile_state"] == "unresolved" for r in self.rows))

    def test_known_frozen_upstream_families(self):
        counts = self.summary["tier_family_counts"]
        self.assertEqual(counts["C_upstream_debug_target_without_flash_bank"], {"STM32N6": 32})
        self.assertEqual(counts["D_no_direct_upstream_target_config"], {
            "STM32C5": 172,
            "STM32H5": 190,
            "STM32WB0": 24,
            "STM32WL3": 47,
        })

    def test_no_claim_escalation(self):
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))

if __name__ == "__main__":
    unittest.main()
