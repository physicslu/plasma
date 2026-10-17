"""MS01 host source/HWH contract tests. No Vivado or real FPGA accesses."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

PL = Path(__file__).resolve().parents[1]
DIR = PL / "projects/z2-ms01-axi"
spec = importlib.util.spec_from_file_location("ms01_artifact", DIR / "artifact.py")
assert spec and spec.loader
artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact)


def handoff() -> ET.Element:
    root = ET.Element("SYSTEM")
    for name, base in artifact.MAP.items():
        module = ET.SubElement(root, "MODULE", INSTANCE=name)
        ET.SubElement(module, "PARAMETER", NAME="AXI_BASE_ADDRESS",
                      VALUE=hex(base))
        if name == "identity_0":
            for k, v in (("CAPABILITY_FLAGS", "0"), ("STRICT_ADDRESS", "1")):
                ET.SubElement(module, "PARAMETER", NAME=k, VALUE=v)
        for k, v in (
            ("s_axi_aclk", "ps7_0_FCLK_CLK0"),
            ("s_axi_aresetn", "rst_ps7_0_100M_peripheral_aresetn"),
        ):
            ET.SubElement(module, "PORT", NAME=k, SIGNAME=v)
        ET.SubElement(root, "MEMRANGE", INSTANCE=name, BASEVALUE=hex(base),
                      HIGHVALUE=hex(base + 4095),
                      MASTERBUSINTERFACE="M_AXI_GP0")
        if name == "transaction_0":
            for pin, signal in (
                ("swclk", "tx_swclk"),
                ("swdio_out", "tx_out"),
                ("swdio_oe", "tx_oe"),
                ("swdio_in", "tx_in"),
            ):
                ET.SubElement(module, "PORT", NAME=pin, SIGNAME=signal)
    fixture = ET.SubElement(root, "MODULE", INSTANCE="fixture_0")
    for k, v in (
        ("clk", "ps7_0_FCLK_CLK0"),
        ("rst_n", "rst_ps7_0_100M_peripheral_aresetn"),
        ("swclk", "tx_swclk"),
        ("host_out", "tx_out"),
        ("host_oe", "tx_oe"),
        ("swdio_in", "tx_in"),
    ):
        ET.SubElement(fixture, "PORT", NAME=k, SIGNAME=v)
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


def verify(root: ET.Element, tmp_path: Path) -> dict:
    target = tmp_path / "system.hwh"
    ET.ElementTree(root).write(target)
    return artifact.verify_hwh(target)


def test_independent_dual_site_ranges(tmp_path):
    result = verify(handoff(), tmp_path)
    assert len(result) == 6
    assert result["lt02_0"]["base_address"] == "0x40004000"
    assert result["lt02_1"]["base_address"] == "0x40005000"
    assert artifact.SITE_BASES == {1: 0x40004000, 2: 0x40005000}


@pytest.mark.parametrize("fault", [
    "lt02_0_decoder", "lt02_1_decoder", "lt02_1_base",
    "lt02_1_overlap", "lt02_1_missing", "lt02_1_wrong_clock",
    "lt02_1_wrong_reset", "fixture", "extra", "gp1", "identity",
])
def test_hwh_fault_injections_fail_closed(fault, tmp_path):
    root = handoff()
    site2 = root.find("./MODULE[@INSTANCE='lt02_1']")
    site2range = root.find("./MEMRANGE[@INSTANCE='lt02_1']")
    if fault == "lt02_0_decoder":
        root.find("./MODULE[@INSTANCE='lt02_0']/PARAMETER[@NAME='AXI_BASE_ADDRESS']").set(
            "VALUE", "0x40006000")
    elif fault == "lt02_1_decoder":
        site2.find("./PARAMETER[@NAME='AXI_BASE_ADDRESS']").set("VALUE", "0x40006000")
    elif fault == "lt02_1_base":
        site2range.set("HIGHVALUE", "0x40005FFE")
    elif fault == "lt02_1_overlap":
        site2range.set("BASEVALUE", "0x40004000")
    elif fault == "lt02_1_missing":
        root.remove(site2range)
    elif fault == "lt02_1_wrong_clock":
        site2.find("./PORT[@NAME='s_axi_aclk']").set("SIGNAME", "bad")
    elif fault == "lt02_1_wrong_reset":
        site2.find("./PORT[@NAME='s_axi_aresetn']").set("SIGNAME", "bad")
    elif fault == "fixture":
        root.find("./MODULE[@INSTANCE='fixture_0']/PORT[@NAME='host_oe']").set(
            "SIGNAME", "bad")
    elif fault == "extra":
        ET.SubElement(root, "MEMRANGE", INSTANCE="rogue",
                      MASTERBUSINTERFACE="M_AXI_GP0")
    elif fault == "gp1":
        site2range.set("MASTERBUSINTERFACE", "M_AXI_GP1")
    elif fault == "identity":
        root.find("./MODULE[@INSTANCE='identity_0']/PARAMETER[@NAME='STRICT_ADDRESS']").set(
            "VALUE", "0")
    with pytest.raises((ValueError, KeyError)):
        verify(root, tmp_path)


def test_vivado_scripts_internal_only_and_distinct(tmp_path):
    design = (DIR / "create_block_design.tcl").read_text()
    project = (DIR / "create_project.tcl").read_text()
    build = (DIR / "build-on-swpc.sh").read_text()
    implementation = (DIR / "build_bitstream.tcl").read_text()
    for site, address in (("lt02_0", "0x40004000"),
                          ("lt02_1", "0x40005000")):
        assert design.count(site) >= 2
        assert design.count(address) >= 2
    assert "create_project z2_ms01_axi" in project
    assert "pl_mmio_loopback_axi_lite.sv" in project
    assert "External PL port forbidden" in design
    assert "!= 6" in design
    assert "pl/build/z2-ms01-axi" in build
    assert "MS01_HOST_ARTIFACT_PASS_NO_Z2_OR_TARGET_CLAIM" in build
    assert "flock -n" in build and "mktemp -d" in build
    assert "source ps7_init" not in build
    assert "report_timing_summary" in implementation
    assert "MS01_BITSTREAM_BUILD_PASS" in implementation
