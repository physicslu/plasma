"""NXP Phase1/2 governance: ADR-0002 is the ONLY live acceptance authority.

Historical v9-v12, reverse source waves and interim S1-count report workflows
must remain deleted. Their evidence bytes and tests are retained offline for
forensic replay, not as a production gating workflow or alternative policy.
"""
from pathlib import Path
import unittest

import nxp_adr0002_phase1_phase2_canonical_v1 as canonical

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
RETIRED = (
    "device-catalog-nxp-adr0002-v9.yml",
    "device-catalog-nxp-openocd-reverse-coverage-v1.yml",
    "device-catalog-nxp-source-first-active-v2.yml",
    "device-catalog-nxp-source-first-wave3-v1.yml",
    "device-catalog-nxp-source-first-wave4-v1.yml",
    "device-catalog-nxp-discovery-65-gates-v1.yml",
    "device-catalog-nxp-phase1-funnel-audit-v1.yml",
    "device-catalog-nxp-phase1-lpc11u-lpc83x-11-v1.yml",
    "device-catalog-nxp-phase1-official-lpc25-v1.yml",
    "device-catalog-nxp-phase1-kinetis21-v1.yml",
)
LEGACY_EXECUTABLES = (
    "nxp_adr0002_openocd_triage_v9.py",
    "nxp_adr0002_core_qual_v10.py",
    "nxp_27_p0_flash_evidence_v11.py",
    "nxp_38_p1_bounded_v12.py",
    "nxp_adr0002_reverse_coverage_v1.py",
    "nxp_validate_source_first_active_v2.py",
    "nxp_validate_source_first_wave3_v1.py",
    "nxp_validate_source_first_wave4_v1.py",
    "nxp_65_discovery_gates_v1.py",
    "nxp_phase1_funnel_audit_v1.py",
    "nxp_phase1_lpc11u_lpc83x_11_v1.py",
    "nxp_phase1_official_lpc_25_v1.py",
    "nxp_phase1_kinetis_21_official_v1.py",
)
RAW_HISTORICAL_RETAINED = (
    "nxp-501-adr0002-openocd-priority-v9.csv",
    "nxp-501-adr0002-core-transport-qualification-v10.csv",
    "nxp-27-p0-exact-flash-review-v11.csv",
    "nxp-38-p1-one-pass-v12.csv",
    "nxp-501-phase1-ic-information-v13.csv",
    "nxp-65-openocd-discovery-gates-v1.csv",
)

class NxpSingleAuthorityContract(unittest.TestCase):
    def test_retire_all_ten_priority_or_transitive_legacy_workflows(self):
        for name in RETIRED:
            with self.subTest(name=name):
                self.assertFalse((WORKFLOWS/name).exists(), name+" must not be active")

    def test_all_current_workflows_forbid_old_nxp_priority_executables(self):
        for f in WORKFLOWS.glob("*.yml"):
            content=f.read_text(encoding="utf-8")
            for name in LEGACY_EXECUTABLES:
                with self.subTest(workflow=f.name,legacy=name):
                    self.assertNotIn("python data/device-catalog/research/"+name,content,
                                     f.name+" must not execute deprecated "+name)
        for f in WORKFLOWS.glob("*.yaml"):
            content=f.read_text(encoding="utf-8")
            for name in LEGACY_EXECUTABLES:
                self.assertNotIn("python data/device-catalog/research/"+name,content)

    def test_historical_evidence_retained_not_deleted(self):
        for name in RAW_HISTORICAL_RETAINED:
            with self.subTest(name=name):
                self.assertTrue((ROOT/"data/device-catalog/research"/name).is_file())
        for name in LEGACY_EXECUTABLES:
            with self.subTest(script=name):
                self.assertTrue((ROOT/"data/device-catalog/research"/name).is_file())

    def test_one_normative_nxp_phase1_phase2_entrypoint(self):
        active = (WORKFLOWS/"device-catalog-nxp-adr0002-phase1-phase2-v1.yml")
        self.assertTrue(active.is_file())
        text=active.read_text(encoding="utf-8")
        self.assertIn("nxp_adr0002_phase1_phase2_canonical_v1.py",text)
        self.assertIn("test_nxp_adr0002_phase1_phase2_canonical_v1.py",text)
        self.assertIn("test_nxp_adr0002_single_authority_v1.py",text)
        self.assertNotIn("P0",text)
        self.assertNotIn("P1",text)
        self.assertNotIn("P2",text)

    def test_no_legacy_priority_state_in_canonical_records(self):
        rows=canonical.build()
        self.assertEqual(len(rows),297)
        for part in rows:
            self.assertNotIn("research_priority",part)
            self.assertNotIn("priority_proposal",part)
            self.assertNotIn("source_priority",part)
            self.assertNotIn("p0",part)
            self.assertEqual(part["identity_state"],"IDENTIFIED")
            self.assertIn(part["catalog_level"],(0,1))
            self.assertIn(part["catalog_level_state"],("DISCOVERED","PROGRAMMING_CANDIDATE"))
            self.assertIn(part["programming_state"],("UNKNOWN","CANDIDATE"))
        summary=canonical.report(rows)
        self.assertEqual(summary["programming_state_counts"]["SUPPORTED"],0)
        self.assertEqual(summary["catalog_level_2_programmable_in_this_source_audit"],0)
        self.assertFalse(summary["execution_authorized"] if "execution_authorized" in summary
                         else summary.get("execution_authorized",False))

if __name__ == "__main__":
    unittest.main(verbosity=2)
