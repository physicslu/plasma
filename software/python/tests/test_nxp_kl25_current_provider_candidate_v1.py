"""Offline, non-executable NXP KL25 exact L1->L2 qualification gate."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from plasma_web.catalog_promotion_framework import (
    CatalogPromotionFramework, EVIDENCE_REVIEWED_PROGRAMMING_PROVIDER,
    PROVIDER_QUALIFICATION_INCOMPLETE,
)
from plasma_web.device_catalog import DeviceCatalogIntegrityError, get_default_device_catalog
from plasma_web.nxp_kl25_qualification import (
    BLOCKERS, ICPN, NxpKl25QualificationProvider, _read_locked,
    get_default_nxp_kl25_qualification_provider,
)
from plasma_web.programming_qualification import get_default_programming_qualification_registry

ROOT = Path(__file__).resolve().parents[3]


class NxpKl25CurrentProviderCandidateTests(unittest.TestCase):
    def test_full_source_exact_provider_is_candidate_not_supported(self) -> None:
        provider = get_default_nxp_kl25_qualification_provider()
        self.assertIsNotNone(provider)
        self.assertEqual(provider.reviewed_exact_keys, (("NXP", ICPN),))
        raw = provider.describe("NXP", ICPN)
        self.assertTrue(raw["reviewed"])
        self.assertEqual(raw["software_state"], "CANDIDATE")
        self.assertEqual(raw["provider"]["source_commit"],
                         "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c")
        self.assertIsNone(raw["programming"])
        self.assertEqual(tuple(raw["qualification_gaps"]), BLOCKERS)
        self.assertEqual(set(raw["operations"]), {"READ", "VERIFY", "PROGRAM", "ERASE"})
        self.assertTrue(all(row["state"] == "UNKNOWN" for row in raw["operations"].values()))
        self.assertFalse(raw["hardware_runtime_ready"])
        self.assertFalse(raw["physical_programming_qualified"])
        self.assertIsNone(provider.lookup("NXP", "MKL25Z128VLH4"))
        self.assertIsNone(provider.lookup("STMicroelectronics", ICPN))

    def test_canonical_level_and_job_execution_remain_fail_closed(self) -> None:
        registry = get_default_programming_qualification_registry()
        self.assertEqual(registry.summary["reviewed_exact_icpns"], 66)
        self.assertEqual(registry.summary["catalog_level_2_programmable_exact_icpns"], 65)
        row = registry.describe("NXP", ICPN)
        self.assertEqual(row["state"], "CANDIDATE")
        self.assertTrue(row["reviewed"])
        self.assertEqual(row["catalog_level"], 1)
        self.assertEqual(row["catalog_level_state"], "PROGRAMMING_CANDIDATE")
        self.assertEqual(tuple(row["qualification_gaps"]), BLOCKERS)
        self.assertTrue(row["selector_visible"])
        self.assertFalse(row["job_selectable"])
        self.assertFalse(row["execution_authorized"])
        self.assertFalse(row["installed_runtime_attested"])
        self.assertFalse(row["hardware_runtime_ready"])
        self.assertFalse(row["physical_programming_qualified"])

        framework = CatalogPromotionFramework(get_default_device_catalog(), registry)
        obs = framework.observe(get_default_device_catalog().resolve("NXP", ICPN))
        self.assertEqual(obs["promotion_evidence_class"], EVIDENCE_REVIEWED_PROGRAMMING_PROVIDER)
        self.assertEqual(obs["promotion_blocker"], PROVIDER_QUALIFICATION_INCOMPLETE)
        nxp = next(x for x in framework.report["manufacturers"] if x["manufacturer"] == "NXP")
        self.assertEqual(nxp["catalog_level_counts"], {"0": 212, "1": 29, "2": 0, "3": 0})
        self.assertEqual(nxp["job_selectable_exact_icpns"], 0)
        self.assertEqual(nxp["promotion_blocker_counts"]["L1_TO_L2"],
                         {"MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED": 28,
                          "PROVIDER_QUALIFICATION_INCOMPLETE": 1})
        other = registry.describe("NXP", "MKL25Z128VLH4")
        self.assertFalse(other["reviewed"])
        self.assertEqual(other["catalog_level"], 1)
        self.assertEqual(other["state"], "UNKNOWN")

    def test_pinned_historical_rejected_review_and_provider_delta(self) -> None:
        provider = NxpKl25QualificationProvider(get_default_device_catalog(), ROOT)
        self.assertEqual(provider.describe("NXP", ICPN)["software_state"], "CANDIDATE")
        rel = "data/ic-support/benchmarks/nxp-kl25/vendor-neutral-admission-adapter-contract-v1.json"
        review = json.loads(_read_locked(ROOT, rel))
        self.assertEqual(review["gate58"]["qualification_status"], "REJECTED_REVIEW")
        self.assertNotEqual(review["legacy_release"]["openocd_commit"],
                            provider.describe("NXP", ICPN)["provider"]["source_commit"])

    def test_evidence_tampering_rejected_by_git_blob_lock(self) -> None:
        from plasma_web import nxp_kl25_qualification as module
        real_read = module._read_locked

        def corrupted(root: Path, path: str) -> bytes:
            if path.endswith("nxp-kl25-fcf-sector-safety-v1.json"):
                return b'{"schema_version":1, "result":{"current_provider_operation_qualification_certified":true}}'
            return real_read(root, path)

        with patch.object(module, "_read_locked", side_effect=corrupted):
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "FCF safety"):
                NxpKl25QualificationProvider(get_default_device_catalog(), ROOT)

        with patch.object(module, "BLOBS", {**module.BLOBS,
                          "release/openocd.json": "0" * 40}):
            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "Git blob mismatch"):
                NxpKl25QualificationProvider(get_default_device_catalog(), ROOT)

    def test_no_implicit_support_from_other_11_kl25_variants(self) -> None:
        registry = get_default_programming_qualification_registry()
        for family_suffix in ("VFM4", "VFT4", "VLH4", "VLK4"):
            for flash_kib in (32, 64, 128):
                icpn = "MKL25Z" + str(flash_kib) + family_suffix
                qualified = registry.describe("NXP", icpn)
                self.assertEqual(qualified["catalog_level"], 1)
                self.assertNotEqual(qualified["state"], "SUPPORTED")
                self.assertFalse(qualified["job_selectable"])
                self.assertFalse(qualified["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
