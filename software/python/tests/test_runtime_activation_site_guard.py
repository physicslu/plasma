from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.site_configuration import SiteConfigurationController


CONFIG = """
ppu:
  id: ppu-guard
  facility_id: lab
  model: virtual
  display_name: Guard PPU
server:
  host: 127.0.0.1
  port: 9900
  max_supported_sites: 8
  max_concurrent_jobs: 1
  max_queue_depth_per_site: 4
  output_root: output
  log_root: logs
sites:
  - id: 1
    enabled: true
    interface: mock
    target: TARGET-A
"""


def test_site_desired_write_fails_closed_while_runtime_activation_guard_is_active(tmp_path: Path) -> None:
    path = tmp_path / "ppu.yaml"
    path.write_text(textwrap.dedent(CONFIG).lstrip(), encoding="utf-8")
    controller = SiteConfigurationController(path)
    baseline = controller.current()["sites"][0]["desired_revision"]

    with controller.runtime_activation_guard():
        with pytest.raises(PlasmaError) as exc_info:
            controller.update(
                1,
                {"enabled": False, "interface": "mock", "target": "TARGET-A"},
                expected_revision=baseline,
            )
        assert exc_info.value.code is ErrorCode.PPU_BUSY

    saved = controller.update(
        1,
        {"enabled": False, "interface": "mock", "target": "TARGET-A"},
        expected_revision=baseline,
    )
    assert saved["sites"][0]["enabled"] is False


def test_concurrent_runtime_activation_guard_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "ppu.yaml"
    path.write_text(textwrap.dedent(CONFIG).lstrip(), encoding="utf-8")
    controller = SiteConfigurationController(path)

    with controller.runtime_activation_guard():
        with pytest.raises(PlasmaError) as exc_info:
            with controller.runtime_activation_guard():
                pass
        assert exc_info.value.code is ErrorCode.PPU_BUSY
