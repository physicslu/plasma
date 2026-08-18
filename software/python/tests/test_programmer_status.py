from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_core.config import ChannelConfig, PlasmaConfig, ProgrammerConfig, ServerConfig
from plasma_server.channel_manager import ChannelManager


class ProgrammerStatusTests(unittest.TestCase):
    def test_status_exposes_programmer_identity_and_dynamic_channel_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = PlasmaConfig(
                server=ServerConfig(
                    max_supported_channels=8,
                    max_concurrent_jobs=1,
                    output_root=root / "output",
                    log_root=root / "logs",
                ),
                channels=[ChannelConfig(id=0), ChannelConfig(id=1), ChannelConfig(id=2)],
                programmer=ProgrammerConfig(
                    id="programmer-42",
                    site_id="factory-a",
                    model="Plasma-4CH",
                    display_name="Line A Programmer",
                ),
            )

            status = ChannelManager(config).status()

            self.assertEqual(
                status["programmer"],
                {
                    "programmer_id": "programmer-42",
                    "site_id": "factory-a",
                    "model": "Plasma-4CH",
                    "display_name": "Line A Programmer",
                    "channel_count": 3,
                    "enabled_channel_count": 0,
                    "capabilities": {
                        "max_supported_channels": 8,
                        "operations": ["erase", "program", "verify", "read"],
                    },
                },
            )
            self.assertEqual([item["channel_id"] for item in status["channels"]], [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
