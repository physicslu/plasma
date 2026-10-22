from __future__ import annotations

import unittest

from plasma_web.device_catalog import (
    DeviceCatalog,
    DeviceCatalogIntegrityError,
    DeviceCatalogRecord,
)
from plasma_web.openocd_software_qualification import (
    get_default_openocd_software_qualification_registry,
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
    def test_provider_requires_identified_exact_icpn(self):
        catalog = DeviceCatalog((_record(admitted=False),))
        with self.assertRaisesRegex(
            DeviceCatalogIntegrityError,
            "Programming Qualification lacks IDENTIFIED exact ICPN prerequisite",
        ):
            ProgrammingQualificationRegistry(catalog, (_FakeProvider(),))

    def test_canonical_projection_separates_visibility_from_execution(self):
        catalog = DeviceCatalog((_record(admitted=True),))
        registry = ProgrammingQualificationRegistry(catalog, (_FakeProvider(),))
        result = registry.describe("ExampleVendor", "EXAMPLE123")
        self.assertEqual(result["identity_state"], "IDENTIFIED")
        self.assertEqual(result["catalog_level"], 2)
        self.assertEqual(result["catalog_level_state"], "PROGRAMMABLE")
        self.assertEqual(result["state"], "SUPPORTED")
        self.assertTrue(result["selector_visible"])
        self.assertTrue(result["job_selectable"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["hardware_runtime_ready"])
        self.assertFalse(result["physical_programming_qualified"])

    def test_default_registries_are_process_cached(self):
        provider_first = get_default_openocd_software_qualification_registry()
        provider_second = get_default_openocd_software_qualification_registry()
        self.assertIsNotNone(provider_first)
        self.assertIs(provider_first, provider_second)

        registry_first = get_default_programming_qualification_registry()
        registry_second = get_default_programming_qualification_registry()
        self.assertIs(registry_first, registry_second)
        self.assertIs(registry_first.summary, registry_first.summary)

    def test_default_registry_preserves_st_65_and_derives_levels_from_routes(self):
        registry = get_default_programming_qualification_registry()
        self.assertEqual(registry.summary["reviewed_exact_icpns"], 78)
        self.assertEqual(registry.summary["catalog_level_2_programmable_exact_icpns"], 77)
        self.assertEqual(
            registry.summary["selector_visibility_rule"],
            "CATALOG_LEVEL_1_OR_HIGHER",
        )
        self.assertEqual(
            registry.summary["job_picker_rule"],
            "CATALOG_LEVEL_2_OR_HIGHER",
        )

        st = registry.describe("STMicroelectronics", "STM32F103ZCT6")
        self.assertEqual(st["identity_state"], "IDENTIFIED")
        self.assertEqual(st["catalog_level"], 2)
        self.assertEqual(st["catalog_level_state"], "PROGRAMMABLE")
        self.assertEqual(st["state"], "SUPPORTED")
        self.assertTrue(st["selector_visible"])
        self.assertEqual(st["provider"]["provider_id"], "openocd-upstream")
        self.assertFalse(st["execution_authorized"])

        packaged = registry.describe("STMicroelectronics", "STM32F103RCY6TR")
        self.assertEqual(packaged["catalog_level"], 2)
        self.assertEqual(packaged["state"], "SUPPORTED")
        self.assertTrue(packaged["job_selectable"])
        self.assertEqual(packaged["programming"]["flash_geometry"]["main_flash_size_bytes"], 256 * 1024)
        self.assertFalse(packaged["execution_authorized"])

        routed = registry.describe("STMicroelectronics", "STM32F407VGT6")
        self.assertEqual(routed["identity_state"], "IDENTIFIED")
        self.assertEqual(routed["catalog_level"], 1)
        self.assertEqual(routed["catalog_level_state"], "PROGRAMMING_CANDIDATE")
        self.assertEqual(routed["state"], "UNKNOWN")
        self.assertTrue(routed["selector_visible"])
        self.assertFalse(routed["job_selectable"])
        self.assertIsNone(routed["provider"])

        h5_candidate = registry.describe("STMicroelectronics", "STM32H503CBT6")
        self.assertEqual(h5_candidate["identity_state"], "IDENTIFIED")
        self.assertEqual(h5_candidate["catalog_level"], 1)
        self.assertEqual(h5_candidate["catalog_level_state"], "PROGRAMMING_CANDIDATE")
        self.assertEqual(h5_candidate["state"], "CANDIDATE")
        self.assertEqual(h5_candidate["route_evidence"], "backend_candidate_registry")
        self.assertTrue(h5_candidate["selector_visible"])
        self.assertFalse(h5_candidate["job_selectable"])

        nxp = registry.describe("NXP", "MCXA132VFM")
        self.assertEqual(nxp["identity_state"], "IDENTIFIED")
        self.assertEqual(nxp["catalog_level"], 1)
        self.assertEqual(nxp["catalog_level_state"], "PROGRAMMING_CANDIDATE")
        self.assertEqual(nxp["state"], "CANDIDATE")
        self.assertTrue(nxp["selector_visible"])
        self.assertFalse(nxp["job_selectable"])
        self.assertIsNone(nxp["provider"])
        self.assertFalse(nxp["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
