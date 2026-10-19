#!/usr/bin/env python3
"""F1 fail-closed HWH and implemented-artifact evidence parser. NO device I/O."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

GP0_BASE = 0x40000000
GP0_LENGTH = 0x10000
REPORTS = ("timing_summary.rpt", "drc.rpt", "methodology.rpt",
           "utilization.rpt", "check_timing.rpt")


class F1Denied(ValueError):
    """Fail closed. A syntactically valid HWH is not hardware qualification."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise F1Denied(code)


def number(v: str | None) -> int | float:
    """Match existing Z2 HWH encodings: binary vectors and PS7 bool/floats."""
    require(v is not None and bool(v.strip()), "HWH_NUMBER_MISSING")
    value = v.strip().lower()
    if len(value) == 32 and set(value) <= {"0", "1"}:
        return int(value, 2)
    if value in {"true", "false"}:
        return int(value == "true")
    try:
        return int(value, 0)
    except ValueError:
        try:
            from math import isfinite
            parsed = float(value)
            require(isfinite(parsed), "HWH_NUMBER_NONFINITE")
            return parsed
        except ValueError as exc:
            raise F1Denied("HWH_NUMBER_INVALID") from exc


def parameters(module: ET.Element) -> dict[str, str]:
    return {p.get("NAME"): p.get("VALUE")
            for p in module.iter("PARAMETER")}


def ports(module: ET.Element) -> dict[str, str | None]:
    return {p.get("NAME"): p.get("SIGNAME")
            for p in module.iter("PORT")}


def validate_hwh(root: ET.Element) -> dict:
    modules = {m.get("INSTANCE"): m for m in root.iter("MODULE")}
    require({"ps7_0", "rst_ps7_0_100M", "unified_0"}.issubset(modules),
            "HWH_REQUIRED_MODULE_MISSING")
    for external in root.iter("EXTERNALPORTS"):
        for port in external.iter("PORT"):
            name = port.get("NAME", "")
            require(name.startswith(("DDR_", "FIXED_IO_")),
                    "HWH_EXTERNAL_PL_PORT_DENIED")
    gp0 = [m for m in root.iter("MEMRANGE")
           if m.get("MASTERBUSINTERFACE") == "M_AXI_GP0"]
    require(len(gp0) == 1, "HWH_ONE_64K_SEGMENT_REQUIRED")
    r = gp0[0]
    require(r.get("INSTANCE") == "unified_0"
            and number(r.get("BASEVALUE")) == GP0_BASE
            and number(r.get("HIGHVALUE")) == GP0_BASE + GP0_LENGTH - 1,
            "HWH_GP0_ADDRESS_MISMATCH")
    require(len(list(root.iter("MEMRANGE"))) == 1,
            "HWH_UNEXPECTED_MEMORY_APERTURE")
    config = parameters(modules["ps7_0"])
    for key, expected in (
        ("PCW_GPIO_EMIO_GPIO_ENABLE", 0),
        ("PCW_USE_M_AXI_GP0", 1),
        ("PCW_CRYSTAL_PERIPHERAL_FREQMHZ", 50),
        ("PCW_FPGA0_PERIPHERAL_FREQMHZ", 100),
    ):
        require(number(config.get(key)) == expected, "HWH_PS7_CONFIG_MISMATCH")
    clk = ports(modules["ps7_0"]).get("M_AXI_GP0_ACLK")
    require(clk == "ps7_0_FCLK_CLK0", "HWH_PS7_GP0_CLOCK_MISMATCH")
    ps_port = next((p for p in modules["ps7_0"].iter("PORT")
                    if p.get("NAME") == "M_AXI_GP0_ACLK"), None)
    require(ps_port is not None and
            number(ps_port.get("CLKFREQUENCY")) == 100000000,
            "HWH_FCLK0_FREQ_MISMATCH")
    up = parameters(modules["unified_0"])
    require(number(up.get("PPU_BASE")) == GP0_BASE,
            "HWH_UNIFIED_DECODER_MISMATCH")
    wiring = ports(modules["unified_0"])
    require(wiring.get("s_axi_aclk") == "ps7_0_FCLK_CLK0",
            "HWH_UNIFIED_CLOCK_MISMATCH")
    require(wiring.get("s_axi_aresetn") ==
            "rst_ps7_0_100M_peripheral_aresetn",
            "HWH_UNIFIED_RESET_MISMATCH")
    reset = modules["rst_ps7_0_100M"]
    require(number(parameters(reset).get("C_EXT_RESET_HIGH")) == 0 and
            ports(reset).get("ext_reset_in") == "ps7_0_FCLK_RESET0_N",
            "HWH_RESET_SOURCE_MISMATCH")
    for banned in ("swdio_in", "swclk", "swdio_out", "swdio_oe"):
        require(banned not in wiring, "HWH_EXTERNAL_SWD_PORT_DENIED")
    return {
        "base": f"0x{GP0_BASE:08X}",
        "bytes": GP0_LENGTH,
        "regions": {"global_identity": "0x0000", "global_health": "0x1000",
                    "site1_swd": "0x4000", "site2_8": "ABSENT"},
        "external_pl_io": False,
        "virtual_dpidr_fixture_only": True,
        "hardware_runtime_ready": False,
        "z2_hil": "NOT_RUN",
    }


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_artifacts(*, hwh: Path, bit: Path, reports: Path,
                     source_sha: str) -> dict:
    require(bool(re.fullmatch(r"[a-f0-9]{40}", source_sha)),
            "SOURCE_SHA_INVALID")
    require(hwh.is_file() and bit.is_file()
            and hwh.stat().st_size > 0 and bit.stat().st_size > 0,
            "ARTIFACT_MISSING")
    result = validate_hwh(ET.parse(hwh).getroot())
    for name in REPORTS:
        file = reports / name
        require(file.is_file() and file.stat().st_size > 0,
                "IMPLEMENTATION_REPORT_MISSING")
    # The Vivado build must first independently check timing slack, blocking
    # DRC and methodology; a report's existence alone proves no result.
    return {
        "schema": "plasma.fixed-f1-z2-host-build-candidate.v1",
        "source_sha": source_sha,
        "hwh_sha256": digest(hwh),
        "bit_sha256": digest(bit),
        "report_sha256": {name: digest(reports / name) for name in REPORTS},
        "map": result,
        "vivado_implemented": "SUPERVISOR_REVIEW_REQUIRED",
        "physical_image_loaded": "NOT_RUN",
        "z2_fixed_abi_hil": "NOT_RUN",
        "m1": "NO_GO",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hwh", type=Path, required=True)
    p.add_argument("--bit", type=Path, required=True)
    p.add_argument("--reports", type=Path, required=True)
    p.add_argument("--source-sha", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = verify_artifacts(hwh=args.hwh, bit=args.bit,
                              reports=args.reports, source_sha=args.source_sha)
    # Creating a candidate JSON NEVER marks a physical build or HIL as PASS.
    require(not args.output.exists(), "ARTIFACT_OUTPUT_EXISTS")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("FIXED_F1_HWH_ARTIFACT_INSPECTION_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
