"""Regression: Render wheels must never use .venv/lib as the data root."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import plasma_web.nxp_manufacturer_device_evidence as evidence_module
from plasma_web.catalog_sqlite_repository import CatalogSqliteShadowRepository
from plasma_web.device_catalog import default_catalog_manifest_path
from plasma_web.programming_qualification import get_default_programming_qualification_registry
from plasma_web.device_catalog import DEVICE_CATALOG_MANIFEST_ENV
from plasma_web.legacy_device_selector import _device_search_payload


class NXPInstalledWheelDataRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Offline test fixture: runtime Selector always consumes a qualified SQLite revision.
        cls._sqlite_temporary = tempfile.TemporaryDirectory(prefix="plasma-selector-regression-")
        cls.addClassCleanup(cls._sqlite_temporary.cleanup)
        database = Path(cls._sqlite_temporary.name) / "catalog.sqlite3"
        CatalogSqliteShadowRepository(database).import_verified_manifest(
            default_catalog_manifest_path(),
            qualification_registry=get_default_programming_qualification_registry(),
        )
        cls._sqlite_environment = patch.dict(os.environ, {"PLASMA_CATALOG_SQLITE_DB": str(database)})
        cls._sqlite_environment.start()
        cls.addClassCleanup(cls._sqlite_environment.stop)

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
        self.assertEqual(found["total_count"], 140)
        self.assertTrue(found["results"])
        self.assertTrue(all(item["vendor"] == "NXP" for item in found["results"]))
        self.assertTrue(all(item["family"] in {"KL25", "LPC11U6X", "LPC81X", "LPC11U2X", "MCX"} for item in found["results"]))
        self.assertTrue(all(item["catalog_level"] == 1 for item in found["results"]))

        # Only the 111 reviewed MCX A routes are visible, never A18.
        mcx = _device_search_payload("MCXA132VFM", limit=1)
        self.assertEqual(mcx["count"], 1)
        self.assertEqual(mcx["total_count"], 1)
        a18 = _device_search_payload("MCXA185VLH", limit=1)
        self.assertEqual(a18["total_count"], 0)


if __name__ == "__main__":
    unittest.main()
