"""Negative-only hardware gate and 190-IC synthetic STM32H5 readback comparisons."""
from __future__ import annotations

import unittest
from dataclasses import replace

from plasma_web.backend_candidate_registry import BackendCandidateRegistry
from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.h5_host_readback_guard import H5HostReadbackGuard, H5SyntheticReads


class H5HostReadbackGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = get_default_device_catalog()
        cls.candidates = BackendCandidateRegistry(cls.catalog)
        cls.guard = H5HostReadbackGuard(cls.catalog, cls.candidates)

    @staticmethod
    def sample(idcode, size, **kwargs):
        return H5SyntheticReads(
            idcode=idcode,
            flash_size_register_kib=size,
            idcode_read_state=kwargs.get("idcode_read_state", "ok"),
            flash_size_read_state=kwargs.get("flash_size_read_state", "ok"),
            flash_size_origin=kwargs.get("flash_size_origin", "direct_register"),
        )

    def assert_not_hardware_admitted(self, result):
        self.assertEqual(result["scope"], "host_supplied_synthetic_inputs_only")
        self.assertFalse(result["hardware_runtime_ready"])
        self.assertFalse(result["production_write_authorized"])
        self.assertFalse(result["executable"])
        self.assertFalse(result["physical_readback_verified"])
        self.assertFalse(result["security_state_verified"])
        self.assertIsNone(result["actual_silicon_device_id"])
        self.assertIsNone(result["actual_flash_size_register_kib"])
        self.assertEqual(result["qualified_hardware_operations"], [])

    def test_all_190_exact_icpns_match_only_as_synthetic_vectors(self):
        count = 0
        groups = set()
        for row in self.catalog.records:
            if row.family != "STM32H5":
                continue
            count += 1
            c = self.candidates.lookup(row)
            groups.add(c["expected_device_id"])
            sample = self.sample(0x12340000 | int(c["expected_device_id"], 16),
                                 c["catalog_flash_kib"])
            result = self.guard.evaluate(row.identifier, sample)
            self.assertEqual(result["assessment"], "synthetic_consistent", row.identifier)
            self.assertTrue(result["synthetic_geometry_consistent"])
            self.assert_not_hardware_admitted(result)
            self.assertEqual(row.mapping_status, "no_mapping")
            self.assertFalse(row.target_config)
        self.assertEqual(count, 190)
        self.assertEqual(groups, {"0x474", "0x478", "0x47A", "0x47C", "0x484"})

    def test_bad_read_status_is_blocked_even_when_fallback_equals_catalog(self):
        # 128 KiB is both the H503 declared size and driver group maximum.
        base = self.sample(0x474, 128)
        for sample in (
            replace(base, idcode_read_state="failed"),
            replace(base, idcode_read_state="unknown"),
            replace(base, flash_size_read_state="failed"),
            replace(base, flash_size_read_state="unknown"),
            replace(base, flash_size_origin="driver_max_fallback"),
            replace(base, flash_size_origin="user_override"),
            replace(base, flash_size_origin="unknown"),
        ):
            with self.subTest(sample=sample):
                result = self.guard.evaluate("STM32H503CBT6", sample)
                self.assertEqual(result["assessment"], "blocked")
                self.assertFalse(result["synthetic_geometry_consistent"])
                self.assert_not_hardware_admitted(result)

    def test_wrong_device_group_and_invalid_idcodes_fail_closed(self):
        for idcode in (0x478, 0, 0xFFFFFFFF, -1, 0x100000000, True, None, "0x474"):
            with self.subTest(idcode=idcode):
                result = self.guard.evaluate("STM32H503CBT6", self.sample(idcode, 128))
                self.assertEqual(result["assessment"], "blocked")
                self.assert_not_hardware_admitted(result)

    def test_invalid_flash_register_and_geometry_fail_closed(self):
        for size in (None, True, -1, 0, 0xFFFF, 0x10000, 1, 127, 129, 256, "128"):
            with self.subTest(size=size):
                result = self.guard.evaluate("STM32H503CBT6", self.sample(0x474, size))
                self.assertEqual(result["assessment"], "blocked")
                self.assert_not_hardware_admitted(result)

    def test_3072k_sku_must_not_accept_4096k_driver_fallback(self):
        record = self.catalog.resolve("STMicroelectronics", "STM32H5E4IKT6")
        self.assertIsNotNone(record)
        c = self.candidates.lookup(record)
        self.assertEqual(c["catalog_flash_kib"], 3072)
        self.assertEqual(c["driver_max_flash_kib"], 4096)
        idcode = int(c["expected_device_id"], 16)
        self.assertEqual(self.guard.evaluate(record.identifier, self.sample(idcode, 3072))["assessment"],
                         "synthetic_consistent")
        for size in (4096, 2048, 0xFFFF):
            result = self.guard.evaluate(record.identifier, self.sample(idcode, size))
            self.assertEqual(result["assessment"], "blocked")
            self.assert_not_hardware_admitted(result)

    def test_no_automatic_promotion_for_wrong_or_nonexact_identity(self):
        for icpn in ("STM32F103C8T6", "STM32C531CBT6", "STM32N657X0Q3",
                     "STM32H503CB", "STM32H503CBT6 ", "stm32h503cbt6", "", None):
            with self.subTest(icpn=icpn):
                result = self.guard.evaluate(icpn, self.sample(0x474, 128))
                self.assertEqual(result["assessment"], "blocked")
                self.assert_not_hardware_admitted(result)

    def test_guard_never_returns_commands_or_permissions(self):
        result = self.guard.evaluate("STM32H503CBT6", self.sample(0x474, 128))
        for name in ("commands", "command", "erase", "write", "option_bytes",
                     "mass_erase", "obk", "target_config", "programming_plan"):
            self.assertNotIn(name, result)
        self.assertFalse(any(callable(getattr(self.guard, name, None))
                             for name in ("erase", "program", "verify", "execute", "run_openocd")))


if __name__ == "__main__":
    unittest.main()
