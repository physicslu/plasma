#!/usr/bin/env python3
"""Fail-closed HWH/BIT/Timing qualification for Common and two SWD Sites.

No device IO. Never use F1-B's internal synthetic DPIDR verifier.
A positive receipt means actual files satisfy checked HOST-BUILD contracts,
not that Z2/FPGA Manager/PMOD electrical/HIL/real OpenOCD is qualified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

BASES = {"swd_site1": 0x43C01000, "swd_site2": 0x43C02000}
COMMON_BASE = 0x43C03000
IMAGE_ID = 0x7a322d7377642d6f70702d76352d3031
LENGTH = 0x1000
PINS = {"swclk_site1": "Y18", "swdio_site1": "Y19",
        "swclk_site2": "W14", "swdio_site2": "Y14"}
REPORT_NAMES = ("timing_summary.rpt", "drc.rpt", "methodology.rpt",
                "utilization.rpt", "check_timing.rpt", "datasheet_io.rpt",
                "io_pad_configuration.rpt")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")


class SWDBuildDenied(ValueError):
    pass


def require(ok: bool, code: str) -> None:
    if not ok:
        raise SWDBuildDenied(code)


def number(value: str | None) -> int:
    require(isinstance(value, str) and bool(value.strip()), "SWD_HWH_VALUE_MISSING")
    raw = value.strip().lower()
    try:
        if len(raw) == 32 and set(raw) <= {"0", "1"}:
            return int(raw, 2)
        if raw in ("true", "false"):
            return int(raw == "true")
        try:
            return int(raw, 0)
        except ValueError:
            numeric = float(raw)
            require(math.isfinite(numeric) and numeric.is_integer(),
                    "SWD_HWH_NONINTEGER_NUMBER")
            return int(numeric)
    except ValueError as exc:
        raise SWDBuildDenied("SWD_HWH_INTEGER_INVALID") from exc


def parameters(module: ET.Element) -> dict[str, str | None]:
    return {p.get("NAME"): p.get("VALUE") for p in module.iter("PARAMETER")}


def ports(module: ET.Element) -> dict[str, str | None]:
    return {p.get("NAME"): p.get("SIGNAME") for p in module.iter("PORT")}


def wide_number(value: str | None) -> int:
    require(isinstance(value, str), "OPP_HWH_IDENTITY_MISSING")
    raw = value.strip().lower().replace("_", "")
    try:
        literal = re.fullmatch(r"\d+'([hbd])([0-9a-f]+)", raw)
        if literal:
            radix = {"h": 16, "b": 2, "d": 10}[literal[1]]
            raw = str(int(literal[2], radix))
        result = int(raw, 0) if raw.startswith("0x") else int(raw, 10)
    except ValueError as exc:
        raise SWDBuildDenied("OPP_HWH_IDENTITY_INVALID") from exc
    require(0 <= result < (1 << 128), "OPP_HWH_IDENTITY_INVALID")
    return result


def validate_hwh(root: ET.Element, source_sha: str | None = None) -> dict:
    modules = {m.get("INSTANCE"): m for m in root.iter("MODULE")}
    require({"ps7_0", "rst_ps7_0_100M", "axi_interconnect_0",
             "opp_common", *BASES}.issubset(modules), "SWD_HWH_REQUIRED_MODULE_MISSING")
    require(number(parameters(modules["axi_interconnect_0"]).get("NUM_MI")) == 3,
            "OPP_HWH_INTERCONNECT_COUNT_MISMATCH")
    # The Linux owner resource at 0x43C00000 is not an AXI slave.
    mem = list(root.iter("MEMRANGE"))
    require(len(mem) == 3, "OPP_HWH_REQUIRES_THREE_AXI_REGIONS")
    mapped = {}
    expected_bases = {**BASES, "opp_common": COMMON_BASE}
    for item in mem:
        require(item.get("MASTERBUSINTERFACE") == "M_AXI_GP0",
                "SWD_HWH_UNEXPECTED_AXIMASTER")
        name = item.get("INSTANCE")
        require(name in expected_bases and name not in mapped and
                item.get("SLAVEBUSINTERFACE") == "S_AXI",
                "OPP_HWH_UNEXPECTED_OR_DUPLICATE_SLAVE")
        start = number(item.get("BASEVALUE"))
        high = number(item.get("HIGHVALUE"))
        require(start == expected_bases[name] and high == start + LENGTH - 1,
                "OPP_HWH_WINDOW_MISMATCH")
        mapped[name] = (start, high)
    require(set(mapped) == set(expected_bases) and
            all(hi < other_lo or other_hi < lo
                for index, (lo, hi) in enumerate(mapped.values())
                for other_lo, other_hi in list(mapped.values())[index + 1:]),
            "OPP_HWH_WINDOW_OVERLAP_OR_ABSENT")
    ps = modules["ps7_0"]
    config = parameters(ps)
    for key, expected in (
        ("PCW_GPIO_EMIO_GPIO_ENABLE", 0),
        ("PCW_USE_M_AXI_GP0", 1),
        ("PCW_CRYSTAL_PERIPHERAL_FREQMHZ", 50),
        ("PCW_FPGA0_PERIPHERAL_FREQMHZ", 100),
    ):
        require(number(config.get(key)) == expected, "SWD_HWH_PS7_CONFIG_MISMATCH")
    psclk = next((p for p in ps.iter("PORT")
                  if p.get("NAME") == "M_AXI_GP0_ACLK"), None)
    require(psclk is not None and
            number(psclk.get("CLKFREQUENCY")) == 100000000,
            "SWD_HWH_FCLK_FREQUENCY_MISMATCH")
    require(ports(ps).get("M_AXI_GP0_ACLK") == "ps7_0_FCLK_CLK0",
            "SWD_HWH_FCLK_NET_MISMATCH")
    rst = modules["rst_ps7_0_100M"]
    require(number(parameters(rst).get("C_EXT_RESET_HIGH")) == 0 and
            ports(rst).get("ext_reset_in") == "ps7_0_FCLK_RESET0_N",
            "SWD_HWH_RESET_SOURCE_MISMATCH")
    for name, sid in (("swd_site1", 1), ("swd_site2", 2)):
        p = parameters(modules[name])
        require(number(p.get("SITE_ID")) == sid and
                number(p.get("SITE_BASE_ADDRESS")) == BASES[name],
                "SWD_HWH_SITE_PARAM_MISMATCH")
        wiring = ports(modules[name])
        require(wiring.get("s_axi_aclk") == "ps7_0_FCLK_CLK0" and
                wiring.get("s_axi_aresetn") ==
                "rst_ps7_0_100M_peripheral_aresetn",
                "SWD_HWH_SITE_CLOCK_RESET_MISMATCH")
    common = modules["opp_common"]
    common_params = parameters(common)
    require(wide_number(common_params.get("IMAGE_ID")) == IMAGE_ID and
            wide_number(common_params.get("SITE_PRESENT")) == 3 and
            wide_number(common_params.get("SITE_READY")) == 0 and
            wide_number(common_params.get("CAPABILITIES")) == 0 and
            wide_number(common_params.get("PPU_STATUS")) == 0,
            "OPP_HWH_COMMON_IDENTITY_OR_STATUS_MISMATCH")
    if source_sha is not None:
        require(SHA40.fullmatch(source_sha) is not None and
                wide_number(common_params.get("BUILD_ID")) == int(source_sha[:32], 16),
                "OPP_HWH_BUILD_ID_MISMATCH")
    common_wiring = ports(common)
    require(common_wiring.get("s_axi_aclk") == "ps7_0_FCLK_CLK0" and
            common_wiring.get("s_axi_aresetn") ==
            "rst_ps7_0_100M_peripheral_aresetn",
            "OPP_HWH_COMMON_CLOCK_RESET_MISMATCH")
    fabric_wiring = ports(modules["axi_interconnect_0"])
    require(all(fabric_wiring.get(name) == "ps7_0_FCLK_CLK0"
                for name in ("ACLK", "S00_ACLK", "M00_ACLK", "M01_ACLK",
                             "M02_ACLK")) and
            all(fabric_wiring.get(name) ==
                "rst_ps7_0_100M_peripheral_aresetn"
                for name in ("ARESETN", "S00_ARESETN", "M00_ARESETN",
                             "M01_ARESETN", "M02_ARESETN")),
            "OPP_HWH_INTERCONNECT_CLOCK_RESET_MISMATCH")
    buses = {name: {b.get("NAME"): b.get("BUSNAME")
                    for b in modules[name].iter("BUSINTERFACE")}
             for name in ("ps7_0", "axi_interconnect_0", "opp_common", *BASES)}
    fabric_buses = buses["axi_interconnect_0"]
    require(buses["ps7_0"].get("M_AXI_GP0") == fabric_buses.get("S00_AXI") and
            all(fabric_buses.get(port) == buses[slave].get("S_AXI") and
                fabric_buses.get(port) is not None
                for port, slave in (("M00_AXI", "swd_site1"),
                                    ("M01_AXI", "swd_site2"),
                                    ("M02_AXI", "opp_common"))),
            "OPP_HWH_INTERCONNECT_ROUTE_MISMATCH")
    exposed = []
    for ext in root.iter("EXTERNALPORTS"):
        exposed.extend(p.get("NAME") for p in ext.iter("PORT"))
    require(all(isinstance(p, str) for p in exposed),
            "SWD_HWH_EXTERNAL_PORT_UNNAMED")
    actual = {p for p in exposed
              if not p.startswith(("DDR_", "FIXED_IO_"))}
    require(actual == set(PINS) and len(actual) == 4 and len(exposed) == len(set(exposed)),
            "SWD_HWH_WRONG_EXTERNAL_SWDPADS")
    return {
        "regions": {name: {"base": f"0x{value:08X}", "size": LENGTH}
                    for name, value in expected_bases.items()},
        "external_swd_pads": sorted(actual),
        "ps7_fclk_hz": 100000000,
        "site_count_implemented": 2,
        "real_target_qualified": False,
    }


def sha256(path: Path) -> str:
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size > 0, "SWD_ARTIFACT_MISSING_OR_UNSAFE")
    result = hashlib.sha256()
    with path.open("rb") as src:
        for data in iter(lambda: src.read(1024 * 1024), b""):
            result.update(data)
    return result.hexdigest()


def check_xdc(xdc: Path) -> str:
    body = xdc.read_text(encoding="utf-8")
    for pad, physical in PINS.items():
        line = (f"set_property -dict {{PACKAGE_PIN {physical} "
                f"IOSTANDARD LVCMOS33}} [get_ports {pad}]")
        require(body.count(line) == 1, "SWD_XDC_PIN_OR_IOSTANDARD_MISMATCH")
    active = [x for x in body.splitlines() if x.startswith("set_property ")]
    require(len(active) == 4, "SWD_XDC_ADDITIONAL_PIN_DRIVE_DENIED")
    return sha256(xdc)


def pair_manifest(build: Path, source_sha: str, verified_hwh: Path) -> dict:
    """Write a Host-only candidate paired to the exact generated BIN and HWH."""
    artifacts = build / "artifacts"
    firmware = artifacts / "system_wrapper.bin"
    bit = artifacts / "system_wrapper.bit"
    hwh = artifacts / "system.hwh"
    require(all(p.is_file() and not p.is_symlink() for p in (firmware, bit, hwh)),
            "OPP_PAIRED_ARTIFACT_MISSING")
    project = build / "project/z2_swd_independent.runs/impl_1"
    require(sha256(firmware) == sha256(project / "system_wrapper.bin") and
            sha256(bit) == sha256(project / "system_wrapper.bit") and
            sha256(hwh) == sha256(verified_hwh),
            "OPP_PAIRED_ARTIFACT_MISMATCH")
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from pl.hil import fpga_image_guard as guard
    manifest = {
        "schema": "plasma.fpga.image.v1",
        "image_id": f"z2-swd-opp-v1-{source_sha[:12]}",
        "board_id": "pynq-z2", "fpga_part": "xc7z020clg400-1",
        "soc_compatible": "xlnx,zynq-7000",
        "firmware_name": "system_wrapper.bin",
        "firmware_sha256": sha256(firmware),
        "recovery_name": guard.GOLDEN_RECOVERY_NAME,
        "recovery_sha256": guard.GOLDEN_RECOVERY_SHA256,
        "abi_version": 0x00010000, "abi_offset": 0x2004,
        "identity_words": [[0, 0x00050001, 0xFFFFFFFF],
                           [0x1000, 0x00050002, 0xFFFFFFFF],
                           [0x2000, 0x4D534C50, 0xFFFFFFFF],
                           [0x2004, 0x00010000, 0xFFFFFFFF],
                           [0x2030, 3, 0xFFFFFFFF]],
        "site_bitmap": 3, "site_bitmap_offset": 0x2030,
        "axi_base": 0x43C01000, "axi_bytes": 0x3000,
        "owner_base": 0x43C00000, "owner_bytes": 0x10000,
        "expected_uio": {"platform_node": "43c00000.audio-codec-ctrl",
                         "driver": "uio_pdrv_genirq",
                         "maps": [[0x43C00000, 0x10000]],
                         "runtime": "suspended"},
    }
    # This source-only candidate is never an authorization to stage/load.
    from pl.hil.fpga_image_root import parse_image_manifest_bytes, validate_hwh_bytes
    raw = (json.dumps(manifest, indent=2) + "\n").encode()
    parse_image_manifest_bytes(raw)
    validate_hwh_bytes(hwh.read_bytes(), parse_image_manifest_bytes(raw))
    path = artifacts / "plasma-image-manifest.json"
    require(not path.exists(), "OPP_PAIRED_MANIFEST_ALREADY_EXISTS")
    path.write_bytes(raw)
    return {"bin_sha256": sha256(firmware), "manifest_sha256": sha256(path),
            "manifest_path": str(path), "image_id": manifest["image_id"]}


def audit_external_io_timing(reports: Path) -> dict:
    """Parse real Vivado reports; never infer SWD I/O qualification from WNS.

    This gate is intentionally NOT auto-approved even when all 6 TIMING-18
    warnings disappear: a source-controlled target/board min+max timing
    budget must first be justified and audited.
    """
    ct = (reports / "check_timing.rpt").read_text(encoding="utf-8")
    meth = (reports / "methodology.rpt").read_text(encoding="utf-8")
    found = {}
    for kind in ("no_input_delay", "no_output_delay"):
        counts = re.findall(r"checking " + kind + r" \((\d+)\)", ct)
        require(len(counts) >= 1 and len(set(counts)) == 1,
                "SWD_IO_CHECK_TIMING_COUNTS_MISSING")
        found[kind] = int(counts[0])
    match = re.search(
        r"TIMING-18\s*\|\s*Warning\s*\|[^\n]*?\|\s*(\d+)\s*\|",
        meth)
    timing18 = int(match.group(1)) if match else 0
    # An absent TIMING-18 row is valid only if there are no unmodelled ports.
    require(timing18 == found["no_input_delay"] + found["no_output_delay"],
            "SWD_IO_TIMING_REPORTS_DISAGREE")
    if timing18:
        disposition = "BLOCKED_MISSING_OFFCHIP_TIMING"
    else:
        disposition = "PENDING_SOURCE_REVIEWED_TARGET_BOARD_BUDGET"
    return {
        "gate": disposition,
        "timing18_warnings": timing18,
        "unconstrained_input_ports": found["no_input_delay"],
        "unconstrained_output_ports": found["no_output_delay"],
        "external_io_timing_qualified": False,
        "scope": "Vivado IO constraint completeness, NOT SWD target HIL",
    }


def fpga_only_swd_rx_ideal_budget(reports: Path) -> dict:
    """Use real routed Vivado pad times; external target/cable delay is UNKNOWN.

    SWD target changes outgoing SWDIO on SWCLK rising, host samples on
    subsequent falling. Both source and sample edges use 100MHz FCLK.
    The measured clock-to-SWCLK-pad and SWDIO-pad-to-register setup time
    form a necessary, never sufficient, one-half-period condition.
    """
    report = (reports / "datasheet_io.rpt").read_text(encoding="utf-8")
    require("Input Ports Setup/Hold" in report and
            "Output Ports Clock-to-out" in report and
            "Setup between Clocks" in report,
            "SWD_FPGA_DATASHEET_REQUIRED_SECTIONS_MISSING")
    rx = report.split("Input Ports Setup/Hold", 1)[1].split(
        "Output Ports Clock-to-out", 1)[0]
    tx = report.split("Output Ports Clock-to-out", 1)[1].split(
        "Setup between Clocks", 1)[0]

    def slow_max(table: str, port: str) -> float:
        rows = []
        for line in table.splitlines():
            fields = [v.strip() for v in line.strip().strip("|").split("|")]
            if len(fields) > 5 and fields[0] == "clk_fpga_0" and (
                    fields[1] == port) and fields[5] == "SLOW":
                try:
                    value = float(fields[4].split()[0])
                except (ValueError, IndexError) as exc:
                    raise SWDBuildDenied("SWD_FPGA_DATASHEET_BAD_NUMBER") from exc
                require(math.isfinite(value) and value > 0,
                        "SWD_FPGA_DATASHEET_BAD_NUMBER")
                rows.append(value)
        require(len(rows) == 1, "SWD_FPGA_DATASHEET_PORT_ABSENT_OR_DUPLICATE")
        return rows[0]

    # Design candidate max 12.5MHz: FCLK 100MHz, N=4, half cycle=40ns.
    # Only an FPGA-side necessary condition. No target/cable closure is implied.
    half_ns = 40.0
    per_site = {}
    for idx in (1, 2):
        tclk = slow_max(tx, f"swclk_site{idx}")
        tsetup = slow_max(rx, f"swdio_site{idx}")
        minimum = tclk + tsetup
        margin = half_ns - minimum
        require(margin > 0, "SWD_FPGA_RX_12_5MHZ_CANDIDATE_INFEASIBLE")
        per_site[f"site{idx}"] = {
            "clock_to_swclk_pad_slow_max_ns": round(tclk, 3),
            "swdio_input_setup_slow_ns": round(tsetup, 3),
            "necessary_fpga_only_halfcycle_ns": round(minimum, 3),
            "unqualified_25mhz_ideal_margin_ns": round(20.0 - minimum, 3),
            "candidate_12_5mhz_fpga_only_margin_ns": round(margin, 3),
            "target_tco_and_cable_accounted": False,
        }
    return {"fclk_hz": 100000000, "candidate_hw_max_swd_hz": 12500000,
            "candidate_max_half_period_ns": 40.0,
            "estimated_ideal_fpga_only": per_site,
            "external_timing_qualified": False,
            "warning": "FPGA-only necessary condition; not a DUT timing proof"}


def verify_artifacts(*, hwh: Path, bit: Path, reports: Path,
                     source_sha: str, build: Path | None = None,
                     xdc: Path | None = None, build_stdout: str = "") -> dict:
    # The generic Path 2 runner supplies only build; the historical project
    # verifier CLI supplies xdc and build_stdout. Both enforce identical
    # source-locked HWH, XDC, report, and off-board timing checks.
    if build is not None:
        require(xdc is None and build_stdout == "" and
                build.is_dir() and not build.is_symlink(),
                "SWD_GENERIC_BUILD_INPUT_INVALID")
        xdc = Path(__file__).resolve().parents[2] / (
            "constraints/pynq-z2/z2-swd-independent.xdc")
        log = build / "vivado-stdout.log"
        require(log.is_file() and not log.is_symlink() and
                0 < log.stat().st_size <= 2_000_000,
                "SWD_GENERIC_BUILD_LOG_MISSING_OR_UNSAFE")
        build_stdout = log.read_text(encoding="utf-8")
    require(xdc is not None, "SWD_BUILD_XDC_MISSING")
    require(isinstance(source_sha, str) and SHA40.fullmatch(source_sha) is not None,
            "SWD_BUILD_SOURCE_SHA_DENIED")
    require(hwh.is_file() and not hwh.is_symlink() and
            hwh.stat().st_size > 0 and hwh.stat().st_size < 8 * 1024 * 1024,
            "SWD_HWH_MISSING_OR_UNSAFE")
    require(bit.is_file() and not bit.is_symlink() and
            bit.stat().st_size > 1024, "SWD_BITSTREAM_MISSING_OR_UNSAFE")
    try:
        hw = validate_hwh(ET.parse(hwh).getroot(), source_sha)
    except ET.ParseError as exc:
        raise SWDBuildDenied("SWD_HWH_XML_INVALID") from exc
    report_hashes = {}
    for name in REPORT_NAMES:
        path = reports / name
        require(path.is_file() and not path.is_symlink() and
                0 < path.stat().st_size < 8 * 1024 * 1024,
                "SWD_IMPLEMENTATION_REPORT_MISSING_OR_UNSAFE")
        report_hashes[name] = sha256(path)
    io_timing = audit_external_io_timing(reports)
    fpga_budget = fpga_only_swd_rx_ideal_budget(reports)
    # Real Vivado Tcl must fail on slack/DRC/errors; reports are immutable
    # evidence for reviewer. A positive exit alone does NOT qualify timing.
    require("SWD_HOST_IMPL_REPORTS_TIMING_DRC_PASS" in build_stdout,
            "SWD_BUILD_TCL_SIGNOFF_MARKER_MISSING")
    paired = pair_manifest(build, source_sha, hwh) if build is not None else {}
    return {
        "schema": "plasma.opp.swd5.host-build.evidence.v1",
        "source_sha": source_sha,
        "board": "pynq-z2", "part": "xc7z020clg400-1",
        "abi": "opp.common.v1+swd.site.v5-candidate",
        "bit_sha256": sha256(bit), "hwh_sha256": sha256(hwh),
        "xdc_sha256": check_xdc(xdc),
        "report_sha256": report_hashes, "hwh": hw,
        "map": hw["regions"],
        **paired,
        "external_swd_io_timing": io_timing,
        "fpga_only_swd_rx_ideal_budget": fpga_budget,
        "host_build_status": "SUPERVISOR_REVIEW_REQUIRED",
        "physical_image_loaded": "NOT_RUN", "z2_hil": "NOT_RUN",
        "openocd_swd": "NOT_QUALIFIED", "real_dut": "NOT_RUN",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hwh", type=Path, required=True)
    parser.add_argument("--bit", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--xdc", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = verify_artifacts(hwh=args.hwh, bit=args.bit,
                              reports=args.reports, xdc=args.xdc,
                              source_sha=args.source_sha,
                              build_stdout=args.build_log.read_text(encoding="utf-8"))
    require(not args.output.exists(), "SWD_EVIDENCE_OUTPUT_ALREADY_EXISTS")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print("SWD_HWH_AND_ARTIFACT_INSPECTION_HOST_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
