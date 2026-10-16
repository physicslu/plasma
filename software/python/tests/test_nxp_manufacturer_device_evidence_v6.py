from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import _device_search_payload
from plasma_web.nxp_manufacturer_device_evidence import (
    EVIDENCE_RELATIVE_PATH,
    NXPManufacturerDeviceEvidence,
    NXPManufacturerDeviceEvidenceError,
    _root,
    get_default_nxp_manufacturer_device_evidence,
)


class NXPManufacturerDeviceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = get_default_device_catalog()
        cls.evidence = get_default_nxp_manufacturer_device_evidence()
        cls.nxp = [r for r in cls.catalog.records if r.vendor == "NXP"]
        cls.new = [r for r in cls.nxp if r.family in {"MCX", "K32L2"}]

    def test_bounded_212_admitted_exact_and_source_verified(self) -> None:
        self.assertEqual(self.catalog.size, 4975)
        self.assertEqual(self.evidence.size, 212)
        self.assertEqual(len(self.nxp), 224)
        self.assertEqual(len(self.new), 212)
        self.assertEqual(sum(r.family == "MCX" for r in self.new), 196)
        self.assertEqual(sum(r.family == "K32L2" for r in self.new), 16)
        payloads = [self.evidence.resolve_exact(r) for r in self.new]
        self.assertTrue(all(p is not None for p in payloads))
        self.assertEqual(sum(p["operating_vdd_v"] is not None for p in payloads), 208)
        self.assertEqual(sum(p["operating_vdd_v"] is None for p in payloads), 4)
        for p in payloads:
            self.assertEqual(p["status"], "manufacturer_device_partial_evidence")
            self.assertEqual(p["manufacturer"], "NXP")
            self.assertIn(p["family"], {"MCX", "K32L2"})
            self.assertEqual(p["base_device"], p["icpn"])
            self.assertEqual(p["evidence"]["exact_url"],
                             "https://www.nxp.com/part/" + p["icpn"])
            self.assertTrue(p["ram_size"].endswith(" kB"))
            self.assertIn("io_supply", p["unknown_fields"])
            self.assertIn("vdda", p["unknown_fields"])
            self.assertIsNone(p["io_supply_v"])
            self.assertIsNone(p["vdda_v"])
            self.assertFalse(p["manufacturer_device_full_profile_complete"])
            self.assertFalse(p["programming_profile_authority"])
            self.assertFalse(p["hardware_runtime_ready"])
            self.assertFalse(p["physical_programming_qualified"])

    def test_existing_st_and_kl25_are_not_silently_assigned_nxp_metadata(self) -> None:
        self.assertIsNone(self.evidence.resolve_exact(
            self.catalog.resolve("NXP", "MKL25Z128VFM4")))
        st = next(r for r in self.catalog.records if r.vendor == "STMicroelectronics")
        self.assertIsNone(self.evidence.resolve_exact(st))

    def test_metadata_cannot_cross_exact_catalog_identity_or_route(self) -> None:
        record = self.new[0]
        with self.assertRaisesRegex(NXPManufacturerDeviceEvidenceError, "Package|package"):
            self.evidence.resolve_exact(replace(record, package="FAKE"))
        with self.assertRaisesRegex(NXPManufacturerDeviceEvidenceError, "backend route"):
            self.evidence.resolve_exact(replace(record, target_config="tcl/target/fictional.cfg"))
        with self.assertRaisesRegex(NXPManufacturerDeviceEvidenceError, "not a Production"):
            self.evidence.resolve_exact(replace(record, production_admitted=False))
        with self.assertRaisesRegex(NXPManufacturerDeviceEvidenceError, "source_authority"):
            self.evidence.resolve_exact(replace(record, source_authority="https://bad.example/"))

    def test_evidence_tampering_fails_closed_before_any_lookup(self) -> None:
        original = (_root() / EVIDENCE_RELATIVE_PATH).read_bytes()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "evidence.csv"
            path.write_bytes(original.replace(b"K32L2A31VLH1A", b"K32L2A31VLH1B", 1))
            with self.assertRaisesRegex(NXPManufacturerDeviceEvidenceError, "Git blob changed"):
                NXPManufacturerDeviceEvidence.from_file(path)

    def test_customer_selector_hides_nxp_level0_and_keeps_level1_routes(self) -> None:
        payload = _device_search_payload("NXP", 100)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["levels"], [1, 2, 3])
        self.assertLess(payload["catalog_size"], self.catalog.size)
        self.assertEqual(payload["total_count"], 12)
        self.assertEqual(len(payload["results"]), 12)
        for item in payload["results"]:
            self.assertEqual(item["family"], "KL25")
            self.assertEqual(item["catalog_level"], 1)
            self.assertEqual(item["catalog_level_state"], "PROGRAMMING_CANDIDATE")
            self.assertFalse(item["job_selectable"])
            self.assertIsNone(item["nxp_manufacturer_device_profile"])
            self.assertIsNone(item["selected_profile"])
            self.assertEqual(item["physical_validation"]["ppu_status"], "no_evidence")

        # The 212 MCX/K32L2 exact ICPNs remain admitted identity records but are
        # Level 0 in the active runtime and therefore absent from the public selector.
        self.assertEqual(sum(r.family in {"MCX", "K32L2"} for r in self.nxp), 212)

    def test_new_unqualified_discovery_skus_not_added_to_production(self) -> None:
        import csv
        with (_root() / "data/device-catalog/research/nxp-new-148-active-discovery-v5.csv").open(
                encoding="utf-8", newline="") as fp:
            candidates = [r["icpn"] for r in csv.DictReader(fp)]
        self.assertEqual(len(candidates), 148)
        self.assertTrue(all(self.catalog.resolve("NXP", sku) is None
                            for sku in candidates))


if __name__ == "__main__":
    unittest.main()
