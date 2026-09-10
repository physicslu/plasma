from __future__ import annotations

import re
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from plasma_core.config import load_config
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.site_configuration import SiteConfigurationConflictError, SiteConfigurationController


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

    def revision(self, site_id: int) -> str:
        site = next(item for item in self.controller.current()["sites"] if item["site_id"] == site_id)
        return site["desired_revision"]

    def test_current_reads_canonical_ppu_configuration_with_deterministic_revision(self) -> None:
        current = self.controller.current()
        self.assertEqual(current["source"], "canonical_ppu_config")
        self.assertEqual(len(current["sites"]), 2)
        self.assertEqual(
            {key: value for key, value in current["sites"][0].items() if key != "desired_revision"},
            {"site_id": 1, "enabled": True, "interface": "mock", "target": "TARGET-A"},
        )
        self.assertEqual(
            {key: value for key, value in current["sites"][1].items() if key != "desired_revision"},
            {"site_id": 2, "enabled": False, "interface": "mock", "target": "TARGET-B"},
        )
        for site in current["sites"]:
            self.assertRegex(site["desired_revision"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(self.controller.current()["sites"][0]["desired_revision"], current["sites"][0]["desired_revision"])

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
        self.assertRegex(current["sites"][1]["desired_revision"], r"^sha256:[0-9a-f]{64}$")

    def test_update_persists_only_writable_site_fields(self) -> None:
        saved = self.controller.update(
            1,
            {"enabled": False, "interface": "openocd", "target": "STM32F103C8T6"},
            expected_revision=self.revision(1),
        )
        self.assertEqual(
            {key: value for key, value in saved["sites"][0].items() if key != "desired_revision"},
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
            expected_revision=self.revision(2),
        )
        after_restart = SiteConfigurationController(self.path).current()
        self.assertEqual(after_restart, saved)

    def test_revision_changes_only_for_modified_site(self) -> None:
        before_one = self.revision(1)
        before_two = self.revision(2)
        saved = self.controller.update(
            1,
            {"enabled": True, "interface": "mock", "target": "TARGET-NEW"},
            expected_revision=before_one,
        )
        after_one = saved["sites"][0]["desired_revision"]
        after_two = saved["sites"][1]["desired_revision"]
        self.assertNotEqual(after_one, before_one)
        self.assertEqual(after_two, before_two)
        self.assertTrue(re.fullmatch(r"sha256:[0-9a-f]{64}", after_one))

    def test_stale_revision_is_rejected_without_mutation(self) -> None:
        stale = self.revision(1)
        self.controller.update(
            1,
            {"enabled": True, "interface": "mock", "target": "TARGET-NEW"},
            expected_revision=stale,
        )
        before_conflict = self.path.read_text(encoding="utf-8")

        with self.assertRaises(SiteConfigurationConflictError) as caught:
            self.controller.update(
                1,
                {"enabled": True, "interface": "mock", "target": "TARGET-STALE"},
                expected_revision=stale,
            )

        self.assertEqual(caught.exception.site_id, 1)
        self.assertEqual(caught.exception.expected_revision, stale)
        self.assertNotEqual(caught.exception.current_revision, stale)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before_conflict)

    def test_unknown_site_is_rejected_without_mutation(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        with self.assertRaises(PlasmaError) as caught:
            self.controller.update(
                3,
                {"enabled": True, "interface": "mock", "target": "TARGET-C"},
                expected_revision=self.revision(1),
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
        expected_revision = self.revision(1)
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(PlasmaError) as caught:
                self.controller.update(1, candidate, expected_revision=expected_revision)
            self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)
            self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_persistence_failure_does_not_replace_canonical_config(self) -> None:
        before = self.path.read_text(encoding="utf-8")
        with mock.patch.object(self.controller, "_write_atomic", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.controller.update(
                    1,
                    {"enabled": False, "interface": "mock", "target": "TARGET-A"},
                    expected_revision=self.revision(1),
                )
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
