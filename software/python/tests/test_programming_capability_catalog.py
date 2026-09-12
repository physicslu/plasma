from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from plasma_web.configured_mock_provider import ConfiguredMockEngineeringPPUProvider
from plasma_web.shared_image_mock_provider import SharedImageMockEngineeringPPUProvider


class ProgrammingCapabilityCatalogTests(unittest.TestCase):
    def test_shared_image_mock_advertises_synthetic_image_without_target_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = SharedImageMockEngineeringPPUProvider(
                Path(directory),
                flash_size_bytes=64 * 1024,
            )
            self.assertEqual(
                provider.catalog()["programming_capabilities"],
                {
                    "synthetic_programming_image": True,
                    "target_device_required": False,
                },
            )

    def test_configured_mock_requires_real_image_but_not_explicit_target_device(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "ppu.yaml"
            sites: list[str] = []
            for site_id in range(1, 9):
                enabled = "true" if site_id == 1 else "false"
                mock = "\n    mock: {flash_size: 65536}" if site_id == 1 else ""
                sites.append(
                    f"  - id: {site_id}\n"
                    f"    enabled: {enabled}\n"
                    "    interface: mock\n"
                    f"    target: STM32F103C8T6{mock}"
                )
            config.write_text(
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
                      output_root: {root / "output"}
                      log_root: {root / "logs"}
                    sites:
                    """
                ).lstrip()
                + "\n".join(sites)
                + "\n",
                encoding="utf-8",
            )

            provider = ConfiguredMockEngineeringPPUProvider(config)
            self.assertEqual(
                provider.catalog()["programming_capabilities"],
                {
                    "synthetic_programming_image": False,
                    "target_device_required": False,
                },
            )


if __name__ == "__main__":
    unittest.main()
