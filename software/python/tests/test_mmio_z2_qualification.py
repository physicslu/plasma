"""MMIO-13/15 offline-only qualification tests. No hardware access."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pl.hil.swd04 import contract as c
from pl.hil.swd04 import native_qualify as q
from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOError, MMIOAperture


def test_explicit_stage_apertures_match_reviewed_four_segment_build():
    read = q.apertures("HIL01")
    write = q.apertures("HIL02")
    assert [x.base for x in read] == list(c.AXI_BASES.values())
    assert [x.base for x in write] == list(c.AXI_BASES.values())
    assert all(isinstance(x, MMIOAperture) for x in read + write)
    assert all(not x.writable for x in read)
    assert read[1].readable == frozenset({4})
    assert write[1].writable == frozenset({0})
    assert write[1].readable == frozenset({0, 4})
    assert 0x04 in write[3].writable
    assert 0x04 not in write[3].readable
    assert 0x24 in write[3].readable
    assert 0x24 not in write[3].writable
    with pytest.raises(c.SafetyError):
        q.apertures("HIL03")


def test_runtime_validation_rejects_wrong_python_or_cpu():
    kwargs = {
        "version": (3, 12, 13),
        "executable": "/opt/plasma/python/3.12.13/bin/python3",
        "machine": "armv7l",
        "endian": "little",
    }
    q.check_runtime(**kwargs)
    for change in (
        {"version": (3, 10, 4)}, {"version": (3, 12, 15)},
        {"machine": "x86_64"}, {"endian": "big"},
        {"executable": "/usr/bin/python3"},
    ):
        with pytest.raises(c.SafetyError):
            q.check_runtime(**(kwargs | change))


def test_default_cli_without_both_flags_stays_inert(monkeypatch, tmp_path, capsys):
    def forbid(*args, **kwargs):
        raise AssertionError("HIL guard should not touch real devices")

    monkeypatch.setattr(q, "run_stage", forbid)
    monkeypatch.setattr(q, "require_live_session", forbid)
    monkeypatch.setattr(q, "check_runtime", forbid)
    argv = [
        "--stage", "HIL01", "--p0-report", str(tmp_path / "p0.json"),
        "--session", str(tmp_path / "session.json"),
        "--candidate-bin", str(tmp_path / "candidate.bin"),
        "--output", str(tmp_path / "evidence"),
    ]
    assert q.main(argv) == 2
    assert not (tmp_path / "evidence").exists()
    assert "inert" in capsys.readouterr().err
    assert q.main(argv + ["--execute-live"]) == 2
    assert q.main(argv + ["--ack-unrecoverable-axi-stall-risk"]) == 2


def test_false_session_rejected_before_dev_mem(monkeypatch, tmp_path):
    def reject_runtime():
        raise c.SafetyError("not the approved ARMv7 Python runtime")

    def forbid(*args, **kwargs):
        raise AssertionError("must not touch /dev/mem")

    monkeypatch.setattr(q, "check_runtime", reject_runtime)
    monkeypatch.setattr(q, "require_live_session", forbid)
    monkeypatch.setattr(q, "run_stage", forbid)
    flags = ["--execute-live", "--ack-unrecoverable-axi-stall-risk"]
    argv = [
        "--stage", "HIL01", "--p0-report", str(tmp_path / "p0.json"),
        "--session", str(tmp_path / "session.json"),
        "--candidate-bin", str(tmp_path / "candidate.bin"),
        "--output", str(tmp_path / "evidence"),
    ]
    assert q.main(argv + flags) == 2
    assert not (tmp_path / "evidence").exists()


def _put32(path: Path, address: int, value: int):
    with path.open("r+b") as f:
        f.seek(address)
        f.write(value.to_bytes(4, "little"))


@pytest.fixture
def fake_image(tmp_path):
    # A sparse regular file emulating address layout (NOT FPGA semantics).
    file = tmp_path / "not-devmem"
    with file.open("wb") as f:
        f.truncate(q.TRANSACTION + 4096)
    identity = (0x504C534D, 0x100, 1, 0, *(
        int(c.SOURCE_SHA[i:i + 8], 16) for i in range(0, 32, 8)
    ))
    for i, word in enumerate(identity):
        _put32(file, q.IDENTITY + i * 4, word)
    values = {
        q.CONTROL + 4: 0xA5A55A5A,
        q.WAVEFORM: 1,
        q.WAVEFORM + 0x1C: 0,
        q.TRANSACTION: 1,
        q.TRANSACTION + 0x08: 4,
        q.TRANSACTION + 0x10: 2,
        q.TRANSACTION + 0x14: 1,
        q.TRANSACTION + 0x18: 8,
        q.TRANSACTION + 0x1C: 0,
        q.TRANSACTION + 0x20: 1000000,
        q.TRANSACTION + 0x24: 2,
        q.TRANSACTION + 0x28: 0,
        q.TRANSACTION + 0x2C: 0,
    }
    for address, value in values.items():
        _put32(file, address, value)
    return str(file), str(tmp_path / "mmio.lock")


def test_hil01_file_backed_native_backend_complete_identity(fake_image):
    device, lock = fake_image
    result = q.run_stage("HIL01", device=device, owner_lock=lock)
    assert result["read_only"] is True
    assert result["identity"]["transaction_abi"] == 1
    assert result["identity"]["control_status"] == 0xA5A55A5A


def test_hil01_rejects_unverified_build_identity_without_retry(fake_image):
    device, lock = fake_image
    _put32(Path(device), q.IDENTITY + 0x1C, 0)
    with pytest.raises(c.SafetyError, match="Identity"):
        q.run_stage("HIL01", device=device, owner_lock=lock)
    with LinuxMMIO(q.apertures("HIL01"), device=device, owner_lock=lock, readonly=True):
        pass  # prior instance released its advisory lock and mappings


def test_hil01_rejects_unverified_axi_abi(fake_image):
    device, lock = fake_image
    _put32(Path(device), q.TRANSACTION, 0)
    with pytest.raises(c.SafetyError, match="transaction_abi"):
        q.run_stage("HIL01", device=device, owner_lock=lock)


class FakeControl:
    def __init__(self, broken=False):
        self.control = 0
        self.log = []
        self.broken = broken

    def write32(self, address, value):
        assert address == q.CONTROL
        self.control = value
        self.log.append(("write", address, value))

    def read32(self, address):
        self.log.append(("read", address))
        if address == q.CONTROL:
            return self.control
        assert address == q.CONTROL + 4
        return (self.control ^ 0xA5A55A5A) ^ (1 if self.broken else 0)


def test_control_echo_patterns_and_restore_zero():
    hw = FakeControl()
    result = q.control_echo(hw)
    assert result["count"] == 6
    assert result["control_restored_zero"] is True
    assert hw.control == 0
    assert [x[2] for x in hw.log if x[0] == "write"] == list(q.CONTROL_PATTERNS)


def test_control_echo_failure_stops_and_does_not_retry():
    hw = FakeControl(broken=True)
    with pytest.raises(c.SafetyError, match="STOP without retry"):
        q.control_echo(hw)
    assert len([x for x in hw.log if x[0] == "write"]) == 1


def test_swd05_uses_production_driver(monkeypatch):
    observed = []

    class FakeDriver:
        def __init__(self, port, *, base, site_id, poll_budget, max_poll_seconds):
            observed.append(("construct", port, base, site_id,
                             poll_budget, max_poll_seconds))

        def line_reset(self):
            observed.append(("reset",))

        def read_dp(self, address):
            observed.append(("read_dp", address))
            return c.DPIDR

    monkeypatch.setattr(q, "SWDTransactionDriver", FakeDriver)
    port = object()
    assert q.synthetic_dpidr(port)["dpidr"] == "0x2BA01477"
    assert observed == [
        ("construct", port, q.TRANSACTION, 1, 10000, 2.0),
        ("reset",), ("read_dp", 0),
    ]


def test_swd05_mismatch_is_fail_closed(monkeypatch):
    class FakeDriver:
        def __init__(self, *args, **kwargs):
            pass

        def line_reset(self):
            pass

        def read_dp(self, address):
            return 0

    monkeypatch.setattr(q, "SWDTransactionDriver", FakeDriver)
    with pytest.raises(c.SafetyError, match="Synthetic DPIDR mismatch"):
        q.synthetic_dpidr(object())


def test_started_and_result_evidence_never_overwritten(tmp_path):
    path = tmp_path / "record.json"
    q._record(path, {"result": "STARTED", "restoration": "NOT_RUN"})
    assert json.loads(path.read_text())["restoration"] == "NOT_RUN"
    with pytest.raises(FileExistsError):
        q._record(path, {"result": "PASS"})
