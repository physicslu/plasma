"""Host-only, negative-safe admission of 111 MCX A exact commercial ICPNs."""
from __future__ import annotations

from dataclasses import replace
import unittest

from plasma_web.device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, get_default_device_catalog
from plasma_web.nxp_mcxa_route_evidence import (
    COHORT_SHA256, PROCESSORS_SHA256, WORKFLOW_SHA256,
    admitted_nxp_mcxa_official_programming_routes,
)
from plasma_web.programming_qualification import get_default_programming_qualification_registry


class McxaRouteEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = get_default_device_catalog()

    def test_111_exact_icpns_and_8_a18_holds(self) -> None:
        routes = admitted_nxp_mcxa_official_programming_routes(self.catalog)
        registry = get_default_programming_qualification_registry()
        mcxa = [r for r in self.catalog.records
                if r.vendor == "NXP" and r.family == "MCX" and r.identifier.startswith("MCXA")]
        admitted = [r for r in mcxa if routes.lookup(r) is not None]
        held = [r for r in mcxa if routes.lookup(r) is None]
        self.assertEqual((len(mcxa), len(admitted), len(held)), (119, 111, 8))
        self.assertEqual({r.identifier[:7] for r in held}, {"MCXA185", "MCXA186"})
        self.assertEqual(len({r.identifier[:7] for r in admitted}), 28)
        self.assertEqual(len(WORKFLOW_SHA256), 64)
        self.assertEqual(len(PROCESSORS_SHA256), 64)
        self.assertEqual(len(COHORT_SHA256), 64)
        for row in mcxa:
            q = registry.describe("NXP", row.identifier)
            self.assertEqual(q["catalog_level"], 1 if row in admitted else 0)
            self.assertEqual(q["state"], "CANDIDATE" if row in admitted else "UNKNOWN")
            self.assertEqual(q["selector_visible"], row in admitted)
            self.assertFalse(q["job_selectable"])
            self.assertFalse(q["execution_authorized"])
            self.assertFalse(q["hardware_runtime_ready"])
        self.assertEqual(registry.describe("NXP", "MCXA255VLH")["catalog_level"], 1)
        self.assertEqual(registry.describe("NXP", "MCXA185VLH")["catalog_level"], 0)

    def test_source_and_cohort_tampering_fail_closed(self) -> None:
        base = list(self.catalog.records)
        target = next(i for i, row in enumerate(base) if row.identifier == "MCXA132VFM")
        row = base[target]
        for change in (
            {"source_authority": "https://example.invalid/part/MCXA132VFM"},
            {"source_reference": "unreviewed page"},
            {"base_device": "MCXA132"},
            {"target_config": "tcl/target/unreviewed.cfg"},
            {"mapping_status": "mapped"},
        ):
            with self.subTest(change=change):
                tampered = list(base)
                tampered[target] = replace(row, **change)
                catalog = DeviceCatalog(tampered, status="production")
                with self.assertRaises(DeviceCatalogIntegrityError):
                    admitted_nxp_mcxa_official_programming_routes(catalog)
        trimmed = [r for r in base if r.identifier != "MCXA132VFM"]
        with self.assertRaisesRegex(DeviceCatalogIntegrityError, "119 exact"):
            admitted_nxp_mcxa_official_programming_routes(DeviceCatalog(trimmed, status="production"))


if __name__ == "__main__":
    unittest.main()
