import unittest
import probe_openocd_c0_one_char_generalization_v611 as p

class TestOpenOCDC0OneCharGeneralizationV611(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,_,cls.summary=p.build()

    def test_scope(self):
        self.assertEqual(self.summary["input_c0_policy_shape_gap_exact_count"],11)
        self.assertEqual(len(self.rows),11)
        self.assertEqual(self.summary["c0_base_variant_inventory_gap_exact_count"],5)

    def test_fail_closed(self):
        for key in (
            "c0_one_char_policy_authorized","identifier_promoted",
            "route_inventory_modified","production_write_authorized",
            "programming_verified","hil_verified"
        ):
            self.assertFalse(self.summary["claims"][key])

    def test_unique_rows_have_one_identifier(self):
        for r in self.rows:
            if r["probe_state"]=="unique_under_one_char_generalization":
                self.assertEqual(r["match_count"],"1")
                self.assertTrue(r["resolved_identifier"])
                self.assertEqual(r["resolved_identifier_kind"],"ordering_pattern")

if __name__=="__main__":
    unittest.main()
