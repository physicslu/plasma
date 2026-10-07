import unittest

import analyze_stm32h7_active_gap_v57 as a


class TestSTM32H7ActiveGapV57(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gap = a.load_gap()
        cls.auth = a.load_authority()
        cls.rows = {
            x: a.decode_one(x, cls.auth, set(cls.gap))
            for x in cls.gap
        }
        cls.result = a.analyze()

    def test_complete(self):
        self.assertEqual(self.result["metadata_decodable_exact_count"], 14)
        self.assertEqual(self.result["metadata_blocked_exact_count"], 0)
        self.assertEqual(self.result["bounded_exact_exception_count"], 0)

    def test_h730_current_ordering_semantics(self):
        self.assertEqual(self.rows["STM32H730ABI6Q"]["pin_count"], "169")
        self.assertEqual(self.rows["STM32H730ABI6Q"]["package"], "UFBGA")
        self.assertEqual(self.rows["STM32H730IBK6QTR"]["pin_count"], "176")
        self.assertEqual(self.rows["STM32H730IBK6QTR"]["option_suffix"], "QTR")

    def test_h7a3_h7b3_extended_pin_counts(self):
        self.assertEqual(self.rows["STM32H7A3QIY6QTR"]["pin_count"], "132")
        self.assertEqual(self.rows["STM32H7A3QIY6QTR"]["package"], "WLCSP")
        self.assertEqual(self.rows["STM32H7A3LGH6Q"]["pin_count"], "225")
        self.assertEqual(self.rows["STM32H7B3LIH6Q"]["pin_count"], "225")
        self.assertEqual(self.rows["STM32H7B3AII6Q"]["pin_count"], "169")

    def test_existing_h743_semantics_replay(self):
        row = self.rows["STM32H743IIT6TR"]
        self.assertEqual(row["package"], "LQFP")
        self.assertEqual(row["pin_count"], "176")
        self.assertEqual(row["flash_size"], "2048 KiB")
        self.assertEqual(row["option_suffix"], "TR")

    def test_capability_boundary(self):
        claims = self.result["claims"]
        self.assertTrue(claims["metadata_replay_complete"])
        for key in (
            "backend_scope_evaluated",
            "existing_family_backend_mapping_inherited",
            "programming_profile_scope_expanded",
            "engineering_verified",
            "field_evidence",
            "ps_hil_qualification",
            "production_write_authorized",
        ):
            self.assertFalse(claims[key])


if __name__ == "__main__":
    unittest.main()
