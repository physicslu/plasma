import unittest
from nxp_phase1_pin_package_v15 import build,report,verify,LEDGER,csv_bytes
from nxp_phase1_datasheet_v14 import enrich as v14_enrich

class TestNXPOfficialJHI33PadReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=build()
        cls.m={x["icpn"]:x for x in cls.rows}
    def test_exact_five_and_grounded_32_plus_one(self):
        affected=[x for x in self.rows if x["peripheral_terminal_count"]]
        self.assertEqual(len(affected),5)
        for r in affected:
            self.assertEqual(r["pin_count"],"32")
            self.assertEqual(r["package"],"HVQFN33")
            self.assertEqual(r["manufacturer_commercial_package_alias"],"HVQFN32")
            self.assertEqual(r["thermal_pad_count"],"1")
            self.assertEqual(r["thermal_pad_net"],"VSS")
            self.assertEqual(r["thermal_pad_contact_number"],"33")
            self.assertEqual(r["electrical_contact_count_including_pad"],"33")
            self.assertEqual(r["package_state"],"VERIFIED")
            self.assertEqual(r["pin_count_state"],"VERIFIED")
    def test_no_collateral_silicon_or_identity_mutation(self):
        original=v14_enrich()
        old={x["icpn"]:x for x in original}
        self.assertEqual(len(self.rows),501)
        for x in self.rows:
            prior=old[x["icpn"]]
            self.assertEqual(x["identity_state"],prior["identity_state"])
            for fld in prior:
                if "JHI33" in x["icpn"] and fld in (
                  "pin_count","pin_count_state","package_state",
                  "field_evidence_note","document_page_evidence"):continue
                self.assertEqual(x[fld],prior[fld],x["icpn"]+":"+fld)
        self.assertEqual(sum(x["identity_state"]=="ADMITTED" for x in self.rows),224)
        self.assertEqual(sum(x["identity_state"]=="RESEARCH_ONLY" for x in self.rows),277)
        self.assertNotIn("openocd_software_support",self.rows[0])
    def test_coverage_reconciles_not_suppresses_history(self):
        s=report(self.rows)
        self.assertEqual(s["all"]["fields"]["package"]["CONFLICT"],0)
        self.assertEqual(s["all"]["fields"]["pin_count"]["CONFLICT"],0)
        self.assertEqual(s["all"]["fields"]["package"]["VERIFIED"],239)
        self.assertEqual(s["all"]["fields"]["pin_count"]["VERIFIED"],239)
        self.assertEqual(s["all"]["fields"]["ram"]["VERIFIED"],27)
        self.assertIsNone(s["software_qualified_exact_icpns"])
        self.assertIsNone(s["physical_hil_qualified_configurations"])
    def test_reproducible_sourced_output(self):
        self.assertEqual(LEDGER.read_bytes(),csv_bytes(self.rows))
        verify()
if __name__=="__main__":unittest.main()
