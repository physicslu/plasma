"""PSPL-02 offline verification and inert-by-default live MMIO CLI.

Never loads firmware, changes drivers/metadata, stops/restarts services or
operates power. Supervised loading/recovery are separate steps in the runbook.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import mmap
import os
from pathlib import Path
import platform
import struct
import sys

from pl.hil.pspl02 import contract as c, mmio as m
from pl.hil.pspl02 import identity
from pl.hil.swd04.collect import fclk0_from_summary, systemctl_status


def utc():
    return datetime.now(timezone.utc).isoformat()


def require_session(p0: Path, session: Path, stage: str, previous: Path | None):
    proof, record = c.json_object(p0), c.json_object(session)
    c._require(proof.get("qualification") == "PSPL-02/SWD-00"
               and proof.get("preflight") == "PASS" and proof.get("sha256") == c.HASHES,
               "Preflight not bound to reviewed baseline/recovery")
    profile = proof.get("profile", "qualification")
    c.preflight(proof.get("inventory", {}), proof.get("attestation", {}), profile=profile)
    if profile == "development":
        c._require(stage in c.DEVELOPMENT_STAGES,
                   "Development mode excludes ERROR/RESET due to AXI-stall recovery risk")
    c._require(record.get("board_identity_sha256") == identity.digest_report(
        proof["inventory"]["board_identity"]), "Session board identity mismatch")
    c._require(record.get("stage") == stage and record.get("p0_sha256") == c.sha256_file(p0),
               "Session stage/preflight mismatch")
    c.require_fresh(record.get("observed_utc"))
    session_required = (
        "candidate_loaded_and_verified", "original_uios_unbound",
        "kernel_and_clocks_reviewed_after_load",
        "no_shared_service_changes", "no_asynchronous_pl_reconfiguration",
    )
    if profile == "qualification":
        session_required += (
            "uart_login_verified_now", "independent_power_recovery_ready",
            "operator_present",
        )
    for key in session_required:
        c._require(record.get(key) is True, "Missing current observation: " + key)
    load_log = Path(record.get("load_log", ""))
    c._require(load_log.is_file() and load_log.stat().st_size > 0
               and record.get("load_log_sha256") == c.sha256_file(load_log),
               "Actual supervised load log required")
    index = c.STAGES.index(stage)
    if index == 0:
        c._require(previous is None, "Unexpected predecessor")
    else:
        c._require(previous is not None, "Missing preceding stage")
        prior = c.json_object(previous)
        c._require(prior.get("qualification") == "PSPL-02/SWD-00"
                   and prior.get("stage") == c.STAGES[index-1] and prior.get("result") == "PASS"
                   and prior.get("p0_sha256") == c.sha256_file(p0)
                   and prior.get("load_log_sha256") == c.sha256_file(load_log)
                   and prior.get("sha256") == c.HASHES, "Invalid preceding stage")
    record["profile"] = profile
    return record


def runtime_audit(session: dict, *, board_options=None):
    """Recheck privileged facts before opening /dev/mem; no PL register access."""
    c._require(os.geteuid() == 0 and platform.machine() == "armv7l", "Requires root on Z2")
    state = Path("/sys/class/fpga_manager/fpga0/state").read_text().strip()
    c._require(state == "operating", "FPGA not operating")
    board = identity.verify(**(board_options or {}))
    c._require(identity.digest_report(board) == session.get("board_identity_sha256"),
               "Current board identity differs from preflight/session")
    summary = Path("/sys/kernel/debug/clk/clk_summary").read_text()
    c._require(fclk0_from_summary(summary) == 100_000_000, "FCLK0 mismatch")
    rows = [line.split() for line in summary.splitlines()
            if line.split() and line.split()[0].lower() in {"fclk0", "fclk_clk0", "fclk0_clk"}]
    c._require(len(rows) == 1 and int(rows[0][2]) > 0, "FCLK0 disabled")
    for device in ("40000000.fabric", "43c00000.audio-codec-ctrl"):
        c._require(not (Path("/sys/bus/platform/devices")/device/"driver").exists(),
                   "Original UIO driver still bound")
    c._require({s: systemctl_status(s) for s in c.SERVICES} == dict.fromkeys(c.SERVICES, "active"),
               "Shared service state changed")
    metadata, backup = Path(session.get("metadata_file", "")), Path(session.get("metadata_backup", ""))
    c._require(metadata.is_file() and backup.is_file()
               and c.sha256_file(metadata) == c.sha256_file(backup)
               == session.get("metadata_sha256"), "Metadata/backup mismatch")
    from pl.hil.pspl02.inventory import process_users, metadata_hashes
    hits, errors = process_users()
    c._require(not hits and not errors, "PL consumers or incomplete process audit")
    # Check every retained PYNQ state file, not only the selected metadata file.
    c._require(metadata.parent.resolve() != backup.parent.resolve()
               and metadata_hashes(metadata.parent) == metadata_hashes(backup.parent),
               "PYNQ metadata set/backup mismatch")


class DevMem:
    def __init__(self, readonly):
        self.readonly, self.pages, self.fd = readonly, {}, None

    def __enter__(self):
        c._require(Path("/dev/mem").is_char_device(), "No real /dev/mem")
        self.fd = os.open("/dev/mem", (os.O_RDONLY if self.readonly else os.O_RDWR) | os.O_SYNC)
        return self

    def __exit__(self, *_):
        for page in self.pages.values():
            page.close()
        if self.fd is not None:
            os.close(self.fd)

    def page(self, address):
        c._require(type(address) is int and address in m.READS | m.WRITES, "Unlisted address")
        base = address & ~4095
        c._require(base in c.BASES.values() and self.fd is not None, "Outside reviewed apertures")
        if base not in self.pages:
            self.pages[base] = mmap.mmap(self.fd, 4096, flags=mmap.MAP_SHARED,
                                        prot=mmap.PROT_READ | (0 if self.readonly else mmap.PROT_WRITE),
                                        offset=base)
        return self.pages[base], address-base

    def read32(self, address):
        c._require(address in m.READS, "Unlisted read")
        page, offset = self.page(address)
        return struct.unpack_from("<I", page, offset)[0]

    def write32(self, address, value):
        c._require(not self.readonly and address in m.WRITES, "Unlisted write")
        page, offset = self.page(address)
        struct.pack_into("<I", page, offset, value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "preflight", "live"))
    parser.add_argument("--profile", choices=c.PROFILES, default="qualification",
                        help="Preflight mode; development allows only IDENTITY/PSPL02/SWD00")
    for key in c.HASHES:
        parser.add_argument("--" + key.replace(".", "-"), dest=key, type=Path, required=True)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--p0", type=Path)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--stage", choices=c.STAGES)
    parser.add_argument("--output", type=Path, required=True,
                        help="New JSON file, or new evidence directory for live")
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--ack-unrecoverable-axi-stall-risk", action="store_true")
    identity.add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        c._require(not args.output.exists(), "Refuse existing evidence output")
        if args.action == "live":
            c._require(args.execute_live and args.ack_unrecoverable_axi_stall_risk,
                       "Default INERT; explicit live flags required")
            c._require(args.p0 and args.session and args.stage, "Missing live evidence inputs")
        report = c.verify_artifacts({key: vars(args)[key] for key in c.HASHES})
        report["qualification"] = "PSPL-02/SWD-00"
        if args.action == "verify":
            c.write_record(args.output, report)
        elif args.action == "preflight":
            c._require(args.inventory and args.attestation, "Missing preflight inputs")
            inventory, attestation = c.json_object(args.inventory), c.json_object(args.attestation)
            c.preflight(inventory, attestation, profile=args.profile)
            report.update(profile=args.profile, preflight="PASS", inventory=inventory, attestation=attestation,
                          loading="NOT_RUN")
            c.write_record(args.output, report)
        else:
            record = require_session(args.p0, args.session, args.stage, args.previous)
            runtime_audit(record, board_options=identity.options(args))
            args.output.mkdir(exist_ok=False, mode=0o700)
            common = dict(qualification="PSPL-02/SWD-00", profile=record["profile"],
                          stage=args.stage, sha256=c.HASHES,
                          p0_sha256=c.sha256_file(args.p0), session_sha256=c.sha256_file(args.session),
                          load_log_sha256=record["load_log_sha256"], physical_swd="NOT_RUN",
                          ic_programming="NOT_RUN", restoration="NOT_RUN")
            c.write_record(args.output/"started.json", dict(common, utc_started=utc()))
            io = None
            try:
                with DevMem(readonly=args.stage == "IDENTITY") as hardware:
                    io = m.RestrictedMMIO(hardware, readonly=args.stage == "IDENTITY")
                    # Every process rechecks Identity before any write.
                    identity_result = m.identity(io)
                    observations = (m.RUNNERS[args.stage](io) if args.stage != "IDENTITY"
                                    else identity_result)
                result = dict(common, result="PASS", observations=observations)
            except (OSError, ValueError, c.SafetyError) as exc:
                # No extra MMIO/reset/retry on failure. SIGBUS/kernel stalls may
                # leave only started.json; absence of PASS always means STOP.
                result = dict(common, result="FAIL", error=str(exc))
            result.update(utc_finished=utc(), mmio_audit=[] if io is None else io.audit)
            c.write_record(args.output/"result.json", result)
            c._require(result["result"] == "PASS", "HIL failed; follow supervised base recovery")
        print("PSPL02_" + args.action.upper() + "_PASS_HARDWARE_RECOVERY_NOT_IMPLIED")
        return 0
    except (OSError, ValueError, TypeError, c.SafetyError) as exc:
        print("PSPL02_NO_GO: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
