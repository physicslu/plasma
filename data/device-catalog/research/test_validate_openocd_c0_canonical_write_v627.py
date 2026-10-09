import unittest
import validate_openocd_c0_canonical_write_v627 as v

class TestOpenOCDC0CanonicalWriteV627(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=v.validate()

    def test_frozen_postimage(self):
        self.assertEqual(self.s["canonical_rows"],7661)
        self.assertEqual(
            self.s["canonical_postimage_git_blob_sha"],
            "81e44f6a6df902f3b206d06bfac38e37ec74630b",
        )

    def test_exact_delta(self):
        self.assertEqual(self.s["delta_rows"],4)
        self.assertEqual(
            self.s["delta_sha256"],
            "5d6f2b022a0efab409f57dece8cfcb06dace9cbf93c4a533beef9b4ecbf84b24",
        )

    def test_inverse_reconstructs_preimage(self):
        self.assertEqual(self.s["inverse_preimage_rows"],7657)
        self.assertEqual(
            self.s["inverse_preimage_git_blob_sha"],
            "0ef056e3363e20bb527590c4a4cc1cc0d7afb810",
        )

    def test_production_unchanged(self):
        self.assertEqual(self.s["production_mapped"],4054)
        self.assertEqual(self.s["production_no_mapping"],575)
        self.assertEqual(self.s["production_exact_scope_still_no_mapping"],5)

    def test_no_production_authority(self):
        self.assertFalse(self.s["next_gate"]["production_mapping_write_authorized"])

if __name__=="__main__":
    unittest.main()
