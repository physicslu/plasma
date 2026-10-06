import copy
import unittest

import analyze_stm32wl3_metadata_replay_v45 as a


class TestSTM32WL3MetadataReplayV45(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authority = a.load_authority()
        cls.exact = set(a.load_exact())
        cls.result = a.analyze()

    def test_complete_replay(self):
        self.assertEqual(self.result["input_active_exact_count"], 47)
        self.assertEqual(self.result["metadata_decodable_exact_count"], 47)
        self.assertEqual(self.result["metadata_blocked_exact_count"], 0)
        self.assertEqual(self.result["direct_ordering_information_exact_count"], 45)
        self.assertEqual(self.result["bounded_exact_exception_count"], 2)

    def test_representative_ordering_decode(self):
        cases = {
            "STM32WL30K8V6": ("VFQFPN", 32, 64, "-40 to 85 C", ""),
            "STM32WL31KBV6": ("VFQFPN", 32, 128, "-40 to 85 C", ""),
            "STM32WL33CCV7ATR": ("VFQFPN", 48, 256, "-40 to 105 C", "ATR"),
            "STM32WL33K8V6XTR": ("VFQFPN", 32, 64, "-40 to 85 C", "XTR"),
            "STM32WL3RKBV6X": ("VFQFPN", 32, 128, "-40 to 85 C", "X"),
        }
        for icpn, expected in cases.items():
            with self.subTest(icpn=icpn):
                row = a.decode_one(icpn, self.authority, self.exact)
                self.assertEqual(
                    (
                        row["package"],
                        row["pin_count"],
                        row["flash_kib"],
                        row["temperature_grade"],
                        row["option_suffix"],
                    ),
                    expected,
                )

    def test_wl31_c_pin48_exceptions_are_exact_bounded(self):
        for icpn in ("STM32WL31C8V6", "STM32WL31CBV6"):
            row = a.decode_one(icpn, self.authority, self.exact)
            self.assertEqual(row["pin_count"], 48)
            self.assertEqual(
                row["metadata_exception"],
                "WL31_C_PIN48_EXACT_PRODUCT_EXCEPTION",
            )

        with self.assertRaises(ValueError):
            a.decode_one(
                "STM32WL31CCV6",
                self.authority,
                self.exact | {"STM32WL31CCV6"},
            )

    def test_frequency_option_boundaries_fail_closed(self):
        for bad in (
            "STM32WL30K8V6X",
            "STM32WL31K8V6X",
            "STM32WL3RKBV6A",
            "STM32WL33K8V6Z",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    a.decode_one(bad, self.authority, self.exact | {bad})

    def test_unknown_codes_fail_closed(self):
        for bad in (
            "STM32WL30C8V6",
            "STM32WL33KDV6",
            "STM32WL33K8T6",
            "STM32WL3RKBV8",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    a.decode_one(bad, self.authority, self.exact | {bad})

    def test_authority_mutation_fails(self):
        mutated = copy.deepcopy(self.authority)
        mutated["series"]["STM32WL33"]["frequency_band_options"] = [""]
        with self.assertRaises(ValueError):
            a.decode_one("STM32WL33CCV6A", mutated, self.exact)

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
