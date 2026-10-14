import csv, tempfile, unittest, zipfile
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
    def test_xlsx_shared_strings_actual_openxml(self):
        """Small synthetic XLSX fixture tests the advertised built-in XML reader."""
        file=self.path.with_suffix(".xlsx")
        ns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        shared=["Part","Flash (kB)","SRAM (kB)",
                "Supply Voltage [Min to Max] (V)","MCXA132VFM","1.71 to 3.6"]
        si=''.join('<si><t>'+v+'</t></si>' for v in shared)
        xshared='<sst xmlns="'+ns+'" count="6" uniqueCount="6">'+si+'</sst>'
        sheet=(
          '<worksheet xmlns="'+ns+'"><sheetData>'
          '<row r="1"><c r="A1" t="s"><v>0</v></c>'
          '<c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c>'
          '<c r="D1" t="s"><v>3</v></c></row>'
          '<row r="2"><c r="A2" t="s"><v>4</v></c>'
          '<c r="B2"><v>64</v></c><c r="C2"><v>16</v></c>'
          '<c r="D2" t="s"><v>5</v></c></row>'
          '</sheetData></worksheet>'
        )
        with zipfile.ZipFile(file,"w",compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml",
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            z.writestr("xl/workbook.xml",'<workbook xmlns="'+ns+'"/>')
            z.writestr("xl/sharedStrings.xml",xshared)
            z.writestr("xl/worksheets/sheet1.xml",sheet)
        report=inspect(file,PAGE)
        self.assertEqual(report["source_file_type"],".xlsx")
        self.assertEqual(report["rows"][0]["result"],"EXACT_MATCH_REVIEW_ONLY")
        self.assertEqual(report["rows"][0]["suggested_ram"],"16")
        self.assertEqual(report["rows"][0]["suggested_vdd"],"1.71 to 3.6")
        self.assertEqual(report["automatically_admitted_rows"],0)
    def test_xlsx_formula_cells_fail_closed(self):
        file=self.path.with_suffix(".xlsx")
        ns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        sheet='<worksheet xmlns="'+ns+'"><sheetData><row r="1"><c r="A1"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>'
        with zipfile.ZipFile(file,"w",compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml","x")
            z.writestr("xl/workbook.xml",'<workbook xmlns="'+ns+'"/>')
            z.writestr("xl/worksheets/sheet1.xml",sheet)
        with self.assertRaisesRegex(ImportErrorSafe,"Formula cells"):read_export(file)
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
