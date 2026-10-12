"""STM32C5 host-only source lookup, negative cases, 139/33 split."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from plasma_web.backend_candidate_registry import BackendCandidateRegistry
from plasma_web.c5_host_loader_guard import C5HostLoaderGuard, C5SyntheticReads
from plasma_web.device_catalog import get_default_device_catalog

TCL = Path(__file__).resolve().parent / "fixtures/c5_stldr_array_lookup_v1.tcl"


class C5HostLoaderGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = get_default_device_catalog()
        cls.registry = BackendCandidateRegistry(cls.catalog)
        cls.guard = C5HostLoaderGuard(cls.catalog, cls.registry)

    @staticmethod
    def sample(did, size, **kwargs):
        return C5SyntheticReads(
            idcode=did, flash_size_kib=size,
            idcode_state=kwargs.get("idcode_state", "ok"),
            flash_size_state=kwargs.get("flash_size_state", "ok"),
            flash_size_origin=kwargs.get("flash_size_origin", "direct_register"),
        )

    def assert_never_executable(self, x):
        self.assertEqual(x["scope"], "synthetic_host_only_no_runtime")
        for key in ("real_device_id_verified", "real_flash_size_verified", "loader_staged",
                    "loader_executed", "loader_ram_abi_verified",
                    "vendor_binary_redistribution_approved", "security_state_verified",
                    "hardware_runtime_ready", "production_write_authorized", "executable"):
            self.assertIs(x[key], False, key)
        self.assertEqual(x["qualified_hardware_operations"], [])
        self.assertNotIn("target_config", x)
        self.assertNotIn("flash_command", x)

    def test_172_partition_exact_139_base_only_33_three_group_source(self):
        status = Counter()
        groups = Counter()
        for row in self.catalog.records:
            if row.family != "STM32C5":
                continue
            c = self.registry.lookup(row)
            groups[c["expected_device_id"]] += 1
            x = self.guard.evaluate(
                row.identifier,
                self.sample(int(c["expected_device_id"], 16), c["catalog_flash_kib"]))
            self.assert_never_executable(x)
            self.assertEqual(row.mapping_status, "no_mapping")
            self.assertEqual(row.target_config, "")
            status[x["status"]] += 1
            if c["dfp_exact_variant_status"] == "exact":
                self.assertEqual(x["status"], "synthetic_source_match_only", row.identifier)
                self.assertEqual(x["candidate_loader_source_path"], c["loader_source_path"])
                self.assertEqual(x["candidate_loader_sha256"], c["loader_sha256"])
                self.assertTrue(x["dfp_exact_variant_evidence"])
            else:
                self.assertEqual(x["status"], "blocked")
                self.assertEqual(x["reason"], "dfp_base_only_not_exact_loader_evidence")
                self.assertIsNone(x["candidate_loader_source_path"])
        self.assertEqual(groups, {"0x44F": 63, "0x44E": 60, "0x45A": 49})
        self.assertEqual(status, {"synthetic_source_match_only": 139, "blocked": 33})

    def test_all_three_groups_deny_wrong_id_flash_or_untrusted_fallback(self):
        selected = {}
        for row in self.catalog.records:
            if row.family == "STM32C5":
                c = self.registry.lookup(row)
                if c["dfp_exact_variant_status"] == "exact":
                    selected.setdefault(c["expected_device_id"], (row.identifier, c))
        self.assertEqual(len(selected), 3)
        for did, (icpn, c) in selected.items():
            good = self.sample(int(did, 16), c["catalog_flash_kib"])
            self.assertEqual(self.guard.evaluate(icpn, good)["status"], "synthetic_source_match_only")
            cases = (
                replace(good, idcode=0x474),
                replace(good, idcode_state="failed"),
                replace(good, flash_size_state="unobserved"),
                replace(good, flash_size_origin="vendor_max_fallback"),
                replace(good, flash_size_origin="user_override"),
                replace(good, flash_size_kib=0),
                replace(good, flash_size_kib=0xFFFF),
                replace(good, flash_size_kib=True),
                replace(good, flash_size_kib="128"),
                replace(good, flash_size_kib=c["driver_max_flash_kib"] + 1),
                replace(good, idcode=True),
                replace(good, idcode=None),
            )
            for s in cases:
                with self.subTest(icpn=icpn, sample=s):
                    result = self.guard.evaluate(icpn, s)
                    self.assertEqual(result["status"], "blocked")
                    self.assert_never_executable(result)

    def test_non_exact_unknown_other_vendor_never_inherit_source(self):
        for icpn in ("STM32C531CB", "STM32C531CBT6 ", "stm32c531cbt6",
                     "STM32H503CBT6", "STM32F103C8T6", "NONEXISTENT", "", None):
            with self.subTest(icpn=icpn):
                result = self.guard.evaluate(icpn, self.sample(0x44F, 128))
                self.assertEqual(result["status"], "blocked")
                self.assert_never_executable(result)

    def test_candidate_mutation_and_missing_sample_fail_closed(self):
        row = next(r for r in self.catalog.records if r.family == "STM32C5" and
                   self.registry.lookup(r)["dfp_exact_variant_status"] == "exact")
        orig = self.registry.lookup(row)
        for mutation in (
            {"loader_installed": True},
            {"executable": True},
            {"production_binding_authorized": True},
            {"loader_sha256": "0" * 64 + "bad"},
            {"dfp_declared_algorithm_ram_bytes": 32768},
            {"source_commit": "0" * 40},
        ):
            with self.subTest(mutation=mutation):
                corrupted = {**orig, **mutation}
                with patch.object(self.registry, "lookup", return_value=corrupted):
                    x = self.guard.evaluate(
                        row.identifier, self.sample(int(orig["expected_device_id"], 16),
                                                    orig["catalog_flash_kib"]))
                self.assertEqual(x["status"], "blocked")
                self.assert_never_executable(x)
        self.assertEqual(self.guard.evaluate(row.identifier, None)["status"], "blocked")

    @unittest.skipUnless(shutil.which("tclsh"), "tclsh unavailable; dedicated CI requires Tcl")
    def test_host_tcl_research_arrays_three_groups_and_empty_runtime(self):
        proc = subprocess.run(["tclsh", str(TCL)], check=False, text=True,
                              capture_output=True, timeout=5)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "ST_C5_HOST_ARRAY_ONLY_PASS")


if __name__ == "__main__":
    unittest.main()
