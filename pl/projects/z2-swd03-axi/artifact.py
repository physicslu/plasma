#!/usr/bin/env python3
"""SWD-03 isolated Vivado artifact checks; NEVER programs FPGA or DUT."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

PL = Path(__file__).resolve().parents[2]
BASELINE_PATH = PL / "projects/z2-control-waveform/artifact.py"
spec = importlib.util.spec_from_file_location("swd03_retained_baseline", BASELINE_PATH)
assert spec and spec.loader
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
shared = baseline.shared

MAP = {**baseline.MAP, "transaction_0": 0x40003000}
PROJECT = "z2_swd03_axi"
STEM = "plasma-z2-swd03-axi-fixture"


def prepare(build: Path, version: str) -> None:
    baseline.prepare(build, version)
    path = build / "generated/build-identity.json"
    metadata = json.loads(path.read_text())
    metadata.update(
        design_variant="swd03_axi_internal_dpidr_fixture",
        capabilities=[
            "axi_control_loopback",
            "swd_waveform_digital",
            "swd_transaction_digital",
            "internal_synthetic_dpidr_only",
        ],
        capability_flags=0,
        external_pl_io=False,
        swd_transaction_abi_version=1,
        internal_test_fixture="synthetic_dpidr_only",
        hardware_runtime_ready=False,
        physical_programming_qualified=False,
        target_programming_qualified=False,
    )
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def _ports(module: ET.Element) -> dict[str, str | None]:
    return {p.get("NAME"): p.get("SIGNAME") for p in module.iter("PORT")}


def verify_hwh(path: Path) -> dict:
    # Enforce the full *original* three-aperture and clock/reset/PS contract.
    result = baseline.verify_hwh(path)
    root = ET.parse(path).getroot()
    modules = {m.get("INSTANCE"): m for m in root.iter("MODULE")}
    txn = modules["transaction_0"]
    fixture = modules["fixture_0"]
    base = MAP["transaction_0"]
    params = {p.get("NAME"): p.get("VALUE") for p in txn.iter("PARAMETER")}
    if baseline.number(params["AXI_BASE_ADDRESS"]) != base:
        raise ValueError("SWD-03 decoder/segment mismatch")

    ranges = [x for x in root.iter("MEMRANGE")
              if x.get("INSTANCE") == "transaction_0"]
    if len(ranges) != 1:
        raise ValueError("Missing or duplicate SWD-03 AXI range")
    rng = ranges[0]
    if (baseline.number(rng.get("BASEVALUE")) != base
            or baseline.number(rng.get("HIGHVALUE")) != base + 4095
            or rng.get("MASTERBUSINTERFACE") != "M_AXI_GP0"):
        raise ValueError("SWD-03 expected GP0 4KiB AXI range")

    master_ranges = [x for x in root.iter("MEMRANGE")
                     if x.get("MASTERBUSINTERFACE") == "M_AXI_GP0"]
    if len(master_ranges) != 4 or {x.get("INSTANCE") for x in master_ranges} != set(MAP):
        raise ValueError("Expected exactly four non-overlapping GP0 apertures")
    if any(x.get("INSTANCE") == "fixture_0" for x in root.iter("MEMRANGE")):
        raise ValueError("Fixture must not expose its own MMIO aperture")

    ap = _ports(txn)
    fp = _ports(fixture)
    if ap.get("s_axi_aclk") != "ps7_0_FCLK_CLK0":
        raise ValueError("SWD-03 clock is not FCLK0")
    if ap.get("s_axi_aresetn") != "rst_ps7_0_100M_peripheral_aresetn":
        raise ValueError("SWD-03 clock-domain reset mismatch")
    if fp.get("clk") != "ps7_0_FCLK_CLK0":
        raise ValueError("Fixture is not on FCLK0")
    if fp.get("rst_n") != "rst_ps7_0_100M_peripheral_aresetn":
        raise ValueError("Fixture reset is not synchronized")
    for a, b in [
        ("swclk", "swclk"),
        ("swdio_out", "host_out"),
        ("swdio_oe", "host_oe"),
        ("swdio_in", "swdio_in"),
    ]:
        if not ap.get(a) or not fp.get(b) or ap[a] != fp[b]:
            raise ValueError("Internal SWD-03/fixture wiring mismatch: " + a)

    result["transaction_0"] = {"base_address": f"0x{base:08X}", "segment_size_bytes": 4096}
    return result


def _require_pass(path: Path, minimum: int) -> None:
    data = path.read_text()
    if "failed" in data.lower() or "error" in data.lower():
        raise ValueError("Host regression contains an error: " + str(path))
    matches = re.findall(r"\b(\d+) passed\b", data)
    if not matches or max(map(int, matches)) < minimum:
        raise ValueError("Missing required regression count: " + str(path))


def finalize(build: Path, version: str) -> None:
    metadata = json.loads((build / "generated/build-identity.json").read_text())
    if metadata["source_git_sha"] != shared._commit():
        raise ValueError("Source changed after prepare")
    if version != "2026.1":
        raise ValueError("SWD-03 baseline requires Vivado 2026.1")
    logs = build / "logs"
    _require_pass(logs / "legacy-regression.log", 3)
    _require_pass(logs / "host-regression.log", 4)
    _require_pass(logs / "artifact-regression.log", 10)
    vivado = (logs / "vivado-console.log").read_text()
    if ("SWD03_BITSTREAM_BUILD_PASS\n" not in vivado
            or "SWD03_IMPLEMENTED_TIMING_PASS setup=" not in vivado):
        raise ValueError("Missing Vivado implemented timing evidence")
    if "CRITICAL WARNING:" in vivado or "ERROR:" in vivado:
        raise ValueError("Critical/error Vivado console message")
    project = build / "project"
    for run_log in project.glob("*.runs/*/runme.log"):
        data = run_log.read_text(errors="replace")
        if "CRITICAL WARNING:" in data or "ERROR:" in data:
            raise ValueError("Critical/error child run: " + str(run_log))
    match = re.search(
        r"^SWD03_IMPLEMENTED_TIMING_PASS setup=(-?[\d.]+) hold=(-?[\d.]+)$",
        vivado, re.MULTILINE,
    )
    if not match:
        raise ValueError("Missing numerical setup/hold slack evidence")
    setup, hold = (float(match[1]), float(match[2]))
    if not all(math.isfinite(v) and v >= 0 for v in (setup, hold)):
        raise ValueError("Timing not met")

    bit = project / f"{PROJECT}.runs/impl_1/system_wrapper.bit"
    hwh = project / f"{PROJECT}.gen/sources_1/bd/system/hw_handoff/system.hwh"
    if not bit.is_file() or bit.stat().st_size == 0:
        raise ValueError("Missing/nonempty implemented bitstream")
    if not hwh.is_file() or hwh.stat().st_size == 0:
        raise ValueError("Missing/nonempty hardware handoff")
    metadata["axi_address_map"] = verify_hwh(hwh)

    lines = (build / "generated/axi-address-map.txt").read_text().splitlines()
    if len(lines) != len(MAP):
        raise ValueError("Tcl must export exactly four AXI mappings")
    seen = set()
    for line in lines:
        instance, addr, size = line.split()
        if (instance in seen or instance not in MAP
                or int(addr, 0) != MAP[instance] or int(size, 0) != 4096):
            raise ValueError("Tcl and HWH map disagree")
        seen.add(instance)
    if seen != set(MAP):
        raise ValueError("Incomplete AXI address map")

    reports = [build / "reports" / f for f in (
        "timing_summary.rpt", "drc.rpt", "methodology.rpt",
        "utilization.rpt", "check_timing.rpt",
    )]
    for report in reports:
        if not report.is_file() or report.stat().st_size == 0:
            raise ValueError("Missing/empty report: " + str(report))
    artifacts = build / "artifacts"
    artifacts.mkdir(exist_ok=False)
    for key, source, suffix in [
        ("bitstream", bit, "bit"), ("hwh", hwh, "hwh"),
    ]:
        dst = artifacts / f"{STEM}-{metadata['bitstream_version']}.{suffix}"
        shutil.copyfile(source, dst)
        digest = shared._digest(dst)
        metadata[f"{key}_file"] = dst.name
        metadata[f"{key}_sha256"] = digest
        (artifacts / f"{dst.name}.sha256").write_text(
            f"{digest}  {dst.name}\n")
    evidence_paths = [
        logs / "legacy-regression.log",
        logs / "host-regression.log",
        logs / "artifact-regression.log",
        logs / "vivado-console.log",
        *reports,
    ]
    metadata.update(
        toolchain={"name": "Vivado", "version": version},
        acceptance={
            "SWD03_HOST_RTL": "PASS",
            "SWD03_IMPLEMENTED_HOST": "PASS",
            "Z2_HIL": "NOT_RUN",
            "physical_swd": "NOT_RUN",
            "real_ic_programming": "NOT_RUN",
        },
        implemented_slack_ns={"setup": setup, "hold": hold},
        evidence_sha256={
            str(p.relative_to(build)): shared._digest(p) for p in evidence_paths
        },
        physical_programming_qualified=False,
        hardware_runtime_ready=False,
        loading_safety="NOT_QUALIFIED",
        baseline_retention="Preserve entire uniquely named run; never overwrite prior baseline",
    )
    manifest = artifacts / "manifest.json"
    manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    (artifacts / "manifest.json.sha256").write_text(
        f"{shared._digest(manifest)}  manifest.json\n")
    print("SWD03_ARTIFACT_PASS", artifacts)


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
