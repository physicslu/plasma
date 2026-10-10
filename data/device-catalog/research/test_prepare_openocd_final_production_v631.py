import unittest
import prepare_openocd_final_production_v631 as p

class TestFinalProductionDryRunV631(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary,cls.before,cls.after,cls.delta=p.build()

    def test_scope(self):
        self.assertEqual(self.summary["safe_exact_count"],103)
        self.assertEqual(self.summary["blocked_exact_count"],465)
        self.assertEqual(
            self.summary["family_changed_counts"],
            {"STM32F3":10,"STM32F7":92,"STM32G4":1},
        )

    def test_route_delta_is_two_rows(self):
        self.assertEqual([r["part_number"] for r in self.delta],
            ["STM32F378VCHx","STM32G491RCYx"])
        self.assertEqual(self.summary["postimages"]["ROUTE_INVENTORY"]["sha256"],
            "6f11d74a7172f05fe81df5bdebfe55e32a5752663ad506d03d33925d94c4fd69")

    def test_projection(self):
        s=self.summary["projected_poststate"]
        self.assertEqual((s["mapped"],s["no_mapping"]),(4164,465))
        self.assertEqual(s["active_openocd_route"],4085)
        self.assertEqual(s["coverage_percent"],89.7802)

    def test_no_write_authority_or_overclaim(self):
        self.assertFalse(self.summary["approval"]["owner_approval_received"])
        self.assertFalse(self.summary["approval"]["production_write_authorized"])
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))

if __name__=="__main__":
    unittest.main()
