"""Host-only ADR-0002 STM32F103 low-density Gate 1 negative assurance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "ci"))
from stm32f103_low_density_candidate import (
    ROOT, EXPECTED, EXCLUDED, LowDensityEvidenceError,
    audit_candidate, load_snapshot, verify_snapshot,
)
from plasma_web.openocd_software_qualification import (
    get_default_openocd_software_qualification_registry,
)


class STM32F103LowDensityCandidateGate1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original = load_snapshot(ROOT)

    def mutated(self, location, key, value):
        candidate = deepcopy(self.original)
        node = candidate
        for piece in location:
            node = node[piece]
        node[key] = value
        with self.assertRaises(LowDensityEvidenceError):
            verify_snapshot(candidate, ROOT)

    def test_all_12_are_candidate_not_supported(self):
        report = audit_candidate(ROOT)
        self.assertEqual(report["state"], "BLOCKED")
        self.assertEqual(report["candidate_exact_icpns"], 12)
        self.assertEqual(report["supported_added"], 0)
        self.assertEqual(report["retained_existing_l2"], 77)
        self.assertEqual(set(report["excluded_exact_icpns"]), EXCLUDED)
        self.assertEqual({r["icpn"] for r in self.original["app"]["records"]}, EXPECTED)

    def test_existing_provider_stays_at_77(self):
        registry = get_default_openocd_software_qualification_registry()
        self.assertEqual(len(registry.supported_exact_icpns("STMicroelectronics")), 77)
        for row in self.original["app"]["records"]:
            self.assertEqual(registry.state_for("STMicroelectronics", row["icpn"]), "UNKNOWN")
        for icpn in EXCLUDED:
            self.assertEqual(registry.state_for("STMicroelectronics", icpn), "UNKNOWN")

    def test_source_hash_unavailable_must_fail_closed(self):
        self.mutated(["source", "evidence", "official_datasheet"], "original_bytes_attested", True)
        self.mutated(["source", "evidence", "official_datasheet"], "sha256", "0" * 64)
        self.mutated(["source", "evidence", "openocd"], "device_id", "0x410")

    def test_all_12_cannot_be_marked_supported(self):
        for name in EXPECTED:
            s = deepcopy(self.original)
            next(row for row in s["qual"]["records"] if row["icpn"] == name)["software_state"] = "SUPPORTED"
            with self.subTest(icpn=name), self.assertRaises(LowDensityEvidenceError):
                verify_snapshot(s, ROOT)

    def test_geometry_and_device_id_mismatch_rejected(self):
        self.mutated(["geometries", "C4", "data"], "main_flash_size_bytes", 32768)
        self.mutated(["geometries", "R6", "data"], "page_size_bytes", 2048)
        self.mutated(["geometries", "R4", "data"], "main_flash_end", "0x08007FFF")
        self.mutated(["program", "data"], "expected_device_id", "0x410")
        self.mutated(["program", "data"], "program_granularity_bytes", 4)

    def test_unsafe_flash_paths_rejected(self):
        self.mutated(["program", "data"], "flash_size_read_fail_closed", False)
        self.mutated(["program", "data"], "user_flash_size_override_as_authority", True)
        self.mutated(["program", "data"], "prohibit_full_bank_erase_until_separately_approved", False)
        self.mutated(["program", "data"], "disallowed_operations", ["option_write"])

    def test_exact_package_and_tr_inheritance_rejected(self):
        s = deepcopy(self.original)
        s["app"]["records"][0]["package"] = "VFQFPN"
        with self.assertRaises(LowDensityEvidenceError):
            verify_snapshot(s, ROOT)
        s = deepcopy(self.original)
        tr = next(row for row in s["app"]["records"] if row["icpn"].endswith("TR"))
        tr["source_nontr_exact_icpn"] = "STM32F103C8T6"
        with self.assertRaises(LowDensityEvidenceError):
            verify_snapshot(s, ROOT)

    def test_exclusions_and_drift_rejected(self):
        self.mutated(["v10"], "supported_exact_icpn_count", 89)
        self.mutated(["v10", "predecessor_qualification"], "git_blob_sha1", "0" * 40)
        self.mutated(["v10", "pending_cohort"], "git_blob_sha1", "0" * 40)
        self.mutated(["app"], "excluded_exact_icpns", [])
        self.mutated(["qual"], "supported_exact_icpn_count", 12)
        self.mutated(["app", "production_catalog"], "git_blob_sha1", "0" * 40)


if __name__ == "__main__":
    unittest.main()
