import unittest
from nxp_phase1_mcxa1fs_v18 import build,verify,report,OUTPUT,emit,headers,BASE,EXTRA
from nxp_phase1_selector_v17 import generate
class TestExactNXPManufacturerA1RAM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=build()
        cls.by={r["icpn"]:r for r in cls.rows}
    def test_vendor_exact_sram(self):
        for icpn,ram in (("MCXA132VFM","16"),("MCXA143VFT","32"),
            ("MCXA144VFT","64"),("MCXA155VLL","96"),
            ("MCXA156VMP","128"),("MCXA175VPN","128"),
            ("MCXA176VLL","256"),("MCXA186VLH","256")):
            self.assertEqual(self.by[icpn]["ram"],ram)
            self.assertEqual(self.by[icpn]["ram_state"],"VERIFIED")
    def test_research_4_are_not_newly_admitted(self):
        for icpn in ("MCXA144VLH","MCXA145VLH","MCXA146VLH","MCXA155VLH"):
            self.assertEqual(self.by[icpn]["identity_state"],"RESEARCH_ONLY")
            self.assertEqual(self.by[icpn]["ram"],"")
            self.assertEqual(self.by[icpn]["ram_state"],"UNKNOWN")
    def test_no_unapproved_voltage_identity_or_phase_shift(self):
        old={x["icpn"]:x for x in generate()[0]}
        for x in self.rows:
            o=old[x["icpn"]]
            self.assertEqual(x["identity_state"],o["identity_state"])
            for k in ("working_vdd","vdda","io_supply","phase"):
                self.assertEqual(x[k],o[k])
        self.assertEqual(len(self.rows),501)
    def test_completeness_and_source_replay(self):
        m=report(self.rows)
        self.assertEqual(m["current_admitted"]["fields"]["ram"],
          {"VERIFIED":114,"PARTIAL":13,"UNKNOWN":97,"CONFLICT":0})
        self.assertEqual(m["all_501"]["fields"]["ram"],
          {"VERIFIED":129,"PARTIAL":61,"UNKNOWN":311,"CONFLICT":0})
        self.assertIsNone(m["pdf_original_sha256"])
        self.assertEqual(OUTPUT.read_bytes(),emit(self.rows,headers(BASE)+list(EXTRA)))
        verify()
if __name__=="__main__":unittest.main()
