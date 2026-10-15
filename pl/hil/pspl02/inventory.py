"""Read-only privileged snapshot. Never opens MMIO, imports PYNQ or changes state.

Backups must already exist. Unknown/unreadable facts remain explicit NO-GO.
Run before loading and after base restoration; output is private evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import platform
import sys

from pl.hil.pspl02 import contract as c
from pl.hil.swd04.collect import collect, systemctl_status


def metadata_hashes(directory: Path):
    paths = sorted(directory.glob("global_pl_state_*.json"))
    if (directory/"_current_metadata.pkl").is_file():
        paths.append(directory/"_current_metadata.pkl")
    c._require(bool(paths), "No original PYNQ metadata files")
    return {p.name: c.sha256_file(p) for p in paths}


def process_users(procroot: Path = Path("/proc")):
    hits, errors = [], []
    targets = ("/dev/mem", "/dev/uio", "/dev/dri", "/dev/xlnk", "/dev/xdevcfg", "/dev/dma_heap")
    for proc in procroot.iterdir():
        if not proc.name.isdigit():
            continue
        try:
            for fd in (proc/"fd").iterdir():
                try:
                    link = os.readlink(fd)
                except FileNotFoundError:
                    continue
                if link.startswith(targets):
                    hits.append({"pid": proc.name, "kind": "fd", "device": link})
            for line in (proc/"maps").read_text().splitlines():
                if any(t in line for t in targets):
                    hits.append({"pid": proc.name, "kind": "mmap", "mapping": line})
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append({"pid": proc.name, "error": str(exc)})
    return hits, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-dir", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        c._require(not args.output.exists(), "Refuse overwrite")
        c._require(os.geteuid() == 0, "Root required for complete clock/process inventory")
        metadata = metadata_hashes(args.metadata_dir)
        backup = metadata_hashes(args.backup_dir)
        c._require(args.metadata_dir.resolve() != args.backup_dir.resolve(), "Backup must be independent")
        clock = Path("/sys/kernel/debug/clk/clk_summary")
        report = collect(sysroot=Path("/sys"), device_tree=Path("/proc/device-tree"),
                         clock_summary=clock, metadata_path=args.metadata_dir/next(iter(metadata)),
                         service_status=systemctl_status, architecture=platform.machine(),
                         pynq_version=importlib.metadata.version("pynq"))
        rows = [line.split() for line in clock.read_text().splitlines()
                if line.split() and line.split()[0].lower() in {"fclk0", "fclk_clk0", "fclk0_clk"}]
        hits, errors = process_users()
        bindings = {}
        for device in ("40000000.fabric", "43c00000.audio-codec-ctrl"):
            driver = Path("/sys/bus/platform/devices")/device/"driver"
            bindings[device] = driver.resolve().name if driver.exists() else None
        report.update(observed_utc=datetime.now(timezone.utc).isoformat(), root_audit_complete=not errors, pl_users=hits,
                      audit_errors=errors, fclk0_enabled=len(rows) == 1 and int(rows[0][2]) > 0,
                      metadata_sha256=metadata, metadata_backup_matches=metadata == backup,
                      driver_bindings=bindings,
                      original_drivers_reviewed=False)
        # Never manufacture operator review of drivers/other consumers.
        c.write_record(args.output, report)
    except (OSError, ValueError, c.SafetyError, importlib.metadata.PackageNotFoundError) as exc:
        print("PSPL02_INVENTORY_NO_GO: " + str(exc), file=sys.stderr)
        return 2
    print("PSPL02_READ_ONLY_SNAPSHOT_REQUIRES_INDEPENDENT_OPERATOR_REVIEW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
