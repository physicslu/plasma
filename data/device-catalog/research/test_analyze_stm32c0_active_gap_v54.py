import unittest
import analyze_stm32c0_active_gap_v54 as a

class TestSTM32C0ActiveGapV54(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gap = a.load_gap()
        cls.auth = a.load_authority()
        cls.by = {x: a.decode_one(x, cls.auth, set(cls.gap)) for x in cls.gap}
        cls.result = a.analyze()

    def test_complete(self):
        self.assertEqual(self.result["metadata_decodable_exact_count"], 17)
        self.assertEqual(self.result["metadata_blocked_exact_count"], 0)
        self.assertEqual(self.result["bounded_exact_exception_count"], 0)

    def test_new_wlcsp_semantics(self):
        self.assertEqual(self.by["STM32C011D6Y6TR"]["package"], "WLCSP")
        self.assertEqual(self.by["STM32C011D6Y6TR"]["pin_count"], "12")
        self.assertEqual(self.by["STM32C051D8Y6TR"]["package"], "WLCSP")
        self.assertEqual(self.by["STM32C051D8Y6TR"]["pin_count"], "15")

    def test_existing_semantics_replay(self):
        self.assertEqual(self.by["STM32C071FBY6TR"]["pin_count"], "19")
        self.assertEqual(self.by["STM32C071R8I6N"]["option_suffix"], "N")
        self.assertEqual(self.by["STM32C091KBT3"]["temperature_grade"], "-40 to 125 C")
        self.assertEqual(self.by["STM32C092ECY3TR"]["pin_count"], "24")
        self.assertEqual(self.by["STM32C092RBI6"]["package"], "UFBGA")

    def test_governance(self):
        claims = self.result["claims"]
        self.assertTrue(claims["metadata_replay_complete"])
        for key in (
            "backend_scope_evaluated","programming_profile_scope_expanded",
            "engineering_verified","field_evidence","ps_hil_qualification",
            "production_write_authorized"
        ):
            self.assertFalse(claims[key])

if __name__ == "__main__":
    unittest.main()
