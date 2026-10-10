"""Backend Candidate Registry is display-only and can never admit a device for programming."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from plasma_web import backend_candidate_registry as registry
from plasma_web.device_catalog import (
    DeviceCatalog, DeviceCatalogIntegrityError, get_default_device_catalog,
)
from plasma_web.gateway import _device_search_payload


class BackendCandidateRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = get_default_device_catalog()
        cls.registry = registry.BackendCandidateRegistry(cls.catalog)

    def exact(self, icpn):
        row = self.catalog.resolve("STMicroelectronics", icpn)
        self.assertIsNotNone(row)
        return row

    def test_total_partition_no_duplicate_or_extra_icpn(self):
        self.assertEqual(self.catalog.size, 4629)
        self.assertEqual(self.registry.size, 362)
        all_candidates = [
            (row.identifier, self.registry.lookup(row))
            for row in self.catalog.records if self.registry.lookup(row)
        ]
        self.assertEqual(len(all_candidates), 362)
        self.assertEqual(len({key for key, _ in all_candidates}), 362)
        self.assertEqual(Counter(c["family"] for _, c in all_candidates),
                         {"STM32H5": 190, "STM32C5": 172})

    def test_h5_five_source_groups_and_exact_catalog_flash(self):
        counts = Counter()
        for row in self.catalog.records:
            if row.family != "STM32H5":
                continue
            candidate = self.registry.lookup(row)
            self.assertIsNotNone(candidate, row.identifier)
            counts[candidate["expected_device_id"]] += 1
            self.assertEqual(candidate["flash_driver"], "stm32h5x")
            self.assertEqual(candidate["catalog_flash_kib"], int(row.flash_size.split()[0]))
            self.assertLessEqual(candidate["catalog_flash_kib"], candidate["driver_max_flash_kib"])
            self.assertEqual(candidate["sector_size_kib_source_only"], 8)
            self.assertEqual(candidate["write_alignment_bytes_source_only"], 16)
            self.assertIsNone(candidate["flash_size_readback_kib"])
            self.assertIsNone(candidate["loader_source_path"])
        self.assertEqual(counts, {"0x474": 14, "0x478": 53, "0x47C": 6,
                                  "0x484": 82, "0x47A": 35})

    def test_c5_three_source_loaders_and_exact_dfp_absent_partition(self):
        by_die = Counter()
        matched = Counter()
        for row in self.catalog.records:
            if row.family != "STM32C5":
                continue
            c = self.registry.lookup(row)
            self.assertIsNotNone(c, row.identifier)
            by_die[c["expected_device_id"]] += 1
            matched[c["dfp_exact_variant_status"]] += 1
            self.assertEqual(c["flash_driver"], "stldr")
            self.assertTrue(c["loader_sha256"])
            self.assertFalse(c["loader_installed"])
            self.assertFalse(c["loader_qualified"])
            self.assertEqual(c["fork_default_workarea_bytes"], 32768)
            self.assertGreater(c["dfp_declared_algorithm_ram_bytes"], 32768)
            self.assertIsNone(c["flash_size_readback_kib"])
            self.assertLessEqual(c["catalog_flash_kib"], c["driver_max_flash_kib"])
        self.assertEqual(by_die, {"0x44F": 63, "0x44E": 60, "0x45A": 49})
        self.assertEqual(matched, {"exact": 139, "base_device_only": 33})

    def test_display_only_must_not_mutate_production_mapping(self):
        for row in self.catalog.records:
            c = self.registry.lookup(row)
            if not c:
                continue
            self.assertEqual(row.mapping_status, "no_mapping")
            self.assertFalse(row.target_config)
            self.assertEqual(c["production_mapping_status"], "no_mapping")
            self.assertEqual(c["status"], "research_only")
            for field in ("executable", "production_binding_authorized",
                          "hardware_runtime_ready", "physical_programming_qualified"):
                self.assertIs(c[field], False, (row.identifier, field))
            self.assertTrue(c["blockers"])

    def test_mapped_or_non_candidate_must_not_inherit_vendor_research(self):
        for icpn in ("STM32F103C8T6", "STM32F301C6T6", "STM32N657X0Q3", "STM32WL3"):
            r = self.catalog.resolve("STMicroelectronics", icpn)
            if r is not None:
                self.assertIsNone(self.registry.lookup(r), icpn)
        for r in self.catalog.records:
            if r.mapping_status == "mapped" or r.family in {"STM32N6", "STM32WB0", "STM32WL3"}:
                self.assertIsNone(self.registry.lookup(r))

    def test_current_api_keeps_mapping_separate_from_candidate(self):
        with patch("plasma_web.gateway.get_default_device_catalog", return_value=self.catalog), \
             patch("plasma_web.gateway.get_default_backend_candidate_registry", return_value=self.registry):
            h5 = _device_search_payload("STM32H503CBT6", 3)
            c5 = _device_search_payload("STM32C531CBT3TR", 3)
            f1 = _device_search_payload("STM32F103C8T6", 3)
        # Exact match ranks first, but the search API also returns matching
        # packing variants such as an ICPN ending in TR. Preserve that contract.
        for payload, requested in ((h5, "STM32H503CBT6"),
                                   (c5, "STM32C531CBT3TR"),
                                   (f1, "STM32F103C8T6")):
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["catalog_size"], self.catalog.size)
            self.assertGreaterEqual(payload["count"], 1)
            self.assertEqual(payload["results"][0]["icpn"], requested)
        for payload in (h5, c5):
            result = payload["results"][0]
            self.assertEqual(result["backend"]["mapping_status"], "no_mapping")
            self.assertFalse(result["backend"]["target_config"])
            self.assertEqual(result["backend_candidate"]["status"], "research_only")
            self.assertFalse(result["backend_candidate"]["executable"])
            self.assertEqual(result["physical_validation"]["ppu_status"], "no_evidence")
            self.assertEqual(result["physical_validation"]["socket_status"], "no_evidence")
        self.assertIsNone(f1["results"][0]["backend_candidate"])
        self.assertEqual(f1["results"][0]["backend"]["mapping_status"], "mapped")

    def test_api_still_returns_only_admitted_exact_icpns(self):
        with patch("plasma_web.gateway.get_default_device_catalog", return_value=self.catalog), \
             patch("plasma_web.gateway.get_default_backend_candidate_registry", return_value=self.registry):
            payload = _device_search_payload("STM32H5", 100)
        self.assertEqual(payload["count"], 100)
        self.assertEqual({r["family"] for r in payload["results"]}, {"STM32H5"})
        self.assertTrue(all(r["icpn"] and r["catalog"]["scope"] == "production_admitted"
                            for r in payload["results"]))
        self.assertTrue(all(r["backend_candidate"] and
                            r["backend_candidate"]["status"] == "research_only"
                            for r in payload["results"]))

    def test_source_integrity_fails_closed_if_h5_file_drifted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            location = root / registry.H5_FACTS
            location.parent.mkdir(parents=True)
            location.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "source lock mismatch"):
                registry._locked_json(root, registry.H5_FACTS, registry.H5_FACTS_BLOB)

    def test_source_integrity_fails_closed_if_crosswalk_changed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            location = root / registry.C5_CROSSWALK
            location.parent.mkdir(parents=True)
            location.write_text("icpn,candidate_dev_id\nSTM32C531CBT3TR,0x45A\n", encoding="utf-8")
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "source lock mismatch"):
                registry._locked_bytes(root, registry.C5_CROSSWALK, registry.C5_CROSSWALK_BLOB)

    def test_missing_authority_file_is_a_hard_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "missing"):
                registry._locked_json(Path(temp), registry.H5_FACTS, registry.H5_FACTS_BLOB)

    def test_alternate_catalog_without_h5_c5_has_no_candidate_injection(self):
        from plasma_web.device_catalog import DeviceCatalogRecord
        alternate = DeviceCatalog([
            DeviceCatalogRecord(
                vendor="OtherVendor", family="MCU", subfamily=None,
                plasma_series="MCU", identifier="ABC123",
                identifier_kind="manufacturer_part_number", cpu_architectures=(),
                target_config="", openocd_distribution="", mapping_status="no_mapping",
                validation_status="no_evidence", catalog_origin="test",
                production_admitted=True,
            )
        ])
        scoped = registry.BackendCandidateRegistry(alternate)
        self.assertEqual(scoped.size, 0)

    def test_forged_unadmitted_or_wrong_mapping_never_returns_candidate(self):
        row = self.exact("STM32H503CBT6")
        from dataclasses import replace
        self.assertIsNone(self.registry.lookup(replace(row, production_admitted=False)))
        self.assertIsNone(self.registry.lookup(replace(row, mapping_status="mapped")))

    def test_documented_source_commits_are_pinned(self):
        h5 = self.registry.lookup(self.exact("STM32H503CBT6"))
        c5 = self.registry.lookup(self.exact("STM32C531CBT6"))
        self.assertEqual(h5["source_commit"], "c8d973bdad9a6fddb51459eda109b3b95d23b57a")
        self.assertEqual(c5["source_commit"], h5["source_commit"])
        self.assertEqual(c5["dfp_source_commit"], "a5f65bc64535cfa723e9d25f58d7ce23d0937aed")

if __name__ == "__main__":
    unittest.main()
