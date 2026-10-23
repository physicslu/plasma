"""New candidate source/HWH negative checks. NOT a Vivado/HIL assertion."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest

PL = Path(__file__).resolve().parents[1]
PROJECT = PL / "projects/z2-bluepill-rbb"
XDC = PL / "constraints/pynq-z2/z2-bluepill-rbb.xdc"

spec = importlib.util.spec_from_file_location("bluepill_hwh", PROJECT / "verify_hwh.py")
assert spec and spec.loader
hwh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hwh)


def fixture_hwh() -> str:
    root = ET.Element("SYSTEM")
    external = ET.SubElement(root, "EXTERNALPORTS")
    for pin in ("swclk_io", "swdio_io", "DDR_addr", "FIXED_IO_mio"):
        ET.SubElement(external, "PORT", NAME=pin)
    for instance in ("ps7_0", "swd_0", "pads_0", "rst_ps7_0_100M"):
        module = ET.SubElement(root, "MODULE", INSTANCE=instance)
        if instance == "swd_0":
            ET.SubElement(module, "PARAMETER", NAME="AXI_BASE_ADDRESS", VALUE="0x40008000")
        ports = ["swclk", "swdio_out", "swdio_oe", "swdio_in"]
        if instance in ("swd_0", "pads_0"):
            for p in ports:
                ET.SubElement(module, "PORT", NAME=p, SIGNAME=p)
        if instance == "swd_0":
            ET.SubElement(module, "PORT", NAME="s_axi_aclk", SIGNAME="fclk0")
            ET.SubElement(module, "PORT", NAME="s_axi_aresetn", SIGNAME="rstn")
        if instance == "ps7_0":
            for key, value in (
                ("PCW_CRYSTAL_PERIPHERAL_FREQMHZ", "50.000000"),
                ("PCW_FPGA0_PERIPHERAL_FREQMHZ", "100"),
                ("PCW_USE_M_AXI_GP0", "1"),
                ("PCW_GPIO_EMIO_GPIO_ENABLE", "0"),
            ):
                ET.SubElement(module, "PARAMETER", NAME=key, VALUE=value)
            ET.SubElement(module, "PORT", NAME="FCLK_CLK0", SIGNAME="fclk0")
        if instance == "rst_ps7_0_100M":
            ET.SubElement(module, "PORT", NAME="peripheral_aresetn", SIGNAME="rstn")
    ET.SubElement(root, "MEMRANGE", MASTERBUSINTERFACE="M_AXI_GP0",
                  INSTANCE="swd_0", BASEVALUE="0x40008000", HIGHVALUE="0x40008fff")
    return ET.tostring(root, encoding="unicode")


def test_xdc_is_exactly_two_3v3_pmod_pins_without_dut_reset():
    xdc = XDC.read_text()
    active = [x.strip() for x in xdc.splitlines() if x.strip().startswith("set_property")]
    assert len(active) == 2
    assert "PACKAGE_PIN W14 IOSTANDARD LVCMOS33" in active[0]
    assert "[get_ports swclk_io]" in active[0]
    assert "PACKAGE_PIN Y14 IOSTANDARD LVCMOS33" in active[1]
    assert "[get_ports swdio_io]" in active[1]


def test_source_wiring_keeps_real_iobuf_and_no_emio_shortcut():
    pads = (PL / "rtl/site/plasma_poc_swd_pmod.sv").read_text()
    block = (PROJECT / "create_block_design.tcl").read_text()
    gate = (PROJECT / "create_project.tcl").read_text()
    assert "IOBUF swdio_pad" in pads and ".T(~swdio_oe)" in pads
    assert "OBUF swclk_pad" in pads
    assert "CONFIG.PCW_GPIO_EMIO_GPIO_ENABLE {0}" in block
    assert "0x40008000" in block and "4096" in block
    rtl = (PL / "rtl/bus/plasma_poc_swd_gpio_axi_lite.sv").read_text()
    assert "ASSOCIATED_BUSIF S_AXI" in rtl
    assert "PROTOCOL AXI4LITE, DATA_WIDTH 32" in rtl
    assert "SWD AXI clock not sourced from PS7 FCLK0" in block
    assert "SWD AXI reset is not PS7 synchronized peripheral_aresetn" in block
    assert "validate_bd_design" in block
    assert "get_bd_ports swdio_io" in block
    assert "get_bd_ports swclk_io" in block
    assert "e02d6a3866b5465218f777168cdc51344ac94e07" in gate
    assert "-force" not in gate


def test_fixture_hwh_positive_is_only_offline_contract():
    state = hwh.verify_hwh_xml(fixture_hwh())
    assert state["hwh_source_check"] == "PASS"
    assert state["bitstream_loaded"] == "NOT_RUN"
    assert state["physical_swd"] == "NOT_RUN"


@pytest.mark.parametrize("old,new", [
    ("0x40008000", "0x40002000"),
    ("0x40008fff", "0x4000afff"),
    ("INSTANCE=\"pads_0\"", "INSTANCE=\"pads_wrong\""),
    ("NAME=\"swdio_io\"", "NAME=\"swdo_io\""),
    ("SIGNAME=\"fclk0\"", "SIGNAME=\"badclock\""),
    ("SIGNAME=\"swdio_oe\"", "SIGNAME=\"wrong_oe\""),
])
def test_corrupt_hwh_fails_closed(old, new):
    with pytest.raises(hwh.HWHRejected):
        hwh.verify_hwh_xml(fixture_hwh().replace(old, new, 1))


def test_missing_build_artifacts_never_yield_pass(tmp_path):
    with pytest.raises(hwh.HWHRejected, match="MISSING"):
        hwh.inspect_files(tmp_path / "no.hwh", tmp_path / "no.bit")


@pytest.mark.parametrize("key,wrong", [
    ("PCW_CRYSTAL_PERIPHERAL_FREQMHZ", "125"),
    ("PCW_FPGA0_PERIPHERAL_FREQMHZ", "125"),
    ("PCW_USE_M_AXI_GP0", "0"),
    ("PCW_GPIO_EMIO_GPIO_ENABLE", "1"),
])
def test_corrupt_ps7_config_fails_closed(key, wrong):
    root = ET.fromstring(fixture_hwh())
    ps7 = next(m for m in root.iter("MODULE") if m.get("INSTANCE") == "ps7_0")
    param = next(p for p in ps7.iter("PARAMETER") if p.get("NAME") == key)
    param.set("VALUE", wrong)
    with pytest.raises(hwh.HWHRejected, match="HWH_PS7_CONFIG_MISMATCH"):
        hwh.verify_hwh_xml(ET.tostring(root, encoding="unicode"))


def test_build_source_requires_actual_bit_hwh_inspection():
    script = (PROJECT / "build_bitstream.tcl").read_text()
    assert "BLUEPILL_Z2_BIT_HWH_MISSING" in script
    assert "exec python3 [file join $script_dir verify_hwh.py]" in script
    assert "artifact-inspection.json" in script
    assert "BLUEPILL_Z2_BIT_HWH_INSPECTION_PASS_OFFLINE_NOT_HIL" in script


def test_synthetic_hwh_bit_inspection_denies_admission(tmp_path):
    source = tmp_path / "fixture.hwh"
    bit = tmp_path / "fixture.bit"
    source.write_text(fixture_hwh())
    bit.write_bytes(b"synthetic-bit-not-real-fpga")
    result = hwh.inspect_files(source, bit)
    assert len(result["hwh_sha256"]) == 64
    assert len(result["bit_sha256"]) == 64
    assert result["runtime_admitted"] is False
    assert result["gate_2_ready"] is False
    assert result["restorable_original_bit_sha256"] == "NOT_PROVIDED"
