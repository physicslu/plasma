"""Host-only negative/positive tests for SWD-04 safety gates.

No Z2, device nodes, network, clocks, services or FPGA are touched.
"""
from __future__ import annotations

import hashlib
import json
import mmap
from pathlib import Path
from unittest.mock import Mock

import pytest

from pl.hil.swd04 import contract as c
from pl.hil.swd04 import mmio_contract as m


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_files(tmp_path: Path, monkeypatch):
    paths = {name: tmp_path / name for name in (
        "candidate.bit", "candidate.hwh", "base.bin", "base.hwh")}
    for name, path in paths.items():
        path.write_bytes(name.encode())
    monkeypatch.setattr(c, "BIT_SHA256", _hash(paths["candidate.bit"]))
    monkeypatch.setattr(c, "HWH_SHA256", _hash(paths["candidate.hwh"]))
    monkeypatch.setattr(c, "RECOVERY_BIN_SHA256", _hash(paths["base.bin"]))
    monkeypatch.setattr(c, "RECOVERY_HWH_SHA256", _hash(paths["base.hwh"]))
    manifest = {
        "identity_schema_version": 1, "hardware_abi_version": 1,
        "swd_command_abi_version": 1, "swd_transaction_abi_version": 1,
        "bitstream_version": "0.1.0", "build_id": c.SOURCE_SHA[:32],
        "fpga_part": "xc7z020clg400-1", "board_part": "tul.com.tw:pynq-z2:part0:1.0",
        "external_pl_io": False, "capability_flags": 0,
        "source_git_sha": c.SOURCE_SHA,
        "bitstream_sha256": c.BIT_SHA256,
        "hwh_sha256": c.HWH_SHA256,
        "design_variant": "swd03_axi_internal_dpidr_fixture",
        "hardware_runtime_ready": False,
        "physical_programming_qualified": False,
        "axi_address_map": {
            name: {
                "base_address": f"0x{base:08X}", "segment_size_bytes": 4096,
            } for name, base in c.AXI_BASES.items()
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return c.Candidate(paths["candidate.bit"], paths["candidate.hwh"],
                       manifest_path, paths["base.bin"], paths["base.hwh"])


def inventory_attestation():
    return ({
        "architecture": "armv7l",
        "pynq_version": "3.1.1",
        "fpga_manager_state": "operating",
        "fclk0_hz": 100000000,
        "metadata_sha256": "a" * 64,
        "sysfs_read_only": True,
        "device_model_confirmed": True,
        "services": {s: "active" for s in c.REQUIRED_SERVICES},
        "uio": [
            {"name": "fabric", "address": "0x40000000", "size": "0x00010000"},
            {"name": "audio-codec-ctrl", "address": "0x43C00000", "size": "0x00010000"},
        ],
    }, {
        "schema_version": 1,
        "exclusive_pl_ownership_confirmed": True,
        "uart_console_verified": True,
        "independent_power_recovery_verified": True,
        "maintenance_window_confirmed": True,
        "restoration_operator_ready": True,
        "no_external_dut_connected": True,
        "original_metadata_backed_up": True,
        "uio_driver_reconciliation_planned": True,
    })


def test_offline_p0_valid_and_never_authorizes_loading(tmp_path, monkeypatch):
    candidate = candidate_files(tmp_path, monkeypatch)
    inv, att = inventory_attestation()
    report = c.plan(candidate, inv, att)
    assert report["preflight"] == "PASS"
    assert report["fpga_loading"] == "NOT_RUN"
    assert report["go_live_authorization"] == "NOT_GRANTED"
    assert report["hardware_access"] == "NOT_RUN"


@pytest.mark.parametrize("bad", [
    "bit", "hwh", "base", "base_hwh", "source", "four_segments",
    "map_offset", "manufactured_capability", "hardware_claim", "variant"
])
def test_p0_rejects_artifact_faults(tmp_path, monkeypatch, bad):
    candidate = candidate_files(tmp_path, monkeypatch)
    inv, att = inventory_attestation()
    if bad == "bit": candidate.bit.write_bytes(b"wrong bit")
    elif bad == "hwh": candidate.hwh.write_bytes(b"wrong hwh")
    elif bad == "base": candidate.recovery_bin.write_bytes(b"wrong recovery")
    elif bad == "base_hwh": candidate.recovery_hwh.write_bytes(b"wrong HWH")
    else:
        doc = json.loads(candidate.manifest.read_text())
        if bad == "source": doc["source_git_sha"] = "bad"
        elif bad == "four_segments": doc["axi_address_map"].pop("transaction_0")
        elif bad == "map_offset":
            doc["axi_address_map"]["transaction_0"]["base_address"] = "0x40004000"
        elif bad == "manufactured_capability":
            doc["physical_programming_qualified"] = True
        elif bad == "hardware_claim": doc["hardware_runtime_ready"] = True
        elif bad == "variant": doc["design_variant"] = "physical_swd"
        candidate.manifest.write_text(json.dumps(doc))
    with pytest.raises(c.SafetyError):
        c.plan(candidate, inv, att)


@pytest.mark.parametrize("bad", [
    "architecture", "pynq", "manager", "clock", "services",
    "fabric", "fd", "serial", "power", "maintenance",
    "metadata", "rebind", "dut"
])
def test_p0_rejects_inventory_and_operator_risk(tmp_path, monkeypatch, bad):
    candidate = candidate_files(tmp_path, monkeypatch)
    inv, att = inventory_attestation()
    if bad == "architecture": inv["architecture"] = "x86_64"
    elif bad == "pynq": inv["pynq_version"] = "3.0"
    elif bad == "manager": inv["fpga_manager_state"] = "unknown"
    elif bad == "clock": inv["fclk0_hz"] = 10000000
    elif bad == "services": inv["services"]["plasma-server.service"] = "failed"
    elif bad == "fabric": inv["uio"][0]["address"] = "0x40001000"
    elif bad == "fd": att["exclusive_pl_ownership_confirmed"] = False
    elif bad == "serial": att["uart_console_verified"] = False
    elif bad == "power": att["independent_power_recovery_verified"] = False
    elif bad == "maintenance": att["maintenance_window_confirmed"] = False
    elif bad == "metadata": att["original_metadata_backed_up"] = False
    elif bad == "rebind": att["uio_driver_reconciliation_planned"] = False
    elif bad == "dut": att["no_external_dut_connected"] = False
    with pytest.raises(c.SafetyError):
        c.plan(candidate, inv, att)


class SimulatedMMIO:
    """Deterministic *functional* model; no device or firmware access."""

    def __init__(self):
        self.state = {}
        identity = c.AXI_BASES["identity_0"]
        fields = [0x504C534D, 0x100, 1, 0]
        fields += [int(c.SOURCE_SHA[i:i+8], 16) for i in range(0, 32, 8)]
        for i, val in enumerate(fields):
            self.state[identity + 4*i] = val
        base = c.AXI_BASES["transaction_0"]
        self.state.update({
            c.AXI_BASES["control_0"] + 4: 0xA5A55A5A,
            c.AXI_BASES["swd_0"]: 1,
            c.AXI_BASES["swd_0"] + 0x1C: 0,
            base: 1,
            c.CONFIG: 4,
            c.HALF: 2,
            base + 0x14: 1,
            base + 0x18: 8,
            base + 0x1C: 0,
            base + 0x20: 1_000_000,
            c.STATUS: c.READY, c.META: 0, c.RDATA: 0,
        })
        self.events = []

    def read32(self, address):
        self.events.append(("read", address))
        return self.state.get(address, 0)

    def write32(self, address, value):
        self.events.append(("write", address, value))
        if address == c.COMMAND:
            if value == 1:
                cfg = self.state[c.CONFIG]
                if cfg == 0 and self.state[c.HALF] == 65535:
                    self.state[c.STATUS] = 1  # Busy, awaiting ABORT
                else:
                    self.state[c.STATUS] = c.RESP_VALID
                    self.state[c.META] = 0x190 if cfg == 4 else 0
                    self.state[c.RDATA] = c.DPIDR if cfg == 4 else 0
            elif value == 2:
                self.state[c.STATUS] = c.RESP_VALID
                self.state[c.META] = 8
                self.state[c.RDATA] = 0
            elif value == 4:
                self.state[c.STATUS] = c.READY
        else:
            self.state[address] = value


def test_hil01_is_read_only_and_exact():
    hw = SimulatedMMIO()
    io = m.RestrictedMMIO(hw)
    assert len(m.hil01_registers(io)) == 21
    assert all(item[0] == "read" for item in hw.events)


def test_hil01_detects_identity_corruption_no_further_access():
    hw = SimulatedMMIO()
    hw.state[c.AXI_BASES["identity_0"]] = 0
    with pytest.raises(c.SafetyError):
        m.hil01_registers(m.RestrictedMMIO(hw))
    assert len(hw.events) == 1


def test_hil02_dpidr_and_explicit_ack():
    hw = SimulatedMMIO()
    io = m.RestrictedMMIO(hw)
    assert m.hil02_dpidr(io)["dpidr"] == "0x2BA01477"
    assert [e[2] for e in hw.events if e[0] == "write" and e[1] == c.COMMAND] == [1,4,1,4]


def test_hil03_abort_and_bounded_recovery():
    hw = SimulatedMMIO()
    io = m.RestrictedMMIO(hw)
    m.hil02_dpidr(io)
    result = m.hil03_recovery(io)
    assert result["repeated_dpidr"] == 3
    assert ("write", c.COMMAND, 2) in hw.events


@pytest.mark.parametrize("addr,val", [
    (0xDEADBEEF, 1), (c.COMMAND, 3), (c.COMMAND, 0),
    (c.CONFIG, 0xFF), (c.HALF, 1), (c.RDATA, 0),
    (c.AXI_BASES["swd_0"] + 4, 1)
])
def test_mmio_write_denylist(addr, val):
    hw = SimulatedMMIO()
    with pytest.raises(c.SafetyError):
        m.RestrictedMMIO(hw).write(addr, val)
    assert hw.events == []


@pytest.mark.parametrize("addr", [
    0x40003FFC, 0x40004000, 0x00000000, 0x40000003,
    c.COMMAND, c.AXI_BASES["swd_0"] + 0x24,
])
def test_mmio_read_denylist(addr):
    hw = SimulatedMMIO()
    with pytest.raises(c.SafetyError):
        m.RestrictedMMIO(hw).read(addr)
    assert hw.events == []


def test_failed_response_halts_without_retry():
    hw = SimulatedMMIO()
    hw.state[c.STATUS] = c.RESP_VALID
    hw.state[c.META] = 0
    hw.state[c.RDATA] = 0
    io = m.RestrictedMMIO(hw)
    with pytest.raises(c.SafetyError):
        m.hil02_dpidr(io)
    assert not any(op == "write" for op, *_ in hw.events)


def test_poll_limit_does_not_initiate_recovery():
    hw = SimulatedMMIO()
    hw.state[c.STATUS] = 1
    with pytest.raises(c.SafetyError):
        m._response(m.RestrictedMMIO(hw), limit=3, sleep_seconds=0)
    assert not any(op == "write" for op, *_ in hw.events)


def test_restore_accepts_only_full_recovery_evidence():
    from pl.hil.swd04 import restore
    before, _ = inventory_attestation()
    after = json.loads(json.dumps(before))
    evidence = {
        "recovery_bin_sha256": c.RECOVERY_BIN_SHA256,
        "base_bin_load_returned_operating": True,
        "candidate_unloaded": True,
        "uios_reconciled": True,
        "public_key_ssh_verified": True,
        "jupyter_http_verified": True,
        "gateway_live_verified": True,
        "gateway_ready_verified": True,
        "no_new_kernel_axi_or_fpga_errors": True,
        "no_ps7_init_or_ddr_reinitialization": True,
    }
    assert restore.verify_restoration(before, after, evidence)["restoration"] == "PASS"


@pytest.mark.parametrize("fault", [
    "metadata", "uio", "clock", "service", "manager", "bin",
    "ssh", "gateway", "kernel",
])
def test_restore_fails_closed_on_missing_recovery(fault):
    from pl.hil.swd04 import restore
    before, _ = inventory_attestation()
    after = json.loads(json.dumps(before))
    evidence = {
        "recovery_bin_sha256": c.RECOVERY_BIN_SHA256,
        "base_bin_load_returned_operating": True,
        "candidate_unloaded": True,
        "uios_reconciled": True,
        "public_key_ssh_verified": True,
        "jupyter_http_verified": True,
        "gateway_live_verified": True,
        "gateway_ready_verified": True,
        "no_new_kernel_axi_or_fpga_errors": True,
        "no_ps7_init_or_ddr_reinitialization": True,
    }
    if fault == "metadata": after["metadata_sha256"] = "b" * 64
    if fault == "uio": after["uio"][0]["address"] = "0x40001000"
    if fault == "clock": after["fclk0_hz"] = 10000000
    if fault == "service": after["services"]["plasma-server.service"] = "inactive"
    if fault == "manager": after["fpga_manager_state"] = "unknown"
    if fault == "bin": evidence["recovery_bin_sha256"] = "x" * 64
    if fault == "ssh": evidence["public_key_ssh_verified"] = False
    if fault == "gateway": evidence["gateway_ready_verified"] = False
    if fault == "kernel": evidence["no_new_kernel_axi_or_fpga_errors"] = False
    with pytest.raises(c.SafetyError):
        restore.verify_restoration(before, after, evidence)


def test_live_harness_is_inert_without_double_confirmation(tmp_path):
    from pl.hil.swd04 import live
    argv = [
        "--stage", "HIL01",
        "--p0-report", str(tmp_path / "missing-p0.json"),
        "--session", str(tmp_path / "missing-session.json"),
        "--candidate-bin", str(tmp_path / "missing-bin"),
        "--output", str(tmp_path / "out.json"),
    ]
    assert live.main(argv) == 2
    assert live.main([*argv, "--execute-live"]) == 2
    assert not (tmp_path / "out.json").exists()


def test_live_backend_does_not_map_anything_when_outside_whitelist():
    from pl.hil.swd04.live import DevMemBackend
    backend = DevMemBackend(readonly=True)
    with pytest.raises(c.SafetyError):
        backend.read32(0xDEADBEEF)
    with pytest.raises(c.SafetyError):
        backend.write32(0x40001000, 0)
    assert backend.fd is None and backend.pages == {}


@pytest.fixture
def ordinary_ram_mmio(tmp_path, monkeypatch):
    """Exercise the actual backend on ordinary files, never /dev/mem or PL."""
    from pl.hil.swd04 import live
    real_mmap = mmap.mmap
    opened, mappings = [], []
    closed_fd = Mock()
    monkeypatch.setattr(live.os, "open", lambda path, flags: 123)
    monkeypatch.setattr(live.os, "close", closed_fd)

    def map_ram(fd, length, *, flags, prot, offset):
        assert fd == 123
        assert length == c.SEGMENT_SIZE and flags == mmap.MAP_SHARED
        image = tmp_path / f"ram-{offset:08x}.bin"
        if not image.exists():
            image.write_bytes(bytes.fromhex("aabbccdd") * (length // 4))
        handle = image.open("r+b")
        opened.append(handle)
        page = real_mmap(handle.fileno(), length, flags=flags, prot=prot)
        mappings.append((offset, page, prot, image))
        return page

    monkeypatch.setattr(live.mmap, "mmap", map_ram)
    yield live, mappings, closed_fd
    for handle in opened:
        handle.close()


def test_live_native_word_mmio_preserves_adjacent_registers(ordinary_ram_mmio):
    live, mappings, closed = ordinary_ram_mmio
    base = c.AXI_BASES["transaction_0"]
    with live.DevMemBackend(readonly=False) as hw:
        hw.write32(c.CONFIG, 0x12345678)  # +8, native word index 2
        assert hw.read32(c.CONFIG) == 0x12345678
        assert hw.read32(c.HALF) == 0xDDCCBBAA  # unrelated word unchanged
        hw.write32(c.HALF, 0x87654321)
        assert hw.read32(c.HALF) == 0x87654321
        hw.write32(c.CONFIG, 0)
        assert hw.read32(c.CONFIG) == 0
        assert len(mappings) == 1
        assert hw.words[base].itemsize == 4
    assert mappings[0][1].closed
    assert mappings[0][3].read_bytes()[8:20] == (
        bytes.fromhex("00000000aabbccdd21436587")
    )
    closed.assert_called_once_with(123)


def test_live_native_word_readonly_mapping_and_cleanup(ordinary_ram_mmio):
    live, mappings, closed = ordinary_ram_mmio
    with pytest.raises(RuntimeError, match="unwind"):
        with live.DevMemBackend(readonly=True) as hw:
            assert hw.read32(c.CONFIG) == 0xDDCCBBAA
            assert hw.words[c.AXI_BASES["transaction_0"]].readonly
            assert mappings[0][2] == mmap.PROT_READ
            with pytest.raises(c.SafetyError, match="HIL-01"):
                hw.write32(c.CONFIG, 0)
            raise RuntimeError("unwind")
    assert mappings[0][1].closed  # no BufferError from exported memoryview
    closed.assert_called_once_with(123)


def test_live_native_word_invalid_inputs_never_map(ordinary_ram_mmio):
    live, mappings, closed = ordinary_ram_mmio
    with live.DevMemBackend(readonly=False) as hw:
        for bad in (c.CONFIG + 1, c.CONFIG + 2, c.CONFIG + 3,
                    0x40004000, True, None):
            with pytest.raises(c.SafetyError):
                hw.write32(bad, 1)
        for bad in (-1, 1 << 32, True, None, "0"):
            with pytest.raises(c.SafetyError):
                hw.write32(c.CONFIG, bad)
        with pytest.raises(c.SafetyError):
            hw.read32(c.CONFIG + 1)
        assert mappings == []
    closed.assert_called_once_with(123)


def live_session_fixture(tmp_path, monkeypatch):
    from pl.hil.swd04 import live
    import os
    import platform
    p0 = tmp_path / "p0.json"
    p0.write_text(json.dumps({
        "preflight": "PASS",
        "candidate_source": c.SOURCE_SHA,
        "sha256": {
            "bit": c.BIT_SHA256,
            "hwh": c.HWH_SHA256,
            "recovery_bin": c.RECOVERY_BIN_SHA256,
        },
    }))
    bin_file = tmp_path / "approved.bin"
    bin_file.write_bytes(b"synthetic firmware; never flash")
    monkeypatch.setattr(c, "CANDIDATE_BIN_SHA256", c.sha256_file(bin_file))
    session = tmp_path / "session.json"
    fields = dict.fromkeys((
        "confirmed_after_gate2_merge",
        "live_fpga_manager_load_supervised",
        "candidate_bitstream_loaded_and_verified",
        "original_services_quiesced_for_pl_access",
        "all_prior_pl_consumers_isolated",
        "uios_unbound_or_ownership_reconciled",
        "uart_console_verified",
        "independent_power_recovery_verified",
        "no_external_dut_connected",
        "operator_present_at_console",
        "original_metadata_backup_verified",
    ), True)
    fields.update({
        "stage": "HIL01",
        "candidate_source": c.SOURCE_SHA,
        "candidate_bit_sha256": c.BIT_SHA256,
        "candidate_hwh_sha256": c.HWH_SHA256,
        "recovery_bin_sha256": c.RECOVERY_BIN_SHA256,
        "p0_sha256": c.sha256_file(p0),
        "candidate_bin_sha256": c.sha256_file(bin_file),
        "supervised_load_log_sha256": "f" * 64,
    })
    session.write_text(json.dumps(fields))
    monkeypatch.setattr(live.os, "geteuid", lambda: 0)
    monkeypatch.setattr(live.platform, "machine", lambda: "armv7l")
    prior_text = Path.read_text
    def read_text(path, *args, **kwargs):
        if str(path) == "/sys/class/fpga_manager/fpga0/state":
            return "operating\n"
        return prior_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(
        Path, "is_char_device", lambda self: str(self) == "/dev/mem"
    )
    return p0, session, bin_file, fields


def test_live_preopen_gate_accepts_only_complete_synthetic_session(tmp_path, monkeypatch):
    from pl.hil.swd04 import live
    p0, session, bin_file, _ = live_session_fixture(tmp_path, monkeypatch)
    live.require_live_session(
        phase="HIL01", p0=p0, session=session,
        candidate_bin=bin_file, previous=None,
    )
    assert not (tmp_path / "devmem-activity").exists()


@pytest.mark.parametrize("tamper", [
    "gate2", "ownership", "candidate", "preflight", "log",
    "wrong_stage", "unexpected_previous"
])
def test_live_preopen_gate_denies_corrupt_session(tmp_path, monkeypatch, tamper):
    from pl.hil.swd04 import live
    p0, session, bin_file, fields = live_session_fixture(tmp_path, monkeypatch)
    previous = None
    if tamper == "gate2": fields["confirmed_after_gate2_merge"] = False
    elif tamper == "ownership": fields["all_prior_pl_consumers_isolated"] = False
    elif tamper == "candidate": fields["candidate_bin_sha256"] = "0" * 64
    elif tamper == "preflight": fields["p0_sha256"] = "0" * 64
    elif tamper == "log": fields["supervised_load_log_sha256"] = ""
    elif tamper == "wrong_stage": fields["stage"] = "HIL02"
    elif tamper == "unexpected_previous":
        previous = tmp_path / "unexpected.json"
        previous.write_text("{}")
    session.write_text(json.dumps(fields))
    with pytest.raises(c.SafetyError):
        live.require_live_session(
            phase="HIL01", p0=p0, session=session,
            candidate_bin=bin_file, previous=previous,
        )
