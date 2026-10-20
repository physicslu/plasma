"""Gate A only: Microchip source provenance is NOT a Production CFG binding."""
from __future__ import annotations

from dataclasses import replace
import unittest

from plasma_web.device_catalog import DeviceCatalogIntegrityError, get_default_device_catalog
from plasma_web.gateway import _device_search_payload, _microchip_ic_information
from plasma_web.microchip_upstream_openocd_evidence import microchip_upstream_openocd_evidence
from plasma_web.programming_qualification import get_default_programming_qualification_registry


class ICSelectorEvidenceConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = get_default_device_catalog()
        cls.qualification = get_default_programming_qualification_registry()
        cls.microchip = [r for r in cls.catalog.records if r.vendor == "Microchip"]

    def test_all_1015_read_only_upstream_evidence_and_job_denied(self):
        self.assertEqual(len(self.microchip), 1015)
        self.assertEqual(sum(r.family == "PIC32MX" for r in self.microchip), 893)
        self.assertEqual(sum(r.family == "SAML1X" for r in self.microchip), 122)
        for row in self.microchip:
            with self.subTest(icpn=row.icpn):
                evidence = microchip_upstream_openocd_evidence(row)
                q = self.qualification.describe("Microchip", row.icpn)
                self.assertEqual(row.mapping_status, "no_mapping")
                self.assertFalse(row.target_config)
                self.assertEqual(q["catalog_level"], 1)
                self.assertEqual(q["state"], "CANDIDATE")
                self.assertFalse(q["job_selectable"])
                self.assertFalse(q["execution_authorized"])
                self.assertEqual(evidence["scope"], "source_only_non_executable")
                self.assertEqual(evidence["source_version"], "0.12.0")
                self.assertFalse(evidence["executable"])
                self.assertFalse(evidence["production_binding_authorized"])
                self.assertFalse(evidence["physical_programming_qualified"])
                self.assertEqual(evidence["base_device"], row.base_device)
                self.assertEqual(len(evidence["target_cfg"]["git_blob"]), 40)
                if row.family == "PIC32MX":
                    self.assertEqual(evidence["target_cfg"]["path"], "tcl/target/pic32mx.cfg")
                    self.assertEqual(evidence["flash_driver"]["path"], "src/flash/nor/pic32mx.c")
                    self.assertEqual(evidence["device_id"]["kind"], "DEVID")
                else:
                    self.assertEqual(evidence["target_cfg"]["path"], "tcl/target/atsaml1x.cfg")
                    self.assertIsNone(evidence["flash_driver"])
                    self.assertIsNone(evidence["device_id"])

    def test_pic32mx_and_saml1x_details_use_actual_source_and_level(self):
        samples = (
            next(r for r in self.microchip if r.family == "PIC32MX" and
                 r.base_device == "PIC32MX110F016B"),
            next(r for r in self.microchip if r.family == "SAML1X"),
        )
        for row in samples:
            q = self.qualification.describe("Microchip", row.icpn)
            info = _microchip_ic_information(row, q)
            self.assertEqual(info["catalog_level"], q["catalog_level"])
            self.assertEqual(info["programming_state"], q["state"])
            self.assertEqual(info["catalog_level_state"], q["catalog_level_state"])
            self.assertEqual(info["catalog_level"], 1)
            if row.family == "PIC32MX":
                self.assertNotIn("pdf_revision", info["source"])
                self.assertEqual(info["source"]["provider_route_evidence"],
                                 "OpenOCD v0.12.0 pinned driver DEVID")
                self.assertEqual(microchip_upstream_openocd_evidence(row)["device_id"]["value"],
                                 "0x04A07053")
            else:
                self.assertEqual(info["source"]["pdf_revision"], "DS60001513G")
        result = _device_search_payload(samples[0].icpn, limit=30)
        found = [r for r in result["results"] if r["icpn"] == samples[0].icpn]
        self.assertEqual(len(found), 1)
        item = found[0]
        self.assertEqual(item["catalog_level"], 1)
        self.assertFalse(item["job_selectable"])
        self.assertEqual(item["backend"]["mapping_status"], "no_mapping")
        self.assertEqual(item["upstream_openocd_evidence"]["device_id"]["value"], "0x04A07053")
        self.assertEqual(item["microchip_ic_information"]["programming_state"], "CANDIDATE")

    def test_other_manufacturers_have_no_inferred_upstream_route(self):
        for vendor in ("STMicroelectronics", "NXP"):
            row = next(r for r in self.catalog.records if r.vendor == vendor)
            self.assertIsNone(microchip_upstream_openocd_evidence(row))
            q = self.qualification.describe(row.vendor, row.icpn or row.identifier)
            self.assertEqual(q["catalog_level"], q["catalog_level"])

    def test_modified_source_devid_or_binding_fail_closed(self):
        row = next(r for r in self.microchip if r.family == "PIC32MX")
        for altered in (
            replace(row, source_reference=(row.source_reference or "").replace(
                "expected_devid=", "tampered_dev=")),
            replace(row, source_reference=(row.source_reference or "").replace(
                "source_commit=", "modified_commit=")),
            replace(row, mapping_status="mapped", target_config="tcl/target/pic32mx.cfg"),
        ):
            with self.assertRaises(DeviceCatalogIntegrityError):
                microchip_upstream_openocd_evidence(altered)


if __name__ == "__main__":
    unittest.main()
