import unittest
from nxp_phase1_k32l2b_v22 import build,coverage,verify,LEDGER,to_csv,original_cols,PREV,EXTRA
from nxp_phase1_four_doc_v21 import build as old_build
class TestNXPK32L2BStrictGroupEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=build()
        cls.by={r["icpn"]:r for r in cls.rows}
    def test_group_flash_and_sram_12_partial_not_verified(self):
        for prefix,flash in (("11","64"),("21","128"),("31","256")):
            for suffix in ("FM","FT","LH","MP"):
                x=self.by["K32L2B"+prefix+"V"+suffix+"0A"]
                self.assertEqual(x["ram"],"32")
                self.assertEqual(x["ram_state"],"PARTIAL")
                self.assertEqual(x["flash"].split()[0],flash)
                self.assertEqual(x["k32l2b_family_pattern_v22"],"K32L2B"+prefix+"Vxx0A")
    def test_no_claim_of_exact_row_or_archived_pdf(self):
        subset=[x for x in self.rows if x["k32l2b_evidence_limit_v22"]]
        self.assertEqual(len(subset),12)
        self.assertTrue(all("not_single_exact_ram_row" in x["k32l2b_evidence_limit_v22"] for x in subset))
        self.assertTrue(all(x["identity_state"]=="ADMITTED" for x in subset))
    def test_all_other_fields_original(self):
        previous={x["icpn"]:x for x in old_build()}
        for x in self.rows:
            r=previous[x["icpn"]]
            self.assertEqual(x["identity_state"],r["identity_state"])
            self.assertEqual(x["phase"],"1")
            for k in ("flash","package","pin_count","working_vdd","io_supply","vdda"):
                self.assertEqual(x[k],r[k])
        self.assertEqual(len(self.rows),501)
    def test_admitted_coverage_and_replay(self):
        s=coverage(self.rows)
        self.assertEqual(s["current_admitted"]["fields"]["ram"],
          {"VERIFIED":199,"PARTIAL":25,"UNKNOWN":0,"CONFLICT":0})
        self.assertEqual(s["all_501"]["fields"]["ram"],
          {"VERIFIED":214,"PARTIAL":73,"UNKNOWN":214,"CONFLICT":0})
        self.assertEqual(LEDGER.read_bytes(),to_csv(self.rows,original_cols(PREV)+list(EXTRA)))
        verify()
if __name__=="__main__":unittest.main()
