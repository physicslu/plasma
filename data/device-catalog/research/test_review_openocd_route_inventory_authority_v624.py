import unittest

import review_openocd_route_inventory_authority_v624 as r


class TestOpenOCDRouteInventoryAuthorityV624(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = r.build()
        cls.by = {x["icpn"]: x for x in cls.rows}

    def test_scope_partition(self):
        self.assertEqual(len(self.rows), 7)
        self.assertEqual(self.summary["excluded_g4_ambiguity_exact_count"], 1)
        self.assertEqual(self.summary["review_state_counts"], {
            "authoritative_pattern_present_resolver_shape_blocked": 1,
            "authoritative_pattern_present_suffix_transform_blocked": 1,
            "authoritative_pattern_ready_for_inventory_proposal": 5,
        })

    def test_c0_is_authority_ready(self):
        c0 = [x for x in self.rows if x["family"] == "STM32C0"]
        self.assertEqual(len(c0), 5)
        self.assertTrue(all(x["pattern_fullmatch"] == "true" for x in c0))
        self.assertTrue(all(x["current_resolver_compatible"] == "true" for x in c0))
        self.assertEqual(len({x["authoritative_pattern"] for x in c0}), 4)

    def test_l4_ptr_is_pattern_present_but_resolver_blocked(self):
        row = self.by["STM32L496WGY6PTR"]
        self.assertEqual(row["authoritative_pattern"], "STM32L496WGYxP")
        self.assertEqual(row["pattern_fullmatch"], "true")
        self.assertEqual(row["current_resolver_compatible"], "false")
        self.assertEqual(row["review_state"],
                         "authoritative_pattern_present_resolver_shape_blocked")

    def test_l4_pst_needs_bounded_suffix_transform(self):
        row = self.by["STM32L496WGY6PST"]
        self.assertEqual(row["authoritative_pattern"], "STM32L496WGYxP")
        self.assertEqual(row["pattern_fullmatch"], "false")
        self.assertEqual(row["review_state"],
                         "authoritative_pattern_present_suffix_transform_blocked")

    def test_governance(self):
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))
        self.assertTrue(all(x["canonical_inventory_write_authorized"] == "false" for x in self.rows))
        self.assertTrue(all(x["production_write_authorized"] == "false" for x in self.rows))


if __name__ == "__main__":
    unittest.main()
