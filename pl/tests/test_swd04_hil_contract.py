"""Host-only negative/positive tests for SWD-04 safety gates.

No Z2, device nodes, network, clocks, services or FPGA are touched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

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
                if cfg == 0 and self.state[c.HALF] == 9:
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
