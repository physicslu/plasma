import unittest
import classify_openocd_tier_a_blocked_v66 as c

class TestOpenOCDTierABlockedV66(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,cls.csv_text,cls.summary=c.build()

    def test_cardinality(self):
        self.assertEqual(len(self.rows),69)
        self.assertEqual(self.summary["input_blocked_exact_count"],69)
        self.assertEqual(sum(self.summary["structural_gap_counts"].values()),69)

    def test_total_classification(self):
        allowed={
            "same_base_route_inventory_present_but_no_policy_match",
            "same_series_route_inventory_present_but_base_variant_absent",
            "no_same_series_route_inventory_row",
        }
        self.assertTrue(set(self.summary["structural_gap_counts"]).issubset(allowed))
        self.assertTrue(all(r["structural_gap_class"] in allowed for r in self.rows))

    def test_fail_closed(self):
        for key,value in self.summary["claims"].items():
            self.assertFalse(value)

if __name__=="__main__":
    unittest.main()
