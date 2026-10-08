import unittest
import propose_openocd_tier_a_bounded_suffix_v613 as p

class TestOpenOCDTierABoundedSuffixV613(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = p.build()

    def test_scope(self):
        scope = self.policy["scope"]
        self.assertEqual(scope["exact_icpn_count"], 33)
        self.assertEqual(len(scope["exact_icpns"]), 33)
        self.assertEqual(len(self.policy["bridges"]), 33)

    def test_exact_set_only(self):
        gov = self.policy["governance"]
        self.assertTrue(gov["exact_set_bridge_only"])
        self.assertFalse(gov["family_wide_suffix_removal_authorized"])
        self.assertFalse(gov["future_unseen_icpn_covered"])

    def test_unique_bound_rows(self):
        for icpn, row in self.policy["bridges"].items():
            self.assertTrue(row["option_suffix"], icpn)
            self.assertTrue(row["existing_identifier"], icpn)
            self.assertIn(row["existing_identifier_kind"], {"ordering_pattern", "cmsis_device_name"})
            self.assertTrue(row["openocd_target_config"], icpn)

    def test_fail_closed_governance(self):
        gov = self.policy["governance"]
        for key in (
            "family_wide_suffix_removal_authorized",
            "future_unseen_icpn_covered",
            "production_mapping_write_authorized",
            "programming_profile_binding_claimed",
            "programming_verified_claimed",
            "engineering_verified_claimed",
            "hil_verified_claimed",
        ):
            self.assertFalse(gov[key])

    def test_projection(self):
        cov = self.policy["coverage_projection_if_later_promoted"]
        self.assertEqual(cov["potential_active_openocd_route_exact_count"], 3947)
        self.assertEqual(cov["remaining_gap"], 603)
        self.assertAlmostEqual(cov["potential_coverage_percent"], 86.7473)

if __name__ == "__main__":
    unittest.main()
