import copy
import unittest

import analyze_stm32f7_metadata_replay_v35 as a


class TestSTM32F7MetadataReplayV35(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authority = a.load_authority()
        cls.result = a.analyze()

    def test_complete_replay(self):
        self.assertEqual(self.result["input_gap_exact_count"], 154)
        self.assertEqual(self.result["metadata_decodable_exact_count"], 154)
        self.assertEqual(self.result["metadata_blocked_exact_count"], 0)
        self.assertEqual(self.result["direct_ordering_information_exact_count"], 151)
        self.assertEqual(self.result["exact_product_override_count"], 3)

    def test_bounded_f750_override_set(self):
        self.assertEqual(
            set(self.result["exact_product_override_icpns"]),
            a.EXPECTED_OVERRIDE_IDS,
        )
        self.assertEqual(
            a.decode_one("STM32F750V8T7", self.authority),
            {
                "icpn": "STM32F750V8T7",
                "family": "STM32F7",
                "series": "STM32F750",
                "base_device": "STM32F750V8",
                "package": "LQFP",
                "pin_count": 100,
                "flash_kib": 64,
                "temperature_grade": "-40 to 105 C",
                "option_suffix": "",
                "authority_kind": "exact_product_override",
                "authority_document": "STM32F750 exact product surface",
                "authority_revision": None,
                "authority_url":
                    "https://www.st.com/en/microcontrollers-microprocessors/stm32f750v8.html",
                "metadata_basis": "official_st_exact_product_metadata_override",
            },
        )

    def test_package_specific_pin_semantics(self):
        ufbga144 = a.decode_one("STM32F723ZCI6", self.authority)
        self.assertEqual((ufbga144["package"], ufbga144["pin_count"]), ("UFBGA", 144))

        wlcsp143 = a.decode_one("STM32F746ZEY6TR", self.authority)
        self.assertEqual((wlcsp143["package"], wlcsp143["pin_count"]), ("WLCSP", 143))
        self.assertEqual(wlcsp143["option_suffix"], "TR")

        ufbga176 = a.decode_one("STM32F765IIK6", self.authority)
        self.assertEqual((ufbga176["package"], ufbga176["pin_count"]), ("UFBGA", 176))
        self.assertEqual(ufbga176["flash_kib"], 2048)

        wlcsp180 = a.decode_one("STM32F769AIY6TR", self.authority)
        self.assertEqual((wlcsp180["package"], wlcsp180["pin_count"]), ("WLCSP", 180))

    def test_series_authority_bindings(self):
        expected = {
            "STM32F722IEK6": ("DS11853", 9),
            "STM32F730R8T6": ("DS12536", 2),
            "STM32F732RET6": ("DS11854", 7),
            "STM32F746NGH6": ("DS10916", 5),
            "STM32F756ZGT6": ("DS10915", 5),
            "STM32F765NIH7": ("DS11532", 9),
            "STM32F777IIK7": ("DS11243", 8),
            "STM32F779NIH6": ("DS11243", 8),
        }
        for icpn, authority in expected.items():
            with self.subTest(icpn=icpn):
                row = a.decode_one(icpn, self.authority)
                self.assertEqual(
                    (row["authority_document"], row["authority_revision"]),
                    authority,
                )

    def test_unknown_or_cross_scope_codes_fail_closed(self):
        with self.assertRaises(ValueError):
            a.decode_one("STM32F722REH6", self.authority)
        with self.assertRaises(ValueError):
            a.decode_one("STM32F756ZET6", self.authority)
        with self.assertRaises(ValueError):
            a.decode_one("STM32F777IGT6", self.authority)
        with self.assertRaises(ValueError):
            a.decode_one("STM32F750V8T6TR", self.authority)

    def test_authority_mutation_fails(self):
        mutated = copy.deepcopy(self.authority)
        del mutated["common"]["pin_package"]["Z/Y"]
        with self.assertRaises(ValueError):
            a.decode_one("STM32F746ZEY6TR", mutated)

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
