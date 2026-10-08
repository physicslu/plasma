import unittest

import prepare_openocd_c0_route_inventory_v625 as p


class TestOpenOCDC0RouteInventoryProposalV625(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = p.build()

    def test_bounded_scope(self):
        self.assertEqual(len(self.rows),4)
        self.assertEqual(self.summary["proposal_exact_icpn_count"],5)
        self.assertEqual(self.summary["proposal_pattern_count"],4)
        self.assertEqual(
            [r["part_number"] for r in self.rows],
            ["STM32C011D6Yx","STM32C051D8Yx","STM32C091ECYx","STM32C092ECYx"],
        )

    def test_unique_resolution_after_proposal(self):
        self.assertEqual(self.summary["pre_proposal_unique_resolutions"],0)
        self.assertEqual(self.summary["post_proposal_unique_resolutions"],5)

    def test_inventory_only_does_not_change_production_coverage(self):
        self.assertEqual(
            self.summary["inventory_only_projection"]["active_openocd_route_exact_count"],3975
        )
        self.assertEqual(
            self.summary["inventory_only_projection"]["remaining_production_gap"],575
        )

    def test_later_production_projection_is_separate(self):
        self.assertEqual(
            self.summary["if_later_separately_promoted_to_production"]["potential_active_openocd_route_exact_count"],
            3980,
        )
        self.assertEqual(
            self.summary["if_later_separately_promoted_to_production"]["potential_remaining_gap"],
            570,
        )

    def test_governance(self):
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))


if __name__=="__main__":
    unittest.main()
