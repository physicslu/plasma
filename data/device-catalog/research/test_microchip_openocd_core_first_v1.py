#!/usr/bin/env python3
"""Offline negative and boundary tests for Microchip OpenOCD-first Research."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from microchip_openocd_core_first_v1 import (
    SOURCE_LOCK, OPENOCD_RELEASE, PINNED_DFP_SOURCE,
    blob_sha, validate_registry, verify_upstream_source, triage_names,
)


class MicrochipCoreFirstResearchGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
        cls.release = json.loads(OPENOCD_RELEASE.read_text(encoding="utf-8"))

    def test_pinned_release_and_research_safety(self):
        result = validate_registry(self.lock, self.release)
        self.assertEqual(result["p0_source_lead_groups"], 9)
        self.assertEqual(result["p1_target_only_groups"], 2)
        self.assertIsNone(result["exact_icpn_software_supported_count"])

    def test_upstream_version_mismatch_fails_closed(self):
        release = dict(self.release, source_commit="0" * 40)
        with self.assertRaisesRegex(ValueError, "version mismatch"):
            validate_registry(self.lock, release)

    def test_p0_does_not_imply_supported(self):
        for key in ("qualification_state", "openocd_supported_asserted",
                    "exact_icpn_software_qualified", "core_is_support_evidence"):
            mutated = deepcopy(self.lock)
            g = mutated["p0_research_leads"][0]
            g[key] = "SUPPORTED" if key == "qualification_state" else True
            with self.subTest(key=key), self.assertRaisesRegex(
                    ValueError, "source lead incorrectly promoted"):
                validate_registry(mutated, self.release)

    def test_no_production_catalog_or_hil_authority(self):
        for key in ("production_write_authorized",
                    "catalog_publication_authorized",
                    "socket_hil_claimed", "ppu_hil_claimed"):
            mutated = deepcopy(self.lock)
            mutated[key] = True
            with self.subTest(key=key), self.assertRaisesRegex(
                    ValueError, "Research cannot authorize"):
                validate_registry(mutated, self.release)

    def test_non_arm_jtag_research_not_erased(self):
        by_id = {x["id"]: x for x in self.lock["p0_research_leads"]}
        self.assertEqual(by_id["pic32mx"]["core_architecture"], "MIPS")
        self.assertEqual(by_id["pic32mx"]["debug_transports"], ["JTAG"])
        self.assertEqual(by_id["atmega128-limited"]["core_architecture"], "AVR")
        self.assertEqual(by_id["atmega128-limited"]["debug_transports"], ["JTAG"])
        self.assertEqual(by_id["atmega128-limited"]["matcher"], "^ATMEGA128$")

    def test_p1_target_only_no_flash_support_claim(self):
        for group in self.lock["p1_bounded_leads"]:
            self.assertNotIn("driver", group)
            self.assertNotIn("driver_source", group)
            self.assertEqual(group["qualification_state"], "UNKNOWN")
            self.assertFalse(group["openocd_supported_asserted"])
            self.assertFalse(group["device_applicability_reviewed"])

    def test_git_blob_hash_is_git_not_plain_sha(self):
        self.assertEqual(blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")
        self.assertNotEqual(blob_sha(b"hello\n"), blob_sha(b"hello"))

    def test_upstream_changed_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / self.lock["p0_research_leads"][0]["target"]
            target.parent.mkdir(parents=True)
            target.write_text("# tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Git blob mismatch"):
                verify_upstream_source(self.lock, root)

    def test_same_core_and_target_without_flash_bank_cannot_pass(self):
        g = deepcopy(self.lock["p0_research_leads"][0])
        g["target"] = "tcl/target/sample.cfg"
        g["driver_source"] = "src/flash/nor/sample.c"
        target = b"target create cpu cortex_m -dap chip.dap\n"
        driver = (b'const struct flash_driver sample_flash = {\n'
                  b' .name = "at91samd",\n .erase = erase,\n'
                  b' .write = write,\n .probe = probe,\n .read = read,\n};\n')
        g["target_sha"] = blob_sha(target)
        g["driver_sha"] = blob_sha(driver)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, data in ((g["target"], target),
                              (g["driver_source"], driver)):
                file = root / rel
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "missing direct Flash Bank"):
                verify_upstream_source({"p0_research_leads": [g],
                                        "p1_bounded_leads": []}, root)

    def test_matched_dfp_name_is_research_lead_not_exact_icpn(self):
        names = ["ATSAMD21G18A", "ATSAML11E16A", "PIC32MX270F256B",
                 "ATMEGA128", "ATMEGA128RFA1", "PIC16F877A", "ATSAM4L8A"]
        fake = {
            "manufacturer": "Microchip",
            "source_bytes_sha256": PINNED_DFP_SOURCE,
            "population_boundary_validated": False,
            "production_write_authorized": False,
            "device_support_list_is_complete_commercial_sku_inventory": False,
            "manufacturer_device_pack_count": 1,
            "observed_manufacturer_device_support_names": len(names),
            "observed_distinct_device_support_names": len(names),
            "device_packs": [{
                "pack_name": "Test_DFP", "discovery_lane": "32bit-pic-sam",
                "device_names": names
            }]
        }
        result = triage_names(self.lock, fake)
        self.assertEqual(result["observed_dfp_names"], len(names))
        self.assertEqual(result["by_research_group"]["P0:sam-d-c-r-l0"], 1)
        self.assertEqual(result["by_research_group"]["P0:pic32mx"], 1)
        self.assertEqual(result["by_research_group"]["P0:atmega128-limited"], 1)
        self.assertEqual(result["by_research_group"]["P1:sam-l1x-target-only"], 1)
        self.assertEqual(result["by_research_group"]["P2:archive_only"], 2)
        self.assertIsNone(result["exact_icpn_qualified_supported"])
        self.assertTrue(result["p2_does_not_mean_openocd_unsupported"])

    def test_same_core_not_same_flash_controller(self):
        groups = {g["id"]: g for g in self.lock["p0_research_leads"]}
        self.assertEqual(groups["sam4-except-l"]["core_model"], "Cortex-M4")
        self.assertEqual(groups["sam4l"]["core_model"], "Cortex-M4")
        self.assertNotEqual(groups["sam4-except-l"]["driver"],
                            groups["sam4l"]["driver"])
        self.assertNotEqual(groups["sam4-except-l"]["driver_sha"],
                            groups["sam4l"]["driver_sha"])


if __name__ == "__main__":
    unittest.main()
