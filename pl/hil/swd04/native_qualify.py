"""MMIO-13/14/15: explicitly armed PYNQ-Z2 native PLASMA-driver HIL.

Reuses the immutable SWD-04 candidate/recovery/session contract. The existing
SWD-04 HIL01 must pass before HIL02; no bitstream load or recovery occurs in
this program. Stages are strictly HIL01 (read-only Identity) and HIL02
(safe CONTROL echo + production SWD-05 synthetic DPIDR).

DEFAULT IS INERT. Never touch real /dev/mem except after an authorized loaded
candidate, exact runtime, supervised board isolation and two live flags.
Kernel AXI faults may SIGBUS or hang indefinitely; a Python timeout, SIGBUS
handler or try/except is not a recovery mechanism.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys

from pl.hil.swd04 import contract as c
from pl.hil.swd04 import mmio_contract as swd04
from pl.hil.swd04.live import require_live_session

from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOAperture, swd03_aperture
from plasma_interfaces.swd_transaction import SWDTransactionDriver


IDENTITY = c.AXI_BASES["identity_0"]
CONTROL = c.AXI_BASES["control_0"]
WAVEFORM = c.AXI_BASES["swd_0"]
TRANSACTION = c.AXI_BASES["transaction_0"]
EXPECTED_RUNTIME = Path("/opt/plasma/python/3.12.13")
CONTROL_PATTERNS = (0, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555, 0x12345678, 0)


def check_runtime(*, version=None, executable=None, machine=None, endian=None) -> None:
    """Reject wrong ABI before opening any MMIO mapping."""
    version = tuple(sys.version_info[:3]) if version is None else tuple(version)
    executable = sys.executable if executable is None else executable
    machine = platform.machine() if machine is None else machine
    endian = sys.byteorder if endian is None else endian
    c._require(version == (3, 12, 13), "PLASMA HIL requires exact CPython 3.12.13")
    c._require(machine == "armv7l" and endian == "little",
               "PLASMA HIL requires little-endian Zynq ARMv7")
    resolved = Path(executable).resolve()
    c._require(resolved.is_relative_to(EXPECTED_RUNTIME),
               "Runtime must be the PLASMA-owned /opt/plasma/python/3.12.13 interpreter")


def apertures(stage: str) -> tuple[MMIOAperture, ...]:
    """No guessed or broad device windows; configure only documented words."""
    if stage not in {"HIL01", "HIL02"}:
        raise c.SafetyError("Unapproved hardware stage")
    return (
        MMIOAperture(
            IDENTITY, frozenset(c.IDENTITY_OFFSETS), frozenset(),
        ),
        MMIOAperture(
            CONTROL, frozenset({4} if stage == "HIL01" else {0, 4}),
            frozenset({0} if stage == "HIL02" else {}),
        ),
        MMIOAperture(
            WAVEFORM, frozenset({0, 0x1C}), frozenset(),
        ),
        swd03_aperture(TRANSACTION) if stage == "HIL02" else MMIOAperture(
            TRANSACTION,
            frozenset({0, 8, 0x10, 0x14, 0x18, 0x1C,
                        0x20, 0x24, 0x28, 0x2C}),
            frozenset(),
        ),
    )


def control_echo(port) -> dict[str, object]:
    """Only documented PSPL-02 CONTROL address; no invalid AXI accesses."""
    samples = []
    for word in CONTROL_PATTERNS:
        port.write32(CONTROL, word)
        actual = port.read32(CONTROL)
        status = port.read32(CONTROL + 4)
        if actual != word or status != (word ^ 0xA5A55A5A):
            raise c.SafetyError("CONTROL/STATUS mismatch; STOP without retry")
        samples.append(f"0x{word:08X}")
    return {"patterns": samples, "count": len(samples),
            "control_restored_zero": True}


def synthetic_dpidr(port) -> dict[str, object]:
    """Production SWD-05 driver, no independent HIL reimplementation."""
    driver = SWDTransactionDriver(
        port, base=TRANSACTION, site_id=1,
        poll_budget=10000, max_poll_seconds=2.0,
    )
    driver.line_reset()
    dpidr = driver.read_dp(0)
    if dpidr != c.DPIDR:
        raise c.SafetyError("Synthetic DPIDR mismatch; STOP without retry")
    return {"line_reset": "PASS", "dpidr": f"0x{dpidr:08X}",
            "synthetic_fixture_only": True}


def run_stage(stage: str, *, device="/dev/mem",
              owner_lock="/run/lock/plasma-mmio.lock") -> dict[str, object]:
    """Real backend defaults; tests may inject a *regular file* as device.

    Caller MUST independently pass strict live prerequisite checks before
    invoking run_stage with /dev/mem. This function is not a public entrypoint.
    """
    with LinuxMMIO(apertures(stage), device=device, owner_lock=owner_lock,
                   readonly=(stage == "HIL01")) as mmio:
        audit = swd04.RestrictedMMIO(mmio)
        # Exact Build ID, reset values and ABI checks before any writes.
        identity = swd04.hil01_registers(audit)
        if stage == "HIL01":
            return {"identity": identity, "read_only": True}
        with mmio.claim_site(site_id=1, base=CONTROL) as port:
            control = control_echo(port)
        with mmio.claim_site(site_id=1, base=TRANSACTION) as port:
            swd = synthetic_dpidr(port)
        return {"identity": identity, "control": control, "swd05": swd}


def _record(path: Path, data: dict[str, object]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("HIL01", "HIL02"), required=True)
    parser.add_argument("--p0-report", type=Path, required=True)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--candidate-bin", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, required=True,
                        help="New private evidence directory (must not exist)")
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--ack-unrecoverable-axi-stall-risk", action="store_true")
    args = parser.parse_args(argv)

    # Gate all physical interactions. Missing flags mean no sysfs/devmem probes.
    if not (args.execute_live and args.ack_unrecoverable_axi_stall_risk):
        print("MMIO_Z2_NO_GO: inert without BOTH explicit live flags", file=sys.stderr)
        return 2
    try:
        c._require(not args.output.exists(), "Evidence destination already exists")
        check_runtime()
        require_live_session(
            phase=args.stage, p0=args.p0_report, session=args.session,
            candidate_bin=args.candidate_bin, previous=args.previous,
        )
    except (OSError, ValueError, KeyError, c.SafetyError) as exc:
        print("MMIO_Z2_NO_GO: " + str(exc), file=sys.stderr)
        return 2

    # Write STARTED before first /dev/mem access. SIGBUS or kernel hangs
    # can terminate execution without result.json; absence is never PASS.
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    base = {
        "qualification": "SWD-04", "scope": "MMIO-13-15",
        "stage": args.stage, "source_git_sha": c.SOURCE_SHA,
        "candidate_bin_sha256": c.CANDIDATE_BIN_SHA256,
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "physical_swd": "NOT_RUN", "real_ic_programming": "NOT_RUN",
        "recovery_restoration": "NOT_RUN",
    }
    _record(args.output / "started.json", {
        **base, "result": "STARTED",
        "utc_started": datetime.now(timezone.utc).isoformat(),
    })
    try:
        observation = run_stage(args.stage)
        result = {"result": "PASS", "observations": observation}
    except (OSError, ValueError, c.SafetyError, RuntimeError) as exc:
        # No repeated hardware access, no implicit recover/reset after error.
        result = {"result": "FAIL", "error": str(exc)}
    _record(args.output / "result.json", {
        **base, **result, "utc_finished": datetime.now(timezone.utc).isoformat(),
    })
    if result["result"] != "PASS":
        print("MMIO_Z2_STOP: failure; use supervised image restoration", file=sys.stderr)
        return 2
    print("MMIO_Z2_" + args.stage + "_FUNCTIONAL_PASS_RECOVERY_NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
