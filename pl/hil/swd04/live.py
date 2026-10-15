"""SWD-04 *post-merge only* live MMIO harness.

This command is deliberately inert without explicit live flags and a matching
operator session, preflight and candidate BIN. It never loads firmware, stops
services, rebinds drivers or restores an overlay. Those remain independently
supervised maintenance operations. A hung AXI MMIO access can hang Linux; Python
timeouts and subprocess timeouts do not make that safe.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import mmap
import os
from pathlib import Path
import platform
import re
import struct
import sys

from pl.hil.swd04 import contract as c
from pl.hil.swd04 import mmio_contract as m


class DevMemBackend:
    """Map only four known PS GP0 4KiB apertures; RO mode for HIL-01."""

    def __init__(self, *, readonly: bool) -> None:
        self.readonly = readonly
        self.fd = None
        self.pages: dict[int, mmap.mmap] = {}

    def __enter__(self):
        flags = os.O_RDONLY if self.readonly else os.O_RDWR
        self.fd = os.open("/dev/mem", flags | os.O_SYNC)
        return self

    def __exit__(self, *_):
        for page in self.pages.values():
            page.close()
        self.pages.clear()
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _page(self, address: int, *, write: bool) -> tuple[mmap.mmap, int]:
        if address & 3:
            raise c.SafetyError("Unaligned MMIO access")
        if write and self.readonly:
            raise c.SafetyError("Write forbidden in HIL-01")
        base = address & ~(c.SEGMENT_SIZE - 1)
        if base not in c.AXI_BASES.values():
            raise c.SafetyError("Outside four reviewed AXI apertures")
        if self.fd is None:
            raise c.SafetyError("MMIO backend not entered")
        if base not in self.pages:
            prot = mmap.PROT_READ | (0 if self.readonly else mmap.PROT_WRITE)
            self.pages[base] = mmap.mmap(
                self.fd, c.SEGMENT_SIZE, flags=mmap.MAP_SHARED,
                prot=prot, offset=base,
            )
        return self.pages[base], address - base

    def read32(self, address: int) -> int:
        if address not in c.READ_WHITELIST:
            raise c.SafetyError("Backend denied unlisted MMIO read")
        page, offset = self._page(address, write=False)
        return struct.unpack_from("<I", page, offset)[0]

    def write32(self, address: int, value: int) -> None:
        if address not in c.WRITE_WHITELIST:
            raise c.SafetyError("Backend denied unlisted MMIO write")
        page, offset = self._page(address, write=True)
        struct.pack_into("<I", page, offset, value)


def require_live_session(*, phase: str, p0: Path, session: Path,
                         candidate_bin: Path, previous: Path | None) -> None:
    """Checks before opening /dev/mem. Session fields are operator assertions."""
    if os.geteuid() != 0 or platform.machine() != "armv7l":
        raise c.SafetyError("Live HIL requires authorized root on ARMv7 Z2")
    if Path("/sys/class/fpga_manager/fpga0/state").read_text().strip() != "operating":
        raise c.SafetyError("FPGA Manager is not operating")
    if not Path("/dev/mem").is_char_device():
        raise c.SafetyError("Missing real /dev/mem character device")
    evidence = json.loads(p0.read_text())
    record = json.loads(session.read_text())
    if type(evidence) is not dict or type(record) is not dict:
        raise c.SafetyError("Preflight/session JSON must be objects")
    if (evidence.get("preflight") != "PASS"
            or evidence.get("candidate_source") != c.SOURCE_SHA
            or evidence.get("sha256", {}).get("bit") != c.BIT_SHA256
            or evidence.get("sha256", {}).get("hwh") != c.HWH_SHA256
            or evidence.get("sha256", {}).get("recovery_bin") != c.RECOVERY_BIN_SHA256):
        raise c.SafetyError("P0 evidence not bound to approved build and recovery")
    required = (
        "confirmed_after_gate2_merge",
        "live_fpga_manager_load_supervised",
        "candidate_bitstream_loaded_and_verified",
        "original_services_quiesced_for_pl_access",
        "all_prior_pl_consumers_isolated",
        "uios_unbound_or_ownership_reconciled",
        "uart_console_verified",
        "independent_power_recovery_verified",
        "no_external_dut_connected",
        "operator_present_at_console",
        "original_metadata_backup_verified",
    )
    if any(record.get(field) is not True for field in required):
        raise c.SafetyError("Live maintenance/ownership/operator prerequisite missing")
    if record.get("stage") != phase:
        raise c.SafetyError("Live session not issued for requested stage")
    if (record.get("candidate_source") != c.SOURCE_SHA
            or record.get("candidate_bit_sha256") != c.BIT_SHA256
            or record.get("candidate_hwh_sha256") != c.HWH_SHA256
            or record.get("recovery_bin_sha256") != c.RECOVERY_BIN_SHA256
            or record.get("p0_sha256") != c.sha256_file(p0)):
        raise c.SafetyError("Session identity mismatch")
    if not candidate_bin.is_file() or not re.fullmatch(
        r"[a-f0-9]{64}", str(record.get("candidate_bin_sha256", ""))
    ):
        raise c.SafetyError("Missing bound converted candidate firmware")
    if c.sha256_file(candidate_bin) != record["candidate_bin_sha256"]:
        raise c.SafetyError("Converted firmware digest mismatch")
    if not re.fullmatch(
        r"[a-f0-9]{64}", str(record.get("supervised_load_log_sha256", ""))
    ):
        raise c.SafetyError("Missing supervised loading evidence digest")
    if phase == "HIL01" and previous is not None:
        raise c.SafetyError("Unexpected previous stage for HIL01")
    if phase in {"HIL02", "HIL03"}:
        if previous is None:
            raise c.SafetyError("Previous stage evidence required")
        prior = json.loads(previous.read_text())
        if (prior.get("qualification") != "SWD-04"
                or prior.get("result") != "PASS"
                or prior.get("stage") != ("HIL01" if phase == "HIL02" else "HIL02")
                or prior.get("source_git_sha") != c.SOURCE_SHA
                or prior.get("candidate_bin_sha256") != record["candidate_bin_sha256"]):
            raise c.SafetyError("Previous stage evidence not accepted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("HIL01", "HIL02", "HIL03"), required=True)
    parser.add_argument("--p0-report", type=Path, required=True)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--candidate-bin", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--ack-unrecoverable-axi-stall-risk", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute_live or not args.ack_unrecoverable_axi_stall_risk:
        print("SWD04_LIVE_NO_GO: default is INERT; two explicit live flags required",
              file=sys.stderr)
        return 2
    if args.output.exists():
        print("SWD04_LIVE_NO_GO: evidence output already exists", file=sys.stderr)
        return 2

    try:
        require_live_session(
            phase=args.stage, p0=args.p0_report, session=args.session,
            candidate_bin=args.candidate_bin, previous=args.previous,
        )
    except (OSError, ValueError, KeyError, c.SafetyError) as exc:
        print("SWD04_LIVE_NO_GO: " + str(exc), file=sys.stderr)
        return 2

    # There is no automatic resume, reset, unload or rollback on error:
    # an AXI stall may leave the kernel unable to process recovery commands.
    try:
        with DevMemBackend(readonly=args.stage == "HIL01") as hw:
            io = m.RestrictedMMIO(hw)
            if args.stage == "HIL01":
                result = m.hil01_registers(io)
            elif args.stage == "HIL02":
                result = m.hil02_dpidr(io)
            else:
                result = m.hil03_recovery(io)
        record = {
            "qualification": "SWD-04",
            "stage": args.stage,
            "result": "PASS",
            "source_git_sha": c.SOURCE_SHA,
            "candidate_bin_sha256": c.sha256_file(args.candidate_bin),
            "utc_finished": datetime.now(timezone.utc).isoformat(),
            "observations": result,
            "mmio_ops": len(io.audit),
            "mmio_audit": [
                {"op": op, "address": f"0x{address:08X}",
                 "value": f"0x{value:08X}"}
                for op, address, value in io.audit
            ],
            "physical_swd": "NOT_RUN",
            "real_ic_programming": "NOT_RUN",
            "recovery_restoration": "NOT_RUN",
        }
        with args.output.open("x") as f:
            json.dump(record, f, indent=2, sort_keys=True)
            f.write("\n")
    except (OSError, ValueError, c.SafetyError) as exc:
        print("SWD04_LIVE_STOP: " + str(exc), file=sys.stderr)
        print("Do not issue more AXI accesses; follow supervised base restoration",
              file=sys.stderr)
        return 2
    print("SWD04_" + args.stage + "_PS_AXI_PL_PASS_RECOVERY_STILL_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
