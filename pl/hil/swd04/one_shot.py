"""One-shot, supervised SWD-05 internal-fixture FPGA load/HIL/recovery.

Z2 TARGET-ONLY entrypoint. DEFAULT INERT. Reuses immutable four-aperture
SWD-04 pins, development ownership/receipt and production LinuxMMIO HIL01/02.
This is not a physical target SWD, DUT, JTAG, USB power or Flash experiment.
Kernel AXI hangs are not always recoverable from userspace, even in finally.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import signal
from typing import Callable

from pl.hil.swd04 import contract as c, development, native_qualify, staging

FIRMWARE_ROOT = Path("/lib/firmware")
MANAGER = Path("/sys/class/fpga_manager/fpga0")
OWNER_DIR = Path("/run/plasma-z2-swd05")
OWNER_LOCK = OWNER_DIR / "supervisor.lock"
SERVICES = c.REQUIRED_SERVICES
STAGES = ("HIL01", "HIL02")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise c.SafetyError(reason)


def protected(path: Path, *, file: bool = True) -> None:
    """No link tricks, non-root owner or group/world-writeable artifact paths."""
    require(path.is_absolute() and not path.is_symlink(), "Untrusted path")
    stat = path.stat()
    require(stat.st_uid == 0 and stat.st_mode & 0o022 == 0, "Unprotected owner/mode")
    require(path.is_file() if file else path.is_dir(), "Unexpected object kind")
    require(path.parent.stat().st_uid == 0 and
            path.parent.stat().st_mode & 0o022 == 0,
            "Unprotected parent")


@dataclass(frozen=True)
class Inputs:
    candidate_bit: Path
    candidate_hwh: Path
    manifest: Path
    candidate_bin: Path
    recovery_bin: Path
    recovery_hwh: Path
    output: Path


def verify_inputs(i: Inputs) -> None:
    native_qualify.check_runtime()
    require(os.geteuid() == 0, "Authorized Z2 root required")
    require(not i.output.exists(), "Evidence directory cannot be reused")
    protected(i.output.parent, file=False)
    for path in (i.candidate_bit, i.candidate_hwh, i.manifest,
                 i.candidate_bin, i.recovery_bin, i.recovery_hwh):
        protected(path)
    require(i.candidate_bin.parent.resolve() == FIRMWARE_ROOT and
            i.recovery_bin.parent.resolve() == FIRMWARE_ROOT,
            "FPGA Manager firmware must be directly under /lib/firmware")
    c.verify_artifacts(c.Candidate(i.candidate_bit, i.candidate_hwh,
                                   i.manifest, i.recovery_bin,
                                   i.recovery_hwh))
    staging.verify_bin(i.candidate_bit, i.candidate_bin)
    require(i.candidate_bin.name != i.recovery_bin.name,
            "Candidate and recovery names must be distinct")
    require(bool(re.fullmatch(r"[A-Za-z0-9_.-]+", i.candidate_bin.name))
            and bool(re.fullmatch(r"[A-Za-z0-9_.-]+", i.recovery_bin.name)),
            "Invalid firmware basename")


def clock_and_owner() -> None:
    require(MANAGER.joinpath("state").read_text().strip() == "operating",
            "FPGA Manager is not operating")
    require(Path("/dev/mem").is_char_device(), "Missing char /dev/mem")
    summary = Path("/sys/kernel/debug/clk/clk_summary").read_text()
    from pl.hil.swd04.collect import fclk0_from_summary
    require(fclk0_from_summary(summary) == 100000000, "FCLK0 not 100MHz")
    active = [line.split() for line in summary.splitlines()
              if line.split() and line.split()[0].lower() in
              ("fclk0", "fclk_clk0", "fclk0_clk")]
    require(len(active) == 1 and int(active[0][2]) > 0, "FCLK0 not enabled")
    development.check_ownership()


def service_snapshot() -> dict[str, str]:
    states = {}
    for name in SERVICES:
        result = subprocess.run(["systemctl", "is-active", "--quiet", name],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, timeout=3, check=False)
        states[name] = "active" if result.returncode == 0 else "not_active"
    require(all(value == "active" for value in states.values()),
            "Original PLASMA services are not all active")
    return states


def uio_snapshot() -> tuple[tuple[str, str, str], ...]:
    """Only basic sysfs view; never open a UIO character device."""
    result = []
    for item in sorted(Path("/sys/class/uio").glob("uio*")):
        name = item.joinpath("name").read_text().strip()
        require(name in ("fabric", "audio-codec-ctrl"), "Unexpected UIO owner")
        result.append((name, str(item.joinpath("device", "driver").exists()),
                       str(item.resolve())))
    return tuple(sorted(result))


def manager_last_load() -> str:
    text = subprocess.run(["dmesg", "--color=never"], text=True, check=True,
                          capture_output=True, timeout=10).stdout
    return development.last_load(text)


def manager_write(name: str) -> None:
    """Only preverified immutable basename; never writes flags or resets."""
    require(bool(re.fullmatch(r"[A-Za-z0-9_.-]+", name)), "Illegal firmware name")
    with MANAGER.joinpath("firmware").open("w") as out:
        out.write(name)
    require(MANAGER.joinpath("state").read_text().strip() == "operating",
            "FPGA Manager firmware load did not reach operating")
    require(f": writing {name} to " in manager_last_load(),
            "Firmware manager load provenance not observed")


def record_json(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write("\n")


def run_protected(
    *,
    preflight: Callable[[], None],
    load_candidate: Callable[[], None],
    hil01: Callable[[], None],
    hil02: Callable[[], None],
    restore: Callable[[], None],
    verify_restoration: Callable[[], None],
) -> dict[str, str]:
    """Injection-friendly core. Set restore-required BEFORE attempting any load."""
    state = {"preflight": "NOT_RUN", "candidate_load": "NOT_RUN",
             "hil01": "NOT_RUN", "hil02": "NOT_RUN",
             "restore": "NOT_RUN", "restoration_verified": "NOT_RUN",
             "overall": "NO_GO"}
    touched = False
    try:
        preflight()
        state["preflight"] = "PASS"
        touched = True
        load_candidate()
        state["candidate_load"] = "PASS"
        hil01()
        state["hil01"] = "PASS"
        hil02()
        state["hil02"] = "PASS"
    except Exception:
        state["overall"] = "FAIL_OR_BLOCKED"
    finally:
        if touched:
            try:
                restore()
                state["restore"] = "PASS"
                verify_restoration()
                state["restoration_verified"] = "PASS"
            except Exception:
                state["restore"] = "FAIL_OR_UNKNOWN"
                state["restoration_verified"] = "FAIL_OR_UNKNOWN"
    if all(state[key] == "PASS" for key in (
        "preflight", "candidate_load", "hil01", "hil02",
        "restore", "restoration_verified",
    )):
        state["overall"] = "PASS_DEVELOPMENT_INTERNAL_FIXTURE"
    return state


def run_live(i: Inputs) -> dict[str, str]:
    verify_inputs(i)  # All hashes and paths before any physical action.
    OWNER_DIR.mkdir(mode=0o700, exist_ok=True)
    protected(OWNER_DIR, file=False)
    if OWNER_LOCK.exists():
        protected(OWNER_LOCK)
    lock_fd = os.open(OWNER_LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    protected(OWNER_LOCK)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not i.output.exists(), "Output path already used")
        i.output.mkdir(mode=0o700)
        snapshot = {}
        receipt = i.output / "load-receipt.json"
        a = i.output / "hil01"
        b = i.output / "hil02"
        outcome = {}
        def preflight() -> None:
            require(Path("/proc/device-tree/compatible").read_bytes().split(b"\0").count(b"xlnx,zynq-7000") == 1,
                    "Zynq Device Tree family not verified")
            clock_and_owner()
            snapshot["services"] = service_snapshot()
            snapshot["uio"] = uio_snapshot()
            snapshot["boot_id"] = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            require(f": writing {i.recovery_bin.name} to " in manager_last_load(),
                    "Current original base image provenance unknown")
            # Recheck actual artifacts just before any hardware action.
            c.verify_artifacts(c.Candidate(i.candidate_bit, i.candidate_hwh,
                                           i.manifest, i.recovery_bin, i.recovery_hwh))
        def load() -> None:
            manager_write(i.candidate_bin.name)
            development.record_loaded_image(i.candidate_bin, receipt)
        def stage(name: str, previous: Path | None) -> None:
            args = [sys.executable, "-m", "pl.hil.swd04.native_qualify",
                    "--profile", "development", "--stage", name,
                    "--session", str(receipt), "--candidate-bin", str(i.candidate_bin),
                    "--output", str(a if name == "HIL01" else b),
                    "--execute-live", "--ack-unrecoverable-axi-stall-risk"]
            if previous is not None:
                args.extend(("--previous", str(previous)))
            # Process isolation is mandatory: a SIGBUS must not kill the
            # supervisor, leaving FPGA Manager unrecovered.
            proc = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    start_new_session=True)
            try:
                status = proc.wait(timeout=35)
            except subprocess.TimeoutExpired as exc:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        # The mapping may still be owned by a kernel-stalled
                        # process. Recovery by FPGA load is now unsafe.
                        raise c.SafetyError("MMIO_CHILD_UNREAPED_NO_RELOAD") from exc
                raise c.SafetyError("MMIO_CHILD_TIMEOUT") from exc
            except BaseException:
                # SSH disconnect / supervisor interruption: do not leave
                # a live MMIO child holding an aperture when finally restores.
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            raise c.SafetyError("MMIO_CHILD_UNREAPED_NO_RELOAD")
                raise
            require(status == 0, name + " child failed or SIGBUS")
            data = json.loads((a if name == "HIL01" else b).joinpath("result.json").read_text())
            require(data["result"] == "PASS" and data["stage"] == name,
                    "Stage report invalid")
        def restore() -> None:
            # A retained /dev/mem or PL mapping is a hard NO-RELOAD even
            # after a child timeout, to avoid reconfiguring under a consumer.
            development.check_ownership()
            # Never trust candidate observations as evidence of original image.
            require(c.sha256_file(i.recovery_bin) == c.RECOVERY_BIN_SHA256,
                    "Recovery bytes changed")
            manager_write(i.recovery_bin.name)
        def verify_restoration() -> None:
            require(snapshot["boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                    "Z2 boot changed")
            require(service_snapshot() == snapshot["services"], "Service state changed")
            require(uio_snapshot() == snapshot["uio"], "UIO binding state differs")
            clock_and_owner()
        # An SSH disconnect normally propagates SIGHUP or SIGTERM; route it
        # into the Python finally recovery path. SIGKILL, SIGBUS in the
        # supervisor and uninterruptible kernel stalls remain unrecoverable.
        watched = (signal.SIGTERM, signal.SIGHUP)
        old_handlers = {sig: signal.getsignal(sig) for sig in watched}
        def interrupt(sig, frame):
            raise c.SafetyError("SUPERVISOR_INTERRUPTED")
        try:
            for sig in watched:
                signal.signal(sig, interrupt)
            outcome = run_protected(
                preflight=preflight, load_candidate=load,
                hil01=lambda: stage("HIL01", None),
                hil02=lambda: stage("HIL02", a / "result.json"),
                restore=restore, verify_restoration=verify_restoration)
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
        # A report never leaks kernel process, paths, addresses or credentials.
        record_json(i.output / "summary.json", {
            "schema": "plasma.z2.swd05.oneshot.v1",
            "stages": outcome,
            "candidate_source": c.SOURCE_SHA,
            "candidate_bin_sha256": c.CANDIDATE_BIN_SHA256,
            "recovery_bin_sha256": c.RECOVERY_BIN_SHA256,
            "site": 1,
            "external_dut": "NOT_RUN",
            "physical_swd": "NOT_RUN",
            "fpga_load_attempted": outcome["preflight"] == "PASS",
        })
        return outcome
    finally:
        os.close(lock_fd)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("candidate-bit", "candidate-hwh", "manifest", "candidate-bin",
                "recovery-bin", "recovery-hwh", "output"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--execute-live", action="store_true")
    p.add_argument("--ack-unrecoverable-axi-stall-risk", action="store_true")
    opts = p.parse_args(argv)
    if not (opts.execute_live and opts.ack_unrecoverable_axi_stall_risk):
        print("SWD05_ONESHOT_NO_GO: inert without both explicit live flags", file=sys.stderr)
        return 2
    inputs = Inputs(opts.candidate_bit, opts.candidate_hwh, opts.manifest,
                    opts.candidate_bin, opts.recovery_bin, opts.recovery_hwh,
                    opts.output)
    try:
        result = run_live(inputs)
    except (OSError, ValueError, c.SafetyError, RuntimeError, subprocess.SubprocessError):
        print("SWD05_ONESHOT_NO_GO: prerequisites or execution blocked", file=sys.stderr)
        return 2
    print("PLASMA_SWD05_REPORT=" + json.dumps({
        "schema": "plasma.z2.swd05.oneshot.v1",
        "stages": result, "site": 1,
        "candidate_source": c.SOURCE_SHA,
        "candidate_bin_sha256": c.CANDIDATE_BIN_SHA256,
        "recovery_bin_sha256": c.RECOVERY_BIN_SHA256,
        "external_dut": "NOT_RUN",
        "physical_swd": "NOT_RUN",
    }, sort_keys=True))
    return 0 if result["overall"] == "PASS_DEVELOPMENT_INTERNAL_FIXTURE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
