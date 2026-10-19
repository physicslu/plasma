"""F1 GitHub-hosted source/HWH negative contracts. No Vivado or hardware."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "pl/projects/z2-fixed-unified-site1"
spec = importlib.util.spec_from_file_location("fixed_f1_hwh_verifier",
                                             DIR / "verify_hwh.py")
assert spec and spec.loader
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def fake_hwh():
    r = ET.Element("SYSTEM")
    ps = ET.SubElement(r, "MODULE", INSTANCE="ps7_0")
    for key, value in (
        ("PCW_GPIO_EMIO_GPIO_ENABLE", 0),
        ("PCW_USE_M_AXI_GP0", 1),
        ("PCW_CRYSTAL_PERIPHERAL_FREQMHZ", 50),
        ("PCW_FPGA0_PERIPHERAL_FREQMHZ", 100),
    ):
        ET.SubElement(ps, "PARAMETER", NAME=key, VALUE=str(value))
    ET.SubElement(ps, "PORT", NAME="M_AXI_GP0_ACLK",
                  CLKFREQUENCY="100000000", SIGNAME="ps7_0_FCLK_CLK0")
    rst = ET.SubElement(r, "MODULE", INSTANCE="rst_ps7_0_100M")
    ET.SubElement(rst, "PARAMETER", NAME="C_EXT_RESET_HIGH", VALUE="0")
    ET.SubElement(rst, "PORT", NAME="ext_reset_in",
                  SIGNAME="ps7_0_FCLK_RESET0_N")
    u = ET.SubElement(r, "MODULE", INSTANCE="unified_0")
    ET.SubElement(u, "PARAMETER", NAME="PPU_BASE", VALUE="0x40000000")
    ET.SubElement(u, "PORT", NAME="s_axi_aclk",
                  SIGNAME="ps7_0_FCLK_CLK0")
    ET.SubElement(u, "PORT", NAME="s_axi_aresetn",
                  SIGNAME="rst_ps7_0_100M_peripheral_aresetn")
    ET.SubElement(r, "MEMRANGE", INSTANCE="unified_0",
                  BASEVALUE="0x40000000", HIGHVALUE="0x4000FFFF",
                  MASTERBUSINTERFACE="M_AXI_GP0")
    ext = ET.SubElement(r, "EXTERNALPORTS")
    ET.SubElement(ext, "PORT", NAME="DDR_DQ")
    ET.SubElement(ext, "PORT", NAME="FIXED_IO_MIO")
    return r


def test_hwh_valid_one_64k_gp0_with_no_pl_pins():
    result = v.validate_hwh(fake_hwh())
    assert result["base"] == "0x40000000"
    assert result["bytes"] == 65536
    assert result["external_pl_io"] is False
    assert result["regions"]["site2_8"] == "ABSENT"
    assert result["z2_hil"] == "NOT_RUN"


def test_hwh_real_vivado_numeric_encodings_are_accepted():
    r = fake_hwh()
    r.find("./MODULE[@INSTANCE='unified_0']/PARAMETER[@NAME='PPU_BASE']").set(
        "VALUE", f"{v.GP0_BASE:032b}")
    ps = r.find("./MODULE[@INSTANCE='ps7_0']")
    ps.find("./PARAMETER[@NAME='PCW_USE_M_AXI_GP0']").set("VALUE", "true")
    ps.find("./PARAMETER[@NAME='PCW_GPIO_EMIO_GPIO_ENABLE']").set("VALUE", "false")
    ps.find("./PARAMETER[@NAME='PCW_FPGA0_PERIPHERAL_FREQMHZ']").set(
        "VALUE", "100.000000")
    assert v.validate_hwh(r)["bytes"] == 65536
    assert v.number("00000000000000000000000000000001") == 1
    with pytest.raises(v.F1Denied):
        v.number("NaN")
    with pytest.raises(v.F1Denied):
        v.number("infinity")


@pytest.mark.parametrize("fault", [
    "missing_ps", "missing_reset", "missing_unified", "wrong_base", "wrong_high",
    "legacy_second_segment", "wrong_master", "extra_memrange", "wrong_decoder",
    "wrong_crystal", "no_gp0", "bad_fclk", "bad_clock", "bad_reset",
    "reset_source", "physical_swd", "external_gpio",
])
def test_hwh_mutations_fail_closed(fault):
    r = fake_hwh()
    ps = r.find("./MODULE[@INSTANCE='ps7_0']")
    rst = r.find("./MODULE[@INSTANCE='rst_ps7_0_100M']")
    u = r.find("./MODULE[@INSTANCE='unified_0']")
    rng = r.find("./MEMRANGE")
    if fault == "missing_ps": r.remove(ps)
    elif fault == "missing_reset": r.remove(rst)
    elif fault == "missing_unified": r.remove(u)
    elif fault == "wrong_base": rng.set("BASEVALUE", "0x40001000")
    elif fault == "wrong_high": rng.set("HIGHVALUE", "0x40000FFF")
    elif fault == "legacy_second_segment":
        ET.SubElement(r, "MEMRANGE", INSTANCE="control_0", BASEVALUE="0x40001000",
                      HIGHVALUE="0x40001FFF", MASTERBUSINTERFACE="M_AXI_GP0")
    elif fault == "wrong_master": rng.set("MASTERBUSINTERFACE", "M_AXI_GP1")
    elif fault == "extra_memrange": ET.SubElement(r, "MEMRANGE", INSTANCE="lt02_0")
    elif fault == "wrong_decoder":
        u.find("./PARAMETER[@NAME='PPU_BASE']").set("VALUE", "0x40004000")
    elif fault == "wrong_crystal":
        ps.find("./PARAMETER[@NAME='PCW_CRYSTAL_PERIPHERAL_FREQMHZ']").set("VALUE", "100")
    elif fault == "no_gp0":
        ps.find("./PARAMETER[@NAME='PCW_USE_M_AXI_GP0']").set("VALUE", "0")
    elif fault == "bad_fclk":
        ps.find("./PORT[@NAME='M_AXI_GP0_ACLK']").set("CLKFREQUENCY", "50000000")
    elif fault == "bad_clock":
        u.find("./PORT[@NAME='s_axi_aclk']").set("SIGNAME", "wrong")
    elif fault == "bad_reset":
        u.find("./PORT[@NAME='s_axi_aresetn']").set("SIGNAME", "wrong")
    elif fault == "reset_source":
        rst.find("./PORT[@NAME='ext_reset_in']").set("SIGNAME", "wrong")
    elif fault == "physical_swd":
        ET.SubElement(u, "PORT", NAME="swclk", SIGNAME="PMOD_A")
    elif fault == "external_gpio":
        ET.SubElement(r.find("./EXTERNALPORTS"), "PORT", NAME="PMOD_SWCLK")
    with pytest.raises(v.F1Denied):
        v.validate_hwh(r)


def test_fail_closed_missing_artifact_and_report(tmp_path):
    root = fake_hwh()
    hwh = tmp_path / "system.hwh"
    ET.ElementTree(root).write(hwh)
    bit = tmp_path / "system_wrapper.bit"
    reports = tmp_path / "reports"
    reports.mkdir()
    with pytest.raises(v.F1Denied, match="ARTIFACT_MISSING"):
        v.verify_artifacts(hwh=hwh, bit=bit, reports=reports, source_sha="a" * 40)
    bit.write_bytes(b"synthetic-not-a-real-bitstream")
    with pytest.raises(v.F1Denied, match="IMPLEMENTATION_REPORT_MISSING"):
        v.verify_artifacts(hwh=hwh, bit=bit, reports=reports, source_sha="a" * 40)
    for name in v.REPORTS:
        (reports / name).write_text("synthetic host fixture; not Vivado\n")
    result = v.verify_artifacts(hwh=hwh, bit=bit, reports=reports,
                                source_sha="a" * 40)
    assert result["physical_image_loaded"] == "NOT_RUN"
    assert result["vivado_implemented"] == "SUPERVISOR_REVIEW_REQUIRED"
    assert result["m1"] == "NO_GO"
    with pytest.raises(v.F1Denied, match="SOURCE_SHA_INVALID"):
        v.verify_artifacts(hwh=hwh, bit=bit, reports=reports, source_sha="BAD")


def test_ps7_bd_and_shell_source_integrity():
    src = (DIR / "rtl/fixed_ppu_z2_internal_fixture_axi.sv").read_text()
    header = src[:src.index(");")]
    assert "X_INTERFACE_INFO" in header
    assert "ASSOCIATED_BUSIF S_AXI" in header
    for pin in ("AWADDR", "AWPROT", "AWVALID", "AWREADY",
                "WDATA", "WSTRB", "WVALID", "WREADY", "BRESP",
                "BVALID", "BREADY", "ARADDR", "ARPROT", "ARVALID",
                "ARREADY", "RDATA", "RRESP", "RVALID", "RREADY"):
        assert f"S_AXI {pin}" in header
    for pin in ("swclk", "swdio_in", "swdio_out", "swdio_oe", "PMOD", "NRST"):
        assert not re.search(r"\b(input|output|inout)\s+(logic\s+)?"+pin+r"\b",header)
    assert "fixed_ppu_unified_axi_site1 #(.PPU_BASE(PPU_BASE)) unified" in src
    assert "swd03_dpidr_responder fixture" in src
    assert ".rst_n(s_axi_aresetn)" in src
    project = (DIR / "create_project.tcl").read_text()
    design = (DIR / "create_block_design.tcl").read_text()
    build = (DIR / "build_bitstream.tcl").read_text()
    for rtl in ("fixed_ppu_unified_axi_site1.sv", "fixed_fpga_ppu_global_identity_axi_lite.sv",
                "fixed_fpga_swd_site_axi_lite.sv", "swd_transaction_master.sv",
                "swd_waveform_engine.sv", "swd03_dpidr_responder.sv"):
        assert rtl in project
    for required in ("xc7z020clg400-1","tul.com.tw:pynq-z2:part0:1.0",
                     "fixed_ppu_z2_internal_fixture_axi.sv"):
        assert required in project
    for required in ("M_AXI_GP0", "PCW_FPGA0_PERIPHERAL_FREQMHZ {100}",
                     "PCW_GPIO_EMIO_GPIO_ENABLE {0}", "64K",
                     "0x40000000", "unified_0/S_AXI", "get_bd_ports",
                     "F1 external PL port prohibited", "F1 AXI reset not synchronized"):
        assert required in design
    assert "LT02" not in design and "control_0" not in design
    for required in ("launch_runs synth_1", "launch_runs impl_1",
                     "report_timing_summary", "get_timing_paths -hold",
                     "get_drc_violations", "FIXED_F1_BITSTREAM_BUILD_PASS_HOST_ONLY_NOT_Z2"):
        assert required in build
    for forbidden in ("write_cfgmem", "program_hw_devices", "fpga_manager",
                      "/dev/mem", "ps7_init", "ssh "):
        assert forbidden not in (project + design + build).lower()


def test_existing_driver_files_not_edited_by_f1():
    source = (ROOT / "software/python/plasma_interfaces/linux_mmio.py").read_text()
    assert 'memoryview(page).cast("I")' in source
    port = (ROOT / "software/python/plasma_interfaces/fixed_abi_mmio_port.py").read_text()
    assert "self._barrier()" in port
    ctrl = (ROOT / "software/python/plasma_interfaces/fixed_abi_swd.py").read_text()
    assert ctrl.index("self._commit_barrier()") < ctrl.index("self._write(self.COMMAND, opcode)")
    assert "self._used_sequences.add(sequence)" in ctrl
