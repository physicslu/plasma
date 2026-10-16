"""NXP Phase 1 exact material 12NC/product group identity negative gates."""
from __future__ import annotations
import copy
import unittest
from unittest.mock import patch
import nxp_phase1_official_lpc_25_v1 as unit
import nxp_phase1_funnel_audit_v1 as baseline
import nxp_phase1_lpc11u_lpc83x_11_v1 as prior

class NxpOfficialLpc25Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=unit.load()
        cls.reverse={r["icpn_observation"] for r in baseline.read("reverse")}
        cls.previous={r["icpn"] for r in baseline.read("legacy")
                      if r["identity_state"]=="ADMITTED"}
        cls.previous|={r["icpn"] for r in baseline.read("lpc82x")}
        cls.previous|={r["icpn"] for r in baseline.read("lpc81x")}
        cls.previous|={r["icpn"] for r in prior.load()}

    def check(self, rows):
        return unit.validate(rows,self.reverse,self.previous)

    def changed(self,key,value,which="LPC1758FBD80"):
        rows=copy.deepcopy(self.rows)
        next(r for r in rows if r["icpn"]==which)[key]=value
        return rows

    def test_exact_s1_counts(self):
        r=unit.build()
        self.assertEqual((r["source_universe_unique_icpns"],
                          r["phase1_identified_s1"],
                          r["phase1_identity_review_backlog"]),(571,276,295))
        self.assertEqual(r["new_reverse_wave_crosswalk"],20)
        self.assertEqual(r["new_official_family_variants_outside_566"],5)
        self.assertEqual(len(r["remaining_reverse_wave_icpns"]),18)
        self.assertEqual(sum(r["backlog_components"].values()),295)
        self.assertIsNone(r["phase2_supported_s2"])
        self.assertIsNone(r["phase3_hil_passed_s3"])

    def test_all_exact_materials(self):
        self.assertEqual(len(self.check(copy.deepcopy(self.rows))),25)

    def test_reject_fabricated_suffix(self):
        with self.assertRaisesRegex(ValueError,"material name"):
            self.check(self.changed("icpn","LPC1758FBD80FAKE"))

    def test_reject_duplicate_material(self):
        r=copy.deepcopy(self.rows);r[1]["icpn"]=r[0]["icpn"]
        with self.assertRaisesRegex(ValueError,"material name"):
            self.check(r)

    def test_reject_12nc_mutation(self):
        with self.assertRaisesRegex(ValueError,"source mismatch"):
            self.check(self.changed("manufacturer_12nc","935200000000"))

    def test_reject_invented_lifecycle_or_source(self):
        for field,value in (
            ("material_lifecycle_observed","UNKNOWN"),
            ("official_package_quality_url","https://www.nxp.com/products/WRONG"),
            ("manufacturer_family","LPC800"),
            ("pin_count","999"),
            ("manufacturer_model_lead","LPC1114"),
        ):
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.check(self.changed(field,value))

    def test_reject_551_declaration_elision(self):
        with self.assertRaisesRegex(ValueError,"source mismatch"):
            self.check(self.changed("material_declaration_display","LPC1758FBD80"))

    def test_reject_research_to_supported_production_hil(self):
        for field in ("phase2_software_supported","production_admitted",
                      "physical_hil_passed"):
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"false"):
                self.check(self.changed(field,"true"))

    def test_reject_fabricated_manufacturer_html_custody(self):
        for field,value in (
            ("raw_original_official_html_archived","true"),
            ("official_page_original_bytes_sha256","f"*64),
        ):
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"false"):
                self.check(self.changed(field,value))

    def test_reject_non_wave_variant_promoted_to_historical(self):
        with self.assertRaisesRegex(ValueError,"mislabeled"):
            self.check(self.changed("original_reverse_wave_icpn","true",
                                    which="LPC1758FBD80Y"))

    def test_reject_wave_record_reclassified_new_without_evidence(self):
        with self.assertRaisesRegex(ValueError,"not traceable"):
            self.check(self.changed("original_reverse_wave_icpn","false"))

    def test_reject_duplicate_existing_s1_identity(self):
        with self.assertRaisesRegex(ValueError,"duplicates"):
            unit.validate(copy.deepcopy(self.rows),self.reverse,
                          self.previous|{"LPC1788FBD208"})

    def test_reject_transcription_git_blob_drift(self):
        with patch.object(unit,"GIT_BLOB","0"*40):
            with self.assertRaisesRegex(ValueError,"Git blob drift"):
                unit.load()

if __name__=="__main__":
    unittest.main(verbosity=2)
