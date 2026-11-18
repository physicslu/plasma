"""Host-only MPE architecture proof: documents/address/pin/ownership, NOT RTL."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

PL = Path(__file__).resolve().parents[1]
DESIGN = PL / "projects/z2-mpe-dual-site"
ARCH = json.loads((DESIGN / "architecture.json").read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location("mpe_architecture", DESIGN / "validate_architecture.py")
assert spec and spec.loader
mpe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mpe)


def test_clean_sheet_has_two_different_real_pmods_and_no_hil_claim():
    result = mpe.validate(ARCH)
    assert result["status"] == "ARCHITECTURE_CONTRACT_PASS_HOST_ONLY"
    assert result["site_1"] == {"connector": "JA", "base": "0x43C01000"}
    assert result["site_2"] == {"connector": "JB", "base": "0x43C02000"}
    assert result["dpidr"] == "NOT_RUN"
    assert result["synthesis"] == "NOT_RUN"


@pytest.mark.parametrize("field,value", [
    ("site_count", 8),
    ("site_ids_one_based", False),
    ("host_execution", "SWPC_REMOTE_BITBANG"),
    ("ps_to_pl", "PER_EDGE_MMIO_BITBANG"),
    ("engine_per_site", "ONE_GLOBAL_SWCLK_MIRROR"),
    ("status", "DEPLOYED"),
])
def test_reject_incorrect_scope_and_mirrored_engines(field, value):
    item = deepcopy(ARCH)
    item[field] = value
    with pytest.raises(mpe.ArchitectureRejected):
        mpe.validate(item)


@pytest.mark.parametrize("index,field,bad", [
    (0, "pmod", "JB"),
    (1, "pmod", "JA"),
    (0, "swclk", {"pmod_pin": 1, "fpga_pin": "W14"}),
    (1, "swdio", {"pmod_pin": 2, "fpga_pin": "Y19"}),
    (0, "ground_pins", [6, 12]),
])
def test_reject_wrong_pmod_and_power_pin_confusion(index, field, bad):
    item = deepcopy(ARCH)
    item["sites"][index][field] = bad
    with pytest.raises(mpe.ArchitectureRejected):
        mpe.validate(item)


@pytest.mark.parametrize("field,bad", [
    ("target_io_voltage", 5),
    ("target_io_voltage", 1.8),
    ("io_standard", "LVCMOS18"),
    ("no_power_control", False),
    ("no_external_reset", False),
    ("pmoda_shared_raspberry_pi_header", False),
    ("other_data_pins", "MIRROR_SWCLK"),
])
def test_reject_unqualified_electrical_assumptions(field, bad):
    item = deepcopy(ARCH)
    item["physical"][field] = bad
    with pytest.raises(mpe.ArchitectureRejected):
        mpe.validate(item)


@pytest.mark.parametrize("field,bad", [
    ("base", "0x40008000"),
    ("span", "0x2000"),
    ("site_stride", "0x800"),
    ("site_bank_index_origin", 0),
    ("fclk_hz", 50_000_000),
    ("full_word_write_required", False),
])
def test_reject_old_or_aliasing_memory_map(field, bad):
    item = deepcopy(ARCH)
    item["axi"][field] = bad
    with pytest.raises(mpe.ArchitectureRejected):
        mpe.validate(item)


def test_reject_duplicate_or_unaligned_registers():
    for changed in ({"offset": "0x15"}, {"offset": "0x14", "name": "TX_DATA"}):
        item = deepcopy(ARCH)
        item["site_registers"][4].update(changed)
        with pytest.raises(mpe.ArchitectureRejected):
            mpe.validate(item)


def test_no_virtual_or_hil_pass_in_architecture_only_evidence():
    item = deepcopy(ARCH)
    item["proof"]["dpidr"] = "PASS"
    with pytest.raises(mpe.ArchitectureRejected, match="FALSE_HARDWARE_OR_SIMULATION_PASS"):
        mpe.validate(item)

def test_both_pmods_have_exact_distinct_xdc_and_no_unexpected_pin_drive():
    xdc = (PL / "constraints/pynq-z2/z2-mpe-dual-swd.xdc").read_text()
    active = [line for line in xdc.splitlines() if line.startswith("set_property ")]
    assert active == [
        "set_property -dict {PACKAGE_PIN Y18 IOSTANDARD LVCMOS33} [get_ports {swclk_io[0]}]",
        "set_property -dict {PACKAGE_PIN Y19 IOSTANDARD LVCMOS33} [get_ports {swdio_io[0]}]",
        "set_property -dict {PACKAGE_PIN W14 IOSTANDARD LVCMOS33} [get_ports {swclk_io[1]}]",
        "set_property -dict {PACKAGE_PIN Y14 IOSTANDARD LVCMOS33} [get_ports {swdio_io[1]}]",
    ]
    # No invented PMOD power/NRST/5V permission.
    assert all("LVCMOS33" in line for line in active)


def test_rtl_physically_instantiates_independent_swd_engines_and_io_guards():
    rtl = (PL / "rtl/mpe/plasma_mpe_dual_swd_core.sv").read_text()
    for required in (
        "parameter integer SITE_COUNT = 2",
        "for (genvar s = 0; s < SITE_COUNT; s = s + 1)",
        "plasma_mpe_swd_engine u_transaction",
        ".cmd_abort(cmd_abort[s] || !site_enable[s])",
        "assign cmd_ready[s] = allowed && cmd_ready_internal",
        "OBUF u_swclk_pad",
        ".I(swclk_internal && allowed)",
        "IOBUF u_swdio_pad",
        ".T(!(allowed && swdio_oe_internal))",
    ):
        assert required in rtl


def test_production_mpe_rtl_and_sim_never_import_legacy_swd_modules():
    """Guard new MPE source graph, not historical files needed for rollback."""
    core = (PL / "rtl/mpe/plasma_mpe_dual_swd_core.sv").read_text()
    engine = (PL / "rtl/mpe/plasma_mpe_swd_engine.sv").read_text()
    runner = (PL / "verification/test_mpe_dual_swd_core_rtl.py").read_text()
    for source in (core, engine, runner):
        for obsolete in (
            "swd_transaction_master",
            "swd_waveform_engine",
            "swd_emio_bridge",
            "plasma_poc_swd_gpio_axi_lite",
            "bluepill_remote_bitbang",
            "bluepill_z2_word_port",
            "z2-swd03-axi",
            "z2-swd-gpio",
            "z2-bluepill-rbb",
        ):
            assert obsolete not in source
    assert "plasma_mpe_swd_engine u_transaction (" in core
    assert '"rtl/mpe/plasma_mpe_swd_engine.sv"' in runner


def test_mpe_axi_and_openocd_replacement_are_not_falsely_claimed():
    """Implementation remains source slice until new bus/driver are qualified."""
    document = (PL.parent /
        "docs/architecture/plasma-mpe-dual-site-gate1.md").read_text()
    assert "AXI/FIFO/IRQ integration" in document
    assert "OpenOCD MPE adapter" in document
    assert "NOT_DEPLOYED" in document
