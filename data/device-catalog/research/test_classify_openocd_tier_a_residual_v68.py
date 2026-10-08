import unittest
import classify_openocd_tier_a_residual_v68 as v


class TestOpenOCDTierAResidualV68(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,cls.csv_text,cls.summary=v.build()

    def test_partition(self):
        self.assertEqual(self.summary["input_v65_blocked_exact_count"],69)
        self.assertEqual(self.summary["v67_unique_after_suffix_normalization_exact_count"],33)
        self.assertEqual(self.summary["residual_exact_count"],36)
        self.assertEqual(
            self.summary["qualified_or_normalizable_tier_a_exact_count"]+
            self.summary["tier_a_residual_exact_count"],389
        )

    def test_fail_closed(self):
        self.assertTrue(all(r["production_write_authorized"]=="false" for r in self.rows))
        self.assertTrue(all(r["programming_profile_state"]=="unresolved" for r in self.rows))
        self.assertFalse(self.summary["claims"]["identifier_inferred_for_residual_rows"])
        self.assertFalse(self.summary["claims"]["suffix_removal_policy_authorized"])

    def test_projection(self):
        self.assertEqual(self.summary["potential_route_exact_count_if_353_later_promoted"],3947)
        self.assertAlmostEqual(self.summary["potential_coverage_percent_if_353_later_promoted"],86.7473)


if __name__=="__main__":
    unittest.main()
