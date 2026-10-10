"""Tests for 190 exact ST H5 research-only flash driver geometry candidates."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import validate_st_h5_offline_flash_matrix_v1 as m


class H5OfflineMatrixV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows, cls.facts, cls.source = m._load(m.ROOT)
        cls.records, cls.summary, cls.blob = m.audit()
        cls.by_icpn = {r["icpn"]: r for r in cls.records}

    def test_all_exact_h5_records_and_group_partition(self) -> None:
        self.assertEqual(len(self.records), 190)
        self.assertEqual(len(self.by_icpn), 190)
        self.assertEqual(self.summary["st_driver_device_id_groups"], 5)
        self.assertEqual(self.summary["group_counts"], {
            "STM32H50xx": 14,
            "STM32H52/H53xx": 53,
            "STM32H54/H55xx": 6,
            "STM32H56/H57xx": 82,
            "STM32H5E/H5Fxx": 35,
        })
        self.assertEqual(self.summary["series_counts"], m.EXPECTED_SERIES)
        self.assertEqual(self.summary["h5_exact_icpns"], 190)

    def test_example_h503_smallest_flash_geometry(self) -> None:
        r = self.by_icpn["STM32H503CBT6"]
        self.assertEqual(r["expected_device_id_from_series"], "0x474")
        self.assertEqual(r["official_catalog_flash_kib"], 128)
        self.assertEqual(r["driver_max_flash_kib"], 128)
        self.assertEqual(r["driver_flash_sector_kib"], 8)
        self.assertEqual(r["estimated_sector_count_if_catalog_size_confirmed"], 16)
        self.assertEqual(r["estimated_per_bank_sectors_if_confirmed"], 8)
        self.assertEqual(r["estimated_protection_blocks_if_confirmed"], 16)
        self.assertFalse(r["driver_has_trustzone"])

    def test_h5e_h5f_and_intermediate_geometry(self) -> None:
        h523 = self.by_icpn["STM32H523CCT6"]
        self.assertEqual(h523["expected_device_id_from_series"], "0x478")
        self.assertEqual(h523["estimated_sector_count_if_catalog_size_confirmed"], 32)
        self.assertEqual(h523["estimated_protection_blocks_if_confirmed"], 8)

        sizes = Counter(r["official_catalog_flash_kib"] for r in self.records)
        self.assertEqual(sizes, {128: 14, 256: 19, 512: 36, 1024: 32, 2048: 54, 3072: 9, 4096: 26})
        for r in self.records:
            if r["official_catalog_flash_kib"] == 3072:
                self.assertEqual(r["expected_device_id_from_series"], "0x47A")
                self.assertEqual(r["estimated_sector_count_if_catalog_size_confirmed"], 384)
                self.assertEqual(r["estimated_protection_blocks_if_confirmed"], 96)
                self.assertEqual(r["driver_max_flash_kib"], 4096)
            if r["official_catalog_flash_kib"] == 4096:
                self.assertEqual(r["estimated_sector_count_if_catalog_size_confirmed"], 512)

    def test_device_ids_are_expected_from_series_not_measured(self) -> None:
        expected = {"STM32H50xx": "0x474", "STM32H52/H53xx": "0x478",
                    "STM32H54/H55xx": "0x47C", "STM32H56/H57xx": "0x484",
                    "STM32H5E/H5Fxx": "0x47A"}
        for record in self.records:
            self.assertEqual(record["expected_device_id_from_series"],
                             expected[record["driver_device_group"]])
            self.assertIsNone(record["actual_silicon_device_id"])
            self.assertIsNone(record["actual_flash_size_register_kib"])
            self.assertEqual(record["flash_size_register_address"], "0x08FFF80C")
            self.assertEqual(record["flash_base_address"], "0x08000000")
            self.assertEqual(record["write_alignment_bytes"], 16)
            self.assertTrue(record["driver_flash_size_probe_max_fallback"])

    def test_all_promotion_and_electrical_gates_remain_closed(self) -> None:
        for record in self.records:
            self.assertEqual(record["production_mapping_status"], "no_mapping")
            self.assertEqual(record["candidate_status"], "research_only_not_production_mapped")
            self.assertEqual(record["qualification_status"], "static_source_and_catalog_only")
            self.assertTrue(record["device_geometry_verification_required"])
            self.assertTrue(record["security_state_verification_required"])
            self.assertFalse(record["programming_write_authorized"])
            self.assertFalse(record["hardware_runtime_ready"])
        self.assertFalse(self.summary["production_mapping_modified"])
        self.assertFalse(self.summary["production_backend_mapping_authorized"])
        self.assertEqual(self.summary["real_silicon_qualifications"], 0)

    def test_source_and_catalog_hashes_bound(self) -> None:
        self.assertEqual(self.facts["source"]["commit"], "c8d973bdad9a6fddb51459eda109b3b95d23b57a")
        self.assertEqual(self.facts["source"]["header_git_blob"], "980ed4673939dd31b14efc74941bbcb10ddbe7ed")
        self.assertEqual(self.facts["source"]["driver_git_blob"], "b5f24a39da05e5235167ff91c110ed89c2e3f9c5")
        self.assertEqual(self.facts["source"]["target_config_git_blob"], "b9e67c604f7d824fefca03b42d0b112e1785235a")
        self.assertEqual(self.summary["catalog_source_sha256"], self.source["sha256"])

    def test_deterministic_complete_jsonl_and_content_hash(self) -> None:
        records, summary, blob = m.audit()
        self.assertEqual(records, self.records)
        self.assertEqual(summary, self.summary)
        self.assertEqual(blob, self.blob)
        self.assertEqual(len(blob.splitlines()), 190)
        self.assertEqual(hashlib.sha256(blob).hexdigest(), summary["records_jsonl_sha256"])
        self.assertEqual(json.loads(blob.splitlines()[0]), records[0])

    def test_reject_mapped_route(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[0]["mapping_status"] = "mapped"
        with self.assertRaisesRegex(m.OfflineMatrixError, "unbound"):
            m.make_records(rows, self.facts)

    def test_reject_silicon_flash_size_outside_driver_group(self) -> None:
        rows = copy.deepcopy(self.rows)
        row = next(r for r in rows if r["series"] == "STM32H503")
        row["flash_size"] = "4096 KiB"
        with self.assertRaisesRegex(m.OfflineMatrixError, "outside driver"):
            m.make_records(rows, self.facts)

    def test_reject_fabricated_series(self) -> None:
        rows = copy.deepcopy(self.rows)
        rows[0]["series"] = "STM32H599"
        with self.assertRaisesRegex(m.OfflineMatrixError, "unrecognized exact H5"):
            m.make_records(rows, self.facts)

    def test_source_pin_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for location in (m.MANIFEST, m.FACTS, m.GAP):
                dest = root / location.relative_to(m.ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(location, dest)
            fake = root / m.FACTS.relative_to(m.ROOT)
            facts = json.loads(fake.read_text(encoding="utf-8"))
            facts["source"]["commit"] = "0" * 40
            fake.write_text(json.dumps(facts), encoding="utf-8")
            with self.assertRaisesRegex(m.OfflineMatrixError, "source commit drift"):
                m._load(root)

    def test_recorded_csv_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for location in (m.MANIFEST, m.FACTS, m.GAP,
                             m.ROOT / "data/device-catalog/research/stm32h5-commercial-icpn.csv"):
                dest = root / location.relative_to(m.ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(location, dest)
            csv_path = root / "data/device-catalog/research/stm32h5-commercial-icpn.csv"
            csv_path.write_bytes(csv_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(m.OfflineMatrixError, "hash mismatch"):
                m._load(root)

    def test_security_flag_escalation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for location in (m.MANIFEST, m.FACTS, m.GAP):
                dest = root / location.relative_to(m.ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(location, dest)
            fake = root / m.FACTS.relative_to(m.ROOT)
            facts = json.loads(fake.read_text(encoding="utf-8"))
            facts["qualification"]["programming_write_authorized"] = True
            fake.write_text(json.dumps(facts), encoding="utf-8")
            with self.assertRaisesRegex(m.OfflineMatrixError, "must be false"):
                m._load(root)


if __name__ == "__main__":
    unittest.main()
