"""ADR-0002: bounded NXP LPC11U67/U68 exact-material and source-route L1 gate.

This is a research-to-Production admission regression, NOT OpenOCD operations
qualification. Never use archived P0/P1 priority as promotion authority.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import unittest
from pathlib import Path

from plasma_web.catalog_promotion_framework import (
    CatalogPromotionFramework,
    EVIDENCE_CATALOG_MAPPED_ROUTE,
    MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED,
)
from plasma_web.device_catalog import DeviceCatalog, get_default_device_catalog
from plasma_web.programming_qualification import get_default_programming_qualification_registry

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "data/device-catalog/research"
PINNED_BLOBS = {
    "nxp-11-lpc11u-lpc83x-phase1-official-material-v1.csv":
        "0a90ceb12dde7e37fbee0e1ede0f230bea0891f5",
    "nxp-openocd-source-first-wave4-v1.json":
        "c2f76934edd9a1ab05761134887fe5aabbaa115c",
    "nxp-openocd-reverse-target-lock-v1.json":
        "70e73d5f837f942ef8e2d745a078303dc29fec65",
    "nxp-lpc11u6x-8-commercial-l1-v1.csv":
        "7eb882262d6f907022d3aaa4e5bd8c656f641a54",
}
COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
UPSTREAM_BLOBS = {
    "tcl/target/lpc11xx.cfg": "d288e2a32b08b5e9ad26b7c86fb7035e8e08b1b6",
    "tcl/target/lpc1xxx.cfg": "70d26d2673900b06c6d5eef8e55b4542103e9e42",
    "src/flash/nor/lpc2000.c": "f12eef7e4ce68fc8830773f6c57da57dfb87d6b8",
}
# Explicit exact material -> ordering base -> reviewed LPC11U67/68 silicon
# group. Never derive another exact commercial part by prefix substitution.
EXPECTED = {
    "LPC11U67JBD100E": ("935304421551", "LPC11U67JBD100", "LPC11U67", 128),
    "LPC11U67JBD48E": ("935302193551", "LPC11U67JBD48", "LPC11U67", 128),
    "LPC11U67JBD64E": ("935304418551", "LPC11U67JBD64", "LPC11U67", 128),
    "LPC11U68JBD48E": ("935303821551", "LPC11U68JBD48", "LPC11U68", 256),
    "LPC11U68JBD48K": ("935303821557", "LPC11U68JBD48", "LPC11U68", 256),
    "LPC11U68JBD64E": ("935302501551", "LPC11U68JBD64", "LPC11U68", 256),
    "LPC11U68JBD64K": ("935302501557", "LPC11U68JBD64", "LPC11U68", 256),
    "LPC11U68JBD64Y": ("935302501518", "LPC11U68JBD64", "LPC11U68", 256),
}


def _read_locked(name: str) -> bytes:
    raw = (RESEARCH / name).read_bytes()
    blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if blob != PINNED_BLOBS[name]:
        raise AssertionError(f"source evidence blob drift: {name}")
    return raw


def _csv(raw: bytes) -> dict[str, dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    assert len(rows) == len({r["icpn"] for r in rows}), "duplicate exact ICPN"
    return {r["icpn"]: r for r in rows}


class NxpLpc11U6xL1AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _csv(_read_locked("nxp-11-lpc11u-lpc83x-phase1-official-material-v1.csv"))
        cls.wave = json.loads(_read_locked("nxp-openocd-source-first-wave4-v1.json"))
        cls.lock = json.loads(_read_locked("nxp-openocd-reverse-target-lock-v1.json"))
        cls.published = _csv(_read_locked("nxp-lpc11u6x-8-commercial-l1-v1.csv"))
        cls.catalog = get_default_device_catalog()
        cls.registry = get_default_programming_qualification_registry()

    def test_exact_material_base_and_12nc_not_inferred_from_prefix(self) -> None:
        self.assertEqual(set(self.published), set(EXPECTED))
        self.assertEqual(len({row[0] for row in EXPECTED.values()}), 8)
        for part, (nc, base, silicon, flash) in EXPECTED.items():
            src = self.source[part]
            dst = self.published[part]
            self.assertEqual(src["manufacturer_12nc"], nc)
            self.assertEqual(src["manufacturer_base"], base)
            self.assertEqual(src["manufacturer_material_status"], "Active")
            self.assertEqual(src["flash_kb"], str(flash))
            self.assertEqual(src["datasheet_id"], "LPC11U6X")
            self.assertEqual(src["source_evidence_scope"],
                "NXP_EXACT_MATERIAL_12NC_PLUS_OFFICIAL_BASE_DATASHEET_RESEARCH_ONLY")
            self.assertEqual(src["original_manufacturer_html_bytes_archived"], "false")
            self.assertEqual(src["original_datasheet_pdf_bytes_archived"], "false")
            self.assertEqual(src["openocd_programming_qualified"], "false")
            self.assertEqual(dst["manufacturer"], "NXP")
            self.assertEqual(dst["icpn"], part)
            self.assertEqual(dst["family"], "LPC11U6X")
            self.assertEqual(dst["series"], silicon)
            self.assertEqual(dst["base_device"], base)
            self.assertEqual(dst["flash_size"], f"{flash} KiB")
            self.assertIn(nc, dst["source_reference"])
            self.assertEqual(dst["source_authority"], src["official_exact_material_page"])
            self.assertEqual(dst["openocd_target_config"], "tcl/target/lpc11xx.cfg")
            self.assertEqual(dst["mapping_status"], "deterministic_reviewed_source_backed_family_route")

    def test_pinned_cfg_include_driver_and_explicit_family_cases(self) -> None:
        self.assertEqual(self.wave["source_commit"], COMMIT)
        self.assertEqual(self.lock["source_commit"], COMMIT)
        targets = {r["path"]: r["git_blob"] for r in self.lock["target_files"]}
        for path, blob in UPSTREAM_BLOBS.items():
            if path.startswith("tcl/target/"):
                self.assertEqual(targets[path], blob)
            else:
                self.assertEqual(self.lock["verified_baseline_driver_blobs"][path], blob)
        observed = {r["icpn"]: r for r in self.wave["records"] if r["icpn"] in EXPECTED}
        self.assertEqual(set(observed), set(EXPECTED))
        for icpn, (nc, base, silicon, flash) in EXPECTED.items():
            wave = observed[icpn]
            self.assertEqual(wave["family"], silicon)
            self.assertEqual(wave["openocd_target"], "tcl/target/lpc11xx.cfg")
            self.assertEqual(wave["openocd_helper"], "tcl/target/lpc1xxx.cfg")
            self.assertEqual(wave["openocd_flash_driver"], "src/flash/nor/lpc2000.c")
            self.assertEqual(
                wave["openocd_driver_part_id_cases"], [silicon + "_1", silicon + "_2"])
            self.assertFalse(wave["exact_material_to_silicon_part_id_verified"])
            self.assertFalse(wave["flash_programming_qualified"])
            self.assertFalse(wave["physical_hil_verified"])

    def test_canonical_qualification_and_selector_are_fail_closed(self) -> None:
        self.assertEqual(len([r for r in self.catalog.records if r.vendor == "NXP"]), 241)
        framework = CatalogPromotionFramework(self.catalog, self.registry)
        for icpn in EXPECTED:
            record = self.catalog.resolve("NXP", icpn)
            self.assertIsNotNone(record)
            self.assertEqual(record.identity_state, "IDENTIFIED")
            q = self.registry.describe("NXP", icpn)
            self.assertEqual(q["catalog_level"], 1)
            self.assertEqual(q["catalog_level_state"], "PROGRAMMING_CANDIDATE")
            self.assertNotEqual(q["state"], "SUPPORTED")
            self.assertFalse(q["job_selectable"])
            self.assertFalse(q["execution_authorized"])
            self.assertFalse(q["physical_programming_qualified"])
            obs = framework.observe(record)
            self.assertEqual(obs["promotion_evidence_class"], EVIDENCE_CATALOG_MAPPED_ROUTE)
            self.assertEqual(obs["promotion_blocker"], MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED)
            self.assertTrue(obs["selector_visible"])
            # Gateway-level search/Level filtering is also covered by the
            # existing NXP selector tests (which install the Web dependencies).
            results = self.catalog.search(icpn)
            self.assertEqual([r.identifier for r in results], [icpn])
            self.assertFalse(q["job_selectable"])
        report = framework.report
        nxp = next(x for x in report["manufacturers"] if x["manufacturer"] == "NXP")
        self.assertEqual(nxp["catalog_level_counts"], {"0": 212, "1": 29, "2": 0, "3": 0})
        self.assertEqual(nxp["selector_visible_exact_icpns"], 29)
        self.assertEqual(nxp["job_selectable_exact_icpns"], 0)

    def test_no_fuzzy_material_admission_and_tamper_evidence_detection(self) -> None:
        for icpn in ("LPC11U68JBD48", "LPC11U68", "LPC11U68JBD48Z"):
            self.assertIsNone(self.catalog.resolve("NXP", icpn))
        original = _read_locked("nxp-lpc11u6x-8-commercial-l1-v1.csv")
        modified = original.replace(b"935303821551", b"935303821552", 1)
        self.assertNotEqual(original, modified)
        self.assertNotEqual(
            hashlib.sha1(f"blob {len(modified)}\0".encode() + modified).hexdigest(),
            PINNED_BLOBS["nxp-lpc11u6x-8-commercial-l1-v1.csv"])


if __name__ == "__main__":
    unittest.main()
