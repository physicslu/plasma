from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plasma_web.device_catalog import (
    DEVICE_CATALOG_PATH_ENV,
    DeviceCatalog,
    default_catalog_path,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class DeviceCatalogRuntimePathTests(unittest.TestCase):
    def test_environment_override_is_authoritative(self) -> None:
        configured = Path("/tmp/plasma-catalog.csv")
        with patch.dict(os.environ, {DEVICE_CATALOG_PATH_ENV: str(configured)}):
            self.assertEqual(default_catalog_path(), configured)

    def test_explicit_runtime_catalog_can_be_loaded_outside_the_python_package(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "catalog.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "vendor",
                        "family",
                        "subfamily",
                        "plasma_series",
                        "part_number",
                        "identifier_kind",
                        "cpu_architectures",
                        "target_config",
                        "openocd_distribution",
                        "mapping_status",
                        "validation_status",
                        "catalog_origin",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "vendor": "STMicroelectronics",
                        "family": "STM32",
                        "subfamily": "STM32F1",
                        "plasma_series": "STM32F1",
                        "part_number": "STM32F103C8T6",
                        "identifier_kind": "manufacturer_part_number",
                        "cpu_architectures": '["arm-cortex-m3"]',
                        "target_config": "target/stm32f1x.cfg",
                        "openocd_distribution": "upstream",
                        "mapping_status": "candidate",
                        "validation_status": "research_only",
                        "catalog_origin": "unit-test",
                    }
                )

            with patch.dict(os.environ, {DEVICE_CATALOG_PATH_ENV: str(path)}):
                catalog = DeviceCatalog.from_csv(default_catalog_path())

            self.assertEqual(catalog.size, 1)
            self.assertEqual(catalog.search("STM32F103C8T6")[0].icpn, "STM32F103C8T6")

    def test_render_start_exports_checkout_catalog_path(self) -> None:
        script = (REPOSITORY_ROOT / "scripts/render-start.sh").read_text(encoding="utf-8")
        self.assertIn("PLASMA_DEVICE_CATALOG_PATH", script)
        self.assertIn("data/device-catalog/research/openocd-parts-canonical.csv", script)
        self.assertIn('export PLASMA_DEVICE_CATALOG_PATH="${catalog_path}"', script)
        self.assertIn("Missing Device Catalog", script)


if __name__ == "__main__":
    unittest.main()
