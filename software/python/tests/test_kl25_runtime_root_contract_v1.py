"""Installed-wheel Runtime: no retired exact-ICPN compiler/admission code, no
module-relative data roots.

S5: the KL25 backend implementation lock and admission evidence are offline IC
Catalog governance data (pinned by ``plasma_web.nxp_kl25_qualification``); the
PPU Runtime ships no KL25/STM32 plan compiler, executor, registry or projection.
"""
from __future__ import annotations
import importlib.util
import unittest
from importlib.resources import files
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RETIRED_RUNTIME_MODULES = (
    "plasma_interfaces.compiler_registry",
    "plasma_interfaces.openocd_plan",
    "plasma_interfaces.openocd_executor",
    "plasma_interfaces.kl25_openocd_plan",
)


class InstalledRuntimeRetiredCompilerTests(unittest.TestCase):
    def test_installed_runtime_has_no_retired_compiler_registry_or_projection(self):
        for module in RETIRED_RUNTIME_MODULES:
            with self.subTest(module=module):
                self.assertIsNone(importlib.util.find_spec(module))
        shipped = {entry.name for entry in files("plasma_interfaces").iterdir()}
        self.assertFalse([name for name in shipped if "admission-projection" in name], shipped)

    def test_module_relative_root_regression_guard_for_affected_loaders(self):
        modules = (
            "software/python/plasma_web/nxp_manufacturer_device_evidence.py",
            "software/python/plasma_web/backend_candidate_registry.py",
            "software/python/plasma_web/backend_source_reference.py",
            "software/python/plasma_web/openocd_provider_registry.py",
        )
        for module in modules:
            with self.subTest(module=module):
                self.assertNotIn("Path(__file__).resolve().parents[3]", (ROOT/module).read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
