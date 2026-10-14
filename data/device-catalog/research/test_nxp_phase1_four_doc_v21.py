import unittest
from nxp_phase1_four_doc_v21 import build,stats,verify,LEDGER,csv_bytes,columns,PREV,EXTRA
from nxp_phase1_mcxa3fs_v20 import build as old_build
class TestNXPOfficialFourDocumentsV21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=build()
        cls.by={x["icpn"]:x for x in cls.rows}
    def test_mcx_a2_exact_flash_and_sram(self):
        for sku,ram in (("MCXA255VLH","128"),("MCXA256VPN","256"),
                        ("MCXA265VLL","128"),("MCXA266VLQ","256")):
            self.assertEqual(self.by[sku]["ram"],ram)
            self.assertEqual(self.by[sku]["ram_state"],"VERIFIED")
    def test_e31_and_n23_n24_n5_n9_distinct_sram(self):
        for sku,ram,ecc in (
          ("MCXE315MLF","64",""),("MCXE316MPA","128",""),
          ("MCXE317MPA","192",""),("MCXE31BMPB","512",""),
          ("MCXN235VKLT","192","160"),("MCXN236VPBT","352","288"),
          ("MCXN946VKLT","352","288"),("MCXN947VPBT","512","416"),
          ("MCXN536VDFT","352","288"),("MCXN547VDFT","512","416"),
          ("MCXN247VKLT","512","416")):
            self.assertEqual(self.by[sku]["ram"],ram)
            self.assertEqual(self.by[sku]["sram_ecc_usable_capacity_kb_v21"],ecc)
    def test_preexisting_research_only_not_promoted(self):
        r=self.by["MCXA255VLL"]
        self.assertEqual(r["identity_state"],"RESEARCH_ONLY")
        self.assertEqual(r["ram_state"],"UNKNOWN")
        self.assertFalse(r["ram"])
    def test_every_other_field_preserved(self):
        old={x["icpn"]:x for x in old_build()}
        self.assertEqual(len(self.rows),501)
        for r in self.rows:
            previous=old[r["icpn"]]
            self.assertEqual(r["identity_state"],previous["identity_state"])
            for k in ("working_vdd","io_supply","vdda","package","pin_count","phase"):
                self.assertEqual(r[k],previous[k])
    def test_metrics_and_replay(self):
        m=stats(self.rows)
        self.assertEqual(m["admitted_after"]["fields"]["ram"],
            {"VERIFIED":199,"PARTIAL":13,"UNKNOWN":12,"CONFLICT":0})
        self.assertEqual(m["all_501"]["fields"]["ram"],
            {"VERIFIED":214,"PARTIAL":61,"UNKNOWN":226,"CONFLICT":0})
        self.assertIsNone(m["software_programming_qualified"])
        self.assertEqual(LEDGER.read_bytes(),csv_bytes(self.rows,columns(PREV)+list(EXTRA)))
        verify()
if __name__=="__main__":unittest.main()
