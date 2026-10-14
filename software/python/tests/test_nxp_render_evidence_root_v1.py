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

    def test_nxp_vendor_and_exact_search_stay_admitted_only(self) -> None:
        found = _device_search_payload("NXP", limit=1)
        self.assertEqual(found["total_count"], 224)
        self.assertEqual(found["results"][0]["vendor"], "NXP")
        mcx = _device_search_payload("MCXA132VFM", limit=1)
        self.assertEqual(mcx["count"], 1)
        item = mcx["results"][0]
        self.assertEqual(item["icpn"], "MCXA132VFM")
        self.assertEqual(item["nxp_manufacturer_device_profile"]["icpn"], item["icpn"])
        self.assertEqual(item["backend"]["mapping_status"], "no_mapping")
        self.assertIsNone(item["selected_profile"])
        self.assertEqual(item["physical_validation"]["socket_status"], "no_evidence")


if __name__ == "__main__":
    unittest.main()
