import unittest

import review_openocd_bounded_evidence_v619 as r


class TestOpenOCDBoundedEvidenceV619(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.csv_text, cls.summary = r.build()

    def test_exact_scope(self):
        self.assertEqual(len(self.rows), 17)
        self.assertEqual(self.summary["family_counts"], {
            "STM32F3": 4,
            "STM32G0": 12,
            "STM32L1": 1,
        })
        self.assertEqual(len(self.summary["bridges"]), 17)

    def test_authority_chain(self):
        self.assertTrue(all(x["commercial_source_authority"] == "STMicroelectronics official" for x in self.rows))
        self.assertTrue(all(x["commercial_verification_status"].startswith("verified_") for x in self.rows))
        self.assertTrue(all(x["openocd_distribution"] == "upstream-openocd" for x in self.rows))
        self.assertTrue(all(x["route_validation_status"] == "not_verified" for x in self.rows))

    def test_bounded_governance(self):
        gov = self.summary["governance"]
        self.assertTrue(gov["exact_set_bridge_candidate"])
        self.assertFalse(gov["generic_one_char_generalization_authorized"])
        self.assertFalse(gov["production_mapping_write_authorized"])
        self.assertFalse(gov["programming_verified_claimed"])
        self.assertFalse(gov["engineering_verified_claimed"])
        self.assertFalse(gov["hil_verified_claimed"])

    def test_projection(self):
        cov = self.summary["coverage_projection_if_later_promoted"]
        self.assertEqual(cov["potential_active_openocd_route_exact_count"], 3975)
        self.assertEqual(cov["remaining_gap"], 575)
        self.assertAlmostEqual(cov["potential_coverage_percent"], 87.3626)


if __name__ == "__main__":
    unittest.main()
