"""Independent Site Vivado artifact qualifier and operator CLI: HOST-ONLY.

Synthetic XML is ONLY an input mutation fixture. These tests never run Vivado,
OpenOCD, FPGA Manager, Z2, or write connected hardware.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import json
import xml.etree.ElementTree as ET
import pytest

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "pl/projects/z2-swd-independent"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


swd = load(PROJECT / "verify_hwh.py", "swd_hwh")
script = load(ROOT / "scripts/plasma_swd_host_build.py", "swd_host_build")


# Host-only excerpt shaped like the actual routed Vivado datasheet; NOT live HW.
ROUTED_FPGA_IO_DATASHEET_FIXTURE = """Input Ports Setup/Hold
clk_fpga_0 | swdio_site1 | FDRE | - | 5.329 (r) | SLOW | -0.699 (r) | SLOW |
clk_fpga_0 | swdio_site2 | FDRE | - | 6.276 (r) | SLOW | -1.348 (r) | SLOW |
Output Ports Clock-to-out
clk_fpga_0 | swclk_site1 | FDRE | - | 13.070 (r) | SLOW | 10.585 (r) | SLOW |
clk_fpga_0 | swclk_site2 | FDRE | - | 14.118 (r) | SLOW | 10.833 (r) | SLOW |
Setup between Clocks
"""

def fixture_hwh() -> ET.Element:
    root = ET.Element("SYSTEM")
    external = ET.SubElement(root, "EXTERNALPORTS")
    for name in ("DDR_addr", "FIXED_IO_mio", *swd.PINS):
        ET.SubElement(external, "PORT", NAME=name)
    ps = ET.SubElement(root, "MODULE", INSTANCE="ps7_0")
    for key, value in {
        "PCW_GPIO_EMIO_GPIO_ENABLE": "0",
        "PCW_USE_M_AXI_GP0": "1",
        "PCW_CRYSTAL_PERIPHERAL_FREQMHZ": "50.0",
        "PCW_FPGA0_PERIPHERAL_FREQMHZ": "100.000",
    }.items():
        ET.SubElement(ps, "PARAMETER", NAME=key, VALUE=value)
    ET.SubElement(ps, "PORT", NAME="M_AXI_GP0_ACLK",
                  SIGNAME="ps7_0_FCLK_CLK0", CLKFREQUENCY="100000000")
    reset = ET.SubElement(root, "MODULE", INSTANCE="rst_ps7_0_100M")
    ET.SubElement(reset, "PARAMETER", NAME="C_EXT_RESET_HIGH", VALUE="0")
    ET.SubElement(reset, "PORT", NAME="ext_reset_in",
                  SIGNAME="ps7_0_FCLK_RESET0_N")
    ET.SubElement(root, "MODULE", INSTANCE="axi_interconnect_0")
    for name, value in swd.BASES.items():
        module = ET.SubElement(root, "MODULE", INSTANCE=name)
        ET.SubElement(module, "PARAMETER", NAME="SITE_ID",
                      VALUE="1" if name.endswith("1") else "2")
        ET.SubElement(module, "PARAMETER", NAME="SITE_BASE_ADDRESS",
                      VALUE=f"0x{value:08x}")
        ET.SubElement(module, "PORT", NAME="s_axi_aclk",
                      SIGNAME="ps7_0_FCLK_CLK0")
        ET.SubElement(module, "PORT", NAME="s_axi_aresetn",
                      SIGNAME="rst_ps7_0_100M_peripheral_aresetn")
        ET.SubElement(root, "MEMRANGE", INSTANCE=name,
                      MASTERBUSINTERFACE="M_AXI_GP0",
                      BASEVALUE=f"0x{value:08x}",
                      HIGHVALUE=f"0x{value + 0xfff:08x}")
    return root


def test_hwh_two_real_slaves_are_not_f1b_composite():
    result = swd.validate_hwh(fixture_hwh())
    assert result["site_count_implemented"] == 2
    assert result["regions"]["swd_site1"]["base"] == "0x43C01000"
    assert result["regions"]["swd_site2"]["base"] == "0x43C02000"
    assert result["real_target_qualified"] is False


@pytest.mark.parametrize("tamper,expected", [
    ("single_site", "SWD_HWH_REQUIRES_TWO_AXI_REGIONS"),
    ("old_composite", "SWD_HWH_UNEXPECTED_OR_DUPLICATE_SITE"),
    ("wrong_base", "SWD_HWH_SITE_WINDOW_MISMATCH"),
    ("duplicate_site", "SWD_HWH_UNEXPECTED_OR_DUPLICATE_SITE"),
    ("wrong_clock", "SWD_HWH_FCLK_FREQUENCY_MISMATCH"),
    ("wrong_reset", "SWD_HWH_RESET_SOURCE_MISMATCH"),
    ("wrong_id", "SWD_HWH_SITE_PARAM_MISMATCH"),
    ("gpio", "SWD_HWH_WRONG_EXTERNAL_SWDPADS"),
    ("drop_pmod", "SWD_HWH_WRONG_EXTERNAL_SWDPADS"),
])
def test_reject_unsafe_or_fabricated_hwh(tamper, expected):
    h = fixture_hwh()
    mem = list(h.iter("MEMRANGE"))
    modules = {m.get("INSTANCE"): m for m in h.iter("MODULE")}
    if tamper == "single_site":
        h.remove(mem[-1])
    elif tamper == "old_composite":
        mem[0].set("INSTANCE", "mpe_0")
    elif tamper == "wrong_base":
        mem[1].set("BASEVALUE", "0x40000000")
    elif tamper == "duplicate_site":
        mem[1].set("INSTANCE", "swd_site1")
    elif tamper == "wrong_clock":
        modules["ps7_0"].find("PORT").set("CLKFREQUENCY", "50000000")
    elif tamper == "wrong_reset":
        modules["rst_ps7_0_100M"].find("PORT").set("SIGNAME", "unsafe")
    elif tamper == "wrong_id":
        modules["swd_site2"].find("PARAMETER").set("VALUE", "1")
    elif tamper == "gpio":
        ET.SubElement(h.find("EXTERNALPORTS"), "PORT", NAME="gpio_extra")
    elif tamper == "drop_pmod":
        external = h.find("EXTERNALPORTS")
        for port in external.findall("PORT"):
            if port.get("NAME") == "swdio_site2":
                external.remove(port)
    with pytest.raises(swd.SWDBuildDenied, match=expected):
        swd.validate_hwh(h)


def test_artifact_requires_real_tcl_marker_and_records_no_hardware(tmp_path):
    hwh = tmp_path / "system.hwh"
    ET.ElementTree(fixture_hwh()).write(hwh, encoding="utf-8")
    bit = tmp_path / "system_wrapper.bit"
    bit.write_bytes(b"\xAA" * 4096)
    reports = tmp_path / "reports"
    reports.mkdir()
    for name in swd.REPORT_NAMES:
        (reports / name).write_text("Synthetic regression fixture ONLY\n")
    (reports / "check_timing.rpt").write_text(
        "5. checking no_input_delay (2)\\n"
        "6. checking no_output_delay (4)\\n")
    (reports / "methodology.rpt").write_text(
        "| TIMING-18 | Warning | Missing input or output delay | 6 |\\n")
    (reports / "datasheet_io.rpt").write_text(
        ROUTED_FPGA_IO_DATASHEET_FIXTURE, encoding="utf-8")
    xdc = ROOT / "pl/constraints/pynq-z2/z2-swd-independent.xdc"
    sha = "a" * 40
    with pytest.raises(swd.SWDBuildDenied, match="SWD_BUILD_TCL_SIGNOFF_MARKER_MISSING"):
        swd.verify_artifacts(hwh=hwh, bit=bit, reports=reports,
                             xdc=xdc, source_sha=sha)
    result = swd.verify_artifacts(
        hwh=hwh, bit=bit, reports=reports, xdc=xdc, source_sha=sha,
        build_stdout="SWD_HOST_IMPL_REPORTS_TIMING_DRC_PASS")
    assert len(result["bit_sha256"]) == 64
    assert result["host_build_status"] == "SUPERVISOR_REVIEW_REQUIRED"
    assert result["z2_hil"] == "NOT_RUN"
    assert result["openocd_swd"] == "NOT_QUALIFIED"
    assert result["fpga_only_swd_rx_ideal_budget"]["candidate_hw_max_swd_hz"] == 12500000
    assert result["external_swd_io_timing"]["timing18_warnings"] == 6

    # The merged generic Path 2 interface supplies build= rather than
    # xdc/build_stdout. It must preserve every project-specific safety gate.
    (tmp_path / "vivado-stdout.log").write_text(
        "SWD_HOST_IMPL_REPORTS_TIMING_DRC_PASS setup=1.0 hold=0.1\n"
        "SWD_HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED\n")
    generic = swd.verify_artifacts(
        hwh=hwh, bit=bit, reports=reports, source_sha=sha, build=tmp_path)
    assert generic["map"] == result["hwh"]["regions"]
    assert generic["bit_sha256"] == result["bit_sha256"]
    assert generic["report_sha256"] == result["report_sha256"]
    assert generic["external_swd_io_timing"]["gate"] == (
        "BLOCKED_MISSING_OFFCHIP_TIMING")
    assert generic["external_swd_io_timing"]["external_io_timing_qualified"] is False
    assert generic["physical_image_loaded"] == "NOT_RUN"
    assert generic["z2_hil"] == "NOT_RUN"

    (tmp_path / "vivado-stdout.log").write_text(
        "SWD_HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED\n")
    with pytest.raises(swd.SWDBuildDenied,
                       match="SWD_BUILD_TCL_SIGNOFF_MARKER_MISSING"):
        swd.verify_artifacts(hwh=hwh, bit=bit, reports=reports,
                             source_sha=sha, build=tmp_path)
    (tmp_path / "vivado-stdout.log").unlink()
    with pytest.raises(swd.SWDBuildDenied,
                       match="SWD_GENERIC_BUILD_LOG_MISSING_OR_UNSAFE"):
        swd.verify_artifacts(hwh=hwh, bit=bit, reports=reports,
                             source_sha=sha, build=tmp_path)


def test_real_swd_timing18_report_fixture_is_blocked(tmp_path):
    # Exact counts, severity, and Tcl report headline from real SWPC run.
    (tmp_path / "check_timing.rpt").write_text(
        "5. checking no_input_delay (2)\\n"
        "6. checking no_output_delay (4)\\n"
        "There are 2 input ports with no input delay specified. (HIGH)\\n"
        "swdio_site1\\nswdio_site2\\n"
        "swdclk_site1\\nswdclk_site2\\n")
    (tmp_path / "methodology.rpt").write_text(
        "| TIMING-18 | Warning | Missing input or output delay | 6 |\\n")
    x = swd.audit_external_io_timing(tmp_path)
    assert x["timing18_warnings"] == 6
    assert x["unconstrained_input_ports"] == 2
    assert x["unconstrained_output_ports"] == 4
    assert x["gate"] == "BLOCKED_MISSING_OFFCHIP_TIMING"
    assert x["external_io_timing_qualified"] is False


def test_zero_warnings_still_requires_real_timing_profile(tmp_path):
    (tmp_path / "check_timing.rpt").write_text(
        "5. checking no_input_delay (0)\\n6. checking no_output_delay (0)\\n")
    (tmp_path / "methodology.rpt").write_text("No timing methodology violations\\n")
    x = swd.audit_external_io_timing(tmp_path)
    assert x["gate"] == "PENDING_SOURCE_REVIEWED_TARGET_BOARD_BUDGET"
    assert x["external_io_timing_qualified"] is False


def test_inconsistent_timing_report_is_rejected(tmp_path):
    (tmp_path / "check_timing.rpt").write_text(
        "5. checking no_input_delay (2)\\n6. checking no_output_delay (4)\\n")
    (tmp_path / "methodology.rpt").write_text(
        "| TIMING-18 | Warning | Missing input or output delay | 5 |\\n")
    with pytest.raises(swd.SWDBuildDenied, match="SWD_IO_TIMING_REPORTS_DISAGREE"):
        swd.audit_external_io_timing(tmp_path)


def test_routed_fpga_only_rx_budget_fails_fast_before_target_tco(tmp_path):
    (tmp_path / "datasheet_io.rpt").write_text(
        ROUTED_FPGA_IO_DATASHEET_FIXTURE, encoding="utf-8")
    result = swd.fpga_only_swd_rx_ideal_budget(tmp_path)
    assert result["fclk_hz"] == 100000000
    assert result["candidate_hw_max_swd_hz"] == 12500000
    assert result["candidate_max_half_period_ns"] == 40.0
    site1 = result["estimated_ideal_fpga_only"]["site1"]
    site2 = result["estimated_ideal_fpga_only"]["site2"]
    assert site1["necessary_fpga_only_halfcycle_ns"] == 18.399
    assert site1["unqualified_25mhz_ideal_margin_ns"] == 1.601
    assert site2["necessary_fpga_only_halfcycle_ns"] == 20.394
    assert site2["unqualified_25mhz_ideal_margin_ns"] == -0.394
    assert site1["candidate_12_5mhz_fpga_only_margin_ns"] == 21.601
    assert site2["candidate_12_5mhz_fpga_only_margin_ns"] == 19.606
    assert result["external_timing_qualified"] is False


def test_fpga_rx_budget_fails_closed_on_missing_pad_or_bad_value(tmp_path):
    path = tmp_path / "datasheet_io.rpt"
    path.write_text(ROUTED_FPGA_IO_DATASHEET_FIXTURE.replace(
        "swclk_site2", "SWCLK_UNKNOWN"), encoding="utf-8")
    with pytest.raises(swd.SWDBuildDenied,
                       match="SWD_FPGA_DATASHEET_PORT_ABSENT_OR_DUPLICATE"):
        swd.fpga_only_swd_rx_ideal_budget(tmp_path)
    path.write_text(ROUTED_FPGA_IO_DATASHEET_FIXTURE.replace(
        "14.118 (r)", "INVALID"), encoding="utf-8")
    with pytest.raises(swd.SWDBuildDenied,
                       match="SWD_FPGA_DATASHEET_BAD_NUMBER"):
        swd.fpga_only_swd_rx_ideal_budget(tmp_path)


def test_operator_entry_is_exact_source_pinned_and_no_root_workflow():
    assert script.VIVADO_TIMEOUT < script.RUNNER_TIMEOUT_EXPECTED == 1800
    assert script.BOARD_SHA == "e02d6a3866b5465218f777168cdc51344ac94e07"
    with pytest.raises(script.BuildRejected, match="SWD_SOURCE_SHA_INVALID"):
        script.validate_source("unverified")
    with pytest.raises(script.BuildRejected, match="SWD_SOURCE_PIN_MISMATCH"):
        script.validate_source("a" * 40)
    body = (ROOT / "scripts/plasma_swd_host_build.py").read_text()
    for forbidden in ("fpga_manager", "z2-root-operation",
                      "plasma_vivado_host_build", "sudo -S", "scp "):
        assert forbidden not in body.lower() or forbidden == "fpga_manager" and "No SSH" in body
    assert 'PLASMA_BOARD_REPO' in body and "XILINXD_LICENSE_FILE" in body


def test_cloned_source_not_counted_as_hardware_build():
    script_text = (ROOT / "scripts/plasma_swd_host_build.py").read_text()
    assert "PREFLIGHT_ONLY_NOT_BUILD" in script_text
    assert "SWPC_HOST_BUILD_ARTIFACTS_VERIFY_REVIEW_REQUIRED" in script_text
    assert "SWD_VIVADO_BUILD_FAILED" in script_text
    assert "SWD_VIVADO_BUILD_TIMED_OUT_STARTED" in script_text
    assert "z2_hil" in script_text and "NOT_RUN" in script_text
