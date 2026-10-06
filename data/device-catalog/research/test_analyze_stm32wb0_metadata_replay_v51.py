import copy
import unittest

import analyze_stm32wb0_metadata_replay_v51 as a


class TestSTM32WB0MetadataReplayV51(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authority = a.load_authority()
        cls.exact = set(a.load_exact())
        cls.result = a.analyze()

    def test_complete_replay(self):
        self.assertEqual(self.result["input_active_exact_count"], 24)
        self.assertEqual(self.result["metadata_decodable_exact_count"], 24)
        self.assertEqual(self.result["metadata_blocked_exact_count"], 0)
        self.assertEqual(self.result["direct_ordering_information_exact_count"], 24)
        self.assertEqual(self.result["bounded_exact_exception_count"], 0)
        self.assertEqual(self.result["network_coprocessor_exact_count"], 4)

    def test_representative_ordering_decode(self):
        cases = {
            "STM32WB05KNV6TR": ("STM32WB05N", "STM32WB05KN", "VFQFPN", 32, "N/A (network coprocessor)", "-40 to 85 C", True),
            "STM32WB05TZF7TR": ("STM32WB05Z", "STM32WB05TZ", "WLCSP", 36, "192 KiB", "-40 to 105 C", False),
            "STM32WB06CCF6TR": ("STM32WB06C", "STM32WB06CC", "WLCSP", 49, "256 KiB", "-40 to 85 C", False),
            "STM32WB07CCV7TR": ("STM32WB07C", "STM32WB07CC", "VFQFPN", 48, "256 KiB", "-40 to 105 C", False),
            "STM32WB09TEF6TR": ("STM32WB09E", "STM32WB09TE", "WLCSP", 36, "512 KiB", "-40 to 85 C", False),
        }
        for icpn, expected in cases.items():
            with self.subTest(icpn=icpn):
                row = a.decode_one(icpn, self.authority, self.exact)
                self.assertEqual(
                    (row["series"], row["base_device"], row["package"], row["pin_count"],
                     row["flash_size"], row["temperature_grade"], row["network_coprocessor"]),
                    expected,
                )

    def test_locked_set_rejects_unobserved_identity(self):
        with self.assertRaises(ValueError):
            a.decode_one("STM32WB09KEV6", self.authority, self.exact)

    def test_unknown_pin_package_pair_fails_closed(self):
        modified = copy.deepcopy(self.authority)
        modified["package_resolution"].pop("C:F")
        with self.assertRaises(ValueError):
            a.decode_one("STM32WB06CCF6TR", modified, self.exact)

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
