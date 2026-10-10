"""Fail-closed exact ST C5 identity / DFP loader research mapping."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from collections import Counter

import validate_st_c5_exact_loader_matrix_v1 as m
import validate_st_c5_dfp_loader_crosswalk_v09 as v09


class C5ExactLoaderMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog, cls.source = m.get_catalog()
        cls.dfp, cls.fork, cls.st = m.source_authority()
        cls.crosswalk = v09.read_rows(v09.CROSSWALK.read_text(encoding="utf-8"))
        cls.records, cls.summary, cls.jsonl = m.audit()
        cls.by_icpn = {r["icpn"]: r for r in cls.records}

    def test_all_172_are_present_only_once(self) -> None:
        self.assertEqual(len(self.records), len(self.by_icpn))
        self.assertEqual(len(self.records), 172)
        self.assertEqual(self.summary["production_c5_exact_icpns"], 172)
        self.assertEqual(self.summary["production_exact_st_icpns"], 4629)
        self.assertEqual(self.summary["production_exact_metadata_missing"], 0)
        self.assertEqual(self.summary["candidate_loader_group_count"], 3)

    def test_three_loader_groups_and_139_33_exact_dfp_partition(self) -> None:
        self.assertEqual(self.summary["candidate_group_counts"], {
            "0x44E": {"total": 60, "dfp_exact": 46, "dfp_base_only": 14},
            "0x44F": {"total": 63, "dfp_exact": 48, "dfp_base_only": 15},
            "0x45A": {"total": 49, "dfp_exact": 45, "dfp_base_only": 4},
        })
        self.assertEqual(self.summary["dfp_exact_dvariant_present"], 139)
        self.assertEqual(self.summary["dfp_exact_dvariant_missing"], 33)
        self.assertEqual(
            Counter(r["series"] for r in self.records), Counter(m.EXPECTED_SERIES)
        )

    def test_current_official_metadata_exists_even_when_old_dfp_exact_variant_missing(self) -> None:
        missing = [r for r in self.records if not r["dfp_exact_dvariant_present"]]
        self.assertEqual(len(missing), 33)
        for row in missing:
            self.assertTrue(row["official_exact_catalog_metadata_verified"])
            self.assertTrue(row["dfp_absence_is_not_catalog_metadata_gap"])
            self.assertIsNone(row["dfp_exact_variant_flash_bytes"])
            self.assertGreater(row["official_catalog_flash_bytes"], 0)
            self.assertEqual(row["dfp_evidence_state"], "BASE_DEVICE_ONLY_NOT_EXACT")
            self.assertEqual(row["production_mapping_status"], "no_mapping")

    def test_exact_dfp_only_evidences_its_own_flash_size(self) -> None:
        exact = [r for r in self.records if r["dfp_exact_dvariant_present"]]
        self.assertEqual(len(exact), 139)
        for row in exact:
            self.assertEqual(row["official_catalog_flash_bytes"], row["dfp_exact_variant_flash_bytes"])
            self.assertEqual(row["official_catalog_flash_bytes"], row["dfp_parent_candidate_flash_bytes"])
            self.assertEqual(row["dfp_evidence_state"], "EXACT_DFP_VARIANT")

    def test_loader_sha_identity_and_flash_fallback_untrusted(self) -> None:
        for row in self.records:
            path = row["candidate_loader_path"]
            self.assertEqual(row["candidate_loader_sha256"], v09.EXPECTED_LOADER_SHA256[path])
            self.assertEqual(row["candidate_loader_source_git_blob"], v09.EXPECTED_LOADERS[path])
            self.assertEqual(row["fork_tcl_scalar_array_defects_unresolved"], True)
            self.assertEqual(row["fork_dev_id_loader_table_empty"], True)
            self.assertIsNone(row["actual_silicon_device_id"])
            self.assertIsNone(row["actual_flash_size_readback_bytes"])
            self.assertGreaterEqual(row["fork_flash_size_fallback_bytes_untrusted"],
                                    row["official_catalog_flash_bytes"])

    def test_dfp_algorithm_ram_not_equated_to_openocd_workarea(self) -> None:
        for row in self.records:
            self.assertEqual(row["fork_default_workarea_bytes"], 32768)
            self.assertIn(row["dfp_declared_algorithm_ram_bytes"], (65536, 131072, 262144))
            self.assertEqual(row["ram_compatibility"], "unverified_not_assumed_incompatible")
            self.assertGreater(row["dfp_declared_algorithm_ram_bytes"],
                               row["fork_default_workarea_bytes"])

    def test_production_and_hardware_gates_blocked_all_172(self) -> None:
        for row in self.records:
            self.assertEqual(row["production_mapping_status"], "no_mapping")
            self.assertEqual(row["candidate_status"], "research_only_not_executable")
            for name in ("plasma_stldr_backend_qualified", "physical_device_probe_verified",
                         "hardware_runtime_ready", "erase_program_verify_authorized",
                         "official_loader_runtime_staging_verified",
                         "vendor_binary_redistribution_approved"):
                self.assertIs(row[name], False, (row["icpn"], name))
        self.assertIs(self.summary["production_backend_mapping_modified"], False)
        self.assertIs(self.summary["production_write_authorized"], False)
        self.assertEqual(self.summary["real_silicon_qualifications"], 0)

    def test_deterministic_records_and_sha256(self) -> None:
        rows, summary, blob = m.audit()
        self.assertEqual(rows, self.records)
        self.assertEqual(summary, self.summary)
        self.assertEqual(blob, self.jsonl)
        self.assertEqual(len(blob.splitlines()), 172)
        self.assertEqual(hashlib.sha256(blob).hexdigest(), summary["records_jsonl_sha256"])
        self.assertEqual(json.loads(blob.splitlines()[0]), rows[0])

    def test_mutated_mapping_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog[0]["mapping_status"] = "mapped"
        with self.assertRaisesRegex(m.MatrixError, "unexpectedly mapped"):
            m.build_rows(catalog, self.crosswalk, self.dfp, self.fork, self.st)

    def test_wrong_dfp_device_id_fails_closed(self) -> None:
        bad = copy.deepcopy(self.crosswalk)
        bad[0]["candidate_dev_id"] = "0x45A"
        with self.assertRaisesRegex(m.MatrixError, "wrong C5 loader/device ID"):
            m.build_rows(self.catalog, bad, self.dfp, self.fork, self.st)

    def test_wrong_flash_geometry_fails_closed(self) -> None:
        bad = copy.deepcopy(self.catalog)
        bad[0]["flash_size"] = "4096 KiB"
        with self.assertRaisesRegex(m.MatrixError, "geometry mismatch"):
            m.build_rows(bad, self.crosswalk, self.dfp, self.fork, self.st)

    def test_mutated_loader_sha_is_rejected(self) -> None:
        dfp = copy.deepcopy(self.dfp)
        dfp["official_dfp_source"]["loader_files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(m.MatrixError, "digest/identity mismatch"):
            m.build_rows(self.catalog, self.crosswalk, dfp, self.fork, self.st)

    def test_reject_route_ready_in_research_csv(self) -> None:
        bad = copy.deepcopy(self.crosswalk)
        bad[0]["plasma_route_ready"] = "true"
        with self.assertRaisesRegex(m.MatrixError, "parent/route unauthorized"):
            m.build_rows(self.catalog, bad, self.dfp, self.fork, self.st)

    def test_dfp_parent_mismatch_fails_closed(self) -> None:
        bad = copy.deepcopy(self.crosswalk)
        bad[0]["dfp_parent_dname"] = "STM32C999XX"
        with self.assertRaisesRegex(m.MatrixError, "parent/route unauthorized"):
            m.build_rows(self.catalog, bad, self.dfp, self.fork, self.st)


if __name__ == "__main__":
    unittest.main()
