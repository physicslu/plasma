"""Regression: Render wheels must never use .venv/lib as the data root."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import plasma_web.nxp_manufacturer_device_evidence as evidence_module
from plasma_web.device_catalog import DEVICE_CATALOG_MANIFEST_ENV
from plasma_web.gateway import _device_search_payload


class NXPInstalledWheelDataRootTests(unittest.TestCase):
    def test_explicit_manifest_anchors_source_regardless_of_installed_python_module(self) -> None:
        root = Path(__file__).resolve().parents[3]
        manifest = root / "data/device-catalog/production/icpn-v1-manifest.json"
        self.assertTrue(manifest.is_file())
        virtual_module = (
            root / ".venv/lib/python3.12/site-packages/plasma_web/nxp_manufacturer_device_evidence.py"
        )
        with patch.dict(os.environ, {DEVICE_CATALOG_MANIFEST_ENV: str(manifest)}):
            with patch.object(evidence_module, "__file__", str(virtual_module)):
                self.assertEqual(evidence_module._root(), root)
                registry = evidence_module.NXPManufacturerDeviceEvidence.from_file(
                    evidence_module._root() / evidence_module.EVIDENCE_RELATIVE_PATH
                )
                self.assertEqual(registry.size, 212)
                self.assertNotIn(".venv/lib/data", str(evidence_module._root()))

    def test_missing_relocated_source_is_not_replaced_with_guess_or_research_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fake_manifest = (
                Path(temp) / "data/device-catalog/production/icpn-v1-manifest.json"
            )
            with patch.dict(os.environ, {DEVICE_CATALOG_MANIFEST_ENV: str(fake_manifest)}):
                with self.assertRaisesRegex(
                    evidence_module.NXPManufacturerDeviceEvidenceError,
                    "cannot load official NXP manufacturer evidence",
                ):
                    evidence_module.NXPManufacturerDeviceEvidence.from_file(
                        evidence_module._root() / evidence_module.EVIDENCE_RELATIVE_PATH
                    )

    def test_nxp_customer_selector_exposes_routes_but_hides_level0_identity(self) -> None:
        found = _device_search_payload("NXP", limit=100)
        self.assertEqual(found["levels"], [1, 2, 3])
        self.assertEqual(found["total_count"], 20)
        self.assertTrue(found["results"])
        self.assertTrue(all(item["vendor"] == "NXP" for item in found["results"]))
        self.assertTrue(all(item["family"] in {"KL25", "LPC11U6X"} for item in found["results"]))
        self.assertTrue(all(item["catalog_level"] == 1 for item in found["results"]))

        # MCX remains source-verified/admitted identity data, but is active Level 0
        # and therefore must not leak into the customer-facing selector.
        mcx = _device_search_payload("MCXA132VFM", limit=1)
        self.assertEqual(mcx["count"], 0)
        self.assertEqual(mcx["total_count"], 0)


if __name__ == "__main__":
    unittest.main()
