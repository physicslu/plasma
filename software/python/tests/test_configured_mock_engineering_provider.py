from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.configured_mock_provider import ConfiguredMockEngineeringPPUProvider
from plasma_web.shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


class ConfiguredMockEngineeringProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root / "ppu.yaml"
        self._write_config()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_config(self, *, site2_interface: str = "mock") -> None:
        output = self.root / "output"
        logs = self.root / "logs"
        sites = []
        for site_id in range(1, 9):
            enabled = "true" if site_id == 1 else "false"
            interface = site2_interface if site_id == 2 else "mock"
            mock = "\n    mock: {flash_size: 65536}" if site_id == 1 else ""
            sites.append(
                f"  - id: {site_id}\n"
                f"    enabled: {enabled}\n"
                f"    interface: {interface}\n"
                f"    target: STM32F103C8T6{mock}"
            )
        self.config.write_text(
            textwrap.dedent(
                f"""
                ppu:
                  id: swpc-z2like-01
                  facility_id: lab
                  model: SWPC-Z2-SURROGATE
                  display_name: SWPC Z2-like PS-only PPU
                server:
                  host: 127.0.0.1
                  port: 9900
                  max_supported_sites: 8
                  max_concurrent_jobs: 1
                  max_queue_depth_per_site: 16
                  output_root: {output}
                  log_root: {logs}
                sites:
                """
            ).lstrip()
            + "\n".join(sites)
            + "\n",
            encoding="utf-8",
        )

    def test_catalog_is_exactly_one_configured_ppu_and_eight_sites(self) -> None:
        provider = ConfiguredMockEngineeringPPUProvider(self.config)
        catalog = provider.catalog()

        self.assertEqual(catalog["provider"], "configured_mock")
        self.assertEqual(catalog["facility_count"], 1)
        self.assertEqual(catalog["ppu_count"], 1)
        self.assertEqual(catalog["site_count"], 8)
        self.assertEqual(catalog["facilities"][0]["facility_id"], "lab")
        ppu = catalog["facilities"][0]["ppus"][0]
        self.assertEqual(ppu["ppu_id"], "swpc-z2like-01")
        self.assertEqual(ppu["site_count"], 8)
        self.assertEqual(ppu["provider"], "configured_mock")
        self.assertEqual(catalog["timing_profile"]["site_flash_size_bytes"]["1"], 65536)
        self.assertEqual(catalog["timing_profile"]["site_flash_size_bytes"]["2"], 256 * 1024)
        self.assertNotIsInstance(provider, SharedImageMockEngineeringPPUProvider)

    def test_constructor_refuses_any_non_mock_site(self) -> None:
        self._write_config(site2_interface="openocd")
        with self.assertRaises(PlasmaError) as caught:
            ConfiguredMockEngineeringPPUProvider(self.config)
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)
        self.assertEqual(caught.exception.context["site_ids"], [2])


if __name__ == "__main__":
    unittest.main()
