import unittest
import propose_openocd_consolidated_backend_promotion_v614 as p

class TestOpenOCDConsolidatedBackendPromotionV614(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deltas, cls.files, cls.summary = p.build()

    def test_exact_count_and_authorities(self):
        self.assertEqual(self.summary["promotion_exact_count"], 364)
        self.assertEqual(self.summary["authority_counts"], {
            "v6.12_c0_bounded_identifier_bridge": 11,
            "v6.13_bounded_suffix_normalization": 33,
            "v6.5_identifier_qualification": 320,
        })

    def test_family_partition(self):
        self.assertEqual(self.summary["family_promotion_counts"], {
            "STM32C0": 12,
            "STM32F2": 72,
            "STM32F3": 168,
            "STM32F4": 3,
            "STM32F7": 62,
            "STM32G0": 30,
            "STM32H7": 14,
            "STM32L1": 1,
            "STM32L4": 1,
            "STM32U3": 1,
        })

    def test_identifier_kinds(self):
        self.assertEqual(self.summary["identifier_kind_counts"], {
            "cmsis_device_name": 13,
            "ordering_pattern": 351,
        })

    def test_backend_only_delta(self):
        self.assertEqual(len(self.deltas), 364)
        self.assertTrue(all(r["before_mapping_status"] == "no_mapping" for r in self.deltas))
        self.assertTrue(all(r["after_existing_identifier"] for r in self.deltas))
        self.assertTrue(all(r["after_openocd_target_config"] for r in self.deltas))
        self.assertTrue(all(r["programming_profile_state"] == "unresolved" for r in self.deltas))
        self.assertTrue(all(r["production_write_authorized"] == "false" for r in self.deltas))

    def test_projected_partition(self):
        self.assertEqual(self.summary["catalog_backend_partition_before"], {
            "mapped": 3673, "no_mapping": 956
        })
        self.assertEqual(self.summary["catalog_backend_partition_after_if_approved"], {
            "mapped": 4037, "no_mapping": 592
        })
        self.assertEqual(self.summary["production_exact_total_after_if_approved"], 4629)

    def test_projected_active_coverage(self):
        self.assertEqual(self.summary["active_openocd_route_after_if_approved"], 3958)
        self.assertEqual(self.summary["active_openocd_route_gap_after_if_approved"], 592)
        self.assertAlmostEqual(
            self.summary["active_openocd_route_coverage_after_if_approved_percent"],
            86.9890,
        )

    def test_governance(self):
        self.assertFalse(self.summary["production_write_authorized"])
        self.assertEqual(self.summary["programming_profile_state_for_promotions"], "unresolved")
        self.assertEqual(self.summary["route_evidence_validation_status"], "not_verified")
        self.assertTrue(all(v is False for v in self.summary["claims"].values()))

if __name__ == "__main__":
    unittest.main()
