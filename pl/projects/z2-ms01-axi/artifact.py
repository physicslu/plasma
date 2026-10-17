#!/usr/bin/env python3
"""Independent MS01 dual-LT02 image checks, inheriting reviewed LT02 gates.

Host-side only: never accesses /dev/mem or programs PYNQ-Z2.
The source image is a NEW six-aperture build, not the five-aperture LT02 HIL.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "z2-lt02-axi/artifact.py"
spec = importlib.util.spec_from_file_location("ms01_retained_lt02_checks", SRC)
assert spec and spec.loader
lt02 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lt02)

MAP = {**lt02.MAP, "lt02_1": 0x40005000}
SITE_BASES = {1: MAP["lt02_0"], 2: MAP["lt02_1"]}
lt02.MAP = MAP
lt02.PROJECT = "z2_ms01_axi"
lt02.STEM = "plasma-z2-ms01-dual-site"


def _params(module: ET.Element) -> dict[str, str]:
    return {x.get("NAME"): x.get("VALUE") for x in module.iter("PARAMETER")}


def verify_hwh(path: Path) -> dict:
    """Independently verify all six nonoverlapping GP0 address ranges."""
    result = lt02.baseline.verify_hwh(path)
    root = ET.parse(path).getroot()
    modules = {m.get("INSTANCE"): m for m in root.iter("MODULE")}
    ranges = [r for r in root.iter("MEMRANGE")
              if r.get("MASTERBUSINTERFACE") == "M_AXI_GP0"]
    if (len(ranges) != 6 or {r.get("INSTANCE") for r in ranges} != set(MAP)):
        raise ValueError("MS01 requires exactly six disjoint GP0 apertures")
    for instance, base in MAP.items():
        if instance not in modules:
            raise ValueError("Missing hardware module: " + instance)
        address = [r for r in ranges if r.get("INSTANCE") == instance]
        if len(address) != 1:
            raise ValueError("Duplicated or missing address range: " + instance)
        r = address[0]
        if (lt02.baseline.number(r.get("BASEVALUE")) != base or
                lt02.baseline.number(r.get("HIGHVALUE")) != base + 4095):
            raise ValueError("MS01 MMIO aperture mismatch: " + instance)
        if instance in {"transaction_0", "lt02_0", "lt02_1"}:
            params = _params(modules[instance])
            if lt02.baseline.number(params["AXI_BASE_ADDRESS"]) != base:
                raise ValueError("MS01 RTL decoder mismatches GP0: " + instance)
        result[instance] = {
            "base_address": f"0x{base:08X}",
            "segment_size_bytes": 4096,
        }
    txn, fixture = modules["transaction_0"], modules["fixture_0"]
    transaction_ports = lt02._ports(txn)
    fixture_ports = lt02._ports(fixture)
    for a, b in (
        ("swclk", "swclk"),
        ("swdio_out", "host_out"),
        ("swdio_oe", "host_oe"),
        ("swdio_in", "swdio_in"),
    ):
        if not transaction_ports.get(a) or transaction_ports[a] != fixture_ports.get(b):
            raise ValueError("Internal DPIDR fixture wiring mismatch: " + a)
    if (fixture_ports.get("clk") != "ps7_0_FCLK_CLK0" or
            fixture_ports.get("rst_n") !=
            "rst_ps7_0_100M_peripheral_aresetn"):
        raise ValueError("Internal fixture reset/clock drift")
    for instance in ("lt02_0", "lt02_1"):
        ports = lt02._ports(modules[instance])
        if (ports.get("s_axi_aclk") != "ps7_0_FCLK_CLK0" or
                ports.get("s_axi_aresetn") !=
                "rst_ps7_0_100M_peripheral_aresetn"):
            raise ValueError("Site clock/reset mismatch: " + instance)
    if any(r.get("INSTANCE") == "fixture_0" for r in root.iter("MEMRANGE")):
        raise ValueError("Fixture cannot expose its own GP0 address")
    return result


# The stable LT02 finalized-artifact gates call these module globals by name;
# rebind only in this dedicated import instance, never the tracked LT02 source.
lt02.verify_hwh = verify_hwh


def prepare(build: Path, version: str) -> None:
    lt02.prepare(build, version)
    path = build / "generated/build-identity.json"
    data = json.loads(path.read_text())
    data.update(
        design_variant="ms01_dual_lt02_internal_dpidr_fixture",
        lt02_site_count=2,
        lt02_sites=[
            {"site_id": site, "base_address": f"0x{base:08X}",
             "scratchpad_bytes": 2048}
            for site, base in SITE_BASES.items()
        ],
        physical_programming_qualified=False,
        external_pl_io=False,
        hardware_runtime_ready=False,
    )
    data["capabilities"] = [
        x for x in data["capabilities"]
        if x != "lt02_2k_scratchpad_internal_only"
    ] + ["dual_lt02_2k_scratchpad_internal_only"]
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def finalize(build: Path, version: str) -> None:
    lt02.finalize(build, version)
    manifest = build / "artifacts/manifest.json"
    data = json.loads(manifest.read_text())
    if data["design_variant"] != "ms01_dual_lt02_internal_dpidr_fixture":
        raise ValueError("Wrong MS01 identity")
    if data["lt02_site_count"] != 2:
        raise ValueError("Dual-site manifest missing")
    if set(data["axi_address_map"]) != set(MAP):
        raise ValueError("Six-site manifest map drift")
    print("MS01_DUAL_SITE_HOST_ARTIFACT_PASS_NO_REAL_Z2_CLAIM")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "finalize"))
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.build.resolve(), args.version)
    else:
        finalize(args.build.resolve(), args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
