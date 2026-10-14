import unittest
from nxp_phase1_selector_v17 import (
    generate,coverage,verify,OUT,AUD,serialize,old_columns,EXTRA,AUD_COLS,read
)
from nxp_phase1_k32l2a_v16 import build as prev
class TestNXPSelectorFirstPhase1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows,cls.audit=generate()
        cls.by={x["icpn"]:x for x in cls.rows}
        cls.aud={x["icpn"]:x for x in cls.audit}
    def test_224_admitted_audit_39_exact_185_unknown_source(self):
        self.assertEqual(len(self.rows),501)
        self.assertEqual(len(self.audit),224)
        self.assertEqual(sum(a["source_row_state"]=="NO_EXACT_ROW_EVIDENCE_IN_V17" for a in self.audit),185)
        self.assertEqual(sum(a["source_row_state"]=="EXACT_INDEXED_PARAMETRIC_UNARCHIVED" for a in self.audit),13)
        self.assertEqual(sum(a["source_row_state"]=="EXACT_OFFICIAL_FACT_SHEET_FALLBACK" for a in self.audit),26)
        self.assertTrue(all(a["parametric_export_verified"]=="false" for a in self.audit))
    def test_exact_ram_pdf_vs_index_confidence(self):
        for sku,val in (("MCXC041VFG","2"),("MCXC143VFT","16"),("MCXC444VMP","32"),
                        ("MCXE245VLF","64"),("MCXE246VLL","128"),("MCXE247VLQ","256")):
            self.assertEqual(self.by[sku]["ram"],val)
            self.assertEqual(self.by[sku]["ram_state"],"VERIFIED")
        self.assertEqual(self.by["MCXC151VFM"]["ram"],"6")
        self.assertEqual(self.by["MCXC161VFM"]["ram"],"12")
        self.assertEqual(self.by["MCXC162VLF"]["ram"],"12")
        self.assertEqual(self.by["MCXW716AMFPAT"]["ram"],"128")
        self.assertEqual(self.by["MCXW716AMFPAT"]["ram_state"],"PARTIAL")
    def test_voltage_scopes_remain_partial_and_unknown(self):
        self.assertEqual(self.by["MCXC151VFM"]["working_vdd"],"1.71 to 3.6")
        self.assertEqual(self.by["MCXC151VFM"]["working_vdd_state"],"PARTIAL")
        self.assertEqual(self.by["MCXC141VFM"]["working_vdd_state"],"PARTIAL")
        self.assertEqual(self.by["MCXE245VLF"]["working_vdd_state"],"UNKNOWN")
        self.assertEqual(self.by["MCXW716CMFTAT"]["working_vdd_state"],"UNKNOWN")
        self.assertEqual(self.by["MCXC151VFM"]["vdda_state"],"UNKNOWN")
        self.assertEqual(self.by["MCXC151VFM"]["io_supply_state"],"UNKNOWN")
    def test_no_changes_outside_39_and_identity_scope(self):
        old={x["icpn"]:x for x in prev()}
        self.assertEqual(len(old),501)
        for row in self.rows:
            self.assertEqual(row["identity_state"],old[row["icpn"]]["identity_state"])
            self.assertEqual(row["phase"],"1")
            if not row["selector_evidence_method_v17"]:
                for field,val in old[row["icpn"]].items():self.assertEqual(row[field],val,row["icpn"]+" "+field)
    def test_metrics_and_replay(self):
        x=coverage(self.rows,self.audit)
        self.assertEqual(x["current_admitted_field_summary"]["fields"]["ram"],
            {"VERIFIED":42,"PARTIAL":13,"UNKNOWN":169,"CONFLICT":0})
        self.assertEqual(x["current_admitted_field_summary"]["fields"]["working_vdd"],
            {"VERIFIED":16,"PARTIAL":27,"UNKNOWN":181,"CONFLICT":0})
        self.assertIsNone(x["software_programming_supported_new"])
        self.assertEqual(OUT.read_bytes(),serialize(self.rows,old_columns()+list(EXTRA)))
        self.assertEqual(AUD.read_bytes(),serialize(self.audit,list(AUD_COLS)))
        verify()
if __name__=="__main__":unittest.main()
