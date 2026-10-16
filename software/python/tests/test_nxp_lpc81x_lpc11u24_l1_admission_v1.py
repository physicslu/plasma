"""ADR-0002: exact LPC811/LPC812/LPC11U24 L1 route/identity gate.

This is identity and candidate-route evidence; it grants neither provider
SUPPORTED nor hardware execution. Historical research original-byte gaps
remain explicitly unarchived.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import unittest
from pathlib import Path

from plasma_web.catalog_promotion_framework import (
    CatalogPromotionFramework, EVIDENCE_CATALOG_MAPPED_ROUTE,
    MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED,
)
from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.programming_qualification import get_default_programming_qualification_registry

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "data/device-catalog/research"
PINNED_BLOBS = {
    "nxp-8-lpc81x-phase1-official-material-v1.csv": "2d94cdc9506b336dc580a178d3309dea6c1d8c63",
    "nxp-11-lpc11u-lpc83x-phase1-official-material-v1.csv": "0a90ceb12dde7e37fbee0e1ede0f230bea0891f5",
    "nxp-openocd-source-first-wave4-v1.json": "c2f76934edd9a1ab05761134887fe5aabbaa115c",
    "nxp-openocd-reverse-target-lock-v1.json": "70e73d5f837f942ef8e2d745a078303dc29fec65",
    "nxp-lpc81x-8-commercial-l1-v1.csv": "37f4f86ddfd2d0c04555af8629977316e9d1572c",
    "nxp-lpc11u24-1-commercial-l1-v1.csv": "0298ee4f8dac009588069adfda932efa7960bcdc",
}
COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
TARGET_BLOBS = {
    "tcl/target/lpc8xx.cfg": "4c54a2a6670d6186297306112deee8d25e2627e4",
    "tcl/target/lpc11xx.cfg": "d288e2a32b08b5e9ad26b7c86fb7035e8e08b1b6",
    "tcl/target/lpc1xxx.cfg": "70d26d2673900b06c6d5eef8e55b4542103e9e42",
}
DRIVER_BLOB = "f12eef7e4ce68fc8830773f6c57da57dfb87d6b8"
# (source family, ordering Base, official 12NC, Flash KiB, route config)
EXPECTED = {
    "LPC811M001JDH16FP": ("LPC81X", "LPC811M001JDH16", "935302397129", 8, "lpc8xx.cfg"),
    "LPC811M001JDH16J": ("LPC81X", "LPC811M001JDH16", "935302397118", 8, "lpc8xx.cfg"),
    "LPC812M101JD20J": ("LPC81X", "LPC812M101JD20", "935302399118", 16, "lpc8xx.cfg"),
    "LPC812M101JDH16FP": ("LPC81X", "LPC812M101JDH16", "935302398129", 16, "lpc8xx.cfg"),
    "LPC812M101JDH16J": ("LPC81X", "LPC812M101JDH16", "935302398118", 16, "lpc8xx.cfg"),
    "LPC812M101JDH20FP": ("LPC81X", "LPC812M101JDH20", "935302401129", 16, "lpc8xx.cfg"),
    "LPC812M101JDH20J": ("LPC81X", "LPC812M101JDH20", "935302401118", 16, "lpc8xx.cfg"),
    "LPC812M101JTB16X": ("LPC81X", "LPC812M101JTB16", "935301584115", 16, "lpc8xx.cfg"),
    "LPC11U24FHI33/301Y": ("LPC11U2X", "LPC11U24FHI33/301", "935297186518", 32, "lpc11xx.cfg"),
}
DRIVER_CASES = {
    "LPC811": ["LPC811_001"],
    "LPC812": ["LPC812_101", "LPC812_101_1", "LPC812_101_2", "LPC812_101_3"],
    "LPC11U24": ["LPC11U24_301", "LPC11U24_401"],
}


def locked(name: str) -> bytes:
    raw = (RESEARCH / name).read_bytes()
    digest = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if digest != PINNED_BLOBS[name]:
        raise AssertionError(f"source/Production Git blob drift: {name}")
    return raw


def csvrows(name: str) -> dict[str, dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(locked(name).decode("utf-8"))))
    assert len(rows) == len({r["icpn"] for r in rows}), "duplicate exact material"
    return {r["icpn"]: r for r in rows}


class NxpLpc81xLpc11U24L1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lpc81x = csvrows("nxp-8-lpc81x-phase1-official-material-v1.csv")
        cls.lpc11u = csvrows("nxp-11-lpc11u-lpc83x-phase1-official-material-v1.csv")
        cls.published = {
            **csvrows("nxp-lpc81x-8-commercial-l1-v1.csv"),
            **csvrows("nxp-lpc11u24-1-commercial-l1-v1.csv"),
        }
        cls.wave = json.loads(locked("nxp-openocd-source-first-wave4-v1.json"))
        cls.lock = json.loads(locked("nxp-openocd-reverse-target-lock-v1.json"))
        cls.catalog = get_default_device_catalog()
        cls.registry = get_default_programming_qualification_registry()

    def test_exact_material_source_to_ordering_base_not_prefix_guess(self) -> None:
        self.assertEqual(set(self.published), set(EXPECTED))
        self.assertEqual(len({row[2] for row in EXPECTED.values()}), 9)
        self.assertEqual(set(self.lpc81x), set(EXPECTED) - {"LPC11U24FHI33/301Y"})
        for icpn, (family, base, nc, flash, config) in EXPECTED.items():
            source = self.lpc81x[icpn] if family == "LPC81X" else self.lpc11u[icpn]
            dst = self.published[icpn]
            self.assertEqual(source["manufacturer_base"], base)
            self.assertEqual(source["manufacturer_12nc"], nc)
            self.assertEqual(source.get("manufacturer_status") or source.get("manufacturer_material_status"), "Active")
            self.assertEqual(source["flash_kb"], str(flash))
            self.assertEqual(source["original_manufacturer_html_bytes_archived"], "false")
            self.assertFalse(source.get("original_pdf_bytes_archived") == "true" or
                             source.get("original_datasheet_pdf_bytes_archived") == "true")
            self.assertEqual(source["production_admitted"], "false")  # historic research only
            self.assertEqual(dst["manufacturer"], "NXP")
            self.assertEqual(dst["family"], family)
            self.assertEqual(dst["base_device"], base)
            self.assertEqual(dst["flash_size"], f"{flash} KiB")
            self.assertEqual(dst["option_suffix"], icpn[len(base):])
            self.assertIn(nc, dst["source_reference"])
            self.assertEqual(dst["openocd_target_config"], "tcl/target/" + config)
            self.assertEqual(dst["mapping_status"], "deterministic_reviewed_source_backed_family_route")

    def test_pinned_openocd_include_driver_and_explicit_part_ids(self) -> None:
        self.assertEqual(self.wave["source_commit"], COMMIT)
        self.assertEqual(self.lock["source_commit"], COMMIT)
        targets = {r["path"]: r["git_blob"] for r in self.lock["target_files"]}
        for path, expected in TARGET_BLOBS.items():
            self.assertEqual(targets[path], expected)
        self.assertEqual(self.lock["verified_baseline_driver_blobs"]["src/flash/nor/lpc2000.c"], DRIVER_BLOB)
        observed = {r["icpn"]: r for r in self.wave["records"] if r["icpn"] in EXPECTED}
        self.assertEqual(set(observed), set(EXPECTED))
        for icpn, (_, _, _, _, config) in EXPECTED.items():
            wave = observed[icpn]
            series = wave["family"]
            self.assertEqual(wave["openocd_target"], "tcl/target/" + config)
            self.assertEqual(wave["openocd_helper"], "tcl/target/lpc1xxx.cfg")
            self.assertEqual(wave["openocd_flash_driver"], "src/flash/nor/lpc2000.c")
            self.assertEqual(wave["openocd_driver_part_id_cases"], DRIVER_CASES[series])
            self.assertFalse(wave["exact_material_to_silicon_part_id_verified"])
            self.assertFalse(wave["flash_programming_qualified"])
            self.assertFalse(wave["physical_hil_verified"])

    def test_only_l1_visible_no_job_or_execution(self) -> None:
        self.assertEqual(sum(r.vendor == "NXP" for r in self.catalog.records), 241)
        framework = CatalogPromotionFramework(self.catalog, self.registry)
        for icpn in EXPECTED:
            record = self.catalog.resolve("NXP", icpn)
            self.assertIsNotNone(record)
            self.assertEqual(record.identity_state, "IDENTIFIED")
            self.assertEqual([r.identifier for r in self.catalog.search(icpn)], [icpn])
            qual = self.registry.describe("NXP", icpn)
            self.assertEqual(qual["catalog_level"], 1)
            self.assertEqual(qual["catalog_level_state"], "PROGRAMMING_CANDIDATE")
            self.assertNotEqual(qual["state"], "SUPPORTED")
            self.assertFalse(qual["job_selectable"])
            self.assertFalse(qual["execution_authorized"])
            self.assertFalse(qual["physical_programming_qualified"])
            observed = framework.observe(record)
            self.assertEqual(observed["promotion_evidence_class"], EVIDENCE_CATALOG_MAPPED_ROUTE)
            self.assertEqual(observed["promotion_blocker"], MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED)
            self.assertTrue(observed["selector_visible"])
        nxp = next(r for r in framework.report["manufacturers"] if r["manufacturer"] == "NXP")
        self.assertEqual(nxp["catalog_level_counts"], {"0": 212, "1": 29, "2": 0, "3": 0})
        self.assertEqual(nxp["selector_visible_exact_icpns"], 29)
        self.assertEqual(nxp["job_selectable_exact_icpns"], 0)

    def test_slash_material_round_trip_and_negative_aliases(self) -> None:
        exact = "LPC11U24FHI33/301Y"
        record = self.catalog.resolve("NXP", exact)
        self.assertEqual(record.identifier, exact)
        self.assertIsNone(self.catalog.resolve("NXP", "LPC11U24FHI33/301"))
        self.assertIsNone(self.catalog.resolve("NXP", "LPC11U24FHI33_301Y"))
        self.assertIsNone(self.catalog.resolve("NXP", "LPC811M001JDH16"))
        self.assertIsNone(self.catalog.resolve("NXP", "LPC812M101JD20FP"))
        self.assertFalse(self.registry.describe("NXP", exact)["job_selectable"])
        original = locked("nxp-lpc11u24-1-commercial-l1-v1.csv")
        modified = original.replace(b"935297186518", b"935297186519", 1)
        self.assertNotEqual(original, modified)
        self.assertNotEqual(
            hashlib.sha1(f"blob {len(modified)}\0".encode() + modified).hexdigest(),
            PINNED_BLOBS["nxp-lpc11u24-1-commercial-l1-v1.csv"])


if __name__ == "__main__":
    unittest.main()
