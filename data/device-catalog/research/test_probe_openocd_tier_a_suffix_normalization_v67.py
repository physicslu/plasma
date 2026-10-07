import unittest
import probe_openocd_tier_a_suffix_normalization_v67 as p

class TestOpenOCDTierASuffixNormalizationV67(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,cls.csv_text,cls.summary=p.build()

    def test_cardinality(self):
        self.assertEqual(len(self.rows),69)
        self.assertEqual(self.summary["input_blocked_exact_count"],69)
        self.assertEqual(sum(self.summary["probe_state_counts"].values()),69)

    def test_unique_rows_have_one_identifier(self):
        for row in self.rows:
            if row["normalization_probe_state"]=="unique_after_catalog_suffix_removal":
                self.assertEqual(row["match_count"],"1")
                self.assertTrue(row["resolved_existing_identifier"])
                self.assertTrue(row["resolved_identifier_kind"])

    def test_fail_closed(self):
        for value in self.summary["claims"].values():
            self.assertFalse(value)

if __name__=="__main__":
    unittest.main()
