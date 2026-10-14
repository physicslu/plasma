import unittest
from nxp_phase1_mcxa_rails_v23 import build,stats,verify,LEDGER,dump,header,BEFORE,EXTRA
from nxp_phase1_k32l2b_v22 import build as prior
class TestNXPMCxaWorkingRails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=build()
        cls.by={r["icpn"]:r for r in cls.rows}
    def test_exact_part_families_verified_normal_vdd_vdda(self):
        for sku in ("MCXA132VFM","MCXA143VFT","MCXA145VLL","MCXA155VFT",
                    "MCXA174VLH","MCXA185VPN","MCXA255VPN","MCXA266VLQ",
                    "MCXA343VFM","MCXA344VLL","MCXA345VLH","MCXA366VPN"):
            x=self.by[sku]
            self.assertEqual(x["working_vdd"],"1.71 to 3.6")
            self.assertEqual(x["working_vdd_state"],"VERIFIED")
            self.assertEqual(x["vdda_state"],"VERIFIED")
            self.assertIn("VDD_ANA",x["vdda"])
            self.assertIn("POR",x["vdda"])
            self.assertEqual(x["io_supply_state"],"VERIFIED")
            self.assertTrue(x["operating_source_uri_v23"].startswith("https://www.nxp.com/"))
    def test_p3_1v2_is_distinct_from_general_vdd_and_usb(self):
        x=self.by["MCXA145VLL"]
        self.assertIn("1.14 to 1.32 V",x["io_supply"])
        self.assertIn("VDD_P3",x["io_supply"])
        self.assertEqual(x["io_rail_mode_v23"],"VDD_P3_DUAL_MODE")
        self.assertEqual(x["working_vdd"],"1.71 to 3.6")
        self.assertEqual(x["usb_analog_supply_v23"],"3.0 to 3.6 V")
        y=self.by["MCXA343VFM"]
        self.assertEqual(y["io_rail_mode_v23"],"VDD_SHARED")
        self.assertNotIn("1.14",y["io_supply"])
        self.assertEqual(y["usb_analog_supply_v23"],"")
    def test_existing_identities_and_other_fields_unchanged(self):
        before={r["icpn"]:r for r in prior()}
        self.assertEqual(len(self.rows),len(before))
        for x in self.rows:
            b=before[x["icpn"]]
            self.assertEqual(x["identity_state"],b["identity_state"])
            for k in ("base_device","flash","ram","ram_state","package","pin_count","temperature","phase"):
                self.assertEqual(x[k],b[k],x["icpn"]+":"+k)
            if x["identity_state"]=="RESEARCH_ONLY":
                for k in ("working_vdd","vdda","io_supply"):
                    self.assertEqual(x[k],b[k])
    def test_denom_and_replay(self):
        s=stats(self.rows)
        self.assertEqual(s["current_admitted"]["fields"]["working_vdd"],
            {"VERIFIED":135,"PARTIAL":27,"UNKNOWN":62,"CONFLICT":0})
        self.assertEqual(s["current_admitted"]["fields"]["vdda"],
            {"VERIFIED":135,"PARTIAL":0,"UNKNOWN":89,"CONFLICT":0})
        self.assertEqual(s["current_admitted"]["fields"]["io_supply"],
            {"VERIFIED":119,"PARTIAL":0,"UNKNOWN":105,"CONFLICT":0})
        self.assertEqual(s["explicit_independent_vdd_p3_1v2_modes"],26)
        self.assertEqual(LEDGER.read_bytes(),dump(self.rows,header(BEFORE)+list(EXTRA)))
        self.assertIsNone(s["software_flash_programming_supported"])
        verify()
if __name__=="__main__":unittest.main()
