import unittest
from nxp_phase1_information_v13 import build,coverage,csv_bytes,LEDGER,verify

class TestPhase1InformationOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=build()
        cls.by={r["icpn"]:r for r in cls.rows}

    def test_phase_only_identity_and_independent_denominators(self):
        self.assertEqual(len(self.rows),501)
        self.assertEqual(coverage(self.rows)["existing_production_identity"]["exact_icpn_records"],224)
        self.assertEqual(coverage(self.rows)["pending_manufacturer_research"]["exact_icpn_records"],277)
        self.assertTrue(all(x["phase"]=="1" for x in self.rows))
    def test_unknown_ram_voltage_never_inferred(self):
        kl=self.by["MKL25Z128VFM4"]
        self.assertEqual(kl["flash"],"128 KiB")
        self.assertEqual(kl["ram_state"],"UNKNOWN")
        self.assertEqual(kl["working_vdd_state"],"UNKNOWN")
        self.assertEqual(kl["io_supply_state"],"UNKNOWN")
        self.assertEqual(kl["vdda_state"],"UNKNOWN")
    def test_unadmitted_exact_id_stays_research_not_supported(self):
        row=self.by["LPC844M201JBD48E"]
        self.assertEqual(row["identity_state"],"RESEARCH_ONLY")
        self.assertEqual(row["package_state"],"UNKNOWN")
        self.assertEqual(row["ram_state"],"UNKNOWN")
        self.assertNotIn("software_support_state",row)
        self.assertNotIn("hardware_ready",row)
    def test_sourced_partials_preserve_original_units(self):
        part=self.by["KW45Z41052AFPBT"]
        self.assertEqual(part["package_state"],"PARTIAL")
        self.assertEqual(part["flash"],"512")
        self.assertEqual(part["flash_unit"],"ORIGINAL_V8_LEGACY_KB_FIELD")
        self.assertEqual(part["working_vdd"],"1.8 to 3.6")
        self.assertEqual(part["source_observation_sha256"].__len__(),64)
    def test_reproducibility_and_no_unknown_to_zero(self):
        self.assertEqual(LEDGER.read_bytes(),csv_bytes(self.rows))
        for row in self.rows:
            for f in ("ram","io_supply","vdda"):
                if row[f+"_state"]=="UNKNOWN":
                    self.assertEqual(row[f],"")
        verify()
if __name__=="__main__":unittest.main()
