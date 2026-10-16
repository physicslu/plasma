"""NXP ADR-0002 Catalog Level canonical negative and regression gates."""
from __future__ import annotations
import copy
import unittest
from unittest.mock import patch
import nxp_adr0002_phase1_phase2_canonical_v1 as subject

class TestNxpCanonicalCatalogLevels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=subject.build()
        cls.by_part={r["icpn"]:r for r in cls.rows}

    def test_level0_297_and_level1_candidate_states(self):
        p=subject.report(self.rows)
        self.assertEqual(p["catalog_level_0_or_higher_discovered"],297)
        self.assertEqual(p["catalog_level_0_only"],269)
        self.assertEqual(p["catalog_level_1_programming_candidate"],28)
        self.assertEqual(p["information_complete"],0)
        self.assertEqual(p["programming_state_counts"],{
            "UNKNOWN":269,"CANDIDATE":28,"SUPPORTED":0,"UNSUPPORTED":0})
        self.assertEqual(p["base_alias_pending"],212)
        self.assertEqual(p["new_original_vendor_bytes_not_archived"],73)

    def test_exact_nxp_icpn_lpc11u68_remains_level0_without_route(self):
        r=self.by_part["LPC11U68JBD48E"]
        self.assertEqual(r["identity_state"],"IDENTIFIED")
        self.assertEqual(r["catalog_level"],0)
        self.assertEqual(r["catalog_level_state"],"DISCOVERED")
        self.assertEqual(r["programming_state"],"UNKNOWN")
        self.assertEqual(r["base_device"],"LPC11U68JBD48")
        self.assertIsNone(r["programming_profile_id"])
        self.assertEqual(r["compatibility_state"],"NOT_AUDITED")

    def test_kl25_and_k32l2_source_only_candidates(self):
        rows=[r for r in self.rows if r["programming_state"]=="CANDIDATE"]
        self.assertEqual(len(rows),28)
        self.assertEqual(sum(r["target_cfg"]=="tcl/target/kl25.cfg" for r in rows),12)
        self.assertEqual(sum(r["driver"]=="kinetis" and not r["target_cfg"] for r in rows),16)
        self.assertTrue(all(r["operations"]["verify"]=="NOT_QUALIFIED" for r in rows))

    def test_catalog_levels_never_include_unverified_research_only_277(self):
        legacy=subject.read_source("legacy")
        admitted={r["icpn"] for r in legacy if r["identity_state"]=="ADMITTED"}
        disallowed={r["icpn"] for r in legacy if r["identity_state"]=="RESEARCH_ONLY"}
        self.assertEqual(len(disallowed),277)
        self.assertTrue(admitted.issubset(self.by_part))
        self.assertFalse(disallowed.intersection(self.by_part))
        self.assertEqual(len(set(self.by_part)-admitted),73)

    def test_reject_fake_programmable_promotion(self):
        rows=copy.deepcopy(self.rows)
        rows[0]["programming_state"]="SUPPORTED"
        with self.assertRaisesRegex(ValueError,"cannot promote"):
            subject.validate(rows)

    def test_reject_fake_software_programming_profile(self):
        rows=copy.deepcopy(self.rows)
        rows[0]["programming_profile_id"]="nxp-unsupported-invented-v1"
        with self.assertRaisesRegex(ValueError,"fabricated"):
            subject.validate(rows)

    def test_reject_fake_flash_or_operation_qualification(self):
        for field,value in (
            ("flash_geometry","VERIFIED"),
            ("security","VERIFIED"),
            ("silicon_revision","VERIFIED"),
        ):
            rows=copy.deepcopy(self.rows)
            rows[0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"fabricated"):
                subject.validate(rows)
        rows=copy.deepcopy(self.rows)
        rows[0]["operations"]["erase"]="SUPPORTED"
        with self.assertRaisesRegex(ValueError,"fabricated"):
            subject.validate(rows)

    def test_reject_identity_loss_or_duplicate(self):
        rows=copy.deepcopy(self.rows)
        rows[0]["identity_state"]="RESEARCH_ONLY"
        with self.assertRaisesRegex(ValueError,"illegal"):
            subject.validate(rows)
        rows=copy.deepcopy(self.rows)
        rows[0]["icpn"]=rows[1]["icpn"]
        with self.assertRaisesRegex(ValueError,"distinct"):
            subject.validate(rows)

    def test_unreviewed_historical_priority_never_public_catalog_state(self):
        row=self.by_part["LPC11U68JBD48E"]
        self.assertNotIn("research_priority",row)
        # NXP may legitimately use /P1K in the official order code. The
        # obsolete research priority field, not those literal characters,
        # must be absent from the canonical Catalog Level schema.
        for row in self.rows:
            self.assertNotIn("research_priority",row)

    def test_no_fake_level3_hil(self):
        rows=copy.deepcopy(self.rows)
        rows[0]["compatibility_state"]="PASSED"
        with self.assertRaisesRegex(ValueError,"fabricated"):
            subject.validate(rows)

    def test_approved_nxp_web_and_official_material_git_source_lock(self):
        with patch.dict(subject.SRC, {"81":("nxp-8-lpc81x-phase1-official-material-v1.csv",
                                            "0"*40,8)}):
            with self.assertRaisesRegex(ValueError,"source bytes changed"):
                subject.read_source("81")

    def test_adr_latest_semantics_and_openocd_release_pin(self):
        policy=subject.authority()
        self.assertEqual(policy["version"],"0.12.0")
        self.assertEqual(policy["source_commit"],subject.COMMIT)

if __name__ == "__main__":
    unittest.main(verbosity=2)
