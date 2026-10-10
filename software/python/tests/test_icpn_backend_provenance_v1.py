"""Contract tests: exact ICPN source attribution must never promote H5/C5 research routes."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from plasma_web.backend_provenance import audit_snapshot, load_source_authorities
from plasma_web.device_catalog import DeviceCatalog, DeviceCatalogIntegrityError


ROOT = Path(__file__).resolve().parents[3]


class BackendProvenanceAuditV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.upstream, cls.gap = load_source_authorities(ROOT)
        cls.catalog = DeviceCatalog.from_manifest(ROOT / "data/device-catalog/production/icpn-v1-manifest.json")
        cls.rows, cls.summary, cls.jsonl = audit_snapshot(cls.catalog, cls.upstream, cls.gap)
        cls.by_icpn = {row["icpn"]: row for row in cls.rows}

    def test_exact_catalog_partition_and_candidate_counts(self) -> None:
        self.assertEqual(self.summary["total_exact_icpns"], 4629)
        self.assertEqual(self.summary["production_mapped"], 4164)
        self.assertEqual(self.summary["production_no_mapping"], 465)
        self.assertEqual(self.summary["research_candidates_not_mapped"], {"STM32C5": 172, "STM32H5": 190})
        self.assertEqual(len(self.by_icpn), 4629)
        self.assertEqual(self.summary["catalog_revision_sha256"], self.catalog.revision_sha256)

    def test_every_mapped_ic_cites_same_pinned_upstream_source_not_st_fork(self) -> None:
        for row in self.rows:
            if row["mapping_status"] != "mapped":
                continue
            binding = row["production_binding"]
            self.assertEqual(binding["source_distribution"], "openocd-org/openocd")
            self.assertEqual(binding["source_commit"], self.upstream["source_commit"])
            self.assertEqual(binding["pinned_release_runtime_id"], self.upstream["runtime_id"])
            self.assertTrue(binding["target_config"].startswith("tcl/target/"))
            self.assertEqual(binding["qualification_boundary"], "catalog_mapping_only")
            self.assertIsNone(row["research_candidate"])
            self.assertIsNone(binding["flash_driver"])  # No false per-IC driver claim.

    def test_unmapped_never_inherit_upstream_distribution_or_source(self) -> None:
        for row in self.rows:
            if row["mapping_status"] != "no_mapping":
                continue
            binding = row["production_binding"]
            for field in ("provider_id", "source_distribution", "source_repository", "source_commit", "target_config", "pinned_release_runtime_id"):
                self.assertIsNone(binding[field], (row["icpn"], field))
            self.assertEqual(binding["qualification_boundary"], "unbound")

    def test_st_fork_candidate_is_explicitly_research_only(self) -> None:
        for family, count in [("STM32H5", 190), ("STM32C5", 172)]:
            rows = [row for row in self.rows if row["family"] == family]
            self.assertEqual(len(rows), count)
            for row in rows:
                candidate = row["research_candidate"]
                self.assertIsNotNone(candidate)
                self.assertEqual(candidate["source_commit"], self.gap["candidate_st_fork"]["commit"])
                self.assertEqual(candidate["status"], "research_only_not_production_mapped")
                self.assertFalse(candidate["production_binding_authorized"])
                self.assertFalse(candidate["hardware_runtime_ready"])
                self.assertIsNone(row["production_binding"]["provider_id"])
                if family == "STM32H5":
                    self.assertEqual(candidate["flash_driver"], "stm32h5x")
                    self.assertEqual(candidate["qualification_boundary"], "host_and_qemu_armv7_software_only")
                else:
                    self.assertEqual(candidate["flash_driver"], "stldr")
                    self.assertIs(candidate["loader_qualified"], False)
                    self.assertEqual(candidate["qualification_boundary"], "source_and_tcl_static_only")

    def test_other_unmapped_st_families_have_no_invented_candidate(self) -> None:
        blocked = Counter(r["family"] for r in self.rows if r["mapping_status"] == "no_mapping")
        self.assertEqual(blocked, {
            "STM32H5": 190, "STM32C5": 172, "STM32WL3": 47, "STM32N6": 32, "STM32WB0": 24
        })
        for row in self.rows:
            if row["family"] in {"STM32N6", "STM32WB0", "STM32WL3"}:
                self.assertIsNone(row["research_candidate"])
                self.assertIsNone(row["production_binding"]["source_repository"])

    def test_software_catalog_evidence_never_fabricates_installed_binary_or_physical_validation(self) -> None:
        for row in self.rows:
            self.assertFalse(row["physical_programming_qualified"])
            self.assertIsNone(row["installed_runtime"]["runtime_id"])
            self.assertIsNone(row["installed_runtime"]["binary_sha256"])
            self.assertIsNone(row["installed_runtime"]["artifact_sha256"])
            self.assertFalse(row["production_binding"]["hardware_runtime_ready"])
            self.assertIsNone(row["production_binding"]["target_config_git_blob"])
            self.assertIsNone(row["production_binding"]["flash_driver"])

    def test_jsonl_is_deterministic_and_hash_bound(self) -> None:
        rows_again, summary_again, blob_again = audit_snapshot(self.catalog, self.upstream, self.gap)
        self.assertEqual(self.rows, rows_again)
        self.assertEqual(self.summary, summary_again)
        self.assertEqual(self.jsonl, blob_again)
        self.assertEqual(hashlib.sha256(self.jsonl).hexdigest(), self.summary["records_jsonl_sha256"])
        self.assertEqual(len(self.jsonl.splitlines()), 4629)
        self.assertEqual(json.loads(self.jsonl.splitlines()[0]), self.rows[0])

    def test_source_commit_mismatch_must_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "release").mkdir()
            (root / "data/device-catalog/research").mkdir(parents=True)
            changed = dict(self.upstream)
            changed["source_commit"] = "0" * 40
            changed["runtime_id"] = "0.12.0-000000000000"
            (root / "release/openocd.json").write_text(json.dumps(changed), encoding="utf-8")
            (root / "data/device-catalog/research/st-h5-c5-runtime-gap-v1.json").write_text(
                json.dumps(self.gap), encoding="utf-8")
            with self.assertRaises(DeviceCatalogIntegrityError):
                load_source_authorities(root)

    def test_vendor_identity_evidence_is_separate_from_backend_source(self) -> None:
        x = self.by_icpn["STM32F301C6T6"]
        self.assertIn("st.com", x["identity_evidence_reference"])
        self.assertEqual(x["production_binding"]["source_repository"], "https://github.com/openocd-org/openocd.git")
        h = self.by_icpn["STM32H503CBT6"]
        self.assertIn("st.com", h["identity_evidence_reference"])
        self.assertIsNone(h["production_binding"]["source_repository"])
        self.assertEqual(h["research_candidate"]["source_repository"], "https://github.com/STMicroelectronics/OpenOCD.git")


if __name__ == "__main__":
    unittest.main()
