import unittest
from nxp_phase1_mcxa3fs_v20 import build,report,verify,OUT,serialize,old_headers,OLD,EXTRA
from nxp_phase1_mcxa1fs_v18 import build as old_build
class TestNXPPhase1MCXA3OfficialRAM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=build()
        cls.by={r["icpn"]:r for r in cls.rows}
    def test_source_exact_part_sram(self):
        for sku,ram in (("MCXA343VFM","32"),("MCXA344VLL","64"),
         ("MCXA345VLQ","128"),("MCXA346VPN","256"),("MCXA355VLH","128"),
         ("MCXA356VLQ","256"),("MCXA365VLL","128"),("MCXA366VLH","256")):
            self.assertEqual(self.by[sku]["ram"],ram)
            self.assertEqual(self.by[sku]["ram_state"],"VERIFIED")
    def test_admissions_and_voltage_unchanged(self):
        prior={x["icpn"]:x for x in old_build()}
        self.assertEqual(len(prior),501)
        for x in self.rows:
            p=prior[x["icpn"]]
            self.assertEqual(x["identity_state"],p["identity_state"])
            for k in ("working_vdd","vdda","io_supply","phase"):
                self.assertEqual(x[k],p[k])
    def test_coverage_exact_and_replay(self):
        m=report(self.rows)
        self.assertEqual(m["current_admitted"]["fields"]["ram"],
            {"VERIFIED":146,"PARTIAL":13,"UNKNOWN":65,"CONFLICT":0})
        self.assertEqual(m["all501"]["fields"]["ram"],
            {"VERIFIED":161,"PARTIAL":61,"UNKNOWN":279,"CONFLICT":0})
        self.assertTrue(m["revision_discrepancy_explicit"])
        self.assertIsNone(m["source_original_pdf_sha256"] if "source_original_pdf_sha256" in m else m["original_pdf_sha256"])
        self.assertEqual(OUT.read_bytes(),serialize(self.rows,old_headers(OLD)+list(EXTRA)))
        verify()
if __name__=="__main__":unittest.main()
