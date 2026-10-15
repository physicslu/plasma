"""SWD-04 read-only Z2 inventory collector, with fake sysfs support.

No FPGA manager writes, memory mapping, service changes, GPIO access or network
requests. Captures only the minimum source-of-truth data for P0 review.
Live use is deferred to the approved post-merge HIL maintenance window.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

from pl.hil.swd04.contract import REQUIRED_SERVICES, SafetyError, sha256_file


def fclk0_from_summary(text: str) -> int:
    """Linux common-clock clk_summary has name + 3 counters + rate."""
    rates = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[0].lower() in {
            "fclk0", "fclk_clk0", "fclk0_clk",
        }:
            if all(re.fullmatch(r"\d+", f) for f in fields[1:5]):
                rates.append(int(fields[4]))
    if len(rates) != 1:
        raise SafetyError("Missing or ambiguous FCLK0 clock-summary rate")
    return rates[0]


def _text(path: Path) -> str:
    return path.read_bytes().replace(b"\x00", b"").decode("utf-8").strip()


def collect(*, sysroot: Path, device_tree: Path, clock_summary: Path,
            metadata_path: Path,
            service_status, architecture: str,
            pynq_version: str) -> dict[str, object]:
    manager = _text(sysroot / "class/fpga_manager/fpga0/state")
    model = _text(device_tree / "model")
    clock = fclk0_from_summary(clock_summary.read_text())
    uios = []
    for entry in sorted((sysroot / "class/uio").glob("uio[0-9]*")):
        name = _text(entry / "name")
        maps = sorted((entry / "maps").glob("map[0-9]*"))
        if len(maps) != 1:
            raise SafetyError("Unexpected UIO map count: " + name)
        addr = int(_text(maps[0] / "addr"), 0)
        size = int(_text(maps[0] / "size"), 0)
        uios.append({
            "name": name,
            "address": f"0x{addr:08X}",
            "size": f"0x{size:08X}",
        })
    return {
        "architecture": architecture,
        "pynq_version": pynq_version,
        "fpga_manager_state": manager,
        "fclk0_hz": clock,
        "metadata_sha256": sha256_file(metadata_path),
        "sysfs_read_only": True,
        "device_model_confirmed": (
            "pynq-z2" in model.lower() or "pynq z2" in model.lower()
        ),
        "services": {name: service_status(name) for name in REQUIRED_SERVICES},
        "uio": uios,
        "pl_consumer_exclusivity": "UNVERIFIED_REQUIRES_OPERATOR_ATTESTATION",
    }


def systemctl_status(name: str) -> str:
    try:
        process = subprocess.run(
            ["systemctl", "is-active", "--", name],
            check=False, capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return process.stdout.strip() if process.returncode == 0 else "unknown"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sysroot", type=Path, default=Path("/sys"))
    p.add_argument("--device-tree", type=Path, default=Path("/proc/device-tree"))
    p.add_argument("--clock-summary", type=Path,
                   default=Path("/sys/kernel/debug/clk/clk_summary"))
    p.add_argument("--metadata-file", type=Path, required=True,
                   help="Current original PYNQ overlay metadata for hash only")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists():
        print("SWD04_COLLECT_NO_GO: Refuse overwrite", file=sys.stderr)
        return 2
    try:
        try:
            pynq = importlib.metadata.version("pynq")
        except importlib.metadata.PackageNotFoundError:
            pynq = "unknown"
        report = collect(
            sysroot=args.sysroot,
            device_tree=args.device_tree,
            clock_summary=args.clock_summary,
            metadata_path=args.metadata_file,
            service_status=systemctl_status,
            architecture=platform.machine(),
            pynq_version=pynq,
        )
        with args.output.open("x") as f:
            json.dump(report, f, indent=2, sort_keys=True)
            f.write("\n")
    except (OSError, ValueError, SafetyError) as exc:
        print("SWD04_COLLECT_NO_GO: " + str(exc), file=sys.stderr)
        return 2
    print("SWD04_READ_ONLY_INVENTORY_COLLECTED_NO_GO_UNTIL_ATTESTATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
