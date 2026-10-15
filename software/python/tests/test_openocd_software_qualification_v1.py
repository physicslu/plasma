from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from plasma_web.device_catalog import DeviceCatalogIntegrityError, get_default_device_catalog
from plasma_web.openocd_software_qualification import (
    OpenOCDSoftwareQualificationRegistry,
    REQUIRED_OPERATIONS,
    ROOT,
    get_default_openocd_software_qualification_registry,
)


class OpenOCDSoftwareQualificationV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = get_default_device_catalog()
        cls.registry = OpenOCDSoftwareQualificationRegistry(cls.catalog, ROOT)

    def test_reference_cohort_is_exact_and_supported(self):
        self.assertEqual(
            self.registry.supported_exact_icpns("STMicroelectronics"),
            (
                "STM32F103C8T6",
                "STM32F103C8T6TR",
                "STM32F103CBT6",
                "STM32F103CBT6TR",
            ),
        )
        for icpn in self.registry.supported_exact_icpns("STMicroelectronics"):
            row = self.registry.lookup("STMicroelectronics", icpn)
            self.assertIsNotNone(row)
            self.assertEqual(row["software_state"], "SUPPORTED")
            self.assertEqual(row["operations"], list(REQUIRED_OPERATIONS))

    def test_exact_geometries_are_not_collapsed(self):
        c8 = self.registry.lookup("STMicroelectronics", "STM32F103C8T6")
        cb = self.registry.lookup("STMicroelectronics", "STM32F103CBT6")
        self.assertEqual(c8["main_flash_size_bytes"], 64 * 1024)
        self.assertEqual(c8["page_count"], 64)
        self.assertEqual(cb["main_flash_size_bytes"], 128 * 1024)
        self.assertEqual(cb["page_count"], 128)
        self.assertEqual(c8["programming_profile_id"], cb["programming_profile_id"])
        self.assertNotEqual(c8["memory_geometry_profile_id"], cb["memory_geometry_profile_id"])

        c8tr = self.registry.lookup("STMicroelectronics", "STM32F103C8T6TR")
        cbtr = self.registry.lookup("STMicroelectronics", "STM32F103CBT6TR")
        self.assertEqual(c8tr["qualification_basis"]["kind"], "ordering_equivalence")
        self.assertEqual(c8tr["qualification_basis"]["equivalent_to_icpn"], "STM32F103C8T6")
        self.assertEqual(cbtr["qualification_basis"]["kind"], "ordering_equivalence")
        self.assertEqual(cbtr["qualification_basis"]["equivalent_to_icpn"], "STM32F103CBT6")
        for variant, source in ((c8tr, c8), (cbtr, cb)):
            self.assertEqual(variant["programming_profile_id"], source["programming_profile_id"])
            self.assertEqual(variant["memory_geometry_profile_id"], source["memory_geometry_profile_id"])
            self.assertEqual(variant["main_flash_size_bytes"], source["main_flash_size_bytes"])
            self.assertEqual(variant["page_count"], source["page_count"])
            self.assertEqual(variant["operations"], source["operations"])

    def test_same_family_or_existing_mapping_does_not_grant_supported(self):
        self.assertEqual(
            self.registry.state_for("STMicroelectronics", "STM32F103R8T6"),
            "UNKNOWN",
        )
        self.assertEqual(
            self.registry.state_for("STMicroelectronics", "STM32F407VGT6"),
            "UNKNOWN",
        )
        self.assertIsNone(self.registry.lookup("STMicroelectronics", "STM32F103R8T6"))

    def test_projection_separates_supported_from_unreviewed_mapping(self):
        c8 = self.registry.describe("STMicroelectronics", "STM32F103C8T6")
        self.assertEqual(c8["software_state"], "SUPPORTED")
        self.assertTrue(c8["reviewed"])
        self.assertEqual(c8["provider"]["version"], "0.12.0")
        self.assertEqual(c8["provider"]["flash_driver"], "stm32f1x")
        self.assertEqual(c8["operations"]["probe"]["state"], "SUPPORTED")
        self.assertEqual(c8["operations"]["verify"]["state"], "SUPPORTED")
        self.assertEqual(
            c8["programming"]["electrical"]["vdd_programming_v"],
            {"min": 2.0, "max": 3.6},
        )
        self.assertFalse(c8["programming"]["electrical"]["external_vpp_required"])
        self.assertEqual(c8["programming"]["flash_geometry"]["main_flash_size_bytes"], 65536)
        self.assertEqual(c8["programming"]["flash_geometry"]["page_count"], 64)

        cb = self.registry.describe("STMicroelectronics", "STM32F103CBT6")
        self.assertEqual(cb["software_state"], "SUPPORTED")
        self.assertEqual(cb["programming"]["flash_geometry"]["main_flash_size_bytes"], 131072)
        self.assertEqual(cb["programming"]["flash_geometry"]["page_count"], 128)

        c8tr = self.registry.describe("STMicroelectronics", "STM32F103C8T6TR")
        self.assertEqual(c8tr["software_state"], "SUPPORTED")
        self.assertTrue(c8tr["reviewed"])
        self.assertEqual(c8tr["programming"]["flash_geometry"]["main_flash_size_bytes"], 65536)
        self.assertEqual(c8tr["programming"]["flash_geometry"]["page_count"], 64)

        cbtr = self.registry.describe("STMicroelectronics", "STM32F103CBT6TR")
        self.assertEqual(cbtr["software_state"], "SUPPORTED")
        self.assertTrue(cbtr["reviewed"])
        self.assertEqual(cbtr["programming"]["flash_geometry"]["main_flash_size_bytes"], 131072)
        self.assertEqual(cbtr["programming"]["flash_geometry"]["page_count"], 128)

        r8 = self.registry.describe("STMicroelectronics", "STM32F103R8T6")
        self.assertEqual(r8["software_state"], "UNKNOWN")
        self.assertFalse(r8["reviewed"])
        self.assertIsNone(r8["provider"])
        self.assertEqual(r8["operations"], {})
        self.assertIsNone(r8["programming"])
        self.assertFalse(r8["public_catalog_visibility_changed"])
        self.assertFalse(r8["job_batch_execution_changed"])
        self.assertFalse(r8["hardware_runtime_ready"])
        self.assertFalse(r8["physical_programming_qualified"])

    def test_operation_qualification_is_source_bounded(self):
        opq = self.registry.operation_qualification
        self.assertEqual(set(opq), set(REQUIRED_OPERATIONS))
        for operation in REQUIRED_OPERATIONS:
            self.assertEqual(opq[operation]["state"], "SUPPORTED")
            self.assertTrue(opq[operation]["openocd_basis"])
            self.assertTrue(opq[operation]["manufacturer_basis"])

        self.assertFalse(self.registry.acceptance_boundary["public_catalog_visibility_changed"])
        self.assertFalse(self.registry.acceptance_boundary["job_batch_execution_changed"])
        self.assertFalse(self.registry.acceptance_boundary["installed_runtime_attested"])
        self.assertFalse(self.registry.acceptance_boundary["hardware_runtime_ready"])
        self.assertFalse(self.registry.acceptance_boundary["physical_programming_qualified"])

    def test_default_registry_is_available_in_full_source_tree(self):
        registry = get_default_openocd_software_qualification_registry()
        self.assertIsNotNone(registry)
        self.assertEqual(registry.summary["supported_exact_icpns"], 4)
        self.assertEqual(registry.summary["reviewed_exact_icpns"], 4)
        self.assertGreater(registry.summary["unreviewed_default_unknown_exact_icpns"], 0)

    def test_local_evidence_blob_drift_fails_closed(self):
        self.assertIsNotNone(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in (
                "release/openocd.json",
                "release/openocd-qualification/openocd-0.12.0-stm32f1-source-lock-v1.json",
                "release/openocd-qualification/openocd-0.12.0-stm32f103c-reference-v2.json",
                "release/openocd-qualification/stm32f103c-tr-ordering-equivalence-v1.json",
                "data/ic-support/openocd-comparison/stm32f103c8t6-openocd-v0.12.0-v1.json",
                "data/ic-support/benchmarks/stm32f103c/vendor-neutral-admission-contract-v1.json",
                "data/ic-support/profiles/programming/stm32f1-medium-density-flash-v0.json",
                "data/ic-support/bindings/stm32f103c-pilot-v0.json",
                "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.json",
                "data/ic-support/execution-ir/stm32f103c-programming-execution-ir-v0.json",
                "data/device-catalog/research/stm32f1-ordering-authority-v2.4.json",
                "data/device-catalog/research/stm32-icpn-phase2-st-authoritative-sources.md",
                "data/device-catalog/research/stm32-icpn-phase2-cb-evidence.md",
                "data/device-catalog/research/stm32f1-commercial-icpn.csv",
            ):
                src = ROOT / rel
                dst = root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())

            drift = root / "data/ic-support/profiles/programming/stm32f1-medium-density-flash-v0.json"
            drift.write_bytes(drift.read_bytes() + b"\n")
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "local evidence blob drift"):
                OpenOCDSoftwareQualificationRegistry(self.catalog, root)

    def test_ordering_equivalence_evidence_drift_fails_closed(self):
        self.assertIsNotNone(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel in (
                "release/openocd.json",
                "release/openocd-qualification/openocd-0.12.0-stm32f1-source-lock-v1.json",
                "release/openocd-qualification/openocd-0.12.0-stm32f103c-reference-v2.json",
                "release/openocd-qualification/stm32f103c-tr-ordering-equivalence-v1.json",
                "data/ic-support/openocd-comparison/stm32f103c8t6-openocd-v0.12.0-v1.json",
                "data/ic-support/benchmarks/stm32f103c/vendor-neutral-admission-contract-v1.json",
                "data/ic-support/profiles/programming/stm32f1-medium-density-flash-v0.json",
                "data/ic-support/bindings/stm32f103c-pilot-v0.json",
                "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.json",
                "data/ic-support/execution-ir/stm32f103c-programming-execution-ir-v0.json",
                "data/device-catalog/research/stm32f1-ordering-authority-v2.4.json",
                "data/device-catalog/research/stm32-icpn-phase2-st-authoritative-sources.md",
                "data/device-catalog/research/stm32-icpn-phase2-cb-evidence.md",
                "data/device-catalog/research/stm32f1-commercial-icpn.csv",
            ):
                src = ROOT / rel
                dst = root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())

            drift = root / "data/device-catalog/research/stm32-icpn-phase2-st-authoritative-sources.md"
            drift.write_bytes(drift.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                DeviceCatalogIntegrityError, "ordering identity evidence blob drift"
            ):
                OpenOCDSoftwareQualificationRegistry(self.catalog, root)


if __name__ == "__main__":
    unittest.main()
