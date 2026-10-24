"""Regression for exact 892 SAM D/E Phase-2 Microchip L1 candidates.

This is Product L1 only; no OpenOCD-qualified implementation, job, power,
physical programming, or inherited family defaults.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import unittest

from plasma_web.catalog_promotion_framework import (
    BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED,
    EVIDENCE_BACKEND_CANDIDATE_ROUTE,
    get_default_catalog_promotion_framework,
)
from plasma_web.device_catalog import (
    DeviceCatalog, DeviceCatalogIntegrityError, get_default_device_catalog,
)
from plasma_web.microchip_sam_explicit_devsel_route_evidence import (
    SAM_EXPLICIT_DEVSEL, admitted_sam_explicit_devsel_routes,
)
from plasma_web.programming_qualification import get_default_programming_qualification_registry


class MicrochipPhase2L1Tests(unittest.TestCase):
    def test_892_source_admitted_are_l1_candidate_only(self):
        catalog = get_default_device_catalog()
        registry = get_default_programming_qualification_registry()
        framework = get_default_catalog_promotion_framework()
        phase2 = [r for r in catalog.records if r.vendor == "Microchip"
                  and r.family in {"SAMDCRL0", "SAMD5E5"}]
        self.assertEqual(len(phase2), 892)
        self.assertEqual(Counter(r.family for r in phase2),
                         {"SAMDCRL0": 538, "SAMD5E5": 354})
        self.assertEqual(len(SAM_EXPLICIT_DEVSEL), 84)
        self.assertEqual({r.base_device for r in phase2}, set(SAM_EXPLICIT_DEVSEL))
        candidate = admitted_sam_explicit_devsel_routes(catalog)
        for row in phase2:
            with self.subTest(icpn=row.identifier):
                item = candidate.lookup(row)
                self.assertIsNotNone(item)
                self.assertEqual(item["route_kind"], "DRIVER")
                self.assertFalse(item["executable"])
                self.assertFalse(item["production_binding_authorized"])
                self.assertFalse(item["physical_programming_qualified"])
                self.assertEqual(row.mapping_status, "no_mapping")
                self.assertFalse(row.target_config)
                q = registry.describe("Microchip", row.identifier)
                self.assertEqual(q["catalog_level"], 1)
                self.assertEqual(q["catalog_level_state"], "PROGRAMMING_CANDIDATE")
                self.assertEqual(q["state"], "CANDIDATE")
                self.assertTrue(q["selector_visible"])
                self.assertFalse(q["job_selectable"])
                self.assertFalse(q["execution_authorized"])
                self.assertFalse(q["physical_programming_qualified"])
                observed = framework.observe(row)
                self.assertEqual(observed["promotion_evidence_class"],
                                 EVIDENCE_BACKEND_CANDIDATE_ROUTE)
                self.assertEqual(observed["promotion_blocker"],
                                 BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED)
        product = [r for r in catalog.records if r.vendor == "Microchip"]
        self.assertEqual(len(product), 1907)
        observed = next(r for r in framework.report["manufacturers"]
                        if r["manufacturer"] == "Microchip")
        self.assertEqual(observed["catalog_level_counts"],
                         {"0": 0, "1": 1907, "2": 0, "3": 0})
        self.assertEqual(observed["job_selectable_exact_icpns"], 0)

    def test_negative_tampered_identity_or_devsel_is_rejected(self):
        catalog = get_default_device_catalog()
        rows = list(catalog.records)
        idx = next(i for i, r in enumerate(rows)
                   if r.vendor == "Microchip" and r.family == "SAMDCRL0")
        old = rows[idx]
        self.assertIsNotNone(old.source_reference)
        for alteration in (
            old.source_reference.replace("driver_devsel=", "driver_devsel=0xBAD"),
            old.source_reference.replace("basePartNumber=", "changedBase="),
            old.source_reference.replace("original_response_sha256=", "NO_SHA="),
            old.source_reference.replace("original_replay_index_git_blob=", "fake_blob="),
        ):
            with self.subTest(alteration=alteration[-80:]):
                new = list(rows)
                new[idx] = replace(old, source_reference=alteration)
                unsafe = DeviceCatalog(new, status="production")
                with self.assertRaises(DeviceCatalogIntegrityError):
                    admitted_sam_explicit_devsel_routes(unsafe)

    def test_remaining_656_are_not_in_product(self):
        registry = get_default_programming_qualification_registry()
        catalog = get_default_device_catalog()
        for icpn in (
            "ATSAMR21E19A",  # no direct upstream named part in SAMD driver
        ):
            self.assertIsNone(catalog.resolve("Microchip", icpn))
            q = registry.describe("Microchip", icpn)
            self.assertIsNone(q["catalog_level"])
            self.assertFalse(q["selector_visible"])
            self.assertFalse(q["job_selectable"])


if __name__ == "__main__":
    unittest.main()
