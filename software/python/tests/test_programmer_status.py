from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_core.config import PPUConfig, PlasmaConfig, ServerConfig, SiteConfig
from plasma_server.channel_manager import SiteManager


class PPUStatusTests(unittest.TestCase):
    def test_status_exposes_ppu_identity_and_dynamic_site_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = PlasmaConfig(
                server=ServerConfig(
                    max_supported_channels=8,
                    max_concurrent_jobs=1,
                    output_root=root / "output",
                    log_root=root / "logs",
                ),
                sites=[SiteConfig(id=0), SiteConfig(id=1), SiteConfig(id=2)],
                ppu=PPUConfig(
                    id="ppu-42",
                    facility_id="factory-a",
                    model="Plasma-4Site",
                    display_name="Line A PPU",
                ),
            )

            status = SiteManager(config).status()

            self.assertEqual(
                status["ppu"],
                {
                    "ppu_id": "ppu-42",
                    "facility_id": "factory-a",
                    "model": "Plasma-4Site",
                    "display_name": "Line A PPU",
                    "site_count": 3,
                    "enabled_site_count": 0,
                    "capabilities": {
                        "max_supported_sites": 8,
                        "operations": ["erase", "program", "verify", "read"],
                    },
                },
            )
            self.assertEqual([item["site_id"] for item in status["sites"]], [0, 1, 2])

    def test_status_retains_legacy_programmer_channel_shape_during_migration(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_channels=2, max_concurrent_jobs=1),
            sites=[SiteConfig(id=0), SiteConfig(id=1)],
            ppu=PPUConfig(id="ppu-legacy", facility_id="facility-1"),
        )

        status = SiteManager(config).status(site_id=1)

        self.assertEqual(status["programmer"]["programmer_id"], "ppu-legacy")
        self.assertEqual(status["programmer"]["site_id"], "facility-1")
        self.assertEqual(status["channels"][0]["channel_id"], 1)
        self.assertEqual(status["sites"][0]["site_id"], 1)


if __name__ == "__main__":
    unittest.main()
