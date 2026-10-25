from __future__ import annotations

import unittest

from plasma_web.catalog_promotion_framework import (
    BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED,
    EVIDENCE_BACKEND_CANDIDATE_ROUTE,
    get_default_catalog_promotion_framework,
)
from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.microchip_saml1x_route_evidence import (
    DOCUMENT_REVISION,
    PDF_URL,
    admitted_saml1x_official_programming_routes,
)
from plasma_web.microchip_phase1_admission_guard import PDF_SHA
from plasma_web.programming_qualification import (
    get_default_programming_qualification_registry,
)


class MicrochipSAML1XOfficialL1Tests(unittest.TestCase):
    def test_source_pinned_mcp_identity_with_official_programming_path_is_l1(self):
        catalog = get_default_device_catalog()
        rows = [r for r in catalog.records if r.vendor == "Microchip" and r.family == "SAML1X"]
        self.assertEqual(len(rows), 122)
        candidates = admitted_saml1x_official_programming_routes(catalog)
        registry = get_default_programming_qualification_registry()
        observer = get_default_catalog_promotion_framework()
        for row in rows:
            with self.subTest(icpn=row.identifier):
                item = candidates.lookup(row)
                self.assertIsNotNone(item)
                self.assertEqual(item["route_kind"], "OFFICIAL_PATH")
                self.assertEqual(item["route_source_url"], PDF_URL)
                self.assertEqual(item["route_source_sha256"], PDF_SHA)
                self.assertFalse(item["executable"])
                q = registry.describe(row.vendor, row.identifier)
                self.assertEqual(q["catalog_level"], 1)
                self.assertEqual(q["state"], "CANDIDATE")
                self.assertTrue(q["selector_visible"])
                self.assertFalse(q["job_selectable"])
                self.assertFalse(q["execution_authorized"])
                self.assertIsNone(q["provider"])
                report = observer.observe(row)
                self.assertEqual(report["promotion_evidence_class"],
                                 EVIDENCE_BACKEND_CANDIDATE_ROUTE)
                self.assertEqual(report["promotion_blocker"],
                                 BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED)
        summary = next(x for x in observer.report["manufacturers"]
                       if x["manufacturer"] == "Microchip")
        self.assertEqual(summary["catalog_level_counts"],
                         {"0": 0, "1": 1907, "2": 0, "3": 0})
        self.assertEqual(summary["job_selectable_exact_icpns"], 0)

    def test_legacy_unadmitted_research_icpns_remain_out_of_product(self):
        registry = get_default_programming_qualification_registry()
        for suffix in (
            "ATSAML10D16A-MZTVAO", "ATSAML10E16A-MZTVAO",
            "ATSAML10E16A-MZVAO", "ATSAML11E16A-MZTVAO",
        ):
            with self.subTest(icpn=suffix):
                q = registry.describe("Microchip", suffix)
                self.assertEqual(q["identity_state"], "NOT_IDENTIFIED")
                self.assertIsNone(q["catalog_level"])
                self.assertFalse(q["selector_visible"])

    def test_official_document_source_is_versioned(self):
        self.assertEqual(DOCUMENT_REVISION, "DS60001513G")
        self.assertEqual(PDF_SHA,
                         "ee9c04451141173b787374388ddf9b607a5a569415ae85d9b5715237fd1cbb9e")


if __name__ == "__main__":
    unittest.main()
