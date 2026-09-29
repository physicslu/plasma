"""Negative-only tests for research-stage exact STM32C5 local loader preflight.

The production path is NOT imported or exercised. For a positive local byte
integrity demonstration CI stages the three pinned official DFP source files
separately and does not redistribute the binaries as an artifact.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import preflight_st_c5_local_loader_candidate_v10 as gate


class C5EvidenceAdmissionBoundary(unittest.TestCase):
    def test_33_gap_partition_and_172_canonical_commercial_identity(self):
        rows = gate.load_and_reconcile()
        self.assertEqual(172, len(rows))
        missing = [r for r in rows.values()
                   if r["dfp_evidence_state"] == "BASE_DEVICE_ONLY_NOT_EXACT"]
        self.assertEqual(33, len(missing))
        self.assertEqual(9, len(gate.DFP_EXACT_NONTR_FOR_MISSING_TR))
        self.assertTrue(gate.DFP_EXACT_NONTR_FOR_MISSING_TR <=
                        {r["icpn"] for r in missing})

    def test_gap_cannot_be_substituted_with_nontr_exact_sibling(self):
        decision = gate.preflight(
            "STM32C551CCT6TR", "0x44E", 262144,
            Path("/tmp/never-provide-a-c5-binary"))
        self.assertEqual("BLOCKED_NO_EXACT_DFP_VARIANT", decision["decision"])
        self.assertFalse(decision["catalog_admission_ready"])
        self.assertFalse(decision["executable"])

    def test_nontr_missing_does_not_inherit_parent(self):
        decision = gate.preflight("STM32C593VET3", "0x45A", 524288)
        self.assertEqual("BLOCKED_NO_EXACT_DFP_VARIANT", decision["decision"])

    def test_unknown_exact_icpn_rejected(self):
        decision = gate.preflight("STM32C531CBT9")
        self.assertEqual("BLOCKED_NOT_IN_FROZEN_C5_COHORT", decision["decision"])

    def test_wildcard_never_expanded(self):
        decision = gate.preflight("STM32C531CBTx")
        self.assertEqual("BLOCKED_NONEXACT_ICPN", decision["decision"])

    def test_exact_dvariant_still_requires_reported_dev_id(self):
        decision = gate.preflight("STM32C531CBT6")
        self.assertEqual("BLOCKED_DEVICE_ID_READBACK_REQUIRED", decision["decision"])

    def test_noncanonical_device_identifier_blocked(self):
        decision = gate.preflight("STM32C531CBT6", "0x44f", 131072)
        self.assertEqual("BLOCKED_NONCANONICAL_DEVICE_ID", decision["decision"])

    def test_mismatched_device_identifier_blocked(self):
        decision = gate.preflight("STM32C531CBT6", "0x44E", 131072)
        self.assertEqual("BLOCKED_DEVICE_ID_MISMATCH", decision["decision"])

    def test_missing_measured_flash_size_blocked(self):
        decision = gate.preflight("STM32C531CBT6", "0x44F")
        self.assertEqual("BLOCKED_FLASH_READBACK_REQUIRED", decision["decision"])

    def test_bool_not_masquerade_as_integer_flash_size(self):
        decision = gate.preflight("STM32C531CBT6", "0x44F", True)
        self.assertEqual("BLOCKED_FLASH_READBACK_REQUIRED", decision["decision"])

    def test_unexpected_flash_geometry_blocked(self):
        decision = gate.preflight("STM32C531CBT6", "0x44F", 262144)
        self.assertEqual("BLOCKED_FLASH_GEOMETRY_MISMATCH", decision["decision"])

    def test_local_staging_is_explicit(self):
        decision = gate.preflight("STM32C531CBT6", "0x44F", 131072)
        self.assertEqual("BLOCKED_STAGED_LOCAL_LOADER_REQUIRED", decision["decision"])

    def test_remote_url_does_not_count_as_staging(self):
        decision = gate.preflight("STM32C531CBT6", "0x44F", 131072,
                                  "https://github.com/fake-loader.xldr")
        self.assertEqual("BLOCKED_LOCAL_LOADER_PROVENANCE", decision["decision"])
        self.assertFalse(decision["production_write_authorized"])

    def test_corrupted_fake_elf_never_counts_as_pinned_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "STM32C5[34]x.xldr"
            path.write_bytes(b"\x7fELF\x01\x01" + b"\0" * 8192)
            decision = gate.preflight("STM32C531CBT6", "0x44F", 131072,
                                      Path(tmp))
            self.assertEqual("BLOCKED_LOCAL_LOADER_PROVENANCE", decision["decision"])
            self.assertIn("SHA256 mismatch", decision["reason"])

    def test_missing_local_file_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            decision = gate.preflight("STM32C531CBT6", "0x44F", 131072, Path(tmp))
            self.assertEqual("BLOCKED_LOCAL_LOADER_PROVENANCE", decision["decision"])

    def test_symbolic_loader_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "unrelated-file"
            outside.write_bytes(b"\x7fELF\x01\x01" + b"\0" * 8192)
            (root / "STM32C5[34]x.xldr").symlink_to(outside)
            decision = gate.preflight("STM32C531CBT6", "0x44F", 131072, root)
            self.assertEqual("BLOCKED_LOCAL_LOADER_PROVENANCE", decision["decision"])
            self.assertIn("symlink", decision["reason"])

    def test_every_result_remains_non_executable(self):
        decisions = [
            gate.preflight("STM32C531CBT6"),
            gate.preflight("STM32C551CCT6TR"),
            gate.preflight("STM32C531CBT9"),
        ]
        for result in decisions:
            for flag in ("executable", "hardware_readback_authenticated",
                         "hardware_runtime_ready", "catalog_admission_ready",
                         "production_write_authorized", "security_mutation_authorized"):
                self.assertFalse(result[flag], flag)


if __name__ == "__main__":
    unittest.main()
