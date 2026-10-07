import json
import unittest

import analyze_st_final_active_tail_gap_v60 as a


class TestSTFinalActiveTailGapV60(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=a.analyze()
        auth=json.loads(a.AUTHORITY.read_text(encoding="utf-8"))
        cls.by={r["icpn"]:r for r in auth["records"]}

    def test_complete(self):
        self.assertEqual(self.result["metadata_ready_exact_count"],9)
        self.assertEqual(self.result["metadata_blocked_exact_count"],0)
        self.assertEqual(self.result["ordering_grammar_exact_count"],4)
        self.assertEqual(self.result["official_exact_product_authority_count"],5)
        self.assertEqual(self.result["metadata_exception_exact_count"],0)

    def test_f4_exact_product_authority(self):
        self.assertEqual(self.by["STM32F405OGY6VTR"]["package"],"WLCSP")
        self.assertEqual(self.by["STM32F405OGY6VTR"]["pin_count"],"90")
        self.assertEqual(self.by["STM32F405OGY6WTR"]["option_suffix"],"WTR")
        self.assertEqual(self.by["STM32F437VIT6WTR"]["flash_size"],"2048 KiB")
        self.assertTrue(all(
            self.by[x]["option_semantics"]=="opaque_manufacturer_suffix_preserved_literal"
            for x in ("STM32F405OGY6VTR","STM32F405OGY6WTR","STM32F437VIT6WTR")
        ))

    def test_l1_exact_product_authority(self):
        self.assertEqual(self.by["STM32L151VDT7X"]["temperature_grade"],"-40..105 C")
        self.assertEqual(self.by["STM32L151VDY6XTR"]["package"],"WLCSP104")
        self.assertEqual(self.by["STM32L151VDY6XTR"]["pin_count"],"104")

    def test_existing_ordering_grammars(self):
        self.assertEqual(self.by["STM32L412RBT3"]["temperature_grade"],"-40..125 C")
        self.assertEqual(self.by["STM32L496WGY6PST"]["option_suffix"],"PST")
        self.assertEqual(self.by["STM32L496WGY6PTR"]["pin_count"],"115")
        self.assertEqual(self.by["STM32U375CET6TR"]["package"],"LQFP")

    def test_capability_boundary(self):
        for value in self.result["claims"].values():
            self.assertFalse(value)


if __name__=="__main__":
    unittest.main()
