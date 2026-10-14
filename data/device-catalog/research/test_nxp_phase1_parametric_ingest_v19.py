import csv, tempfile, unittest
from pathlib import Path
from nxp_phase1_parametric_ingest_v19 import inspect,ImportErrorSafe,read_export

PAGE="https://www.nxp.com/products/MCX-A13X-A14X-A15X?tab=Buy_Parametric_Tab"
H=["Part","Flash (kB)","SRAM (kB)","Supply Voltage [Min to Max] (V)"]
class TestNXPParametricOfflineCandidateImport(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"fixture.csv"
    def write(self,rows):
        with self.path.open("w",encoding="utf-8",newline="") as f:
            w=csv.writer(f);w.writerow(H);w.writerows(rows)
    def test_exact_known_part_readonly_candidate_not_support(self):
        self.write([["MCXA132VFM","64","16","1.71 to 3.6"],
                    ["MCXA143VFT","128","32","1.71 to 3.6"]])
        report=inspect(self.path,PAGE)
        self.assertEqual(report["results"],{"EXACT_MATCH_REVIEW_ONLY":2})
        self.assertEqual(report["scope_admitted_exact_total"],224)
        self.assertEqual(report["source_authenticity"],"UNVERIFIED_OPERATOR_PROVIDED_FILE")
        self.assertEqual(report["automatically_admitted_rows"],0)
        self.assertEqual(report["production_mutations"],0)
        self.assertEqual(report["rows"][0]["suggested_ram"],"16")
        self.assertEqual(report["rows"][0]["suggested_vdd"],"1.71 to 3.6")
    def test_flash_mismatch_cannot_be_accepted(self):
        self.write([["MCXA132VFM","128","16","1.71 to 3.6"],
                    ["MCXA143VFT","128","", ""]])
        report=inspect(self.path,PAGE)
        self.assertEqual(report["results"]["BLOCK_FLASH_MISMATCH_OR_MISSING"],1)
        self.assertEqual(report["results"]["BLOCK_INVALID_OR_MISSING_SRAM"],1)
        self.assertFalse(any(r["suggested_ram"] for r in report["rows"]))
    def test_unrecognized_id_is_not_auto_admitted(self):
        self.write([["TOTALLYOTHER999","64","16","1.71 to 3.6"]])
        report=inspect(self.path,PAGE)
        self.assertEqual(report["results"]["NOT_IN_EXISTING_ADMITTED_SCOPE"],1)
        self.assertEqual(report["automatically_admitted_rows"],0)
    def test_duplicate_fails_closed(self):
        self.write([["MCXA132VFM","64","16",""],["MCXA132VFM","64","16",""]])
        with self.assertRaisesRegex(ImportErrorSafe,"Duplicate"):inspect(self.path,PAGE)
    def test_fake_nxp_hostname_rejected(self):
        self.write([["MCXA132VFM","64","16",""]])
        with self.assertRaisesRegex(ImportErrorSafe,"Source URL"):inspect(
            self.path,"https://www.nxp.com.evil.example/products/MCXA")
    def test_html_and_old_xls_rejected(self):
        self.path.write_text("<html><title>login</title></html>",encoding="utf-8")
        with self.assertRaises(ImportErrorSafe):read_export(self.path)
        self.path.rename(self.path.with_suffix(".xls"))
        with self.assertRaises(ImportErrorSafe):read_export(self.path.with_suffix(".xls"))
    def test_bad_or_ambiguous_headers_rejected(self):
        self.path.write_text("Part,Flash,SRAM\nA,64,16\n",encoding="utf-8")
        with self.assertRaisesRegex(ImportErrorSafe,"header"):read_export(self.path)
    def test_missing_voltage_stays_empty_not_a_guess(self):
        self.write([["MCXA132VFM","64","16","1.5 to 21.0"]])
        r=inspect(self.path,PAGE)["rows"][0]
        self.assertEqual(r["result"],"EXACT_MATCH_REVIEW_ONLY")
        self.assertEqual(r["suggested_vdd"],"")
if __name__=="__main__":unittest.main()
