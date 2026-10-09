import unittest
import analyze_openocd_final_coverage_v631 as m

class TestOpenOCDFinalCoverageV631(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,cls.csv_text,cls.delta,cls.successor,cls.summary=m.build()
        cls.by={r["icpn"]:r for r in cls.rows}

    def test_complete_568_outcome(self):
        self.assertEqual(len(self.rows),568)
        self.assertEqual(self.summary["safe_mapping_candidate_exact_count"],103)
        self.assertEqual(self.summary["blocked_exact_count"],465)
        self.assertEqual(
            self.summary["safe_by_family"],
            {"STM32F3":10,"STM32F7":92,"STM32G4":1},
        )
        self.assertEqual(
            self.summary["blocked_by_family"],
            {"STM32C5":172,"STM32H5":190,"STM32N6":32,"STM32WB0":24,"STM32WL3":47},
        )

    def test_only_two_route_expansions(self):
        self.assertEqual(
            self.summary["route_delta"]["patterns"],
            ["STM32F378VCHx","STM32G491RCYx"],
        )
        self.assertEqual(self.summary["route_successor"]["postimage_row_count"],7663)

    def test_known_boundary_examples(self):
        self.assertEqual(self.by["STM32F328C8T6"]["existing_identifier"],"STM32F328C8Tx")
        self.assertEqual(self.by["STM32F378VCH6"]["existing_identifier"],"STM32F378VCHx")
        self.assertEqual(self.by["STM32G491RCY6TR"]["existing_identifier"],"STM32G491RCYx")
        self.assertEqual(self.by["STM32C531CBT3"]["outcome"],"blocked_runtime_target_absent")
        self.assertEqual(self.by["STM32H503CBT6"]["outcome"],"blocked_runtime_target_absent")
        self.assertEqual(self.by["STM32N645A0H3Q"]["outcome"],"blocked_runtime_target_absent")
        self.assertEqual(self.by["STM32WL30K8V6"]["outcome"],"blocked_runtime_target_absent")

    def test_projection(self):
        p=self.summary["projected_if_103_promoted"]
        self.assertEqual((p["mapped"],p["no_mapping"]),(4164,465))
        self.assertEqual(p["active_openocd_route"],4085)
        self.assertAlmostEqual(p["coverage_percent"],89.7802)

    def test_no_overclaim(self):
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))

if __name__=="__main__":
    unittest.main()
