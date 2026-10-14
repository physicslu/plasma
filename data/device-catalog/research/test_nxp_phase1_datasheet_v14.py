import unittest
from nxp_phase1_datasheet_v14 import enrich,metrics,to_csv,CSV,validate

class OfficialNXPInformationPhase1V14(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=enrich()
        cls.by={r["icpn"]:r for r in cls.rows}
    def test_exact_kl25_datasheet_sram_and_electrical(self):
        self.assertEqual(self.by["MKL25Z128VFM4"]["ram"],"16")
        self.assertEqual(self.by["MKL25Z64VFT4"]["ram"],"8")
        self.assertEqual(self.by["MKL25Z32VLK4"]["ram"],"4")
        self.assertEqual(self.by["MKL25Z128VFM4"]["working_vdd"],"1.71 to 3.6")
        self.assertIn("|VDD-VDDA|",self.by["MKL25Z128VFM4"]["vdda"])
    def test_all_15_exact_lpc_and_package_conflicts(self):
        self.assertEqual(self.by["LPC844M201JBD48E"]["ram"],"8")
        self.assertEqual(self.by["LPC845M301JHI48E"]["ram"],"16")
        self.assertEqual(self.by["LPC844M201JBD48E"]["base_device"],"LPC844M201")
        self.assertEqual(self.by["LPC845M301JHI48E"]["base_device"],"LPC845M301")
        self.assertEqual(self.by["LPC845M301JHI48K"]["package"],"HVQFN48")
        for sku in ("LPC844M201JHI33E","LPC844M201JHI33Y",
                    "LPC845M301JHI33E","LPC845M301JHI33K","LPC845M301JHI33Y"):
            self.assertEqual(self.by[sku]["package_state"],"CONFLICT")
            self.assertEqual(self.by[sku]["pin_count_state"],"CONFLICT")
            self.assertEqual(self.by[sku]["pin_count"],"33")
    def test_phase_boundary_no_admission_propagation(self):
        self.assertEqual(len(self.rows),501)
        self.assertEqual(sum(x["identity_state"]=="ADMITTED" for x in self.rows),224)
        self.assertEqual(sum(x["identity_state"]=="RESEARCH_ONLY" for x in self.rows),277)
        self.assertEqual(self.by["LPC844M201JBD48E"]["identity_state"],"RESEARCH_ONLY")
        self.assertTrue(all(not x["original_document_sha256"] for x in self.rows))
        self.assertTrue(all(x["phase"]=="1" for x in self.rows))
        self.assertTrue(all(not x["io_supply"] for x in self.rows))
    def test_coverage_and_non_inferred_analog_voltage(self):
        s=metrics(self.rows)
        self.assertEqual(s["enriched_source_attested_exact"],27)
        self.assertEqual(s["all"]["fields"]["ram"]["VERIFIED"],27)
        self.assertEqual(s["all"]["fields"]["ram"]["PARTIAL"],48)
        self.assertEqual(s["all"]["fields"]["working_vdd"]["VERIFIED"],27)
        self.assertEqual(s["all"]["fields"]["vdda"]["VERIFIED"],12)
        self.assertEqual(s["all"]["fields"]["package"]["CONFLICT"],5)
        self.assertEqual(self.by["LPC845M301JBD64E"]["vdda_state"],"UNKNOWN")
        self.assertIsNone(s["software_qualified_exact_icpns"])
    def test_replay(self):
        self.assertEqual(CSV.read_bytes(),to_csv(self.rows))
        validate()
if __name__=="__main__":unittest.main()
