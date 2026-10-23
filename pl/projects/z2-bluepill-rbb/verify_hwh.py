#!/usr/bin/env python3
"""Offline-only Z2 Blue Pill HWH/bit candidate inspection, NEVER FPGA I/O."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

BASE = 0x40008000
SIZE = 4096


class HWHRejected(ValueError):
    pass


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise HWHRejected(code)


def _number(value: str | None) -> int:
    _need(bool(value), "HWH_NUMBER_MISSING")
    assert value is not None
    if len(value) == 32 and set(value) <= {"0", "1"}:
        return int(value, 2)
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return int(lowered == "true")
    try:
        return int(lowered, 0)
    except ValueError:
        numeric = float(lowered)
        _need(numeric.is_integer(), "HWH_NUMBER_NOT_INTEGRAL")
        return int(numeric)


def _ports(module: ET.Element) -> dict[str, str | None]:
    return {x.get("NAME"): x.get("SIGNAME") for x in module.iter("PORT")}


def verify_hwh_xml(xml: str) -> dict:
    root = ET.fromstring(xml)
    modules = {x.get("INSTANCE"): x for x in root.iter("MODULE")}
    _need({"ps7_0", "swd_0", "pads_0", "rst_ps7_0_100M"} <= set(modules),
          "HWH_EXPECTED_INSTANCE_MISSING")
    gp0 = [x for x in root.iter("MEMRANGE")
           if x.get("MASTERBUSINTERFACE") == "M_AXI_GP0"]
    _need(len(gp0) == 1 and len(list(root.iter("MEMRANGE"))) == 1,
          "HWH_EXPECTED_ONE_GP0_RANGE")
    region = gp0[0]
    _need(region.get("INSTANCE") == "swd_0" and
          _number(region.get("BASEVALUE")) == BASE and
          _number(region.get("HIGHVALUE")) == BASE + SIZE - 1,
          "HWH_AXI_MAP_MISMATCH")
    pins = {p.get("NAME") for x in root.iter("EXTERNALPORTS")
            for p in x.iter("PORT")}
    _need({"swclk_io", "swdio_io"} <= pins, "HWH_PMOD_EXTERNAL_MISSING")
    _need(all(p in {"swclk_io", "swdio_io"} or
              p.startswith(("DDR_", "FIXED_IO_")) for p in pins),
          "HWH_UNEXPECTED_EXTERNAL")
    ps7 = modules["ps7_0"]
    config = {p.get("NAME"): p.get("VALUE")
              for p in ps7.iter("PARAMETER")}
    for key, expected in (
        ("PCW_CRYSTAL_PERIPHERAL_FREQMHZ", 50),
        ("PCW_FPGA0_PERIPHERAL_FREQMHZ", 100),
        ("PCW_USE_M_AXI_GP0", 1),
        ("PCW_GPIO_EMIO_GPIO_ENABLE", 0),
    ):
        _need(_number(config.get(key)) == expected,
              "HWH_PS7_CONFIG_MISMATCH")
    swd = _ports(modules["swd_0"])
    pads = _ports(modules["pads_0"])
    for name in ("swclk", "swdio_out", "swdio_oe", "swdio_in"):
        _need(swd.get(name) is not None and swd.get(name) == pads.get(name),
              "HWH_SWD_PAD_WIRING_MISMATCH")
    _need(swd.get("s_axi_aclk") == _ports(modules["ps7_0"]).get("FCLK_CLK0"),
          "HWH_CLOCK_MISMATCH")
    _need(swd.get("s_axi_aresetn") ==
          _ports(modules["rst_ps7_0_100M"]).get("peripheral_aresetn"),
          "HWH_RESET_MISMATCH")
    params = {p.get("NAME"): p.get("VALUE")
              for p in modules["swd_0"].iter("PARAMETER")}
    _need(_number(params.get("AXI_BASE_ADDRESS")) == BASE,
          "HWH_RTL_BASE_MISMATCH")
    return {"swd_axi_base": f"0x{BASE:08X}", "bytes": SIZE,
            "io": ["swclk_io", "swdio_io"], "hwh_source_check": "PASS",
            "bitstream_loaded": "NOT_RUN", "physical_swd": "NOT_RUN",
            "flash_programmed": "NOT_RUN"}


def inspect_files(hwh: Path, bit: Path) -> dict:
    _need(hwh.is_file() and bit.is_file() and
          hwh.stat().st_size > 0 and bit.stat().st_size > 0,
          "BIT_OR_HWH_MISSING")
    result = verify_hwh_xml(hwh.read_text())
    result["hwh_sha256"] = hashlib.sha256(hwh.read_bytes()).hexdigest()
    result["bit_sha256"] = hashlib.sha256(bit.read_bytes()).hexdigest()
    result["restorable_original_bit_sha256"] = "NOT_PROVIDED"
    result["runtime_admitted"] = False
    result["gate_2_ready"] = False
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hwh", type=Path, required=True)
    p.add_argument("--bit", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(inspect_files(args.hwh, args.bit),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
