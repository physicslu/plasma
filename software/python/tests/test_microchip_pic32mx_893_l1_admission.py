"""Real Product canonical admission regression for 893 Microchip PIC32MX ICPNs.

Firmware, PL, HIL, OpenOCD erase/write/verify and Job entitlement are excluded.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from plasma_web.catalog_promotion_framework import (
    BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED,
    EVIDENCE_BACKEND_CANDIDATE_ROUTE,
    get_default_catalog_promotion_framework,
)
from plasma_web.device_catalog import (
    DeviceCatalog, DeviceCatalogIntegrityError, get_default_device_catalog,
)
from plasma_web.microchip_pic32mx_route_evidence import (
    PINNED_VERSION, PIC32MX_BASE_DEVID, SOURCE_MAP_GIT_BLOB,
    admitted_pic32mx_openocd_devid_routes,
)
from plasma_web.programming_qualification import get_default_programming_qualification_registry


ROOT = Path(__file__).resolve().parents[3]
PINNED_SOURCE = (
    ROOT / "data/device-catalog/research/microchip-pic32mx-85-devid-route-v1.json"
)


class PIC32MX893ProductionL1AdmissionTests(unittest.TestCase):
    def test_pinned_source_lock_is_identical_to_route_table(self):
        raw = PINNED_SOURCE.read_bytes()
        digest = hashlib.sha1(
            f"blob {len(raw)}\0".encode() + raw,
            usedforsecurity=False,
        ).hexdigest()
        self.assertEqual(digest, SOURCE_MAP_GIT_BLOB)
        source = json.loads(raw)
        self.assertEqual(source["provider_version"], PINNED_VERSION)
        self.assertEqual(source["base_device_devid"], PIC32MX_BASE_DEVID)
        self.assertEqual(source["expected_exact_icpn_count"], 893)
        self.assertEqual(source["base_device_count"], 85)
        self.assertFalse(source["production_binding_authorized"])
        self.assertFalse(source["openocd_software_supported_claimed"])

    def test_exact_manifest_identities_promote_only_to_l1(self):
        catalog = get_default_device_catalog()
        rows = [r for r in catalog.records if r.vendor == "Microchip"
                and r.family == "PIC32MX"]
        self.assertEqual(len(rows), 893)
        self.assertEqual(len(set(r.identifier for r in rows)), 893)
        candidates = admitted_pic32mx_openocd_devid_routes(catalog)
        qualification = get_default_programming_qualification_registry()
        promotion = get_default_catalog_promotion_framework()
        for record in rows:
            with self.subTest(icpn=record.identifier):
                candidate = candidates.lookup(record)
                self.assertIsNotNone(candidate)
                self.assertEqual(candidate["route_kind"], "DRIVER")
                self.assertFalse(candidate["production_binding_authorized"])
                self.assertFalse(candidate["executable"])
                self.assertFalse(candidate["physical_programming_qualified"])
                self.assertEqual(record.mapping_status, "no_mapping")
                self.assertFalse(record.target_config)
                q = qualification.describe(record.vendor, record.identifier)
                self.assertEqual(q["catalog_level"], 1)
                self.assertEqual(q["catalog_level_state"], "PROGRAMMING_CANDIDATE")
                self.assertEqual(q["state"], "CANDIDATE")
                self.assertTrue(q["selector_visible"])
                self.assertFalse(q["job_selectable"])
                self.assertFalse(q["execution_authorized"])
                observed = promotion.observe(record)
                self.assertEqual(observed["promotion_evidence_class"],
                                 EVIDENCE_BACKEND_CANDIDATE_ROUTE)
                self.assertEqual(observed["promotion_blocker"],
                                 BACKEND_CANDIDATE_NOT_PROVIDER_QUALIFIED)
        summary = next(x for x in promotion.report["manufacturers"]
                       if x["manufacturer"] == "Microchip")
        self.assertEqual(summary["catalog_level_counts"],
                         {"0": 0, "1": 1015, "2": 0, "3": 0})
        self.assertEqual(summary["job_selectable_exact_icpns"], 0)

    def test_tampering_pinned_exact_identity_or_device_id_fails_closed(self):
        catalog = get_default_device_catalog()
        rows = list(catalog.records)
        idx = next(i for i, row in enumerate(rows)
                   if row.vendor == "Microchip" and row.family == "PIC32MX")
        original = rows[idx]
        self.assertIsNotNone(original.source_reference)
        for new_ref in (
            original.source_reference.replace("expected_devid=", "expected_devid=0xBAD"),
            original.source_reference.replace("original_response_sha256=", "invalid_hash="),
            original.source_reference.replace("basePartNumber=", "unverifiedBase="),
        ):
            with self.subTest(source=new_ref[-120:]):
                mutated = rows.copy()
                mutated[idx] = replace(original, source_reference=new_ref)
                bad = DeviceCatalog(mutated, status="production")
                with self.assertRaises(DeviceCatalogIntegrityError):
                    admitted_pic32mx_openocd_devid_routes(bad)


if __name__ == "__main__":
    unittest.main()
