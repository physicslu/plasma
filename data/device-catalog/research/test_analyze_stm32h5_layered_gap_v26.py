import unittest

import analyze_stm32h5_layered_gap_v26 as a


class TestSTM32H5LayeredGapV26(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = a.analyze()

    def test_layer1_counts(self):
        l1 = self.result["layer1"]
        self.assertEqual(l1["official_active_exact_mpn_count"], 190)
        self.assertEqual(l1["mx1_structural_pattern_count"], 151)
        self.assertEqual(l1["matched_exact_count"], 190)
        self.assertEqual(l1["matched_pattern_count"], 151)
        self.assertEqual(l1["unmatched_exact_count"], 0)
        self.assertEqual(l1["ambiguous_exact_count"], 0)
        self.assertEqual(l1["tr_exact_count"], 51)
        self.assertEqual(l1["non_tr_exact_count"], 139)

    def test_prefix_distribution(self):
        self.assertEqual(
            self.result["layer1"]["prefix_counts"],
            {
                "STM32H50": 14,
                "STM32H52": 39,
                "STM32H53": 14,
                "STM32H54": 4,
                "STM32H55": 2,
                "STM32H56": 59,
                "STM32H57": 23,
                "STM32H5E": 22,
                "STM32H5F": 13,
            },
        )

    def test_backend_is_fail_closed(self):
        l2 = self.result["layer2"]
        self.assertEqual(l2["current_plasma_target_catalog_h5_entry_count"], 0)
        self.assertEqual(l2["mapping_candidate_exact_count"], 0)
        self.assertEqual(l2["no_mapping_exact_count"], 190)
        self.assertEqual(l2["mapping_status"], "no_mapping")

    def test_claim_boundaries(self):
        claims = self.result["claims"]
        self.assertFalse(claims["metadata_authority_replay_complete"])
        self.assertFalse(claims["catalog_admission_ready"])
        self.assertFalse(claims["programming_profile_applicability_expanded"])
        self.assertFalse(claims["engineering_verified"])
        self.assertFalse(claims["operational_field_evidence"])
        self.assertFalse(claims["production_write_authorized"])

    def test_matching_is_fail_closed(self):
        self.assertEqual(a.matches_for("STM32H503CBT6", ["STM32H503CBTx"]), ["STM32H503CBTx"])
        self.assertEqual(a.matches_for("STM32H503CBT6TR", ["STM32H503CBTx"]), ["STM32H503CBTx"])
        self.assertEqual(a.matches_for("STM32H503CBT6", ["STM32H523CCTx"]), [])
        self.assertEqual(
            len(a.matches_for("STM32H503CBT6", ["STM32H503CBTx", "STM32H503CBTx"])),
            2,
        )


if __name__ == "__main__":
    unittest.main()
