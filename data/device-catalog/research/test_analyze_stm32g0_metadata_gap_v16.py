import unittest
import analyze_stm32g0_metadata_gap_v16 as a

class TestG0MetadataGapV16(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r=a.analyze()
    def test_counts(self):
        self.assertEqual(self.r["layer1_gap_exact"],359)
        self.assertEqual(self.r["new_base_device_count"],87)
        self.assertEqual(self.r["current_policy_fully_decodable_gap_exact"],2)
    def test_root_blockers(self):
        b=self.r["overlapping_blocker_exact_counts"]
        self.assertEqual(b["base_scope"],357)
        self.assertEqual(b["pin_code"],284)
        self.assertEqual(b["package_code"],67)
        self.assertEqual(b["n_version_scope"],40)
        self.assertNotIn("flash_code",b)
        self.assertNotIn("temperature_code",b)
        self.assertNotIn("option_suffix",b)
    def test_authority_surface(self):
        self.assertEqual(self.r["ordering_authority_subfamilies_bound"],12)
        self.assertFalse(self.r["claims"]["production_write_authorized"])

if __name__=="__main__": unittest.main()
