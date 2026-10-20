"""F1-B B1 target library: one-shot Manager load, isolated RO read, restore.

INERT ON IMPORT; NO CLI, NO DISPATCH, NO DEPLOY. Requires future independent
owner hardware authorization. Do not use old SWD-05 four-aperture checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

from pl.hil.fixed_b1_contract import (
    B1Blocked, FPGA_BASE, FPGA_END, F1_BIT_SHA256, F1_HWH_SHA256,
    BASE_BIN_SHA256, BASE_HWH_SHA256, overlaps_64k, one_shot,
)
from pl.hil.fixed_b1_staging import CANDIDATE_BIN_SHA256, derive_candidate
from pl.hil.swd04.contract import REQUIRED_SERVICES

OWNER_LOCK = Path("/run/lock/plasma-f1b-owner.lock")
MANAGER = Path("/sys/class/fpga_manager/fpga0")
FIRMWARE = Path("/lib/firmware")
RUN_DIR = Path("/run/plasma-z2-f1b")
EXPECTED_PYTHON = "/opt/plasma/python/3.12.13/bin/python3"


@dataclass(frozen=True)
class Inputs:
    candidate_bit: Path
    candidate_hwh: Path
    candidate_bin: Path
    recovery_bin: Path
    recovery_hwh: Path
    output: Path
    host_receipt: Path
    # This file is deliberately NOT produced by this PR or the offline converter:
    # future separately approved root-controlled hardware admission must provide it.
    hardware_admission: Path


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_file(path: Path) -> None:
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.stat().st_uid != 0 or path.stat().st_mode & 0o022
            or path.parent.stat().st_uid != 0 or path.parent.stat().st_mode & 0o022):
        raise B1Blocked("B1_UNTRUSTED_LOCAL_FILE")


def check_ownership_full_64k(*, sysroot: Path = Path("/sys"),
                              procroot: Path = Path("/proc")) -> None:
    """Full 64KiB sysfs UIO/platform + /proc fd/maps, fail closed.

    A bound fabric UIO is denied, not automatically unbound. Reading this
    metadata never opens /dev/uio or /dev/mem. A permission-denied PID
    or missing resources make the operation NO_GO.
    """
    if not (sysroot / "class/uio").is_dir() or not (sysroot / "bus/platform/devices").is_dir():
        raise B1Blocked("B1_KERNEL_INVENTORY_INCOMPLETE")
    conflict_nodes = {"/dev/mem", "/dev/fpga0", "/dev/xdevcfg"}
    unrelated_uio = set()
    for node in (sysroot / "class/uio").glob("uio*"):
        known = False
        conflicted = False
        for mapping in (node / "maps").glob("map*"):
            known = True
            addr = int((mapping / "addr").read_text(), 0)
            size = int((mapping / "size").read_text(), 0)
            if overlaps_64k(addr, size):
                conflicted = True
                conflict_nodes.add("/dev/" + node.name)
                if (node / "device/driver").exists():
                    raise B1Blocked("B1_BOUND_UIO_DRIVER")
        if not known:
            raise B1Blocked("B1_UIO_MAP_UNKNOWN")
        if not conflicted:
            unrelated_uio.add("/dev/" + node.name)
    for device in (sysroot / "bus/platform/devices").iterdir():
        if not (device / "driver").exists():
            continue
        name = re.match(r"^([a-fA-F0-9]+)\.", device.name)
        if name and FPGA_BASE <= int(name.group(1), 16) < FPGA_END:
            raise B1Blocked("B1_BOUND_PLATFORM_DRIVER")
        resource = device / "resource"
        if resource.exists():
            for line in resource.read_text().splitlines():
                fields = line.split()
                if len(fields) != 3:
                    raise B1Blocked("B1_BAD_PLATFORM_RESOURCE")
                lo, hi, flags = (int(v, 16) for v in fields)
                if flags & 0x200 and overlaps_64k(lo, hi + 1 - lo):
                    raise B1Blocked("B1_BOUND_PLATFORM_RESOURCE")
    for proc in procroot.iterdir():
        if not proc.name.isdigit():
            continue
        try:
            for fd in (proc / "fd").iterdir():
                target = os.readlink(fd)
                if target in conflict_nodes or (
                    target.startswith("/dev/uio") and target not in unrelated_uio
                ):
                    raise B1Blocked("B1_ACTIVE_PL_CONSUMER")
            # Mappings persist after the underlying FD is closed.
            for line in (proc / "maps").read_text().splitlines():
                fields = line.split()
                if len(fields) >= 6 and (
                    fields[5] in conflict_nodes or (
                        fields[5].startswith("/dev/uio")
                        and fields[5] not in unrelated_uio
                    )
                ):
                    raise B1Blocked("B1_RETAINED_PL_MAPPING")
        except FileNotFoundError:
            # PID disappeared between enumeration and inspection.
            continue
        except PermissionError as exc:
            raise B1Blocked("B1_PROCESS_OWNERSHIP_UNKNOWN") from exc


def exact_pins(i: Inputs) -> None:
    """Fail closed unless future independent admission exists."""
    if os.geteuid() != 0:
        raise B1Blocked("B1_ROOT_REQUIRED")
    for f in (i.candidate_bit, i.candidate_hwh, i.candidate_bin,
              i.recovery_bin, i.recovery_hwh, i.host_receipt, i.hardware_admission):
        protected_file(f)
    if (i.candidate_bin.parent != FIRMWARE or
            i.recovery_bin.parent != FIRMWARE or
            i.recovery_bin.name != "base.bin" or
            i.candidate_bin.name == i.recovery_bin.name or
            not re.fullmatch(r"[A-Za-z0-9_.-]+", i.candidate_bin.name)):
        raise B1Blocked("B1_FIRMWARE_NOT_PINNED")
    if any((digest_file(f) != expected for f, expected in (
        (i.candidate_bit, F1_BIT_SHA256),
        (i.candidate_hwh, F1_HWH_SHA256),
        (i.candidate_bin, CANDIDATE_BIN_SHA256),
        (i.recovery_bin, BASE_BIN_SHA256),
        (i.recovery_hwh, BASE_HWH_SHA256),
    ))):
        raise B1Blocked("B1_FIRMWARE_HASH_MISMATCH")
    receipt = json.loads(i.host_receipt.read_text())
    expected, _ = derive_candidate(i.candidate_bit.read_bytes(),
                                    i.candidate_hwh.read_bytes(), receipt)
    if i.candidate_bin.read_bytes() != expected:
        raise B1Blocked("B1_FIRMWARE_CONTENT_MISMATCH")
    approval = json.loads(i.hardware_admission.read_text())
    if (approval.get("schema") != "plasma.f1b.b1.hardware-admission.v1"
            or approval.get("candidate_bin_sha256") != CANDIDATE_BIN_SHA256
            or approval.get("bootgen_independent_confirmation") != "PASS"
            or approval.get("operator_supervised_recovery") is not True
            or approval.get("exclusive_owner") is not True):
        raise B1Blocked("B1_HARDWARE_ADMISSION_NOT_APPROVED")
    if i.output.exists() or i.output.is_symlink():
        raise B1Blocked("B1_EVIDENCE_OUTPUT_ALREADY_EXISTS")


def manager_last_load() -> str:
    """Return latest FPGA Manager event for this boot; do not trust just operating."""
    from pl.hil.swd04.development import last_load
    result = subprocess.run(
        ["dmesg", "--color=never"], check=True, text=True,
        capture_output=True, timeout=10,
    )
    return last_load(result.stdout)


def manager_write_firmware(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise B1Blocked("B1_INVALID_MANAGER_FIRMWARE_NAME")
    with (MANAGER / "firmware").open("w") as f:
        f.write(name)
    if (MANAGER / "state").read_text().strip() != "operating":
        raise B1Blocked("B1_FPGA_MANAGER_NOT_OPERATING")
    if f": writing {name} to " not in manager_last_load():
        raise B1Blocked("B1_FPGA_MANAGER_LOAD_PROVENANCE_MISMATCH")


class IsolatedIdentity:
    """No external retry; wait/kill/reap before restoration is even considered."""
    def __init__(self, executable: str = EXPECTED_PYTHON):
        self.executable = executable
        self.proc: subprocess.Popen | None = None
        self.reaped = False

    def read(self) -> dict:
        self.proc = subprocess.Popen([
            self.executable, "-m", "pl.hil.fixed_b1_identity_child",
            "--internal-read-identity"
        ], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
           stderr=subprocess.DEVNULL, text=True, start_new_session=True)
        try:
            output, _ = self.proc.communicate(timeout=7)
        except subprocess.TimeoutExpired:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                try:
                    self.proc.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    raise B1Blocked("B1_IDENTITY_CHILD_UNREAPED_NO_RELOAD")
            raise B1Blocked("B1_IDENTITY_CHILD_TIMEOUT")
        self.reaped = self.proc.poll() is not None
        if self.proc.returncode != 0 or len(output) > 2048:
            raise B1Blocked("B1_IDENTITY_READ_FAILED")
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise B1Blocked("B1_IDENTITY_CHILD_INVALID_REPORT") from exc

    def stopped_and_unmapped(self) -> bool:
        if self.proc is not None and (not self.reaped or self.proc.poll() is None):
            return False
        check_ownership_full_64k()
        return True


def clock_and_original_image(i: Inputs) -> None:
    """Relevant load-time facts, NOT a repeated HIL-B0 checklist."""
    from pl.hil.swd04.collect import fclk0_from_summary
    summary = Path("/sys/kernel/debug/clk/clk_summary").read_text()
    if fclk0_from_summary(summary) != 100000000:
        raise B1Blocked("B1_LIVE_FCLK_NOT_100MHZ")
    if (": writing " + i.recovery_bin.name + " to ") not in manager_last_load():
        raise B1Blocked("B1_ORIGINAL_IMAGE_PROVENANCE_UNKNOWN")


def service_snapshot() -> dict[str, bool]:
    """Only the same four known runtime services, no restart or quiesce."""
    states = {}
    for name in REQUIRED_SERVICES:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", name],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=3, check=False)
        states[name] = result.returncode == 0
    return states


def run_live(i: Inputs) -> dict[str, str]:
    """No CLI/dispatcher: integration cannot run without a later approved route.

    FPGA Manager and MMIO are physical, irreversible-risk operations. This
    function must never be called by Actions/host tests.
    """
    from pl.hil.swd04.native_qualify import check_runtime
    check_runtime()
    exact_pins(i)
    if not OWNER_LOCK.parent.is_dir() or OWNER_LOCK.is_symlink():
        raise B1Blocked("B1_OWNER_LOCK_UNAVAILABLE")
    lock_fd = os.open(OWNER_LOCK, os.O_CREAT | os.O_RDWR |
                      getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Exact preflight BEFORE creating evidence or writing FPGA Manager.
        check_ownership_full_64k()
        clock_and_original_image(i)
        if (MANAGER / "state").read_text().strip() != "operating":
            raise B1Blocked("B1_MANAGER_NOT_OPERATING")
        before_services = service_snapshot()
        if not all(before_services.values()):
            raise B1Blocked("B1_SERVICES_NOT_STABLE")
        boot_before = Path("/proc/sys/kernel/random/boot_id").read_text()
        original_state = (MANAGER / "state").read_text().strip()
        i.output.mkdir(mode=0o700, parents=False, exist_ok=False)
        (i.output / "started.json").write_text(json.dumps({
            "schema": "plasma.f1b.b1.target.started.v1",
            "candidate_bin_sha256": CANDIDATE_BIN_SHA256,
            "result": "STARTED",
            "recovery_required": True,
        }) + "\n")
        isolated = IsolatedIdentity()
        def preflight() -> None:
            check_ownership_full_64k()
            if (MANAGER / "state").read_text().strip() != original_state:
                raise B1Blocked("B1_MANAGER_STATE_CHANGED")
        def restore() -> None:
            manager_write_firmware(i.recovery_bin.name)
        def verify() -> None:
            if (Path("/proc/sys/kernel/random/boot_id").read_text() != boot_before
                    or (MANAGER / "state").read_text().strip() != original_state
                    or service_snapshot() != before_services):
                raise B1Blocked("B1_RESTORATION_MISMATCH")
            clock_and_original_image(i)
            check_ownership_full_64k()
        result = one_shot(
            preflight=preflight,
            load_candidate=lambda: manager_write_firmware(i.candidate_bin.name),
            identity_child=isolated.read,
            child_stopped_and_unmapped=isolated.stopped_and_unmapped,
            restore_original=restore,
            verify_restoration=verify,
        )
        (i.output / "result.json").write_text(json.dumps({
            "schema": "plasma.f1b.b1.target.result.v1",
            "stages": result,
            "physical_swd": "NOT_RUN",
            "external_dut": "NOT_RUN",
        }, sort_keys=True) + "\n")
        return result
    finally:
        os.close(lock_fd)

