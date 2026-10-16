from __future__ import annotations

import unittest

from plasma_web.device_catalog import (
    DeviceCatalog,
    DeviceCatalogIntegrityError,
    DeviceCatalogRecord,
)
from plasma_web.programming_qualification import (
    ProgrammingQualificationRegistry,
    get_default_programming_qualification_registry,
)


class _FakeProvider:
    reviewed_exact_keys = (("ExampleVendor", "EXAMPLE123"),)

    def lookup(self, manufacturer: str, exact_icpn: str):
        if (manufacturer, exact_icpn) == self.reviewed_exact_keys[0]:
            return {"software_state": "SUPPORTED"}
        return None

    def describe(self, manufacturer: str, exact_icpn: str):
        assert self.lookup(manufacturer, exact_icpn) is not None
        return {
            "software_state": "SUPPORTED",
            "reviewed": True,
            "provider": {
                "provider_id": "fake",
                "version": "1",
                "source_commit": "0" * 40,
                "runtime_id": "fake-1",
                "target_config": "target/fake.cfg",
                "flash_driver": "fake",
            },
            "operations": {"program": {"state": "SUPPORTED", "scope": "main_flash"}},
            "programming": {"programming_profile_id": "fake-v1"},
            "installed_runtime_attested": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }


def _record(*, admitted: bool) -> DeviceCatalogRecord:
    return DeviceCatalogRecord(
        vendor="ExampleVendor",
        family="Example",
        subfamily=None,
        plasma_series="Example",
        identifier="EXAMPLE123",
        identifier_kind="manufacturer_part_number",
        cpu_architectures=(),
        target_config="target/fake.cfg",
        openocd_distribution="fake",
        mapping_status="mapped",
        validation_status="unknown",
        catalog_origin="test",
        production_admitted=admitted,
    )


class ProgrammingQualificationRegistryTests(unittest.TestCase):
    def test_phase2_provider_requires_phase1_identified(self):
        catalog = DeviceCatalog((_record(admitted=False),))
        with self.assertRaisesRegex(
            DeviceCatalogIntegrityError,
            "Phase 2 record lacks Phase 1 IDENTIFIED prerequisite",
        ):
            ProgrammingQualificationRegistry(catalog, (_FakeProvider(),))

    def test_canonical_projection_separates_visibility_from_execution(self):
        catalog = DeviceCatalog((_record(admitted=True),))
        registry = ProgrammingQualificationRegistry(catalog, (_FakeProvider(),))
        result = registry.describe("ExampleVendor", "EXAMPLE123")
        self.assertEqual(result["phase"], "PROGRAMMING")
        self.assertEqual(result["phase1_identity_state"], "IDENTIFIED")
        self.assertEqual(result["state"], "SUPPORTED")
        self.assertEqual(result["selector_visibility_authority"], "PHASE1_IDENTIFIED")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["hardware_runtime_ready"])
        self.assertFalse(result["physical_programming_qualified"])

    def test_default_registry_preserves_st_49_and_projects_other_phase1_as_unknown(self):
        registry = get_default_programming_qualification_registry()
        self.assertEqual(registry.summary["reviewed_exact_icpns"], 49)
        self.assertEqual(
            registry.summary["selector_visibility_authority"],
            "PHASE1_IDENTIFIED",
        )

        st = registry.describe("STMicroelectronics", "STM32F103ZCT6")
        self.assertEqual(st["phase"], "PROGRAMMING")
        self.assertEqual(st["phase1_identity_state"], "IDENTIFIED")
        self.assertEqual(st["state"], "SUPPORTED")
        self.assertEqual(st["provider"]["provider_id"], "openocd-upstream")
        self.assertFalse(st["execution_authorized"])

        nxp = registry.describe("NXP", "MCXA132VFM")
        self.assertEqual(nxp["phase1_identity_state"], "IDENTIFIED")
        self.assertEqual(nxp["state"], "UNKNOWN")
        self.assertIsNone(nxp["provider"])
        self.assertFalse(nxp["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
