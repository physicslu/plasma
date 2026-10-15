"""Negative evidence gates: NXP LPC11U/LPC83x 11 exact official materials."""
from __future__ import annotations
import copy
import unittest
from unittest.mock import patch
import nxp_phase1_lpc11u_lpc83x_11_v1 as cohort
import nxp_phase1_funnel_audit_v1 as prior

class NxpLpc11uLpc83xPhase1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=cohort.load()
        cls.old={r["icpn"] for r in prior.read("legacy")}
        cls.wave={r["icpn_observation"] for r in prior.read("reverse")}

    def check(self, rows):
        return cohort.verify_rows(rows,self.old,self.wave)

    def test_complete_phase1_funnel_snapshot(self):
        result=cohort.build()
        self.assertEqual((result["phase1_identified_s1"],
                          result["phase1_information_complete_s1_complete"],
                          result["phase1_identity_review_backlog"]), (251,0,315))
        self.assertEqual(result["official_new_exact_materials"],11)
        self.assertEqual(result["production_admission_changes"],0)
        self.assertEqual(result["public_catalog_or_ic_selector_changes"],0)
        self.assertIsNone(result["phase2_supported_s2"])
        self.assertIsNone(result["phase3_hil_passed_s3"])

    def test_crosswalk_exact_materials(self):
        self.assertEqual(len(self.check(copy.deepcopy(self.rows))),11)

    def test_reject_invented_suffix_and_duplicate(self):
        x=copy.deepcopy(self.rows);x[0]["icpn"]+="FAKE"
        with self.assertRaisesRegex(ValueError,"fabricated"):self.check(x)
        x=copy.deepcopy(self.rows);x[0]["icpn"]=x[1]["icpn"]
        with self.assertRaises(ValueError):self.check(x)

    def test_reject_12nc_or_ordering_base_mismatch(self):
        for col,val in [("manufacturer_12nc","935300000000"),
                        ("manufacturer_base","LPC11U24FHI33/401")]:
            x=copy.deepcopy(self.rows);x[0][col]=val
            with self.subTest(col=col),self.assertRaisesRegex(ValueError,"mismatch"):self.check(x)

    def test_reject_electrical_or_flash_inference(self):
        for col,val in [("working_vdd_min_v","1.8"),
                        ("flash_kb","512"),("sram_kb","32")]:
            x=copy.deepcopy(self.rows)
            idx=next(i for i,r in enumerate(x) if r["icpn"]=="LPC11U68JBD64Y")
            x[idx][col]=val
            with self.subTest(col=col),self.assertRaisesRegex(ValueError,"mismatch"):self.check(x)

    def test_reject_datasheet_exposed_pad_conflation(self):
        x=copy.deepcopy(self.rows)
        row=next(r for r in x if r["icpn"]=="LPC834M101FHI33Y")
        row["datasheet_package"]="HVQFN32"
        with self.assertRaisesRegex(ValueError,"mismatch"):self.check(x)

    def test_reject_unproven_original_bytes_custody_or_qualification(self):
        for field in ("original_datasheet_pdf_bytes_archived",
                      "original_manufacturer_html_bytes_archived",
                      "exact_silicon_revision_verified","openocd_programming_qualified",
                      "production_admitted","physical_hil_verified"):
            x=copy.deepcopy(self.rows);x[0][field]="true"
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"falsified"):self.check(x)

    def test_reject_wrong_original_page_or_date(self):
        for field,value in [
            ("official_exact_material_page","https://www.nxp.com/products/OTHER"),
            ("observed_on","2050-01-01"),
            ("datasheet_url","https://www.nxp.com/docs/en/data-sheet/LPC82X.pdf"),
        ]:
            x=copy.deepcopy(self.rows);x[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.check(x)

    def test_reject_nonreverse_discovered_material(self):
        with self.assertRaisesRegex(ValueError,"reverse wave"):
            self.check(copy.deepcopy(self.rows)) if "NOT_ACTUAL" in self.wave else (
                cohort.verify_rows(copy.deepcopy(self.rows),self.old,set()))

    def test_reject_plasma_transcription_blob_drift(self):
        with patch.object(cohort,"SOURCE_GIT_BLOB","0"*40):
            with self.assertRaisesRegex(ValueError,"Git blob mismatch"):cohort.load()

    def test_distinct_usb_sram_topology_retained(self):
        x=copy.deepcopy(self.rows);x[0]["sram_topology_note"]="SRAM 8 kB"
        with self.assertRaisesRegex(ValueError,"separate USB memory"):self.check(x)

if __name__=="__main__":unittest.main(verbosity=2)
