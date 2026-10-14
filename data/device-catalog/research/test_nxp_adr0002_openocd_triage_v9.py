import unittest
from collections import Counter
from nxp_adr0002_openocd_triage_v9 import build,serialize,LEDGER,group

class TestNxpADR0002(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=build()
        cls.by={x["icpn"]:x for x in cls.rows}
    def test_501_and_priority(self):
        self.assertEqual(len(self.rows),501)
        self.assertEqual(Counter(x["research_priority"] for x in self.rows),{"P0":27,"P1":38,"P2":436})
        self.assertEqual(sum(x["production_identity_admitted"]=="true" for x in self.rows),224)
    def test_exact_examples_and_no_support_false_positive(self):
        expected={"MKL25Z128VFM4":"P0","LPC844M201JBD48E":"P0","LPC845M301JHI48E":"P0",
                  "LPC802M001JDH16FP":"P1","LPC804M101JDH20J":"P1",
                  "K32L2B11VFT0AR":"P1","MCXA132VFM":"P2","LPC5502JHI48":"P2"}
        for sku,priority in expected.items():
            self.assertEqual(self.by[sku]["research_priority"],priority)
        self.assertFalse(any(x["openocd_software_state"]=="SUPPORTED" or x["adr_catalog_visibility_authorized"]=="true" for x in self.rows))
    def test_source_locked_ledger_byte_identical(self):
        self.assertEqual(LEDGER.read_bytes(),serialize(self.rows))
    def test_unknown_family_fail_closed(self):
        with self.assertRaises(ValueError):group("MADEUPPART")
if __name__=="__main__":unittest.main()
