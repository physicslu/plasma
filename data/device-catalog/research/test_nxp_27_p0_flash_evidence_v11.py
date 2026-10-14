import unittest
from collections import Counter
from nxp_27_p0_flash_evidence_v11 import build,render,LEDGER,EXPECTED

class Nxp27P0SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=build()
        cls.by={r["icpn"]:r for r in cls.rows}
    def test_exact_27_including_all_15_unadmitted_lpc(self):
        self.assertEqual(Counter(r["family"] for r in self.rows),EXPECTED)
        self.assertEqual(sum(r["manufacturer_metadata_state"]=="LPC84X_EXACT_PART_HTML_BLOCKED" for r in self.rows),15)
        self.assertEqual(sum(r["manufacturer_exact_flash_kib"] in ("32","64","128") for r in self.rows),12)
    def test_driver_source_not_exact_programmability(self):
        self.assertTrue(all(r["software_support_state"]=="CANDIDATE" and r["public_catalog_authorized"]=="false" and r["requested_read_verify_qualified"]=="UNKNOWN" and r["exact_icpn_driver_id_match_verified"]=="false" for r in self.rows))
        self.assertEqual(self.by["MKL25Z32VFM4"]["manufacturer_exact_flash_kib"],"32")
        self.assertEqual(self.by["MKL25Z128VFM4"]["manufacturer_exact_flash_kib"],"128")
        self.assertEqual(self.by["LPC844M201JBD48E"]["manufacturer_exact_flash_kib"],"")
        self.assertEqual(self.by["LPC845M301JHI48E"]["driver_flash_capacity_kib_candidate"],"64")
    def test_security_and_unknown_id_abort_negative_gates(self):
        for r in self.rows:
            if r["family"]=="KL25":
                self.assertIn("FCF",r["source_safety_blocker"])
            else:
                self.assertIn("EXIT_MINUS_ONE",r["source_safety_blocker"])
            self.assertEqual(r["silicon_id_observed"],"UNKNOWN")
    def test_byte_identical_full_source_review(self):
        self.assertEqual(LEDGER.read_bytes(),render(self.rows))
if __name__=="__main__":unittest.main()
