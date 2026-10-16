from __future__ import annotations

from dataclasses import replace
import unittest

from plasma_web.catalog_promotion_framework import (
    BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED,
    EVIDENCE_BACKEND_CANDIDATE_ROUTE,
    CatalogPromotionFramework,
)
from plasma_web.device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, DeviceCatalogRecord
from plasma_web.programming_qualification import ProgrammingQualificationRegistry
from plasma_web.route_evidence_admission import AdmittedRouteCandidateRegistry, RouteEvidence


def row():
    return DeviceCatalogRecord(
        vendor="ExampleVendor", family="Example", subfamily=None, plasma_series="Example",
        identifier="EXACT123", identifier_kind="manufacturer_part_number",
        cpu_architectures=(), target_config="", openocd_distribution="",
        mapping_status="no_mapping", validation_status="unknown",
        catalog_origin="test", production_admitted=True, base_device="BASE123",
    )


def evidence():
    return RouteEvidence(
        manufacturer="ExampleVendor", exact_icpn="EXACT123", base_device="BASE123",
        identity_source="manufacturer:ordering", identity_sha256="a" * 64,
        base_device_source="manufacturer:base-link", provider_id="openocd",
        provider_version="0.12.0", provider_source_commit="b" * 40,
        route_kind="TARGET", route_source_path="target/example.cfg",
        route_source_blob="c" * 40, applicability_source="manufacturer:device-guide",
        applicability="VERIFIED_BASE_DEVICE",
    )


class RouteEvidenceAdmissionTests(unittest.TestCase):
    def test_candidate_is_l1_without_l2_or_execution(self):
        catalog = DeviceCatalog((row(),))
        candidates = AdmittedRouteCandidateRegistry(catalog, (evidence(),))
        qualification = ProgrammingQualificationRegistry(catalog, (), candidate_registry=candidates)
        q = qualification.describe("ExampleVendor", "EXACT123")
        self.assertEqual(q["catalog_level"], 1)
        self.assertEqual(q["state"], "CANDIDATE")
        self.assertTrue(q["selector_visible"])
        self.assertFalse(q["job_selectable"])
        self.assertFalse(q["execution_authorized"])
        observed = CatalogPromotionFramework(catalog, qualification).observe(row())
        self.assertEqual(observed["promotion_evidence_class"], EVIDENCE_BACKEND_CANDIDATE_ROUTE)
        self.assertEqual(observed["promotion_blocker"], BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED)

    def test_unsafe_or_unverified_evidence_fails_closed(self):
        catalog = DeviceCatalog((row(),))
        for patch in (
            {"exact_icpn": "INVENTED"}, {"base_device": "WRONG"},
            {"identity_sha256": ""}, {"provider_source_commit": ""},
            {"route_source_blob": ""}, {"applicability": "UNVERIFIED"},
            {"applicability_source": ""}, {"route_kind": "DEBUG_ONLY"},
        ):
            with self.subTest(patch=patch):
                with self.assertRaises(DeviceCatalogIntegrityError):
                    AdmittedRouteCandidateRegistry(catalog, (replace(evidence(), **patch),))
        with self.assertRaisesRegex(DeviceCatalogIntegrityError, "duplicate"):
            AdmittedRouteCandidateRegistry(catalog, (evidence(), evidence()))

    def test_no_evidence_stays_l0(self):
        catalog = DeviceCatalog((row(),))
        candidates = AdmittedRouteCandidateRegistry(catalog, ())
        qualification = ProgrammingQualificationRegistry(catalog, (), candidate_registry=candidates)
        q = qualification.describe("ExampleVendor", "EXACT123")
        self.assertEqual(q["catalog_level"], 0)
        self.assertFalse(q["selector_visible"])


if __name__ == "__main__":
    unittest.main()
