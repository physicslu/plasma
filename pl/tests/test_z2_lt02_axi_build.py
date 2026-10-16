"""LT02 synthetic HWH fault-injection and build/source-contract checks.

No Vivado tools, FPGA, or real target are used by these source-level tests.
"""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

PL = Path(__file__).resolve().parents[1]
DIR = PL / "projects/z2-lt02-axi"
spec = importlib.util.spec_from_file_location("lt02_artifact", DIR / "artifact.py")
assert spec and spec.loader
artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact)


def handoff():
    root = ET.Element("SYSTEM")
    for inst, base in artifact.MAP.items():
        m = ET.SubElement(root, "MODULE", INSTANCE=inst)
        ET.SubElement(m, "PARAMETER", NAME="AXI_BASE_ADDRESS", VALUE=hex(base))
        if inst == "identity_0":
            for k, v in (("CAPABILITY_FLAGS", "0"), ("STRICT_ADDRESS", "1")):
                ET.SubElement(m, "PARAMETER", NAME=k, VALUE=v)
        for k, signal in (
            ("s_axi_aclk", "ps7_0_FCLK_CLK0"),
            ("s_axi_aresetn", "rst_ps7_0_100M_peripheral_aresetn"),
        ):
            ET.SubElement(m, "PORT", NAME=k, SIGNAME=signal)
        ET.SubElement(root, "MEMRANGE", INSTANCE=inst,
                      BASEVALUE=hex(base), HIGHVALUE=hex(base + 4095),
                      MASTERBUSINTERFACE="M_AXI_GP0")
        if inst == "transaction_0":
            for pin, signal in (
                ("swclk", "txn_swclk"), ("swdio_out", "txn_out"),
                ("swdio_oe", "txn_oe"), ("swdio_in", "txn_in")
            ):
                ET.SubElement(m, "PORT", NAME=pin, SIGNAME=signal)
    lt02_base = artifact.MAP["lt02_0"]
    assert lt02_base == 0x40004000
    fixture = ET.SubElement(root, "MODULE", INSTANCE="fixture_0")
    for pin, signal in (
        ("clk", "ps7_0_FCLK_CLK0"),
        ("rst_n", "rst_ps7_0_100M_peripheral_aresetn"),
        ("swclk", "txn_swclk"), ("host_out", "txn_out"),
        ("host_oe", "txn_oe"), ("swdio_in", "txn_in"),
    ):
        ET.SubElement(fixture, "PORT", NAME=pin, SIGNAME=signal)
    ps = ET.SubElement(root, "MODULE", INSTANCE="ps7_0")
    for k, v in (
        ("PCW_GPIO_EMIO_GPIO_ENABLE", "0"),
        ("PCW_USE_M_AXI_GP0", "1"),
        ("PCW_CRYSTAL_PERIPHERAL_FREQMHZ", "50"),
        ("PCW_FPGA0_PERIPHERAL_FREQMHZ", "100"),
    ):
        ET.SubElement(ps, "PARAMETER", NAME=k, VALUE=v)
    ET.SubElement(ps, "PORT", NAME="M_AXI_GP0_ACLK",
                  CLKFREQUENCY="100000000", SIGNAME="ps7_0_FCLK_CLK0")
    rst = ET.SubElement(root, "MODULE", INSTANCE="rst_ps7_0_100M")
    ET.SubElement(rst, "PARAMETER", NAME="C_EXT_RESET_HIGH", VALUE="0")
    ET.SubElement(rst, "PORT", NAME="ext_reset_in",
                  SIGNAME="ps7_0_FCLK_RESET0_N")
    return root


def verify(root, tmp_path):
    hwh = tmp_path / "system.hwh"
    ET.ElementTree(root).write(hwh)
    return artifact.verify_hwh(hwh)


def test_valid_five_aperture_handoff(tmp_path):
    data = verify(handoff(), tmp_path)
    assert set(data) == set(artifact.MAP)
    assert data["transaction_0"]["base_address"] == "0x40003000"
    assert data["lt02_0"]["base_address"] == "0x40004000"
    assert len(data) == 5


@pytest.mark.parametrize("fault", [
    "decode", "addr", "duplicate", "extra", "master", "clk", "rst",
    "fixture_clk", "fixture_rst", "swd_out", "swd_oe",
    "lt02_decode", "lt02_overlap", "lt02_missing", "lt02_gp1",
    "lt02_clock", "lt02_reset",
    "swd_in", "swd_clk", "fixture_mmio", "external", "legacy",
])
def test_fail_closed_invalid_handoff(tmp_path, fault):
    root = handoff()
    txn = root.find("./MODULE[@INSTANCE='transaction_0']")
    fix = root.find("./MODULE[@INSTANCE='fixture_0']")
    rng = root.find("./MEMRANGE[@INSTANCE='transaction_0']")
    if fault == "decode":
        txn.find("./PARAMETER[@NAME='AXI_BASE_ADDRESS']").set("VALUE", "0x40004000")
    elif fault == "addr":
        rng.set("HIGHVALUE", "0x40005FFF")
    elif fault == "duplicate":
        ET.SubElement(root, "MEMRANGE", INSTANCE="transaction_0")
    elif fault == "extra":
        ET.SubElement(root, "MEMRANGE", INSTANCE="other_0",
                      MASTERBUSINTERFACE="M_AXI_GP0")
    elif fault == "master":
        rng.set("MASTERBUSINTERFACE", "M_AXI_GP1")
    elif fault == "clk":
        txn.find("./PORT[@NAME='s_axi_aclk']").set("SIGNAME", "bad")
    elif fault == "rst":
        txn.find("./PORT[@NAME='s_axi_aresetn']").set("SIGNAME", "bad")
    elif fault == "fixture_clk":
        fix.find("./PORT[@NAME='clk']").set("SIGNAME", "bad")
    elif fault == "fixture_rst":
        fix.find("./PORT[@NAME='rst_n']").set("SIGNAME", "bad")
    elif fault in ("swd_out", "swd_oe", "swd_in", "swd_clk"):
        name = dict(swd_out="host_out", swd_oe="host_oe",
                    swd_in="swdio_in", swd_clk="swclk")[fault]
        fix.find(f"./PORT[@NAME='{name}']").set("SIGNAME", "unconnected")
    elif fault == "fixture_mmio":
        ET.SubElement(root, "MEMRANGE", INSTANCE="fixture_0")
    elif fault == "external":
        ET.SubElement(ET.SubElement(root, "EXTERNALPORTS"),
                      "PORT", NAME="PMOD_SWCLK")
    elif fault == "lt02_decode":
        root.find("./MODULE[@INSTANCE='lt02_0']/PARAMETER[@NAME='AXI_BASE_ADDRESS']").set(
            "VALUE", "0x40005000")
    elif fault == "lt02_overlap":
        root.find("./MEMRANGE[@INSTANCE='lt02_0']").set("BASEVALUE", "0x40003000")
    elif fault == "lt02_missing":
        root.remove(root.find("./MEMRANGE[@INSTANCE='lt02_0']"))
    elif fault == "lt02_gp1":
        root.find("./MEMRANGE[@INSTANCE='lt02_0']").set("MASTERBUSINTERFACE", "M_AXI_GP1")
    elif fault == "lt02_clock":
        root.find("./MODULE[@INSTANCE='lt02_0']/PORT[@NAME='s_axi_aclk']").set("SIGNAME", "wrong_clock")
    elif fault == "lt02_reset":
        root.find("./MODULE[@INSTANCE='lt02_0']/PORT[@NAME='s_axi_aresetn']").set("SIGNAME", "wrong_reset")
    elif fault == "legacy":
        root.find("./MEMRANGE[@INSTANCE='swd_0']").set(
            "BASEVALUE", "0x40004000")
    with pytest.raises((KeyError, ValueError)):
        verify(root, tmp_path)


def test_script_and_source_contracts():
    project = (DIR / "create_project.tcl").read_text()
    design = (DIR / "create_block_design.tcl").read_text()
    build = (DIR / "build-on-swpc.sh").read_text()
    tcl = (DIR / "build_bitstream.tcl").read_text()
    for name in (
        "pl_identity_axi_lite.sv", "pl_control_axi_lite.sv",
        "swd_command_axi_lite.sv", "swd_waveform_engine.sv",
        "pl_loopback_responder.sv", "swd_transaction_master.sv",
        "swd_transaction_axi_lite.sv", "swd03_dpidr_responder.sv",
        "pl_mmio_loopback_axi_lite.sv",
    ):
        assert name in project
    for addr in ("0x40000000", "0x40001000", "0x40002000", "0x40003000", "0x40004000"):
        assert design.count(addr) >= 2
    for name in (
        "transaction_0/swdio_in", "transaction_0/swclk",
        "transaction_0/swdio_out", "transaction_0/swdio_oe",
        "fixture_0/clk", "fixture_0/rst_n",
    ):
        assert name in design or any(
            template in design for template in (
                "transaction_0/$master_port",
            )
        )
    assert "get_bd_ports" in design and "External PL port forbidden" in design
    assert "pl/build/z2-lt02-axi" in build
    assert "lt02-regression.log" in build
    assert "mktemp -d" in build and "flock -n" in build
    assert "source ps7_init" not in build and "exec ps7_init" not in build
    assert "report_timing_summary" in tcl
    assert "get_drc_violations" in tcl
    assert "LT02_BITSTREAM_BUILD_PASS" in tcl
    assert "LT02_HOST_ARTIFACT_PASS_NO_Z2_OR_TARGET_CLAIM" in build
