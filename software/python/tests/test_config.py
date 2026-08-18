from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_core.config import (
    ChannelConfig,
    PlasmaConfig,
    ProgrammerConfig,
    ServerConfig,
    load_config,
)
from plasma_core.errors import ErrorCode, PlasmaError


class ConfigTests(unittest.TestCase):
    def test_default_file_enables_two_of_eight_channels(self) -> None:
        config = load_config(Path(__file__).parents[1] / "config" / "plasma.yaml")
        self.assertEqual(config.server.max_supported_channels, 8)
        self.assertEqual(config.programmer.id, "z2-dev-01")
        self.assertEqual(config.programmer.site_id, "swpc-lab")
        self.assertEqual(config.programmer.model, "PYNQ-Z2")
        self.assertEqual(config.channel_count, 8)
        self.assertEqual(config.enabled_channel_count, 2)
        self.assertEqual([item.id for item in config.channels if item.enabled], [0, 1])
        self.assertTrue(config.server.output_root.is_absolute())

    def test_programmer_identity_has_backward_compatible_defaults(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_channels=4, max_concurrent_jobs=1),
            channels=[ChannelConfig(id=0, enabled=True), ChannelConfig(id=1)],
        )
        config.validate()
        self.assertEqual(config.programmer.id, "local-programmer")
        self.assertEqual(config.programmer.site_id, "default-site")
        self.assertEqual(config.channel_count, 2)
        self.assertEqual(config.enabled_channel_count, 1)

    def test_invalid_programmer_identity_rejected(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_channels=2, max_concurrent_jobs=1),
            channels=[ChannelConfig(id=0)],
            programmer=ProgrammerConfig(id="bad programmer id"),
        )
        with self.assertRaises(PlasmaError) as caught:
            config.validate()
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_duplicate_channel_rejected(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_channels=8, max_concurrent_jobs=1),
            channels=[ChannelConfig(id=0), ChannelConfig(id=0)],
        )
        with self.assertRaises(PlasmaError) as caught:
            config.validate()
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_more_than_eight_channels_rejected(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_channels=9),
            channels=[],
        )
        with self.assertRaises(PlasmaError):
            config.validate()

    def test_hex_register_base(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plasma.yaml"
            path.write_text(
                "server:\n  max_supported_channels: 8\n  max_concurrent_jobs: 1\n"
                "channels:\n  - {id: 0, enabled: true, interface: fpga, register_base: '0x100'}\n",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.channels[0].register_base, 0x100)
