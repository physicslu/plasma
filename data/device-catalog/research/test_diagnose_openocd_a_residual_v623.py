import unittest

import diagnose_openocd_a_residual_v623 as d


class TestOpenOCDAResidualDeepDiagnosticV623(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = d.build()

    def test_scope(self):
        self.assertEqual(len(self.rows), 8)
        self.assertEqual(self.summary["family_counts"], {
            "STM32C0": 5,
            "STM32G4": 1,
            "STM32L4": 2,
        })

    def test_structural_partition(self):
        self.assertEqual(self.summary["structural_counts"], {
            "exact_base_variant_missing_from_route_inventory": 7,
            "same_base_route_family_present_package_variant_ambiguous": 1,
        })

    def test_g4_remains_ambiguous(self):
        row = next(r for r in self.rows if r["family"] == "STM32G4")
        self.assertEqual(row["icpn"], "STM32G491RCY6TR")
        self.assertGreater(int(row["one_char_probe_match_count"]), 1)
        self.assertEqual(row["generic_package_substitution_authorized"], "false")

    def test_seven_need_route_inventory_expansion(self):
        rows = [r for r in self.rows if r["family"] in {"STM32C0","STM32L4"}]
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(r["same_base_mapped_sibling_count"] == "0" for r in rows))
        self.assertTrue(all(r["same_base_route_rows"] == "0" for r in rows))

    def test_governance(self):
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))


if __name__ == "__main__":
    unittest.main()
