import unittest
from nxp_phase1_k32l2a_v16 import build,report,LEDGER,to_csv,verify
from nxp_phase1_pin_package_v15 import build as old_build

class TestPhase1K32L2AxNxpOriginalDatasheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=build()
        cls.by={r["icpn"]:r for r in cls.rows}
    def test_all_exact_four_sram_and_analog_supply(self):
        for sku in ("K32L2A31VLH1A","K32L2A31VLL1A","K32L2A41VLH1A","K32L2A41VLL1A"):
            r=self.by[sku]
            self.assertEqual(r["ram"],"128")
            self.assertEqual(r["working_vdd"],"1.71 to 3.6")
            self.assertEqual(r["vdda"],"1.71 to 3.6 V; |VDD-VDDA| <= 0.1 V")
            self.assertEqual(r["ram_state"],"VERIFIED")
            self.assertEqual(r["vdda_state"],"VERIFIED")
            self.assertEqual(r["document_id"],"K32L2Ax")
        self.assertEqual(self.by["K32L2A41VLH1A"]["flash"],"512 kB")
        self.assertEqual(self.by["K32L2A31VLH1A"]["flash"],"256 kB")
    def test_nxp_b_pdf_unavailable_does_not_infer_sram(self):
        b=[r for r in self.rows if r["k32l2b_pdf_inaccessible_reason"]]
        self.assertEqual(len(b),12)
        self.assertTrue(all(r["ram_state"]=="UNKNOWN" and r["working_vdd_state"]=="UNKNOWN"
                     and r["vdda_state"]=="UNKNOWN" and r["ram"]=="" for r in b))
    def test_preserve_all_501_source_and_phase_boundaries(self):
        prior={r["icpn"]:r for r in old_build()}
        self.assertEqual(len(prior),len(self.rows))
        for r in self.rows:
            old=prior[r["icpn"]]
            self.assertEqual(r["identity_state"],old["identity_state"])
            self.assertEqual(r["phase"],"1")
            if r["icpn"] not in ("K32L2A31VLH1A","K32L2A31VLL1A","K32L2A41VLH1A","K32L2A41VLL1A"):
                for key in old:self.assertEqual(r[key],old[key],r["icpn"]+":"+key)
        self.assertEqual(sum(r["identity_state"]=="ADMITTED" for r in self.rows),224)
        self.assertEqual(sum(r["identity_state"]=="RESEARCH_ONLY" for r in self.rows),277)
    def test_metrics_and_replay(self):
        s=report(self.rows)
        self.assertEqual(s["all"]["fields"]["ram"]["VERIFIED"],31)
        self.assertEqual(s["all"]["fields"]["working_vdd"]["VERIFIED"],31)
        self.assertEqual(s["all"]["fields"]["vdda"]["VERIFIED"],16)
        self.assertEqual(s["K32L2B_source_exception_rows"],12)
        self.assertIsNone(s["software_supported_product_scope"])
        self.assertEqual(LEDGER.read_bytes(),to_csv(self.rows))
        verify()
if __name__=="__main__":unittest.main()
