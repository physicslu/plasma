"""NXP v24 manufacturer metadata is read-only and cannot promote hardware or software."""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from plasma_web.device_catalog import get_default_device_catalog
from plasma_web.gateway import _device_search_payload
from plasma_web.nxp_phase1_information import (
    ADMITTED_ROWS,
    LEDGER_RELATIVE_PATH,
    NXPPhase1Information,
    NXPPhase1InformationError,
    _root,
    get_default_nxp_phase1_information,
)


class NXPPhase1InformationSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = get_default_device_catalog()
        cls.projection = get_default_nxp_phase1_information()
        cls.nxp = [r for r in cls.catalog.records if r.vendor == "NXP"]

    def test_v24_source_and_admission_have_disjoint_authorities(self) -> None:
        self.assertEqual(self.catalog.size, 4853)
        self.assertEqual(len(self.nxp), ADMITTED_ROWS)
        self.assertEqual(self.projection.size, ADMITTED_ROWS)
        summary = {k: {"VERIFIED": 0, "PARTIAL": 0, "UNKNOWN": 0, "CONFLICT": 0}
                   for k in ("ram", "working_vdd", "io_supply", "vdda")}
        for record in self.nxp:
            item = self.projection.resolve_exact(record)
            self.assertIsNotNone(item)
            self.assertEqual(item["scope"], "research_field_evidence_only")
            self.assertEqual(item["icpn"], record.icpn)
            self.assertFalse(item["catalog_admission_changed"])
            self.assertFalse(item["software_programming_qualified"])
            self.assertFalse(item["physical_programming_qualified"])
            self.assertFalse(item["original_manufacturer_pdf_binary_sha256_qualified"])
            for name, field in item["fields"].items():
                summary[name][field["state"]] += 1
                self.assertEqual(field["value"] is None, field["state"] == "UNKNOWN")
                self.assertTrue(field["source_url"] is None or field["source_url"].startswith("https://www.nxp."))
        self.assertEqual(summary["ram"], {"VERIFIED": 199, "PARTIAL": 25, "UNKNOWN": 0, "CONFLICT": 0})
        self.assertEqual(summary["working_vdd"], {"VERIFIED": 135, "PARTIAL": 27, "UNKNOWN": 62, "CONFLICT": 0})
        self.assertEqual(summary["io_supply"], {"VERIFIED": 119, "PARTIAL": 16, "UNKNOWN": 89, "CONFLICT": 0})
        self.assertEqual(summary["vdda"], {"VERIFIED": 135, "PARTIAL": 0, "UNKNOWN": 89, "CONFLICT": 0})

    def test_exact_examples_preserve_relative_rails_and_missing_fields(self) -> None:
        examples = (
            ("MCXA132VFM", "VERIFIED", "VERIFIED", "VERIFIED", "VERIFIED"),
            ("MKL25Z128VFM4", "VERIFIED", "VERIFIED", "PARTIAL", "VERIFIED"),
            ("K32L2A31VLH1A", "VERIFIED", "VERIFIED", "PARTIAL", "VERIFIED"),
            ("MCXC041VFG", "VERIFIED", "PARTIAL", "UNKNOWN", "UNKNOWN"),
            ("MCXE245VLH", "VERIFIED", "UNKNOWN", "UNKNOWN", "UNKNOWN"),
        )
        for sku, ram, vdd, io, vdda in examples:
            with self.subTest(sku=sku):
                record = self.catalog.resolve("NXP", sku)
                item = self.projection.resolve_exact(record)
                self.assertEqual(tuple(item["fields"][x]["state"]
                                       for x in ("ram", "working_vdd", "io_supply", "vdda")),
                                 (ram, vdd, io, vdda))
                if io == "UNKNOWN":
                    self.assertIsNone(item["fields"]["io_supply"]["value"])
        p3 = self.projection.resolve_exact(self.catalog.resolve("NXP", "MCXA144VFT"))
        self.assertIsNotNone(p3)
        self.assertIn("VDD_P3", p3["fields"]["io_supply"]["value"])
        self.assertIn("VDD_ANA", p3["fields"]["vdda"]["value"])

    def test_api_does_not_expand_catalog_or_promote_backend(self) -> None:
        response = _device_search_payload("NXP", 100, 0)
        self.assertEqual(response["catalog_size"], 4853)
        self.assertEqual(response["total_count"], 224)
        for row in response["results"]:
            self.assertEqual(row["vendor"], "NXP")
            self.assertEqual(row["nxp_phase1_information"]["icpn"], row["icpn"])
            self.assertEqual(row["nxp_phase1_information"]["software_programming_qualified"], False)
            self.assertIsNone(row["selected_profile"])
        mcx = _device_search_payload("MCXA132VFM", 1)["results"][0]
        self.assertEqual(mcx["backend"]["mapping_status"], "no_mapping")
        self.assertIsNone(mcx["selected_profile"])
        self.assertEqual(mcx["physical_validation"]["ppu_status"], "no_evidence")
        st = _device_search_payload("STM32F103C8T6", 1)["results"][0]
        self.assertIsNone(st["nxp_phase1_information"])

    def test_identity_mismatch_and_unadmitted_records_are_blocked(self) -> None:
        nxp = self.catalog.resolve("NXP", "MCXA132VFM")
        for altered in (
            replace(nxp, package="NOT_A_REAL_PACKAGE"),
            replace(nxp, flash_size="999 kB"),
            replace(nxp, production_admitted=False),
            replace(nxp, source_authority="https://example.com/untrusted"),
        ):
            with self.subTest(changed=altered):
                with self.assertRaises(NXPPhase1InformationError):
                    self.projection.resolve_exact(altered)
        self.assertIsNone(self.projection.resolve_exact(self.catalog.resolve(
            "STMicroelectronics", "STM32F103C8T6")))

    def test_mutated_source_fails_git_blob_gate(self) -> None:
        raw = (_root() / LEDGER_RELATIVE_PATH).read_bytes()
        with tempfile.TemporaryDirectory() as location:
            bad = Path(location) / "nxp-ledger.csv"
            bad.write_bytes(raw.replace(b"MCXA132VFM", b"MCXA132FAKE", 1))
            with self.assertRaisesRegex(NXPPhase1InformationError, "Git blob changed"):
                NXPPhase1Information.from_file(bad)


if __name__ == "__main__":
    unittest.main()
