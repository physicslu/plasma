"""Host-only static PS/C5 backend source contract tests (never run target cfg)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_st_c5_ps_backend_static_gate_v11 as gate


class C5PSStaticGate(unittest.TestCase):
    def test_v11_contract_is_research_not_runtime(self):
        result = gate.validate_source_repo_boundary()
        self.assertEqual(result["status"], "RESEARCH_PS_SOURCE_BOUNDARY_PASS")
        self.assertEqual((result["c5_commercial_active_exact"],
                          result["exact_dfp_variant"],
                          result["missing_exact_dfp_variant"]),
                         (172, 139, 33))
        self.assertFalse(result["hardware_runtime_ready"])
        self.assertFalse(result["real_ps_binary_installed_and_qualified"])

    def test_three_distinct_official_dfp_ram_algorithm_footprints(self):
        self.assertEqual(gate.EXPECTED_ALGORITHM_RAM_BYTES,
                         {"Flash/STM32C5[34]x.xldr": 65536,
                          "Flash/STM32C5[56]x.xldr": 131072,
                          "Flash/STM32C5[9A]x.xldr": 262144})
        self.assertEqual(gate.EXPECTED_FALLBACK_BYTES,
                         {"0x44E": 524288, "0x44F": 262144, "0x45A": 1048576})

    def test_only_two_exact_source_repairs_are_in_review(self):
        self.assertEqual(2, len(gate.REPLACEMENTS))
        self.assertEqual(gate.REPLACEMENTS[0],
                         ("set die_max_flash_size {", "array set die_max_flash_size {"))
        self.assertEqual(gate.REPLACEMENTS[1],
                         ("set dev_id_loader {\n}", "array set dev_id_loader {\n}"))

    def test_non_pinned_vendor_target_fails_closed(self):
        for bad in (b"", b"set die_max_flash_size {}\nset dev_id_loader {}\n",
                    b"\x7fELF\x01\x01"):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                gate.patch_in_memory(bad)

    def test_vendor_driver_source_must_be_exact_digest(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "bad-driver.c"
            p.write_text("STLDR_FUNC_MANDATORY\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                gate.verify_source_bytes(p, gate.EXPECTED_FORK_DRIVER,
                                         "intentionally untrusted fork driver")

    def assert_mutation_refused(self, key_path, new_value):
        original = json.loads(gate.REPORT.read_text(encoding="utf-8"))
        target = original
        for k in key_path[:-1]:
            target = target[k]
        target[key_path[-1]] = new_value
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "mutated-gate.json"
            p.write_text(json.dumps(original), encoding="utf-8")
            with patch.object(gate, "REPORT", p):
                with self.assertRaises(ValueError):
                    gate.validate_source_repo_boundary()

    def test_cannot_claim_compiled_stldr(self):
        self.assert_mutation_refused(
            ["gates", "stldr_compiled_in_plasma_chosen_binary_verified"], True)

    def test_cannot_claim_hil_readback(self):
        self.assert_mutation_refused(
            ["gates", "real_dev_id_flash_geometry_readback_verified"], True)

    def test_cannot_claim_approved_production_catalog(self):
        self.assert_mutation_refused(
            ["gates", "production_catalog_update_authorized"], True)

    def test_cannot_inflate_frozen_st_production(self):
        self.assert_mutation_refused(
            ["crosswalk", "fixed_production_st_icpns"], 2855)

    def test_cannot_normalize_declared_dpf_ram_as_verified_runtime(self):
        self.assert_mutation_refused(
            ["dfp", "ram_size_field_is_pack_declared_algorithm_footprint_not_proven_runtime_requirement"], False)

    def test_cannot_mark_candidate_cfg_as_production(self):
        self.assert_mutation_refused(
            ["manufacturer_openocd_fork", "source_tcl_defect",
             "candidate_is_not_production_target_cfg"], False)

    def test_real_ps_openocd_installation_not_verified(self):
        self.assert_mutation_refused(
            ["plasma_source", "real_ps_openocd_version_sha256_and_stldr_build_not_observed"], False)

    def test_empty_loader_mapping_must_stay_empty(self):
        self.assert_mutation_refused(
            ["manufacturer_openocd_fork", "source_tcl_defect",
             "loader_table_remains_empty_in_research_fix"], False)

    def test_vendor_loader_license_signoff_not_automatic(self):
        self.assert_mutation_refused(
            ["gates", "official_vendor_binary_license_approved"], True)


if __name__ == "__main__":
    unittest.main()
