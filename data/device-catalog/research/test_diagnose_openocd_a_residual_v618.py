import unittest

import diagnose_openocd_a_residual_v618 as d


class TestOpenOCDAResidualDiagnosticV618(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = d.build()

    def test_scope(self):
        self.assertEqual(len(self.rows), 25)
        self.assertEqual(self.summary["family_counts"], {
            "STM32C0": 5,
            "STM32F3": 4,
            "STM32G0": 12,
            "STM32G4": 1,
            "STM32L1": 1,
            "STM32L4": 2,
        })

    def test_no_previously_qualified_semantics_reappear(self):
        self.assertTrue(all(r["current_policy_match_count"] == "0" for r in self.rows))
        self.assertTrue(all(r["suffix_normalized_policy_match_count"] == "0" for r in self.rows))

    def test_g0_prefix_probe_remains_negative(self):
        g0 = [r for r in self.rows if r["family"] == "STM32G0"]
        self.assertEqual(len(g0), 12)
        self.assertTrue(all(r["prefix_probe_match_count"] == "0" for r in g0))

    def test_c0_is_missing_base_variant_inventory(self):
        c0 = [r for r in self.rows if r["family"] == "STM32C0"]
        self.assertEqual(len(c0), 5)
        self.assertTrue(all(
            r["structural_gap_class"] == "base_variant_absent_from_route_inventory"
            for r in c0
        ))

    def test_governance(self):
        self.assertTrue(all(r["identifier_inferred"] == "false" for r in self.rows))
        self.assertTrue(all(r["policy_change_authorized"] == "false" for r in self.rows))
        self.assertTrue(all(r["production_write_authorized"] == "false" for r in self.rows))
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))


if __name__ == "__main__":
    unittest.main()
