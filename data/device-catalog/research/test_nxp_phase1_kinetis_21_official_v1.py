"""NXP Kinetis 21 official materials: Phase1 source & safety negative tests."""
from __future__ import annotations
import copy
import unittest
from unittest.mock import patch

import nxp_phase1_kinetis_21_official_v1 as unit
import nxp_phase1_funnel_audit_v1 as root
import nxp_phase1_lpc11u_lpc83x_11_v1 as prev11
import nxp_phase1_official_lpc_25_v1 as prev25

class NxpKinetis21OfficialMaterialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=unit.load()
        cls.reverse={r["icpn_observation"] for r in root.read("reverse")}
        cls.previous={r["icpn"] for r in root.read("legacy")
                      if r["identity_state"]=="ADMITTED"}
        cls.previous|={r["icpn"] for r in root.read("lpc81x")}
        cls.previous|={r["icpn"] for r in root.read("lpc82x")}
        cls.previous|={r["icpn"] for r in prev11.load()}
        cls.previous|={r["icpn"] for r in prev25.load()}

    def verify(self, rows):
        return unit.verify_materials(rows,self.previous,self.reverse)

    def tamper(self,key,value,name="MK40DN512VLK10"):
        rows=copy.deepcopy(self.rows)
        next(r for r in rows if r["icpn"]==name)[key]=value
        return rows

    def test_phase1_snapshot(self):
        x=unit.build()
        self.assertEqual((x["phase1_identified_s1"],
                          x["unique_source_observed_or_candidate_icpns"],
                          x["phase1_identity_review_backlog"]),(297,576,279))
        self.assertEqual(x["new_from_previous_cfg_reverse_leads"],16)
        self.assertEqual(x["new_from_same_official_family_products"],5)
        self.assertEqual(x["phase1_information_complete_s1_complete"],0)
        self.assertEqual(sum(x["phase1_backlog_components"].values()),279)
        self.assertEqual(len(x["pending_original_cfg_reverse_icpns"]),2)
        self.assertIsNone(x["phase2_openocd_supported_s2"])
        self.assertIsNone(x["phase3_hil_s3"])
        self.assertFalse(x["production_catalog_ic_selector_changes"])

    def test_all_21_official_commercial_exact_materials(self):
        self.assertEqual(len(self.verify(copy.deepcopy(self.rows))),21)

    def test_reject_invented_material_suffix(self):
        with self.assertRaisesRegex(ValueError,"commercial exact ICPNs"):
            self.verify(self.tamper("icpn","MK40DN512VLK10XX"))

    def test_reject_duplicate_source_material(self):
        d=copy.deepcopy(self.rows)
        d[0]["icpn"]=d[1]["icpn"]
        with self.assertRaisesRegex(ValueError,"commercial exact ICPNs"):
            self.verify(d)

    def test_reject_12nc_or_base_rewrite(self):
        for key,val in (("manufacturer_12nc","935300000000"),
                        ("base_device","MK40DN256"),
                        ("manufacturer_family","K60"),
                        ("package","LQFP64"),
                        ("package_terminal_count","64")):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"mismatch"):
                self.verify(self.tamper(key,val))

    def test_reject_source_material_lifecycle_conflation(self):
        for key,val in (("manufacturer_material_status","UNKNOWN"),
                        ("official_material_product_url","https://www.nxp.com/products/KL4x"),
                        ("manufacturer","ST")):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"provenance"):
                self.verify(self.tamper(key,val))

    def test_reject_fake_specification_and_units(self):
        for key,val in (("flash_kb","256"),("ram_kb","64"),
                        ("working_vdd_min_v","2.4"),
                        ("temperature_max_c","125")):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"mismatch"):
                self.verify(self.tamper(key,val))

    def test_preserve_k60_reel_material_identity(self):
        self.assertIn("MK60DN512VMC10R",unit.MATERIALS)
        self.assertIn("MK60DN512VLL10R",unit.MATERIALS)
        d=self.tamper("manufacturer_12nc","935323339557",
                      "MK60DN512VLL10R")
        with self.assertRaises(ValueError):self.verify(d)

    def test_reject_source_custody_fabrication(self):
        for key in ("original_official_html_archived",
                    "original_official_pdf_archived"):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"falsely promoted"):
                self.verify(self.tamper(key,"true"))

    def test_reject_phase1_information_complete_without_rails(self):
        with self.assertRaisesRegex(ValueError,"falsely promoted"):
            self.verify(self.tamper("phase1_information_complete","true"))

    def test_reject_phase2_production_hil_promotion(self):
        for key in ("phase2_programming_supported","production_admitted",
                    "phase3_hil_passed"):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"falsely promoted"):
                self.verify(self.tamper(key,"true"))

    def test_reject_k43_promotion_as_individual_cfg_backed(self):
        with self.assertRaisesRegex(ValueError,"additional official family"):
            self.verify(self.tamper("prior_reverse_wave_member","true",
                                  "MKL43Z256VMP4"))

    def test_reject_reverse_observation_becomes_untraced(self):
        with self.assertRaisesRegex(ValueError,"reverse family"):
            self.verify(self.tamper("prior_reverse_wave_member","false",
                                  "MKL46Z256VMP4"))

    def test_existing_s1_must_not_be_duplicated(self):
        with self.assertRaisesRegex(ValueError,"overlaps approved"):
            unit.verify_materials(copy.deepcopy(self.rows),
                                  self.previous|{"MKL46Z128VLH4"},self.reverse)

    def test_git_blob_source_drift_fails_closed(self):
        with patch.object(unit,"SOURCE_GIT_BLOB","0"*40):
            with self.assertRaisesRegex(ValueError,"Git blob drift"):
                unit.load()

if __name__=="__main__":
    unittest.main(verbosity=2)
