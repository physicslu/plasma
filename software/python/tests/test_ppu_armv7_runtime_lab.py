from __future__ import annotations

import argparse
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
    assert lab.DEFAULT_CONTROL_CHECKPOINTS == (1000, 5000, 10000)


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


def test_result_marker_can_be_parsed_from_progress_output() -> None:
    lab = _load_module()
    output = "health/live: 1/1 PASS\n" + lab.RESULT_MARKER + '{"functional_result":"PASS"}\n'
    assert lab._parse_result(output) == {"functional_result": "PASS"}


def test_control_checkpoints_are_cumulative_and_strictly_increasing() -> None:
    lab = _load_module()
    assert lab._parse_checkpoints("1000,5000,10000") == (1000, 5000, 10000)
    for value in ("", "0,100", "100,100", "1000,500"):
        try:
            lab._parse_checkpoints(value)
        except argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError(f"expected checkpoint parse failure for {value!r}")


def test_source_contract_keeps_container_mounts_read_only_and_reports_host_owned() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'f"{runtime_dir}:/runtime:ro"' in source
    assert 'f"{Path(__file__).resolve()}:/lab.py:ro"' in source
    assert ":/reports" not in source
    assert "report_path.write_text" in source
    assert '"health/live"' in source
    assert '"health/ready"' in source
    assert '"ps-loopback"' in source
    assert 'time.sleep(30)' in source


def test_threading_control_is_stdlib_only_and_reports_resource_state_separately() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "ThreadingHTTPServer" in source
    assert '"plasma_imported": False' in source
    assert '"functional_result": "PASS"' in source
    assert '"resource_result": "INVESTIGATE"' in source
    assert '"overall_result": "INVESTIGATE"' in source
    assert '"result": "PASS"' not in source
    assert '"native Z2 memory stability"' in source


def test_hardware_evidence_boundary_remains_closed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for claim in (
        "PYNQ-Z2 hardware",
        "systemd boot/reboot",
        "PS-to-PL",
        "Site I/O",
        "target power",
        "real IC programming",
        "native Z2 memory stability",
    ):
        assert claim in source
