from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plasma_web.device_catalog import (
    DEVICE_CATALOG_MANIFEST_ENV,
    DeviceCatalog,
    DeviceCatalogIntegrityError,
    default_catalog_manifest_path,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_HEADER = (
    "manufacturer,icpn,family,series,base_device,package,pin_count,flash_size,temperature_grade,"
    "option_suffix,cmsis_device_name,existing_identifier,existing_identifier_kind,mapping_status,"
    "openocd_target_config,source_type,source_reference,source_authority,verification_status\n"
)


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()  # noqa: S324


class DeviceCatalogRuntimePathTests(unittest.TestCase):
    def test_environment_manifest_override_is_authoritative(self) -> None:
        configured = Path("/tmp/plasma-icpn-manifest.json")
        with patch.dict(os.environ, {DEVICE_CATALOG_MANIFEST_ENV: str(configured)}):
            self.assertEqual(default_catalog_manifest_path(), configured)

    def test_explicit_production_manifest_can_be_loaded_outside_python_package(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            source = root_path / "catalog.csv"
            source.write_text(
                CANONICAL_HEADER
                + "STMicroelectronics,STM32F103C8T6,STM32F1,STM32F103,STM32F103C8,LQFP,48,64 KiB,-40 to 85 C,,STM32F103C8,STM32F103C8,cmsis_device_name,deterministic_pattern,tcl/target/stm32f1x.cfg,official_st_product_page_retained_browser_evidence,https://www.st.com/example,STMicroelectronics official,verified_direct_st_retained_browser_exact_icpn\n",
                encoding="utf-8",
            )
            data = source.read_bytes()
            manifest = root_path / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "catalog_id": "test-icpn",
                        "catalog_version": "1.0.0-test",
                        "status": "production",
                        "selection_policy": "admitted_exact_manufacturer_part_number_only",
                        "sources": [
                            {
                                "manufacturer": "STMicroelectronics",
                                "family": "STM32F1",
                                "path": "catalog.csv",
                                "row_count": 1,
                                "git_blob_sha": _git_blob_sha(data),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            catalog = DeviceCatalog.from_manifest(manifest)

            self.assertEqual(catalog.size, 1)
            self.assertEqual(catalog.search("STM32F103C8T6")[0].icpn, "STM32F103C8T6")

    def test_manifest_rejects_source_mutation_without_binding_update(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            source = root_path / "catalog.csv"
            source.write_text(CANONICAL_HEADER, encoding="utf-8")
            manifest = root_path / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "catalog_id": "test-icpn",
                        "catalog_version": "1.0.0-test",
                        "status": "production",
                        "selection_policy": "admitted_exact_manufacturer_part_number_only",
                        "sources": [
                            {
                                "manufacturer": "STMicroelectronics",
                                "family": "STM32F1",
                                "path": "catalog.csv",
                                "row_count": 1,
                                "git_blob_sha": "0" * 40,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DeviceCatalogIntegrityError, "Git blob mismatch"):
                DeviceCatalog.from_manifest(manifest)

    def test_render_start_exports_checkout_production_manifest(self) -> None:
        script = (REPOSITORY_ROOT / "scripts/render-start.sh").read_text(encoding="utf-8")
        self.assertIn("PLASMA_DEVICE_CATALOG_MANIFEST", script)
        self.assertIn("data/device-catalog/production/icpn-v1-manifest.json", script)
        self.assertIn('export PLASMA_DEVICE_CATALOG_MANIFEST="${catalog_manifest}"', script)
        self.assertIn("Missing production Device Catalog manifest", script)
        self.assertIn("python -m plasma_web.device_catalog --manifest", script)
        self.assertNotIn("openocd-parts-canonical.csv", script)


if __name__ == "__main__":
    unittest.main()
