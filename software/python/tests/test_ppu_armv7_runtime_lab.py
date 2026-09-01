from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ppu-armv7-runtime-lab.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ppu_armv7_runtime_lab", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_runtime_location_is_repo_local_work_dir() -> None:
    lab = _load_module()
    assert lab.DEFAULT_RUNTIME_REL == Path(".work/ppu-runtime")
    assert lab.DEFAULT_REPORT_REL == Path(".work/reports/ppu-armv7-runtime-lab.json")


def test_images_are_digest_pinned() -> None:
    lab = _load_module()
    assert "@sha256:" in lab.ARM_IMAGE
    assert "@sha256:" in lab.BINFMT_IMAGE


def test_percentile_is_deterministic() -> None:
    lab = _load_module()
    values = [1.0, 2.0, 3.0, 4.0, 100.0]
    assert lab._percentile(values, 0.95) == 100.0
    assert lab._percentile(values, 0.50) == 3.0
    assert lab._percentile([], 0.95) == 0.0


def test_loopback_body_is_1k_and_crc_matches() -> None:
    lab = _load_module()
    body, crc = lab._loopback_body(7)
    assert body["endpoint"] == "ps"
    assert body["sequence"] == 7
    assert body["payload_length"] == 1024
    assert body["tx_crc32"] == crc


def test_source_contract_keeps_runtime_mount_read_only() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'f"{runtime_dir}:/runtime:ro"' in source
    assert 'f"{Path(__file__).resolve()}:/lab.py:ro"' in source
    assert '"health/live"' in source
    assert '"health/ready"' in source
    assert '"ps-loopback"' in source
    assert 'time.sleep(30)' in source


def test_hardware_evidence_boundary_remains_closed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for claim in (
        "PYNQ-Z2 hardware",
        "systemd boot/reboot",
        "PS-to-PL",
        "Site I/O",
        "target power",
        "real IC programming",
    ):
        assert claim in source
