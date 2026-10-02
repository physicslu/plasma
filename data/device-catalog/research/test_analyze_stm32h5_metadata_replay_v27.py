import copy
import unittest

import analyze_stm32h5_metadata_replay_v27 as a


class TestSTM32H5MetadataReplayV27(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth = a.load_authority()
        cls.result = a.analyze()

    def test_counts(self):
        self.assertEqual(self.result["input_active_exact_count"], 190)
        self.assertEqual(self.result["metadata_decodable_exact_count"], 190)
        self.assertEqual(self.result["metadata_blocked_exact_count"], 0)
        self.assertEqual(self.result["direct_ordering_information_exact_count"], 187)
        self.assertEqual(self.result["bounded_exact_exception_count"], 3)

    def test_authority_documents(self):
        self.assertEqual(
            set(self.result["authority_documents"]),
            {
                "DS14053 Rev 4",
                "DS14121 Rev 5",
                "DS14258 Rev 6",
                "DS14539 Rev 3",
                "DS14540 Rev 3",
                "DS14971 Rev 1",
                "DS14972 Rev 1",
                "DS15167 Rev 1",
                "DS15168 Rev 1",
            },
        )

    def test_exact_exceptions_are_bounded(self):
        self.assertEqual(
            self.result["exception_exact_identities"],
            [
                "STM32H5E4ZJJ6",
                "STM32H5E4ZJJ7Q",
                "STM32H5E4ZKJ6",
            ],
        )
        decoded = a.decode_one("STM32H5E4ZJJ6", self.auth)
        self.assertEqual(decoded["package"], "UFBGA 144 10x10x0.6 P 0.8 mm")
        self.assertEqual(
            decoded["metadata_basis"],
            "ordering_information_plus_exact_st_quality_exception",
        )

        mutated = copy.deepcopy(self.auth)
        mutated["bounded_exact_exceptions"].pop("STM32H5E4ZJJ6")
        with self.assertRaises(ValueError):
            a.decode_one("STM32H5E4ZJJ6", mutated)

    def test_q_semantics_fail_closed(self):
        with self.assertRaises(ValueError):
            a.decode_one("STM32H563AII3", self.auth)
        with self.assertRaises(ValueError):
            a.decode_one("STM32H563AII6Q", self.auth)
        with self.assertRaises(ValueError):
            a.decode_one("STM32H5E4ZJT7", self.auth)
        with self.assertRaises(ValueError):
            a.decode_one("STM32H5E4ZJT6Q", self.auth)

    def test_h543_h553_exposed_pad_constraint(self):
        with self.assertRaises(ValueError):
            a.decode_one("STM32H543VET3", self.auth)
        decoded = a.decode_one("STM32H543VEZ3", self.auth)
        self.assertEqual(decoded["package"], "LQFP-EP")

    def test_claim_boundaries(self):
        claims = self.result["claims"]
        self.assertTrue(claims["metadata_authority_replay_complete"])
        self.assertTrue(claims["layer1_admission_proposal_ready"])
        self.assertFalse(claims["catalog_production_write_authorized"])
        self.assertFalse(claims["programming_profile_applicability_expanded"])
        self.assertFalse(claims["engineering_verified"])
        self.assertFalse(claims["operational_field_evidence"])
        self.assertEqual(self.result["layer2_backend_state"]["mapping_status"], "no_mapping")


if __name__ == "__main__":
    unittest.main()
