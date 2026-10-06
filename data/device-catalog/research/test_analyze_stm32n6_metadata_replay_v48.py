import copy
import unittest

import analyze_stm32n6_metadata_replay_v48 as a


class TestSTM32N6MetadataReplayV48(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authority = a.load_authority()
        cls.exact = set(a.load_exact())
        cls.result = a.analyze()

    def test_complete_replay(self):
        self.assertEqual(self.result["input_active_exact_count"], 32)
        self.assertEqual(self.result["metadata_decodable_exact_count"], 32)
        self.assertEqual(self.result["metadata_blocked_exact_count"], 0)
        self.assertEqual(self.result["direct_ordering_information_exact_count"], 32)
        self.assertEqual(self.result["bounded_exact_exception_count"], 0)

    def test_representative_ordering_decode(self):
        cases = {
            "STM32N645A0H3Q": (
                "STM32N645", "STM32N645A0", "VFBGA", 169,
                "0-1 KiB", "-40 to 125 C", "Q", False, False,
            ),
            "STM32N647Z0H3Q": (
                "STM32N647", "STM32N647Z0", "VFBGA", 142,
                "0-1 KiB", "-40 to 125 C", "Q", False, True,
            ),
            "STM32N655A0H3QG": (
                "STM32N655", "STM32N655A0", "VFBGA", 169,
                "0-1 KiB", "-40 to 125 C", "QG", True, False,
            ),
            "STM32N657I0H3QTR": (
                "STM32N657", "STM32N657I0", "VFBGA", 178,
                "0-1 KiB", "-40 to 125 C", "QTR", True, True,
            ),
        }
        for icpn, expected in cases.items():
            with self.subTest(icpn=icpn):
                row = a.decode_one(icpn, self.authority, self.exact)
                self.assertEqual(
                    (
                        row["series"],
                        row["base_device"],
                        row["package"],
                        row["pin_count"],
                        row["flash_size"],
                        row["temperature_grade"],
                        row["option_suffix"],
                        row["crypto"],
                        row["neural_art"],
                    ),
                    expected,
                )

    def test_locked_set_rejects_unobserved_ordering_identity(self):
        with self.assertRaises(ValueError):
            a.decode_one("STM32N657A0H3QT", self.authority, self.exact)

    def test_unknown_code_is_not_generalized(self):
        modified = copy.deepcopy(self.authority)
        modified["common"]["pin_codes"].pop("A")
        with self.assertRaises(ValueError):
            a.decode_one("STM32N657A0H3Q", modified, self.exact)

    def test_capability_boundary_remains_closed(self):
        claims = self.result["claims"]
        self.assertTrue(claims["layer1_identity_set_locked"])
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
