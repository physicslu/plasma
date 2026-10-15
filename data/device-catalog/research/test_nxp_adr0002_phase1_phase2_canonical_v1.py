"""NXP ADR-0002 canonical Phase 1/2 negative and regression gates."""
from __future__ import annotations
import copy
import unittest
from unittest.mock import patch
import nxp_adr0002_phase1_phase2_canonical_v1 as subject

class TestNxpCanonicalPhase1Phase2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=subject.build()
        cls.by_part={r["icpn"]:r for r in cls.rows}

    def test_phase1_297_and_phase2_true_states(self):
        p=subject.report(self.rows)
        self.assertEqual(p["phase1_identified"],297)
        self.assertEqual(p["phase1_information_complete"],0)
        self.assertEqual(p["phase2_states"],{
            "UNKNOWN":269,"CANDIDATE":28,"SUPPORTED":0,"UNSUPPORTED":0})
        self.assertEqual(p["phase1_base_alias_pending"],212)
        self.assertEqual(p["phase1_new_original_vendor_bytes_not_archived"],73)

    def test_exact_nxp_icpn_lpc11u68_visible_in_phase1_without_support(self):
        r=self.by_part["LPC11U68JBD48E"]
        self.assertEqual(r["phase1"],"IDENTIFIED")
        self.assertEqual(r["phase2"],"UNKNOWN")
        self.assertEqual(r["base_device"],"LPC11U68JBD48")
        self.assertIsNone(r["programming_profile_id"])
        self.assertEqual(r["phase3"],"NOT_AUDITED")

    def test_kl25_and_k32l2_source_only_candidates(self):
        rows=[r for r in self.rows if r["phase2"]=="CANDIDATE"]
        self.assertEqual(len(rows),28)
        self.assertEqual(sum(r["target_cfg"]=="tcl/target/kl25.cfg" for r in rows),12)
        self.assertEqual(sum(r["driver"]=="kinetis" and not r["target_cfg"] for r in rows),16)
        self.assertTrue(all(r["operations"]["verify"]=="NOT_QUALIFIED" for r in rows))

    def test_phase2_count_never_includes_unverified_research_only_277(self):
        legacy=subject.read_source("legacy")
        admitted={r["icpn"] for r in legacy if r["identity_state"]=="ADMITTED"}
        disallowed={r["icpn"] for r in legacy if r["identity_state"]=="RESEARCH_ONLY"}
        self.assertEqual(len(disallowed),277)
        self.assertTrue(admitted.issubset(self.by_part))
        self.assertFalse(disallowed.intersection(self.by_part))
        self.assertEqual(len(self.by_part-admitted),73)

    def test_reject_fake_phase2_supported(self):
        rows=copy.deepcopy(self.rows)
        rows[0]["phase2"]="SUPPORTED"
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
        rows[0]["phase1"]="RESEARCH_ONLY"
        with self.assertRaisesRegex(ValueError,"illegal"):
            subject.validate(rows)
        rows=copy.deepcopy(self.rows)
        rows[0]["icpn"]=rows[1]["icpn"]
        with self.assertRaisesRegex(ValueError,"distinct"):
            subject.validate(rows)

    def test_unreviewed_historical_priority_never_public_phase_state(self):
        row=self.by_part["LPC11U68JBD48E"]
        self.assertNotIn("research_priority",row)
        self.assertNotIn("P0",str(row))
        self.assertNotIn("P1",str(row))
        self.assertNotIn("P2",str(row))
        for row in self.rows:
            self.assertNotIn("research_priority",row)

    def test_phase3_no_fake_hil(self):
        rows=copy.deepcopy(self.rows)
        rows[0]["phase3"]="PASSED"
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
