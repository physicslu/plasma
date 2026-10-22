from __future__ import annotations

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


EVIDENCE_FILES = (
    "release/openocd.json",
    "release/openocd-qualification/openocd-0.12.0-stm32f1-source-lock-v1.json",
    "release/openocd-qualification/openocd-0.12.0-stm32f103-v8.json",
    "release/openocd-qualification/openocd-0.12.0-stm32f103-v9.json",
    "release/openocd-qualification/stm32f103-medium-nonlqfp-exact-12-applicability-v1.json",
    "release/openocd-qualification/openocd-0.12.0-stm32f103-medium-nonlqfp-12-v1.json",
    "data/ic-support/benchmarks/stm32f103c/source-lock.json",
    "release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json",
    "release/openocd-qualification/stm32f103-medium-density-lqfp-t6-t7-applicability-v2.json",
    "release/openocd-qualification/stm32f103-medium-density-tr-ordering-equivalence-v3.json",
    "release/openocd-qualification/openocd-0.12.0-stm32f103-high-rvz-package-v4.json",
    "release/openocd-qualification/stm32f103-high-density-rvz-package-t6-t7-applicability-v4.json",
    "release/openocd-qualification/stm32f103-high-density-rvz-lqfp-tr-ordering-equivalence-v3.json",
    "data/ic-support/openocd-comparison/stm32f103c8t6-openocd-v0.12.0-v1.json",
    "data/ic-support/openocd-comparison/stm32f103-high-density-openocd-v0.12.0-v1.json",
    "data/ic-support/benchmarks/stm32f103c/vendor-neutral-admission-contract-v1.json",
    "data/ic-support/benchmarks/stm32f103-high-density/programming-review-v3.json",
    "data/ic-support/profiles/programming/stm32f1-medium-density-flash-v0.json",
    "data/ic-support/profiles/programming/stm32f1-high-density-flash-v0.json",
    "data/ic-support/bindings/stm32f103c-pilot-v0.json",
    "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.json",
    "data/ic-support/execution-ir/stm32f103c-programming-execution-ir-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103c8-64k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103cb-128k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103r8-64k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103rb-128k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103v8-64k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103vb-128k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103rc-256k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103rd-384k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103re-512k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103vc-256k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103vd-384k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103ve-512k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103zc-256k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103zd-384k-v0.json",
    "data/ic-support/profiles/memory-geometry/stm32f103ze-512k-v0.json",
    "data/device-catalog/research/stm32f1-ordering-authority-v2.4.json",
    "data/device-catalog/research/stm32f1-commercial-icpn.csv",
)


def copy_evidence_tree(destination: Path) -> None:
    assert ROOT is not None
    for rel in EVIDENCE_FILES:
        src = ROOT / rel
        dst = destination / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())


class OpenOCDSoftwareQualificationV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = get_default_device_catalog()
        cls.registry = OpenOCDSoftwareQualificationRegistry(cls.catalog, ROOT)

    def test_reviewed_cohort_is_exact_and_supported(self):
        expected = (
            "STM32F103C8T6",
            "STM32F103C8T6TR",
            "STM32F103C8T7",
            "STM32F103C8T7TR",
            "STM32F103CBT6",
            "STM32F103CBT6TR",
            "STM32F103CBT7",
            "STM32F103CBT7TR",
            "STM32F103R8T6",
            "STM32F103R8T6TR",
            "STM32F103R8T7",
            "STM32F103R8T7TR",
            "STM32F103RBT6",
            "STM32F103RBT6TR",
            "STM32F103RBT7",
            "STM32F103RBT7TR",
            "STM32F103RCT6",
            "STM32F103RCT6TR",
            "STM32F103RCT7",
            "STM32F103RCT7TR",
            "STM32F103RCY6TR",
            "STM32F103RDT6",
            "STM32F103RDT6TR",
            "STM32F103RDY6TR",
            "STM32F103RET6",
            "STM32F103RET6TR",
            "STM32F103RET7",
            "STM32F103REY6TR",
            "STM32F103V8T6",
            "STM32F103V8T6TR",
            "STM32F103VBT6",
            "STM32F103VBT6TR",
            "STM32F103VBT7",
            "STM32F103VBT7TR",
            "STM32F103VCH6",
            "STM32F103VCT6",
            "STM32F103VCT6TR",
            "STM32F103VDH6",
            "STM32F103VDH6TR",
            "STM32F103VDT6",
            "STM32F103VDT6TR",
            "STM32F103VDT7",
            "STM32F103VDT7TR",
            "STM32F103VEH6",
            "STM32F103VEH6TR",
            "STM32F103VEH7",
            "STM32F103VET6",
            "STM32F103VET6TR",
            "STM32F103VET7",
            "STM32F103VET7TR",
            "STM32F103ZCH6",
            "STM32F103ZCT6",
            "STM32F103ZCT6TR",
            "STM32F103ZCT7",
            "STM32F103ZCT7TR",
            "STM32F103ZDH6",
            "STM32F103ZDH6TR",
            "STM32F103ZDT6",
            "STM32F103ZEH6",
            "STM32F103ZEH6TR",
            "STM32F103ZEH7",
            "STM32F103ZEH7TR",
            "STM32F103ZET6",
            "STM32F103ZET6TR",
            "STM32F103ZET7",
        )
        extra = (
            "STM32F103CBU6",
            "STM32F103CBU6TR",
            "STM32F103R8H6",
            "STM32F103R8H6TR",
            "STM32F103R8H7",
            "STM32F103RBH6",
            "STM32F103RBH6TR",
            "STM32F103RBH7",
            "STM32F103V8H6",
            "STM32F103V8H6TR",
            "STM32F103VBH6",
            "STM32F103VBH7",
        )
        expected = tuple(sorted((*expected, *extra)))
        self.assertEqual(
            self.registry.supported_exact_icpns("STMicroelectronics"),
            expected,
        )
        for icpn in expected:
            row = self.registry.lookup("STMicroelectronics", icpn)
            self.assertIsNotNone(row)
            self.assertEqual(row["software_state"], "SUPPORTED")
            self.assertEqual(row["operations"], list(REQUIRED_OPERATIONS))

    def test_direct_medium_density_applicability_preserves_exact_geometry(self):
        expected = {
            "STM32F103R8T6": ("STM32F103R8", "stm32f103r8-64k-v0", 64 * 1024, 64),
            "STM32F103RBT6": ("STM32F103RB", "stm32f103rb-128k-v0", 128 * 1024, 128),
            "STM32F103V8T6": ("STM32F103V8", "stm32f103v8-64k-v0", 64 * 1024, 64),
            "STM32F103VBT6": ("STM32F103VB", "stm32f103vb-128k-v0", 128 * 1024, 128),
            "STM32F103C8T7": ("STM32F103C8", "stm32f103c8-64k-v0", 64 * 1024, 64),
            "STM32F103CBT7": ("STM32F103CB", "stm32f103cb-128k-v0", 128 * 1024, 128),
            "STM32F103R8T7": ("STM32F103R8", "stm32f103r8-64k-v0", 64 * 1024, 64),
            "STM32F103RBT7": ("STM32F103RB", "stm32f103rb-128k-v0", 128 * 1024, 128),
            "STM32F103VBT7": ("STM32F103VB", "stm32f103vb-128k-v0", 128 * 1024, 128),
        }
        for icpn, (base, geometry, size, pages) in expected.items():
            with self.subTest(icpn=icpn):
                row = self.registry.lookup("STMicroelectronics", icpn)
                self.assertEqual(row["qualification_basis"]["kind"], "manufacturer_applicability")
                self.assertEqual(row["base_device"], base)
                self.assertEqual(row["programming_profile_id"], "stm32f1-medium-density-flash-v0")
                self.assertEqual(row["memory_geometry_profile_id"], geometry)
                self.assertEqual(row["main_flash_size_bytes"], size)
                self.assertEqual(row["page_count"], pages)

    def test_direct_high_density_applicability_uses_2k_page_geometry(self):
        expected = {
            "STM32F103RCT6": ("STM32F103RC", "stm32f103rc-256k-v0", 262144, 128),
            "STM32F103RCT7": ("STM32F103RC", "stm32f103rc-256k-v0", 262144, 128),
            "STM32F103RDT6": ("STM32F103RD", "stm32f103rd-384k-v0", 393216, 192),
            "STM32F103RET6": ("STM32F103RE", "stm32f103re-512k-v0", 524288, 256),
            "STM32F103RET7": ("STM32F103RE", "stm32f103re-512k-v0", 524288, 256),
            "STM32F103VCT6": ("STM32F103VC", "stm32f103vc-256k-v0", 262144, 128),
            "STM32F103VDT6": ("STM32F103VD", "stm32f103vd-384k-v0", 393216, 192),
            "STM32F103VDT7": ("STM32F103VD", "stm32f103vd-384k-v0", 393216, 192),
            "STM32F103VET6": ("STM32F103VE", "stm32f103ve-512k-v0", 524288, 256),
            "STM32F103VET7": ("STM32F103VE", "stm32f103ve-512k-v0", 524288, 256),
            "STM32F103ZCT6": ("STM32F103ZC", "stm32f103zc-256k-v0", 262144, 128),
            "STM32F103ZCT7": ("STM32F103ZC", "stm32f103zc-256k-v0", 262144, 128),
            "STM32F103ZDT6": ("STM32F103ZD", "stm32f103zd-384k-v0", 393216, 192),
            "STM32F103ZET6": ("STM32F103ZE", "stm32f103ze-512k-v0", 524288, 256),
            "STM32F103ZET7": ("STM32F103ZE", "stm32f103ze-512k-v0", 524288, 256),
            "STM32F103RCY6TR": ("STM32F103RC", "stm32f103rc-256k-v0", 262144, 128),
            "STM32F103RDY6TR": ("STM32F103RD", "stm32f103rd-384k-v0", 393216, 192),
            "STM32F103REY6TR": ("STM32F103RE", "stm32f103re-512k-v0", 524288, 256),
            "STM32F103VCH6": ("STM32F103VC", "stm32f103vc-256k-v0", 262144, 128),
            "STM32F103VDH6": ("STM32F103VD", "stm32f103vd-384k-v0", 393216, 192),
            "STM32F103VDH6TR": ("STM32F103VD", "stm32f103vd-384k-v0", 393216, 192),
            "STM32F103VEH6": ("STM32F103VE", "stm32f103ve-512k-v0", 524288, 256),
            "STM32F103VEH6TR": ("STM32F103VE", "stm32f103ve-512k-v0", 524288, 256),
            "STM32F103VEH7": ("STM32F103VE", "stm32f103ve-512k-v0", 524288, 256),
            "STM32F103ZCH6": ("STM32F103ZC", "stm32f103zc-256k-v0", 262144, 128),
            "STM32F103ZDH6": ("STM32F103ZD", "stm32f103zd-384k-v0", 393216, 192),
            "STM32F103ZDH6TR": ("STM32F103ZD", "stm32f103zd-384k-v0", 393216, 192),
            "STM32F103ZEH6": ("STM32F103ZE", "stm32f103ze-512k-v0", 524288, 256),
            "STM32F103ZEH6TR": ("STM32F103ZE", "stm32f103ze-512k-v0", 524288, 256),
            "STM32F103ZEH7": ("STM32F103ZE", "stm32f103ze-512k-v0", 524288, 256),
            "STM32F103ZEH7TR": ("STM32F103ZE", "stm32f103ze-512k-v0", 524288, 256),
        }
        for icpn, (base, geometry, size, pages) in expected.items():
            with self.subTest(icpn=icpn):
                row = self.registry.lookup("STMicroelectronics", icpn)
                self.assertEqual(row["qualification_basis"]["kind"], "manufacturer_applicability")
                self.assertEqual(row["base_device"], base)
                self.assertEqual(row["programming_profile_id"], "stm32f1-high-density-flash-v0")
                self.assertEqual(row["memory_geometry_profile_id"], geometry)
                self.assertEqual(row["main_flash_size_bytes"], size)
                self.assertEqual(row["page_count"], pages)
                projected = self.registry.describe("STMicroelectronics", icpn)
                self.assertEqual(
                    projected["programming"]["flash_geometry"]["erase_unit_bytes"],
                    2048,
                )
                self.assertEqual(
                    projected["programming"]["flash_geometry"]["program_unit_bytes"],
                    2,
                )

    def test_tape_and_reel_variants_inherit_only_from_reviewed_reference(self):
        pairs = (
            ("STM32F103C8T6TR", "STM32F103C8T6"),
            ("STM32F103CBT6TR", "STM32F103CBT6"),
            ("STM32F103R8T6TR", "STM32F103R8T6"),
            ("STM32F103RBT6TR", "STM32F103RBT6"),
            ("STM32F103V8T6TR", "STM32F103V8T6"),
            ("STM32F103VBT6TR", "STM32F103VBT6"),
            ("STM32F103C8T7TR", "STM32F103C8T7"),
            ("STM32F103CBT7TR", "STM32F103CBT7"),
            ("STM32F103R8T7TR", "STM32F103R8T7"),
            ("STM32F103RBT7TR", "STM32F103RBT7"),
            ("STM32F103VBT7TR", "STM32F103VBT7"),
            ("STM32F103RCT6TR", "STM32F103RCT6"),
            ("STM32F103RCT7TR", "STM32F103RCT7"),
            ("STM32F103RDT6TR", "STM32F103RDT6"),
            ("STM32F103RET6TR", "STM32F103RET6"),
            ("STM32F103VCT6TR", "STM32F103VCT6"),
            ("STM32F103VDT6TR", "STM32F103VDT6"),
            ("STM32F103VDT7TR", "STM32F103VDT7"),
            ("STM32F103VET6TR", "STM32F103VET6"),
            ("STM32F103VET7TR", "STM32F103VET7"),
            ("STM32F103ZCT6TR", "STM32F103ZCT6"),
            ("STM32F103ZCT7TR", "STM32F103ZCT7"),
            ("STM32F103ZET6TR", "STM32F103ZET6"),
        )
        for variant_icpn, source_icpn in pairs:
            with self.subTest(icpn=variant_icpn):
                variant = self.registry.lookup("STMicroelectronics", variant_icpn)
                source = self.registry.lookup("STMicroelectronics", source_icpn)
                self.assertEqual(variant["qualification_basis"]["kind"], "ordering_equivalence")
                self.assertEqual(
                    variant["qualification_basis"]["equivalent_to_icpn"],
                    source_icpn,
                )
                for field in (
                    "base_device",
                    "programming_profile_id",
                    "memory_geometry_profile_id",
                    "main_flash_size_bytes",
                    "page_count",
                    "operations",
                ):
                    self.assertEqual(variant[field], source[field])

    def test_same_base_or_cfg_without_exact_review_does_not_grant_supported(self):
        # Same medium-density Base Device is not enough when the package was not reviewed.
        self.assertEqual(
            self.registry.state_for("STMicroelectronics", "STM32F103V8H6"),
            "UNKNOWN",
        )
        # A syntactically plausible but non-admitted exact order code is never synthesized.
        self.assertEqual(
            self.registry.state_for("STMicroelectronics", "STM32F103V8T7"),
            "UNKNOWN",
        )
        # XL-density remains a separate programming transaction and must stay UNKNOWN.
        self.assertEqual(
            self.registry.state_for("STMicroelectronics", "STM32F103RFT6"),
            "UNKNOWN",
        )
        # Ordering syntax must not synthesize exact commercial identities.
        self.assertEqual(
            self.registry.state_for("STMicroelectronics", "STM32F103RDT7"),
            "UNKNOWN",
        )
        # Missing commercial Z-pin ordering codes remain UNKNOWN; grammar must not synthesize them.
        self.assertEqual(
            self.registry.state_for("STMicroelectronics", "STM32F103ZDT7"),
            "UNKNOWN",
        )
        self.assertEqual(
            self.registry.state_for("STMicroelectronics", "STM32F103ZET7TR"),
            "UNKNOWN",
        )
        self.assertEqual(
            self.registry.state_for("STMicroelectronics", "STM32F103RET7TR"),
            "UNKNOWN",
        )
        self.assertEqual(
            self.registry.state_for("STMicroelectronics", "STM32F407VGT6"),
            "UNKNOWN",
        )
        self.assertIsNone(self.registry.lookup("STMicroelectronics", "STM32F103V8H6"))
        self.assertIsNone(self.registry.lookup("STMicroelectronics", "STM32F103V8T7"))

    def test_projection_separates_supported_from_unreviewed_mapping(self):
        for icpn, expected_size, expected_pages in (
            ("STM32F103C8T6", 64 * 1024, 64),
            ("STM32F103CBT6", 128 * 1024, 128),
            ("STM32F103R8T6", 64 * 1024, 64),
            ("STM32F103RBT6", 128 * 1024, 128),
            ("STM32F103V8T6", 64 * 1024, 64),
            ("STM32F103VBT6", 128 * 1024, 128),
            ("STM32F103R8T6TR", 64 * 1024, 64),
            ("STM32F103VBT6TR", 128 * 1024, 128),
            ("STM32F103C8T7", 64 * 1024, 64),
            ("STM32F103RBT7", 128 * 1024, 128),
            ("STM32F103VBT7TR", 128 * 1024, 128),
            ("STM32F103RCT6", 256 * 1024, 128),
            ("STM32F103RDT6TR", 384 * 1024, 192),
            ("STM32F103RET7", 512 * 1024, 256),
            ("STM32F103VCT6", 256 * 1024, 128),
            ("STM32F103VDT7TR", 384 * 1024, 192),
            ("STM32F103VET7", 512 * 1024, 256),
            ("STM32F103ZCT7TR", 256 * 1024, 128),
            ("STM32F103ZDT6", 384 * 1024, 192),
            ("STM32F103ZET7", 512 * 1024, 256),
            ("STM32F103RCY6TR", 256 * 1024, 128),
            ("STM32F103VDH6TR", 384 * 1024, 192),
            ("STM32F103ZEH7TR", 512 * 1024, 256),
        ):
            with self.subTest(icpn=icpn):
                item = self.registry.describe("STMicroelectronics", icpn)
                self.assertEqual(item["software_state"], "SUPPORTED")
                self.assertTrue(item["reviewed"])
                self.assertEqual(item["provider"]["version"], "0.12.0")
                self.assertEqual(item["provider"]["flash_driver"], "stm32f1x")
                self.assertEqual(item["operations"]["probe"]["state"], "SUPPORTED")
                self.assertEqual(item["operations"]["verify"]["state"], "SUPPORTED")
                self.assertEqual(
                    item["programming"]["electrical"]["vdd_programming_v"],
                    {"min": 2.0, "max": 3.6},
                )
                self.assertFalse(
                    item["programming"]["electrical"]["external_vpp_required"]
                )
                self.assertEqual(
                    item["programming"]["flash_geometry"]["main_flash_size_bytes"],
                    expected_size,
                )
                self.assertEqual(
                    item["programming"]["flash_geometry"]["page_count"],
                    expected_pages,
                )

        unreviewed = self.registry.describe("STMicroelectronics", "STM32F103T8U6")
        self.assertEqual(unreviewed["software_state"], "UNKNOWN")
        self.assertFalse(unreviewed["reviewed"])
        self.assertIsNone(unreviewed["provider"])
        self.assertEqual(unreviewed["operations"], {})
        self.assertIsNone(unreviewed["programming"])
        self.assertEqual(unreviewed["selector_visibility_rule"], "CATALOG_LEVEL_2_PROGRAMMABLE")
        self.assertFalse(unreviewed["job_batch_execution_changed"])
        self.assertFalse(unreviewed["hardware_runtime_ready"])
        self.assertFalse(unreviewed["physical_programming_qualified"])

    def test_operation_qualification_is_source_bounded(self):
        opq = self.registry.operation_qualification
        self.assertEqual(set(opq), set(REQUIRED_OPERATIONS))
        for operation in REQUIRED_OPERATIONS:
            self.assertEqual(opq[operation]["state"], "SUPPORTED")
            self.assertTrue(opq[operation]["openocd_basis"])
            self.assertTrue(opq[operation]["manufacturer_basis"])

        self.assertFalse(self.registry.acceptance_boundary["job_batch_execution_changed"])
        self.assertFalse(self.registry.acceptance_boundary["installed_runtime_attested"])
        self.assertFalse(self.registry.acceptance_boundary["hardware_runtime_ready"])
        self.assertFalse(self.registry.acceptance_boundary["physical_programming_qualified"])

    def test_default_registry_is_available_in_full_source_tree(self):
        registry = get_default_openocd_software_qualification_registry()
        self.assertIsNotNone(registry)
        self.assertEqual(registry.summary["supported_exact_icpns"], 77)
        self.assertEqual(registry.summary["reviewed_exact_icpns"], 77)
        self.assertEqual(
            registry.summary["unreviewed_default_unknown_exact_icpns"],
            registry.summary["catalog_exact_icpns"] - 77,
        )
        self.assertEqual(
            registry.summary["qualification_id"],
            "adr0002-phase2-openocd-012-stm32f103-v9",
        )
        self.assertEqual(
            registry.summary["selector_visibility_rule"],
            "CATALOG_LEVEL_2_PROGRAMMABLE",
        )
        self.assertEqual(len(registry.reviewed_exact_keys), 77)

    def test_new_exact_non_lqfp_medium_cohort_is_bounded(self):
        expected = {
            "STM32F103CBU6": ("stm32f103cb-128k-v0", 131072, 128),
            "STM32F103CBU6TR": ("stm32f103cb-128k-v0", 131072, 128),
            "STM32F103R8H6": ("stm32f103r8-64k-v0", 65536, 64),
            "STM32F103R8H6TR": ("stm32f103r8-64k-v0", 65536, 64),
            "STM32F103R8H7": ("stm32f103r8-64k-v0", 65536, 64),
            "STM32F103RBH6": ("stm32f103rb-128k-v0", 131072, 128),
            "STM32F103RBH6TR": ("stm32f103rb-128k-v0", 131072, 128),
            "STM32F103RBH7": ("stm32f103rb-128k-v0", 131072, 128),
            "STM32F103V8H6": ("stm32f103v8-64k-v0", 65536, 64),
            "STM32F103V8H6TR": ("stm32f103v8-64k-v0", 65536, 64),
            "STM32F103VBH6": ("stm32f103vb-128k-v0", 131072, 128),
            "STM32F103VBH7": ("stm32f103vb-128k-v0", 131072, 128),
        }
        for icpn, (geom, size, pages) in expected.items():
            with self.subTest(icpn=icpn):
                row = self.registry.describe("STMicroelectronics", icpn)
                self.assertEqual(row["software_state"], "SUPPORTED")
                self.assertTrue(row["reviewed"])
                self.assertEqual(row["programming"]["memory_geometry_profile_id"], geom)
                self.assertEqual(row["programming"]["flash_geometry"]["main_flash_size_bytes"], size)
                self.assertEqual(row["programming"]["flash_geometry"]["page_count"], pages)
                self.assertEqual(set(row["operations"]), set(REQUIRED_OPERATIONS))
                self.assertFalse(row["installed_runtime_attested"])
                self.assertFalse(row["physical_programming_qualified"])

        excluded = (
            "STM32F103RBH6R", "STM32F103RBH6RTR",
            "STM32F103T8U6", "STM32F103T8U6TR",
            "STM32F103T8U7", "STM32F103T8U7TR",
            "STM32F103TBU6", "STM32F103TBU6TR", "STM32F103TBU7",
        )
        for icpn in excluded:
            with self.subTest(excluded=icpn):
                result = self.registry.describe("STMicroelectronics", icpn)
                self.assertEqual(result["software_state"], "UNKNOWN")
                self.assertFalse(result["reviewed"])
                self.assertIsNone(result["programming"])
                self.assertEqual(result["operations"], {})

    def test_non_lqfp_applicability_integrity_fails_closed(self):
        self.assertIsNotNone(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            copy_evidence_tree(root)
            rel = "release/openocd-qualification/stm32f103-medium-nonlqfp-exact-12-applicability-v1.json"
            file = root / rel
            file.write_bytes(file.read_bytes() + b"\n")
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "source/applicability blob drift"):
                OpenOCDSoftwareQualificationRegistry(self.catalog, root)

    def test_non_lqfp_v9_total_must_match(self):
        import json
        self.assertIsNotNone(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            copy_evidence_tree(root)
            rel = "release/openocd-qualification/openocd-0.12.0-stm32f103-v9.json"
            file = root / rel
            content = json.loads(file.read_text())
            content["supported_exact_icpn_count"] = 89
            file.write_text(json.dumps(content))
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "v9 admission manifest drift"):
                OpenOCDSoftwareQualificationRegistry(self.catalog, root)

    def test_local_evidence_blob_drift_fails_closed(self):
        self.assertIsNotNone(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            copy_evidence_tree(root)
            drift = root / "data/ic-support/profiles/programming/stm32f1-medium-density-flash-v0.json"
            drift.write_bytes(drift.read_bytes() + b"\n")
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "local evidence blob drift"):
                OpenOCDSoftwareQualificationRegistry(self.catalog, root)

    def test_high_density_local_evidence_blob_drift_fails_closed(self):
        self.assertIsNotNone(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            copy_evidence_tree(root)
            drift = root / "data/ic-support/profiles/programming/stm32f1-high-density-flash-v0.json"
            drift.write_bytes(drift.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                DeviceCatalogIntegrityError,
                "high-density local evidence blob drift",
            ):
                OpenOCDSoftwareQualificationRegistry(self.catalog, root)

    def test_high_density_applicability_artifact_drift_fails_closed(self):
        self.assertIsNotNone(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            copy_evidence_tree(root)
            drift = (
                root
                / "release/openocd-qualification/stm32f103-high-density-rvz-package-t6-t7-applicability-v4.json"
            )
            drift.write_bytes(drift.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                DeviceCatalogIntegrityError,
                "high-density qualification authority artifact drift",
            ):
                OpenOCDSoftwareQualificationRegistry(self.catalog, root)

    def test_applicability_authority_artifact_drift_fails_closed(self):
        self.assertIsNotNone(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            copy_evidence_tree(root)
            drift = (
                root
                / "release/openocd-qualification/stm32f103-medium-density-lqfp-t6-t7-applicability-v2.json"
            )
            drift.write_bytes(drift.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                DeviceCatalogIntegrityError,
                "qualification authority artifact drift",
            ):
                OpenOCDSoftwareQualificationRegistry(self.catalog, root)

    def test_manufacturer_applicability_source_drift_fails_closed(self):
        self.assertIsNotNone(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            copy_evidence_tree(root)
            drift = root / "data/device-catalog/research/stm32f1-ordering-authority-v2.4.json"
            drift.write_bytes(drift.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                DeviceCatalogIntegrityError,
                "applicability source blob drift",
            ):
                OpenOCDSoftwareQualificationRegistry(self.catalog, root)


if __name__ == "__main__":
    unittest.main()
