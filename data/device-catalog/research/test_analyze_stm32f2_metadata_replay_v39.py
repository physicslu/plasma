import copy
import unittest

import analyze_stm32f2_metadata_replay_v39 as a


class TestSTM32F2MetadataReplayV39(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authority = a.load_authority()
        cls.result = a.analyze()

    def test_complete_direct_replay(self):
        self.assertEqual(self.result["input_gap_exact_count"], 72)
        self.assertEqual(self.result["metadata_decodable_exact_count"], 72)
        self.assertEqual(self.result["metadata_blocked_exact_count"], 0)
        self.assertEqual(self.result["metadata_exception_exact_count"], 0)
        self.assertEqual(self.result["direct_ordering_information_exact_count"], 72)

    def test_package_specific_pin_semantics(self):
        wlcsp66 = a.decode_one("STM32F205RGY6TR", self.authority)
        self.assertEqual((wlcsp66["package"], wlcsp66["pin_count"]), ("WLCSP", 66))
        self.assertEqual(wlcsp66["flash_kib"], 1024)
        self.assertEqual(wlcsp66["option_suffix"], "TR")

        ufbga176 = a.decode_one("STM32F207IGH7", self.authority)
        self.assertEqual((ufbga176["package"], ufbga176["pin_count"]), ("UFBGA", 176))
        self.assertEqual(ufbga176["flash_kib"], 1024)

        lqfp144 = a.decode_one("STM32F217ZGT6", self.authority)
        self.assertEqual((lqfp144["package"], lqfp144["pin_count"]), ("LQFP", 144))

    def test_series_authority_bindings(self):
        expected = {
            "STM32F205RFT6": ("DS6329", 18),
            "STM32F207ZGT7": ("DS6329", 18),
            "STM32F215VGT7": ("DS6697", 13),
            "STM32F217ZET7": ("DS6697", 13),
        }
        for icpn, authority in expected.items():
            with self.subTest(icpn=icpn):
                row = a.decode_one(icpn, self.authority)
                self.assertEqual(
                    (row["authority_document"], row["authority_revision"]),
                    authority,
                )

    def test_invalid_codes_fail_closed(self):
        with self.assertRaises(ValueError):
            a.decode_one("STM32F215VFT6", self.authority)
        with self.assertRaises(ValueError):
            a.decode_one("STM32F217VEY6TR", self.authority)
        with self.assertRaises(ValueError):
            a.decode_one("STM32F205RGH6", self.authority)
        with self.assertRaises(ValueError):
            a.decode_one("STM32F207ZGT8", self.authority)

    def test_authority_mutation_fails(self):
        mutated = copy.deepcopy(self.authority)
        del mutated["common"]["pin_package"]["Z/T"]
        with self.assertRaises(ValueError):
            a.decode_one("STM32F207ZGT6", mutated)

    def test_claim_boundaries(self):
        claims = self.result["claims"]
        self.assertTrue(claims["metadata_authority_replay_complete"])
        self.assertTrue(claims["layer1_admission_proposal_ready"])
        self.assertFalse(claims["backend_scope_evaluated"])
        self.assertFalse(claims["programming_profile_scope_expanded"])
        self.assertFalse(claims["engineering_verified"])
        self.assertFalse(claims["field_evidence"])
        self.assertFalse(claims["ps_hil_qualification"])
        self.assertFalse(claims["production_write_authorized"])


if __name__ == "__main__":
    unittest.main()
