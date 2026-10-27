#!/usr/bin/env python3
"""Fail-closed HWH/BIT/Timing qualification for TWO independent SWD AXI Sites.

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
from pathlib import Path
import xml.etree.ElementTree as ET

BASES = {"swd_site1": 0x43C01000, "swd_site2": 0x43C02000}
LENGTH = 0x1000
PINS = {"swclk_site1": "Y18", "swdio_site1": "Y19",
        "swclk_site2": "W14", "swdio_site2": "Y14"}
REPORT_NAMES = ("timing_summary.rpt", "drc.rpt", "methodology.rpt",
                "utilization.rpt", "check_timing.rpt")
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


def validate_hwh(root: ET.Element) -> dict:
    modules = {m.get("INSTANCE"): m for m in root.iter("MODULE")}
    require({"ps7_0", "rst_ps7_0_100M", "axi_interconnect_0",
             *BASES}.issubset(modules), "SWD_HWH_REQUIRED_MODULE_MISSING")
    # HWH must describe exactly the two independently mapped AXI slaves.
    # A composite MPE register aperture at 0x43C00000 is NEVER valid.
    mem = list(root.iter("MEMRANGE"))
    require(len(mem) == 2, "SWD_HWH_REQUIRES_TWO_AXI_REGIONS")
    mapped = {}
    for item in mem:
        require(item.get("MASTERBUSINTERFACE") == "M_AXI_GP0",
                "SWD_HWH_UNEXPECTED_AXIMASTER")
        name = item.get("INSTANCE")
        require(name in BASES and name not in mapped,
                "SWD_HWH_UNEXPECTED_OR_DUPLICATE_SITE")
        start = number(item.get("BASEVALUE"))
        high = number(item.get("HIGHVALUE"))
        require(start == BASES[name] and high == start + LENGTH - 1,
                "SWD_HWH_SITE_WINDOW_MISMATCH")
        mapped[name] = (start, high)
    require(set(mapped) == set(BASES), "SWD_HWH_SITE_ABSENT")
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
                    for name, value in BASES.items()},
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


def verify_artifacts(*, hwh: Path, bit: Path, reports: Path,
                     xdc: Path, source_sha: str, build_stdout: str = "") -> dict:
    require(isinstance(source_sha, str) and SHA40.fullmatch(source_sha) is not None,
            "SWD_BUILD_SOURCE_SHA_DENIED")
    require(hwh.is_file() and not hwh.is_symlink() and
            hwh.stat().st_size > 0 and hwh.stat().st_size < 8 * 1024 * 1024,
            "SWD_HWH_MISSING_OR_UNSAFE")
    require(bit.is_file() and not bit.is_symlink() and
            bit.stat().st_size > 1024, "SWD_BITSTREAM_MISSING_OR_UNSAFE")
    try:
        hw = validate_hwh(ET.parse(hwh).getroot())
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
    # Real Vivado Tcl must fail on slack/DRC/errors; reports are immutable
    # evidence for reviewer. A positive exit alone does NOT qualify timing.
    require("SWD_HOST_IMPL_REPORTS_TIMING_DRC_PASS" in build_stdout,
            "SWD_BUILD_TCL_SIGNOFF_MARKER_MISSING")
    return {
        "schema": "plasma.swd.independent.host-build.evidence.v1",
        "source_sha": source_sha,
        "board": "pynq-z2", "part": "xc7z020clg400-1",
        "abi": "swd.independent.site.v1-candidate",
        "bit_sha256": sha256(bit), "hwh_sha256": sha256(hwh),
        "xdc_sha256": check_xdc(xdc),
        "report_sha256": report_hashes, "hwh": hw,
        "external_swd_io_timing": io_timing,
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
