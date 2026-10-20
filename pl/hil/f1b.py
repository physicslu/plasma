"""F1-B offline admission/Identity adapter. No live entrypoint or device access.

The privileged staging route is not established. This deliberately cannot call
SWD04 run_live: that entrypoint's four apertures and write stages remain intact.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from pl.hil.swd04 import one_shot, staging

SOURCE = '00336106ad89eaa9fa0603dbe9e65024a27a6fe6'
BIT_SHA = 'fdbde5c66999a9dab37339587d304b9c16e71a06f1890b24893c8391859cf075'
HWH_SHA = 'bf3690d69fefc8da3fc62964209776466894cd4353aec0a475b373257899ca76'
BASE_SHA = 'c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c'
BASE_HWH_SHA = '222898ef2c0ccc4a0c47608e99d8dc7c9c6cdfed5130964884ff35005827ef3a'
BASE, LENGTH = 0x40000000, 0x10000
# Historical built-source defaults, not unique provenance/authenticity IDs.
# Dynamic health/status and reserved addresses are deliberately excluded.
IDENTITY = {
    0x0000: 0x4D534C50, 0x0004: 0x00010000,
    0x0008: 0x11112222, 0x000C: 0x33334444,
    0x0010: 0x55556666, 0x0014: 0x77778888,
    0x0018: 0xABCDE001, 0x001C: 0xABCDE002,
    0x0020: 0xABCDE003, 0x0024: 0xABCDE004,
    0x0028: 1, 0x002C: 0, 0x0030: 1, 0x003C: 1,
    0x0044: 1, 0x0048: 4096, 0x004C: 64,
    0x4000: 1, 0x4004: 0x00010000, 0x4008: 1,
}


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def verify_file(path: Path, digest: str, size: int | None = None) -> bytes:
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == digest, 'artifact hash rejected')
    require(size is None or len(data) == size, 'artifact size rejected')
    return data


def verify_inputs(bit: Path, hwh: Path, recovery: Path, recovery_hwh: Path) -> None:
    verify_file(bit, BIT_SHA, 4045769)
    verify_file(hwh, HWH_SHA, 138977)
    verify_file(recovery, BASE_SHA)
    verify_file(recovery_hwh, BASE_HWH_SHA)


def verify_conversion(bit: Path, firmware: Path) -> dict:
    """Check byte equivalence only; this is NOT proof Bootgen executed.

    A future admitted live route additionally needs an independently verified
    Bootgen execution receipt. A derived hash alone never grants admission.
    """
    verify_file(bit, BIT_SHA, 4045769)
    payload = staging.bit_payload(bit.read_bytes())
    expected = b''.join(payload[i:i+4][::-1] for i in range(0, len(payload), 4))
    expected += bytes.fromhex('00000020')
    actual = firmware.read_bytes()
    require(actual == expected, 'Bootgen payload mismatch')
    return {'sha256': hashlib.sha256(actual).hexdigest(), 'size_bytes': len(actual)}


def read_identity(read32) -> dict[int, int]:
    """Injected aligned native-u32 reader only; never creates an MMIO mapping."""
    observed = {}
    for offset, expected in IDENTITY.items():
        value = read32(checked_address(offset))
        require(type(value) is int and 0 <= value <= 0xFFFFFFFF,
                'non-u32 readback')
        require(value == expected, 'F1-B Identity/ABI mismatch')
        observed[offset] = value
    return observed


def checked_address(offset: int) -> int:
    require(type(offset) is int and 0 <= offset < LENGTH and
            offset % 4 == 0 and offset in IDENTITY, 'read offset denied')
    return BASE + offset


def reject_retained_maps(text: str) -> None:
    """Pure /proc/PID/maps check covering the entire F1-B 64KiB window.

    An eventual live collector must additionally enforce kernel-driver, open-fd,
    process visibility and AXI-idle guards. This parser alone grants no admission.
    """
    for line in text.splitlines():
        fields = line.split()
        require(len(fields) >= 5, 'malformed VMA record')
        if len(fields) < 6:
            continue
        node = fields[5]
        if node.startswith('/dev/uio') or node in ('/dev/xdevcfg', '/dev/fpga0'):
            raise ValueError('retained PL device VMA')
        if node == '/dev/mem':
            lo, hi = (int(x, 16) for x in fields[0].split('-'))
            offset = int(fields[2], 16)
            require(hi > lo and not (offset < BASE + LENGTH and
                    offset + hi - lo > BASE), 'retained F1-B MMIO VMA')


def offline_sequence(*, preflight, load, identity, restore_guard, restore,
                     verify_restore) -> dict:
    """Failure-injection harness reusing the existing intent/finally core.

    No callback here is a live backend. A future reviewed target adapter must
    supply real lock/receipt, ownership, timeout/reap and current-boot guards.
    The restoration guard must reject unresolved AXI health or retained VMAs.
    """
    def guarded_restore():
        restore_guard()
        restore()
    return one_shot.run_protected(
        preflight=preflight, load_candidate=load, hil01=identity,
        hil02=lambda: None, restore=guarded_restore,
        verify_restoration=verify_restore)



def reject_retained_fds(targets: list[str]) -> None:
    """Conservative snapshot parser; unreadable/incomplete proc scans deny admission."""
    for target in targets:
        require(bool(target) and target != 'UNKNOWN', 'incomplete fd observation')
        require(not (target.startswith('/dev/uio') or target.split(' (deleted)')[0]
                    in ('/dev/mem', '/dev/xdevcfg', '/dev/fpga0')),
                'retained PL device fd')


@dataclass(frozen=True)
class AdmissionEvidence:
    """Facts a future reviewed collector must establish, never user attestations.

    This record is not a collector, a signed receipt, or authority to load.
    Every uncertain observation defaults closed; flock is deliberately separate.
    """
    reviewed_source: str = ''
    boot_id: str = ''
    provenance_boot_id: str = ''
    original_sha: str = ''
    original_hwh_sha: str = ''
    root_owned_source: bool = False
    protected_recovery: bool = False
    bootgen_receipt_verified: bool = False
    root_route: bool = False
    complete_proc_visibility: bool = False
    kernel_driver_excluded: bool = False
    hardware_owner_excluded: bool = False
    axi_idle_isolated: bool = False
    child_reaped: bool = False


def admit(e: AdmissionEvidence, *, maps: str, fds: list[str]) -> None:
    require(e.reviewed_source == SOURCE and e.root_owned_source,
            'reviewed root-owned source required')
    require(bool(e.boot_id) and e.boot_id == e.provenance_boot_id,
            'current-boot provenance required')
    require(e.original_sha == BASE_SHA and e.original_hwh_sha == BASE_HWH_SHA
            and e.protected_recovery, 'protected original recovery required')
    for name in ('bootgen_receipt_verified', 'root_route', 'complete_proc_visibility', 'kernel_driver_excluded',
                 'hardware_owner_excluded', 'axi_idle_isolated', 'child_reaped'):
        require(getattr(e, name) is True, name + ' not established')
    reject_retained_maps(maps)
    reject_retained_fds(fds)


@contextmanager
def exclusive_session(path: Path):
    """Reuse generic protected-path policy; lock is concurrency, not isolation.

    No manager, MMIO, shell, or hardware backend is exposed here.
    """
    one_shot.protected(path)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        require(st.st_uid == 0 and st.st_mode & 0o022 == 0,
                'lock owner/mode changed')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def child_result(returncode: int | None, *, reaped: bool, timed_out: bool) -> None:
    """A timeout, SIGBUS, unknown status or unreaped child can never pass."""
    require(reaped is True, 'MMIO_CHILD_UNREAPED_NO_RELOAD')
    require(not timed_out, 'MMIO_CHILD_TIMEOUT')
    require(type(returncode) is int and returncode == 0, 'MMIO child failed or SIGBUS')


def supervised_sequence(*, lock_path: Path, observe, record_intent, load,
                        identity, restore, verify_restore) -> dict:
    """Backend-free F1-B transaction for future independent review.

    observe returns (AdmissionEvidence, maps, fds) freshly at both boundaries.
    record_intent must durably record restore-required before the first write.
    This function does not supply a privileged route or hardware capability.
    A failed observation, child reap, or AXI isolation blocks any reload.
    """
    def guard():
        evidence, maps, fds = observe()
        admit(evidence, maps=maps, fds=fds)

    def preflight():
        guard()
        record_intent()

    with exclusive_session(lock_path):
        return offline_sequence(preflight=preflight, load=load, identity=identity,
                                restore_guard=guard, restore=restore,
                                verify_restore=verify_restore)
