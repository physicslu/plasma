import copy
import unittest

import analyze_stm32f3_metadata_replay_v31 as a


class TestSTM32F3MetadataReplayV31(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authority = a.load_authority()
        cls.result = a.analyze()

    def test_complete_direct_replay(self):
        self.assertEqual(self.result["input_gap_exact_count"], 182)
        self.assertEqual(self.result["metadata_decodable_exact_count"], 182)
        self.assertEqual(self.result["metadata_blocked_exact_count"], 0)
        self.assertEqual(self.result["metadata_exception_exact_count"], 0)
        self.assertEqual(self.result["direct_ordering_information_exact_count"], 182)

    def test_density_band_partition(self):
        self.assertEqual(
            self.result["authority_band_counts"],
            a.EXPECTED_BAND_COUNTS,
        )
        self.assertEqual(self.result["series_counts"], a.EXPECTED_SERIES_COUNTS)

    def test_package_specific_pin_count_semantics(self):
        wlcsp49 = a.decode_one("STM32F301C8Y6TR", self.authority)
        self.assertEqual(wlcsp49["package"], "WLCSP")
        self.assertEqual(wlcsp49["pin_count"], 49)
        self.assertEqual(wlcsp49["flash_kib"], 64)
        self.assertEqual(wlcsp49["option_suffix"], "TR")

        bga100 = a.decode_one("STM32F302VDH6", self.authority)
        self.assertEqual(bga100["package"], "UFBGA")
        self.assertEqual(bga100["pin_count"], 100)
        self.assertEqual(bga100["flash_kib"], 384)

        wlcsp100 = a.decode_one("STM32F303VEY6TR", self.authority)
        self.assertEqual(wlcsp100["package"], "WLCSP")
        self.assertEqual(wlcsp100["pin_count"], 100)
        self.assertEqual(wlcsp100["flash_kib"], 512)

        wlcsp66 = a.decode_one("STM32F378RCY6TR", self.authority)
        self.assertEqual(wlcsp66["package"], "WLCSP")
        self.assertEqual(wlcsp66["pin_count"], 66)

    def test_representative_series_authorities(self):
        expected = {
            "STM32F301C8T6": "DS9895",
            "STM32F302CBT6": "DS9911",
            "STM32F302RET7": "DS10592 / DocID026900",
            "STM32F303C8T6": "DS9866",
            "STM32F303RCT7": "DS9118",
            "STM32F303VET7": "DS10362 / DocID026415",
            "STM32F318K8U7": "DS10315",
            "STM32F328C8T6": "DS10336 / DocID026351",
            "STM32F334K8U6": "DS9994",
            "STM32F358VCT6": "DocID025540",
            "STM32F373VCH7": "DS8845 / DocID022691",
            "STM32F378VCH6": "DS10062 / DocID025608",
            "STM32F398VET6": "DocID027227",
        }
        for icpn, document in expected.items():
            with self.subTest(icpn=icpn):
                self.assertEqual(a.decode_one(icpn, self.authority)["authority_document"], document)

    def test_invalid_cross_band_combinations_fail_closed(self):
        with self.assertRaises(ValueError):
            a.decode_one("STM32F302CET6", self.authority)
        with self.assertRaises(ValueError):
            a.decode_one("STM32F303KBT6", self.authority)
        with self.assertRaises(ValueError):
            a.decode_one("STM32F378RCH6", self.authority)
        with self.assertRaises(ValueError):
            a.decode_one("STM32F398VEY6", self.authority)

    def test_authority_mutation_fails(self):
        mutated = copy.deepcopy(self.authority)
        mutated["series"]["STM32F378"]["bands"][0]["allowed_pin_package"].remove("R/Y")
        with self.assertRaises(ValueError):
            a.decode_one("STM32F378RCY6TR", mutated)

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
