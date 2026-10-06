import copy
import unittest

import analyze_stm32c5_metadata_replay_v42 as a


class TestSTM32C5MetadataReplayV42(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authority = a.load_authority()
        cls.exact = set(a.load_exact())
        cls.result = a.analyze()

    def test_complete_replay(self):
        self.assertEqual(self.result["input_active_exact_count"], 172)
        self.assertEqual(self.result["metadata_decodable_exact_count"], 172)
        self.assertEqual(self.result["metadata_blocked_exact_count"], 0)
        self.assertEqual(self.result["direct_ordering_information_exact_count"], 170)
        self.assertEqual(self.result["bounded_exact_exception_count"], 2)

    def test_dfp_freshness_gap_does_not_block_layer1_metadata(self):
        self.assertEqual(self.result["dfp_exact_variant_observed_count"], 139)
        self.assertEqual(self.result["dfp_parent_only_count"], 33)
        self.assertEqual(self.result["dfp_parent_only_metadata_decodable_count"], 33)
        self.assertFalse(self.result["claims"]["dfp_exact_variant_required_for_layer1_metadata"])

    def test_representative_metadata(self):
        cases = {
            "STM32C531FBU6TR": ("UFQFPN", 20, 128, "-40 to 85 C"),
            "STM32C542RCT3": ("LQFP", 64, 256, "-40 to 125 C"),
            "STM32C551VET6": ("LQFP", 100, 512, "-40 to 85 C"),
            "STM32C562KEU3TR": ("UFQFPN", 32, 512, "-40 to 125 C"),
            "STM32C593ZGT6": ("LQFP", 144, 1024, "-40 to 85 C"),
            "STM32C5A3KGU3TR": ("UFQFPN", 32, 1024, "-40 to 125 C"),
        }
        for icpn, expected in cases.items():
            with self.subTest(icpn=icpn):
                row = a.decode_one(icpn, self.authority, self.exact)
                self.assertEqual(
                    (row["package"], row["pin_count"], row["flash_kib"], row["temperature_grade"]),
                    expected,
                )

    def test_two_temp7_exceptions_are_exact_bounded(self):
        for icpn in ("STM32C551CCT7", "STM32C551CCT7TR"):
            row = a.decode_one(icpn, self.authority, self.exact)
            self.assertEqual(row["temperature_grade"], "-40 to 105 C")
            self.assertEqual(row["metadata_exception"], "C551_TEMP7_EXACT_ESTORE_EXCEPTION")

        with self.assertRaises(ValueError):
            a.decode_one("STM32C551KCT7", self.authority, self.exact | {"STM32C551KCT7"})

    def test_unknown_codes_fail_closed(self):
        for bad in (
            "STM32C531ZBT6",
            "STM32C542KBT6",
            "STM32C562KCT6",
            "STM32C5A3KET6",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    a.decode_one(bad, self.authority, self.exact | {bad})

    def test_authority_mutation_fails(self):
        mutated = copy.deepcopy(self.authority)
        del mutated["series"]["STM32C591"]["package_codes"]["T"]
        with self.assertRaises(ValueError):
            a.decode_one("STM32C591VET6", mutated, self.exact)

    def test_claim_boundaries(self):
        claims = self.result["claims"]
        self.assertTrue(claims["metadata_authority_replay_complete"])
        self.assertTrue(claims["layer1_admission_proposal_ready"])
        self.assertFalse(claims["backend_scope_evaluated"])
        self.assertFalse(claims["backend_route_ready"])
        self.assertFalse(claims["programming_profile_scope_expanded"])
        self.assertFalse(claims["engineering_verified"])
        self.assertFalse(claims["field_evidence"])
        self.assertFalse(claims["ps_hil_qualification"])
        self.assertFalse(claims["production_write_authorized"])


if __name__ == "__main__":
    unittest.main()
