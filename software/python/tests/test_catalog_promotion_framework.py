from __future__ import annotations

import unittest

from plasma_web.catalog_promotion_framework import (
    BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED,
    EDGE_L0_TO_L1,
    EDGE_L1_TO_L2,
    EDGE_L2_TO_L3,
    EVIDENCE_BACKEND_CANDIDATE_ROUTE,
    EVIDENCE_CATALOG_MAPPED_ROUTE,
    EVIDENCE_IDENTITY_ONLY,
    EVIDENCE_REVIEWED_PROGRAMMING_PROVIDER,
    MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED,
    NO_PROGRAMMING_ROUTE_EVIDENCE,
    PLASMA_VERIFIED_CONFIGURATION_MISSING,
    PROVIDER_QUALIFICATION_BLOCKED,
    CatalogPromotionFramework,
    get_default_catalog_promotion_framework,
)
from plasma_web.device_catalog import DeviceCatalog, DeviceCatalogRecord
from plasma_web.programming_qualification import ProgrammingQualificationRegistry


def _record(
    identifier: str,
    *,
    vendor: str = "ExampleVendor",
    mapped: bool = False,
) -> DeviceCatalogRecord:
    return DeviceCatalogRecord(
        vendor=vendor,
        family="Example",
        subfamily=None,
        plasma_series="Example",
        identifier=identifier,
        identifier_kind="manufacturer_part_number",
        cpu_architectures=(),
        target_config="target/example.cfg" if mapped else "",
        openocd_distribution="example",
        mapping_status="mapped" if mapped else "no_mapping",
        validation_status="unknown",
        catalog_origin="test",
        production_admitted=True,
    )


class _CandidateRegistry:
    def lookup(self, row: DeviceCatalogRecord):
        if row.identifier == "CANDIDATE1":
            return {
                "provider_id": "research-provider",
                "status": "research_only",
            }
        return None


class _StateProvider:
    reviewed_exact_keys = (
        ("ExampleVendor", "BLOCKED1"),
        ("ExampleVendor", "SUPPORTED1"),
    )

    def lookup(self, manufacturer: str, exact_icpn: str):
        if (manufacturer, exact_icpn) in self.reviewed_exact_keys:
            return {"software_state": self._state(exact_icpn)}
        return None

    @staticmethod
    def _state(exact_icpn: str) -> str:
        return "SUPPORTED" if exact_icpn == "SUPPORTED1" else "BLOCKED"

    def describe(self, manufacturer: str, exact_icpn: str):
        state = self._state(exact_icpn)
        return {
            "software_state": state,
            "reviewed": True,
            "provider": {
                "provider_id": "fake",
                "version": "1",
            },
            "operations": {},
            "programming": None,
            "installed_runtime_attested": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }


class CatalogPromotionFrameworkTests(unittest.TestCase):
    def test_vendor_neutral_taxonomy_observes_canonical_levels_without_promoting(self):
        catalog = DeviceCatalog(
            (
                _record("DISCOVERED1"),
                _record("MAPPED1", mapped=True),
                _record("CANDIDATE1"),
                _record("BLOCKED1", mapped=True),
                _record("SUPPORTED1", mapped=True),
            )
        )
        qualification = ProgrammingQualificationRegistry(
            catalog,
            (_StateProvider(),),
            candidate_registry=_CandidateRegistry(),
        )
        framework = CatalogPromotionFramework(catalog, qualification)

        observed = {
            record.identifier: framework.observe(record)
            for record in catalog.records
        }

        self.assertEqual(observed["DISCOVERED1"]["catalog_level"], 0)
        self.assertEqual(
            observed["DISCOVERED1"]["promotion_evidence_class"],
            EVIDENCE_IDENTITY_ONLY,
        )
        self.assertEqual(
            observed["DISCOVERED1"]["promotion_blocker"],
            NO_PROGRAMMING_ROUTE_EVIDENCE,
        )

        self.assertEqual(observed["MAPPED1"]["catalog_level"], 1)
        self.assertEqual(
            observed["MAPPED1"]["promotion_evidence_class"],
            EVIDENCE_CATALOG_MAPPED_ROUTE,
        )
        self.assertEqual(
            observed["MAPPED1"]["promotion_blocker"],
            MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED,
        )

        self.assertEqual(observed["CANDIDATE1"]["catalog_level"], 1)
        self.assertEqual(
            observed["CANDIDATE1"]["promotion_evidence_class"],
            EVIDENCE_BACKEND_CANDIDATE_ROUTE,
        )
        self.assertEqual(
            observed["CANDIDATE1"]["promotion_blocker"],
            BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED,
        )

        self.assertEqual(observed["BLOCKED1"]["catalog_level"], 1)
        self.assertEqual(
            observed["BLOCKED1"]["promotion_evidence_class"],
            EVIDENCE_REVIEWED_PROGRAMMING_PROVIDER,
        )
        self.assertEqual(
            observed["BLOCKED1"]["promotion_blocker"],
            PROVIDER_QUALIFICATION_BLOCKED,
        )

        self.assertEqual(observed["SUPPORTED1"]["catalog_level"], 2)
        self.assertEqual(
            observed["SUPPORTED1"]["promotion_evidence_class"],
            EVIDENCE_REVIEWED_PROGRAMMING_PROVIDER,
        )
        self.assertEqual(
            observed["SUPPORTED1"]["promotion_blocker"],
            PLASMA_VERIFIED_CONFIGURATION_MISSING,
        )
        self.assertFalse(observed["SUPPORTED1"].get("execution_authorized", False))

        report = framework.report
        self.assertEqual(
            report["catalog_level_counts"],
            {"0": 1, "1": 3, "2": 1, "3": 0},
        )
        self.assertEqual(
            report["promotion_evidence_counts"],
            {
                EVIDENCE_BACKEND_CANDIDATE_ROUTE: 1,
                EVIDENCE_CATALOG_MAPPED_ROUTE: 1,
                EVIDENCE_IDENTITY_ONLY: 1,
                EVIDENCE_REVIEWED_PROGRAMMING_PROVIDER: 2,
            },
        )
        self.assertEqual(report["selector_visible_exact_icpns"], 4)
        self.assertEqual(report["job_selectable_exact_icpns"], 1)
        self.assertFalse(report["execution_authorized_by_framework"])
        self.assertEqual(
            report["promotion_blocker_counts"][EDGE_L0_TO_L1],
            {NO_PROGRAMMING_ROUTE_EVIDENCE: 1},
        )
        self.assertEqual(
            report["promotion_blocker_counts"][EDGE_L1_TO_L2],
            {
                BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED: 1,
                MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED: 1,
                PROVIDER_QUALIFICATION_BLOCKED: 1,
            },
        )
        self.assertEqual(
            report["promotion_blocker_counts"][EDGE_L2_TO_L3],
            {PLASMA_VERIFIED_CONFIGURATION_MISSING: 1},
        )

    def test_current_cross_manufacturer_matrix_is_one_canonical_projection(self):
        report = get_default_catalog_promotion_framework().report
        by_manufacturer = {
            row["manufacturer"]: row
            for row in report["manufacturers"]
        }

        self.assertEqual(report["manufacturer_count"], 3)
        self.assertEqual(report["discovered_exact_icpns"], 4975)
        self.assertEqual(
            report["catalog_level_counts"],
            {"0": 437, "1": 4489, "2": 49, "3": 0},
        )
        self.assertEqual(
            report["promotion_evidence_counts"],
            {
                EVIDENCE_BACKEND_CANDIDATE_ROUTE: 362,
                EVIDENCE_CATALOG_MAPPED_ROUTE: 4127,
                EVIDENCE_IDENTITY_ONLY: 437,
                EVIDENCE_REVIEWED_PROGRAMMING_PROVIDER: 49,
            },
        )
        self.assertEqual(report["selector_visible_exact_icpns"], 4538)
        self.assertEqual(report["job_selectable_exact_icpns"], 49)

        self.assertEqual(
            by_manufacturer["STMicroelectronics"]["catalog_level_counts"],
            {"0": 103, "1": 4477, "2": 49, "3": 0},
        )
        self.assertEqual(
            by_manufacturer["NXP"]["catalog_level_counts"],
            {"0": 212, "1": 12, "2": 0, "3": 0},
        )
        self.assertEqual(
            by_manufacturer["Microchip"]["catalog_level_counts"],
            {"0": 122, "1": 0, "2": 0, "3": 0},
        )

        self.assertEqual(
            by_manufacturer["STMicroelectronics"]["promotion_blocker_counts"][EDGE_L1_TO_L2],
            {
                BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED: 362,
                MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED: 4115,
            },
        )
        self.assertEqual(
            by_manufacturer["NXP"]["promotion_blocker_counts"][EDGE_L1_TO_L2],
            {MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED: 12},
        )
        self.assertEqual(
            by_manufacturer["Microchip"]["promotion_blocker_counts"][EDGE_L0_TO_L1],
            {NO_PROGRAMMING_ROUTE_EVIDENCE: 122},
        )
        self.assertEqual(
            report["promotion_blocker_counts"][EDGE_L2_TO_L3],
            {PLASMA_VERIFIED_CONFIGURATION_MISSING: 49},
        )


if __name__ == "__main__":
    unittest.main()
