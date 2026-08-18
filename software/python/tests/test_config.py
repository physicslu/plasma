from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_core.config import (
    ChannelConfig,
    PPUConfig,
    PlasmaConfig,
    ProgrammerConfig,
    ServerConfig,
    SiteConfig,
    load_config,
)
from plasma_core.errors import ErrorCode, PlasmaError


class ConfigTests(unittest.TestCase):
    def test_default_file_enables_two_of_eight_sites(self) -> None:
        config = load_config(Path(__file__).parents[1] / "config" / "plasma.yaml")
        self.assertEqual(config.server.max_supported_sites, 8)
        self.assertEqual(config.ppu.id, "z2-dev-01")
        self.assertEqual(config.ppu.facility_id, "swpc-lab")
        self.assertEqual(config.ppu.model, "PYNQ-Z2")
        self.assertEqual(config.site_count, 8)
        self.assertEqual(config.enabled_site_count, 2)
        self.assertEqual([item.id for item in config.sites if item.enabled], [1, 2])
        self.assertEqual([item.id for item in config.sites], list(range(1, 9)))
        self.assertTrue(config.server.output_root.is_absolute())

    def test_new_domain_identity_is_one_based(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_sites=4, max_concurrent_jobs=1),
            sites=[SiteConfig(id=1, enabled=True), SiteConfig(id=2)],
        )
        config.validate()
        self.assertEqual(config.ppu.id, "local-ppu")
        self.assertEqual(config.ppu.facility_id, "default-facility")
        self.assertEqual(config.site_count, 2)
        self.assertEqual(config.enabled_site_count, 1)

    def test_canonical_site_zero_is_rejected(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_sites=2, max_concurrent_jobs=1),
            sites=[SiteConfig(id=0, enabled=True)],
        )
        with self.assertRaises(PlasmaError) as caught:
            config.validate()
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_legacy_config_and_python_aliases_translate_channel_zero_to_site_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plasma.yaml"
            path.write_text(
                "programmer:\n  id: legacy-pgm\n  site_id: legacy-lab\n"
                "server:\n  max_supported_channels: 4\n  max_concurrent_jobs: 1\n"
                "channels:\n  - {id: 0, enabled: true, interface: mock}\n",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.ppu.id, "legacy-pgm")
            self.assertEqual(config.ppu.facility_id, "legacy-lab")
            self.assertEqual(config.sites[0].id, 1)
            self.assertIs(config.programmer, config.ppu)
            self.assertIs(config.channels, config.sites)

        legacy = PlasmaConfig(
            server=ServerConfig(max_supported_channels=2, max_concurrent_jobs=1),
            channels=[ChannelConfig(id=0)],
            programmer=ProgrammerConfig(id="legacy-pgm", site_id="legacy-lab"),
        )
        self.assertEqual(legacy.sites[0].id, 1)
        self.assertEqual(legacy.ppu.facility_id, "legacy-lab")
        self.assertIsInstance(legacy.ppu, PPUConfig)

    def test_invalid_ppu_identity_rejected(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_sites=2, max_concurrent_jobs=1),
            sites=[SiteConfig(id=1)],
            ppu=PPUConfig(id="bad ppu id"),
        )
        with self.assertRaises(PlasmaError) as caught:
            config.validate()
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_empty_facility_identity_rejected(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_sites=2, max_concurrent_jobs=1),
            sites=[SiteConfig(id=1)],
            ppu=PPUConfig(id="ppu-1", facility_id=""),
        )
        with self.assertRaises(PlasmaError) as caught:
            config.validate()
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_duplicate_site_rejected(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_sites=8, max_concurrent_jobs=1),
            sites=[SiteConfig(id=1), SiteConfig(id=1)],
        )
        with self.assertRaises(PlasmaError) as caught:
            config.validate()
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    def test_more_than_eight_sites_rejected(self) -> None:
        config = PlasmaConfig(
            server=ServerConfig(max_supported_sites=9),
            sites=[],
        )
        with self.assertRaises(PlasmaError):
            config.validate()

    def test_hex_register_base(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plasma.yaml"
            path.write_text(
                "server:\n  max_supported_sites: 8\n  max_concurrent_jobs: 1\n"
                "sites:\n  - {id: 1, enabled: true, interface: fpga, register_base: '0x100'}\n",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.sites[0].id, 1)
            self.assertEqual(config.sites[0].register_base, 0x100)


if __name__ == "__main__":
    unittest.main()
