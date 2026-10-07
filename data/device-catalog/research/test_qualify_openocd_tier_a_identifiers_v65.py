import unittest

import qualify_openocd_tier_a_identifiers_v65 as q


class TestOpenOCDTierAIdentifierQualificationV65(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qualified,cls.blocked,_,_,cls.summary=q.build()

    def test_partition(self):
        self.assertEqual(self.summary["input_tier_a_exact_count"],389)
        self.assertEqual(self.summary["identifier_qualified_exact_count"],320)
        self.assertEqual(self.summary["identifier_blocked_exact_count"],69)
        self.assertEqual(self.summary["identifier_ambiguous_exact_count"],0)

    def test_identifier_kinds(self):
        self.assertEqual(self.summary["resolved_identifier_kind_counts"],{
            "cmsis_device_name":13,
            "ordering_pattern":307,
        })

    def test_blocked_families(self):
        self.assertEqual(self.summary["blocked_family_counts"],{
            "STM32C0":16,
            "STM32F3":4,
            "STM32F4":3,
            "STM32G0":42,
            "STM32G4":1,
            "STM32L1":1,
            "STM32L4":2,
        })

    def test_known_fail_closed_cases(self):
        blocked={r["icpn"] for r in self.blocked}
        for icpn in (
            "STM32F405OGY6VTR",
            "STM32F405OGY6WTR",
            "STM32F437VIT6WTR",
            "STM32G491RCY6TR",
            "STM32L151VDY6XTR",
            "STM32L496WGY6PST",
            "STM32L496WGY6PTR",
        ):
            self.assertIn(icpn,blocked)

    def test_no_capability_overclaim(self):
        for row in self.qualified:
            self.assertEqual(row["programming_profile_state"],"unresolved")
            self.assertEqual(row["route_validation_status"],"not_verified")
            self.assertEqual(row["programming_verified"],"false")
            self.assertEqual(row["engineering_verified"],"false")
            self.assertEqual(row["hil_verified"],"false")
            self.assertEqual(row["production_write_authorized"],"false")
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))

    def test_projection(self):
        self.assertEqual(
            self.summary["projected_route_exact_count_if_qualified_set_later_promoted"],3914
        )
        self.assertEqual(
            self.summary["projected_remaining_gap_if_qualified_set_later_promoted"],636
        )
        self.assertAlmostEqual(
            self.summary["projected_route_coverage_percent_if_qualified_set_later_promoted"],
            86.0220,
        )


if __name__=="__main__":
    unittest.main()
