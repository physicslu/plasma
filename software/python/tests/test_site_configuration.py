from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from plasma_core.config import load_config
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.site_configuration import SiteConfigurationController


CONFIG = """
ppu:
  id: ppu-test-01
  facility_id: test-lab
  model: virtual
  display_name: Virtual PPU
server:
  host: 127.0.0.1
  port: 9900
  max_supported_sites: 8
  max_concurrent_jobs: 2
  max_queue_depth_per_site: 4
  output_root: output
  log_root: logs
  max_metadata_bytes: 65536
  max_map_bytes: 1048576
  max_binary_bytes: 67108864
sites:
  - id: 1
    enabled: true
    interface: mock
    target: TARGET-A
    operation_timeout_s: 12.5
    mock:
      flash_size: 4096
  - id: 2
    enabled: false
    interface: mock
    target: TARGET-B
"""


class SiteConfigurationControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "config" / "plasma.yaml"
        self.path.parent.mkdir(parents=True)
        self.path.write_text(textwrap.dedent(CONFIG).lstrip(), encoding="utf-8")
        self.controller = SiteConfigurationController(self.path)

    def test_current_reads_canonical_ppu_configuration(self) -> None:
        self.assertEqual(
            self.controller.current(),
            {
                "source": "canonical_ppu_config",
                "sites": [
                    {"site_id": 1, "enabled": True, "interface": "mock", "target": "TARGET-A"},
                    {"site_id": 2, "enabled": False, "interface": "mock", "target": "TARGET-B"},
                ],
            },
        )

    def test_current_expands_effective_defaults_when_yaml_omits_target(self) -> None:
        self.path.write_text(
            textwrap.dedent(CONFIG).lstrip().replace(
                "  - id: 2\n    enabled: false\n    interface: mock\n    target: TARGET-B\n",
                "  - id: 2\n    enabled: false\n    interface: mock\n",
            ),
            encoding="utf-8",
        )

        current = SiteConfigurationController(self.path).current()

        self.assertEqual(current["sites"][1]["target"], "STM32F103C8T6")

    def test_update_persists_only_writable_site_fields(self) -> None:
        saved = self.controller.update(
            1,
            {"enabled": False, "interface": "openocd", "target": "STM32F103C8T6"},
        )
        self.assertEqual(
            saved["sites"][0],
            {"site_id": 1, "enabled": False, "interface": "openocd", "target": "STM32F103C8T6"},
        )

        reloaded = load_config(self.path)
        site = next(item for item in reloaded.sites if item.id == 1)
        self.assertFalse(site.enabled)
        self.assertEqual(site.interface, "openocd")
        self.assertEqual(site.target, "STM32F103C8T6")
        self.assertEqual(site.operation_timeout_s, 12.5)
        self.assertEqual(site.mock["flash_size"], 4096)

    def test_restart_persistence_round_trip(self) -> None:
        saved = self.controller.update(
            2,
            {"enabled": True, "interface": "fpga", "target": "TARGET-C"},
        )
        after_restart = SiteConfigurationController(self.path).current()
        self.assertEqual(after_restart, saved)

    def test_unknown_site_is_rejected_without_mutation(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        with self.assertRaises(PlasmaError) as caught:
            self.controller.update(
                3,
                {"enabled": True, "interface": "mock", "target": "TARGET-C"},
            )
        self.assertEqual(caught.exception.code, ErrorCode.SITE_INVALID)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_invalid_site_payload_fails_closed(self) -> None:
        invalid = (
            {"enabled": True, "interface": "uart", "target": "TARGET-A"},
            {"enabled": True, "interface": "mock", "target": ""},
            {"enabled": 1, "interface": "mock", "target": "TARGET-A"},
            {"enabled": True, "interface": "mock", "target": " TARGET-A"},
            {"enabled": True, "interface": "mock", "target": "TARGET-A", "extra": True},
        )
        before = self.path.read_text(encoding="utf-8")
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(PlasmaError) as caught:
                self.controller.update(1, candidate)
            self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)
            self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_persistence_failure_does_not_replace_canonical_config(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        with mock.patch.object(self.controller, "_write_atomic", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.controller.update(
                    1,
                    {"enabled": False, "interface": "mock", "target": "TARGET-A"},
                )
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
