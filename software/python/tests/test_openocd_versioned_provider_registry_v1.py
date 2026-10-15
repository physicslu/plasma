"""Software-only multi-provider OpenOCD metadata with immutable offline H5 build evidence."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from plasma_web.backend_provenance import load_source_authorities
from plasma_web.device_catalog import DeviceCatalogIntegrityError, get_default_device_catalog
from plasma_web.openocd_provider_registry import (
    ROOT, H5_BUILD_EXPECTED, OpenOCDProviderRegistry, _h5_build_evidence,
    get_default_openocd_provider_registry,
    offline_build_correlates,
)


class VersionedProviderRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = get_default_device_catalog()
        cls.provider = OpenOCDProviderRegistry(cls.catalog)

    def describe(self, part):
        return self.provider.describe("STMicroelectronics", part)

    def test_all_4629_exact_icpns_and_independent_states(self):
        self.assertEqual(self.catalog.size, 4975)
        self.assertEqual(sum(row.vendor == "STMicroelectronics" for row in self.catalog.records), 4629)
        self.assertEqual(sum(row.vendor == "NXP" and row.family == "KL25" for row in self.catalog.records), 12)
        self.assertEqual(sum(row.vendor == "NXP" and row.family == "MCX" and row.mapping_status == "no_mapping" for row in self.catalog.records),196)
        self.assertEqual(sum(row.vendor == "NXP" and row.family == "K32L2" and row.mapping_status == "no_mapping" for row in self.catalog.records),16)
        self.assertEqual(self.provider.inventory, {
            "openocd-upstream": 4176,
            "openocd-st-h5-research": 190,
            "openocd-st-c5-stldr-research": 172,
        })
        per_family = Counter()
        no_provider = 0
        for row in self.catalog.records:
            bindings = self.provider.describe(row.vendor, row.identifier)
            self.assertLessEqual(len(bindings), 1)  # Current data, not a one-provider model limit.
            if not bindings:
                no_provider += 1
            else:
                per_family[(row.family, bindings[0]["mapping_status"])] += 1
            for binding in bindings:
                self.assertFalse(binding["executable"])
                self.assertFalse(binding["hardware_runtime_ready"])
                self.assertFalse(binding["production_write_authorized"])
                self.assertIsNone(binding["installed_binary_sha256"])
                self.assertIsNone(binding["installed_runtime_id"])
                self.assertEqual(binding["qualified_hardware_operations"], [])
        self.assertEqual(no_provider, 315)
        self.assertEqual(per_family[("STM32H5", "candidate")], 190)
        self.assertEqual(per_family[("STM32C5", "candidate")], 172)

    def test_upstream_mapped_source_version_not_real_flash_qualification(self):
        record = self.describe("STM32F103C8T6")[0]
        self.assertEqual(record["provider_id"], "openocd-upstream")
        self.assertEqual(record["mapping_status"], "mapped")
        self.assertEqual(record["source_version"], "0.12.0")
        self.assertEqual(record["source_commit"], "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c")
        self.assertEqual(record["declared_release_runtime_id"], "0.12.0-9ea7f3d647c8")
        self.assertEqual(record["target_config"], "tcl/target/stm32f1x.cfg")
        self.assertIsNone(record["flash_driver"])
        self.assertEqual(record["software_build_evidence"], [])
        self.assertFalse(record["real_ic_erase_program_verify"])

    def test_h5_all_190_have_two_independent_build_artifacts(self):
        seen = 0
        for row in self.catalog.records:
            if row.family != "STM32H5":
                continue
            seen += 1
            p = self.provider.describe(row.vendor, row.identifier)[0]
            self.assertEqual(p["provider_id"], "openocd-st-h5-research")
            self.assertEqual(p["flash_driver"], "stm32h5x")
            self.assertEqual(p["mapping_status"], "candidate")
            self.assertEqual(p["target_config"], "tcl/target/stm32h5x.cfg")
            self.assertEqual(p["source_version"], "0.12.0")
            self.assertEqual(len(p["software_build_evidence"]), 2)
            builds = {v["architecture"]: v for v in p["software_build_evidence"]}
            self.assertEqual(set(builds), set(H5_BUILD_EXPECTED))
            self.assertEqual({v["runtime_id"] for v in builds.values()},
                             {"0.12.0-c8d973bdad9a"})
            self.assertEqual(len({v["artifact_sha256"] for v in builds.values()}), 2)
            self.assertEqual(len({v["payload_sha256"] for v in builds.values()}), 2)
            for v in builds.values():
                self.assertIsNone(v["binary_sha256"])
                self.assertFalse(v["published_binary"])
                self.assertFalse(p["hardware_runtime_ready"])
        self.assertEqual(seen, 190)

    def test_c5_all_172_stldr_candidates_have_no_h5_build_credit(self):
        seen = 0
        for row in self.catalog.records:
            if row.family != "STM32C5":
                continue
            seen += 1
            p = self.provider.describe(row.vendor, row.identifier)[0]
            self.assertEqual(p["provider_id"], "openocd-st-c5-stldr-research")
            self.assertEqual(p["flash_driver"], "stldr")
            self.assertEqual(p["mapping_status"], "candidate")
            self.assertIsNone(p["source_version"])
            self.assertIsNone(p["declared_release_runtime_id"])
            self.assertEqual(p["software_build_evidence"], [])
            self.assertFalse(p["executable"])
        self.assertEqual(seen, 172)

    def test_same_runtime_id_different_sha_must_not_share_validation(self):
        record = self.describe("STM32H503CBT6")[0]
        a,b = record["software_build_evidence"]
        self.assertEqual(a["runtime_id"], b["runtime_id"])
        self.assertNotEqual(a["artifact_sha256"], b["artifact_sha256"])
        self.assertNotEqual(a["payload_sha256"], b["payload_sha256"])
        original = {
            "source_commit": record["source_commit"],
            "architecture": a["architecture"],
            "runtime_id": a["runtime_id"],
            "artifact_sha256": a["artifact_sha256"],
            "payload_sha256": a["payload_sha256"],
        }
        self.assertTrue(offline_build_correlates(record, original))
        swapped = dict(original, artifact_sha256=b["artifact_sha256"])
        self.assertFalse(offline_build_correlates(record, swapped))
        swapped = dict(original, source_commit="0"*40)
        self.assertFalse(offline_build_correlates(record, swapped))
        swapped = dict(original, architecture=b["architecture"])
        self.assertFalse(offline_build_correlates(record, swapped))
        self.assertFalse(offline_build_correlates(self.describe("STM32C531CBT6")[0], original))
        self.assertFalse(offline_build_correlates(self.describe("STM32F103C8T6")[0], original))

    def test_malformed_source_or_security_promotion_fails_closed(self):
        upstream, gap = load_source_authorities(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"data/device-catalog/research/st-h5-offline-runtime-evidence-v1.json"
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps({"schema_version": 1, "hardware_runtime_ready": True}))
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "blob drift"):
                _h5_build_evidence(Path(tmp), gap["candidate_st_fork"])
        x = copy.deepcopy(self.describe("STM32H503CBT6")[0])
        x["executable"] = True
        with self.assertRaisesRegex(DeviceCatalogIntegrityError, "cannot impersonate"):
            OpenOCDProviderRegistry._guard_distinct_providers([x])
        clean = self.describe("STM32H503CBT6")[0]
        with self.assertRaisesRegex(DeviceCatalogIntegrityError, "duplicate provider_id"):
            OpenOCDProviderRegistry._guard_distinct_providers([clean, clean])

    def test_returned_metadata_cannot_mutate_shared_registry(self):
        a = self.describe("STM32H503CBT6")
        a[0]["software_build_evidence"][0]["artifact_sha256"] = "0"*64
        a[0]["qualified_hardware_operations"].append("erase")
        b = self.describe("STM32H503CBT6")
        self.assertNotEqual(b[0]["software_build_evidence"][0]["artifact_sha256"], "0"*64)
        self.assertEqual(b[0]["qualified_hardware_operations"], [])

    def test_gateway_adds_read_only_provider_list_without_authorizing_job(self):
        from plasma_web.backend_candidate_registry import BackendCandidateRegistry
        from plasma_web.gateway import _device_search_payload
        candidates = BackendCandidateRegistry(self.catalog)
        with (
            patch("plasma_web.gateway.get_default_device_catalog", return_value=self.catalog),
            patch("plasma_web.gateway.get_default_backend_candidate_registry", return_value=candidates),
            patch("plasma_web.gateway.get_default_openocd_provider_registry", return_value=self.provider),
        ):
            for part, expected in (
                ("STM32F103C8T6", "openocd-upstream"),
                ("STM32H503CBT6", "openocd-st-h5-research"),
                ("STM32C531CBT6", "openocd-st-c5-stldr-research"),
            ):
                payload = _device_search_payload(part, 1)
                row = payload["results"][0]
                self.assertEqual(row["icpn"], part)
                self.assertEqual(len(row["backend_providers"]), 1)
                self.assertEqual(row["backend_providers"][0]["provider_id"], expected)
                # PR #806 source reference and PR #807 provider array coexist.
                self.assertEqual(row["backend_source_reference"]["provider_id"], expected)
                self.assertEqual(row["backend_source_reference"]["source_commit"],
                                 row["backend_providers"][0]["source_commit"])
                self.assertIsNone(row["backend_source_reference"]["installed_binary_sha256"])
                self.assertFalse(row["backend_source_reference"]["hardware_runtime_ready"])
                self.assertFalse(row["backend_providers"][0]["executable"])
                self.assertFalse(row["backend_providers"][0]["production_write_authorized"])
                self.assertFalse(row["backend_providers"][0]["hardware_runtime_ready"])
            h5 = _device_search_payload("STM32H503CBT6", 1)["results"][0]
            self.assertEqual(h5["backend"]["mapping_status"], "no_mapping")
            self.assertEqual(h5["backend"]["target_config"], "")

    def test_slim_ppu_without_optional_metadata_has_no_provider_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("plasma_web.openocd_provider_registry.ROOT", Path(tmp)):
                get_default_openocd_provider_registry.cache_clear()
                self.assertIsNone(get_default_openocd_provider_registry())
            get_default_openocd_provider_registry.cache_clear()

    def test_no_fabricated_provider_for_wrong_vendor_or_unknown_icpn(self):
        self.assertEqual(self.provider.describe("OtherVendor", "STM32H503CBT6"), [])
        self.assertEqual(self.provider.describe("STMicroelectronics", "NONEXISTENT"), [])


if __name__ == "__main__":
    unittest.main()
