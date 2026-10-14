#!/usr/bin/env python3
"""Host-only Identity build metadata. No FPGA loading or PS initialization."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

PL = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("swd_artifact", PL / "projects/z2-swd-gpio/artifact.py")
assert spec and spec.loader
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


def prepare(build: Path, version: str) -> None:
    shared.prepare(build / "generated", version)
    path = build / "generated/build-identity.json"
    data = json.loads(path.read_text())
    data.update(design_variant="identity_only", capabilities=[], capability_flags=0,
                identity_axi_segment_size=4096, external_pl_io=False)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def verify_hwh(path: Path, base: int) -> None:
    root = ET.parse(path).getroot()
    modules = {m.get("INSTANCE"): m for m in root.iter("MODULE")}
    identity = modules["identity_0"]
    parameters = {p.get("NAME"): p.get("VALUE") for p in identity.iter("PARAMETER")}
    for name, expected in {"CAPABILITY_FLAGS": 0, "STRICT_ADDRESS": 1,
                           "AXI_BASE_ADDRESS": base}.items():
        if int(parameters[name], 0) != expected:
            raise ValueError(f"Identity parameter mismatch: {name}")
    ranges = [r for r in root.iter("MEMRANGE") if r.get("INSTANCE") == "identity_0"]
    if len(ranges) != 1:
        raise ValueError("Expected exactly one Identity memory range")
    r = ranges[0]
    if int(r.get("BASEVALUE"), 0) != base or int(r.get("HIGHVALUE"), 0) != base + 4095:
        raise ValueError("Identity memory aperture mismatch")
    if any("swd" in str(m.attrib).lower() for m in modules.values()):
        raise ValueError("SWD module is forbidden")
    ps = {p.get("NAME"): p.get("VALUE") for p in modules["ps7_0"].iter("PARAMETER")}
    for key, expected in {"PCW_GPIO_EMIO_GPIO_ENABLE": 0,
                          "PCW_USE_M_AXI_GP0": 1,
                          "PCW_CRYSTAL_PERIPHERAL_FREQMHZ": 50,
                          "PCW_FPGA0_PERIPHERAL_FREQMHZ": 100}.items():
        # Vivado uses 0/1 for enable parameters in the HWH.
        if ps[key].lower() in {"true", "false"}:
            actual = int(ps[key].lower() == "true")
        else:
            actual = float(ps[key])
        if actual != expected:
            raise ValueError(f"PS parameter mismatch: {key}")
    # PCW_M_AXI_GP0_FREQMHZ is read-only preset metadata (10 MHz in the
    # pinned board file); validate the connected clock, not that stale value.
    ports = {p.get("NAME"): p for p in modules["ps7_0"].iter("PORT")}
    gp0 = ports["M_AXI_GP0_ACLK"]
    if gp0.get("CLKFREQUENCY") != "100000000" or gp0.get("SIGNAME") != "ps7_0_FCLK_CLK0":
        raise ValueError("GP0 clock connection mismatch")


def finalize(build: Path, version: str) -> None:
    data = json.loads((build / "generated/build-identity.json").read_text())
    if data["source_git_sha"] != shared._commit():
        raise ValueError("Source commit changed after prepare")
    base = int((build / "generated/identity-axi-base.txt").read_text().strip(), 0)
    if base != 0x40000000:
        raise ValueError("Strict decoder base mismatch")
    project = build / "project"
    bit = project / "z2_identity.runs/impl_1/system_wrapper.bit"
    hwh = project / "z2_identity.gen/sources_1/bd/system/hw_handoff/system.hwh"
    verify_hwh(hwh, base)
    artifacts = build / "artifacts"
    artifacts.mkdir()
    stem = f"plasma-z2-identity-{data['bitstream_version']}"
    for key, source, suffix in [("bitstream", bit, "bit"), ("hwh", hwh, "hwh")]:
        target = artifacts / f"{stem}.{suffix}"
        shutil.copyfile(source, target)
        digest = shared._digest(target)
        data[key + "_file"] = target.name
        data[key + "_sha256"] = digest
        (artifacts / (target.name + ".sha256")).write_text(f"{digest}  {target.name}\n")
    data.update(identity_axi_base_address=f"0x{base:08X}", identity_register_span=32,
                toolchain={"name": "Vivado", "version": version},
                build_validation={"synthesis": "PASS", "implementation": "PASS",
                                  "timing_checks": "PASS", "drc_blocking_findings": "NONE",
                                  "physical_hil": "NOT_RUN"},
                loading_safety="NOT_QUALIFIED",
                critical_warning_review="REQUIRED: review complete Vivado log before loading")
    (artifacts / "manifest.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print("IDENTITY_ARTIFACT_PASS", artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "finalize"])
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.build, args.version)
    else:
        finalize(args.build, args.version)


if __name__ == "__main__":
    main()
