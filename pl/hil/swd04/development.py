"""Automated checks for the dedicated internal-only Z2 development fixture.

A protected load receipt ties the current boot's last FPGA Manager load to
verified firmware. It permits safe identity readback, not a claim of HIL PASS.
No UART/operator attestation or unrelated service/process inventory is used.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess

from pl.hil.swd04 import contract as c
from pl.hil.swd04.collect import fclk0_from_summary


@dataclass(frozen=True)
class HardwareProfile:
    """Immutable image pins and physical apertures supplied by the caller."""
    source: str
    bit_sha256: str
    hwh_sha256: str
    bin_sha256: str
    recovery_sha256: str
    apertures: tuple[tuple[str, int, int], ...]
    abis: tuple[tuple[str, int], ...]
    recovery_hwh_sha256: str = c.RECOVERY_HWH_SHA256
    identity_words: tuple[tuple[int, int], ...] = ()

    @property
    def bases(self):
        return {name: base for name, base, size in self.apertures}


SWD04_PROFILE = HardwareProfile(
    c.SOURCE_SHA, c.BIT_SHA256, c.HWH_SHA256, c.CANDIDATE_BIN_SHA256,
    c.RECOVERY_BIN_SHA256,
    tuple((name, base, c.SEGMENT_SIZE) for name, base in c.AXI_BASES.items()),
    (('identity', 1), ('waveform', 1), ('transaction', 1)))


def last_load(log: str) -> str:
    loads = [s for s in log.splitlines()
             if 'fpga_manager fpga0: writing ' in s]
    c._require(bool(loads), 'No current-boot FPGA Manager loading evidence')
    return loads[-1]


def verify_receipt(record: dict, *, boot_id: str, load_line: str,
                   profile: HardwareProfile = SWD04_PROFILE) -> None:
    c._require(type(record) is dict, 'Load receipt must be an object')
    expected = {
        'boot_id': boot_id, 'load_line': load_line,
        'candidate_bin_sha256': profile.bin_sha256,
        'build_id': profile.source[:32], 'axi_address_map': profile.bases,
        'abis': dict(profile.abis),
        'external_pl_io': False,
    }
    c._require(all(record.get(k) == v for k, v in expected.items()),
               'Loaded image provenance/Build ID/ABI/internal fixture mismatch')


def check_ownership(*, sys: Path = Path('/sys'), proc: Path = Path('/proc'),
                    profile: HardwareProfile = SWD04_PROFILE) -> None:
    """Only aperture-overlapping kernel resources and PL device fds/maps.

    Read fd symlinks and mapping ranges, never enumerate process commands or
    unrelated open files. An open /dev/mem is conservatively ambiguous; a
    retained mapping is checked even after the fd was closed. Permission
    errors fail closed; processes disappearing during the scan are normal.
    """
    ranges = tuple((base, base + size) for _, base, size in profile.apertures)
    def overlaps(lo, hi):
        return any(lo < end and hi > start for start, end in ranges)
    relevant_uio, unrelated_uio = set(), set()
    for uio in (sys/'class/uio').glob('uio*'):
        known, conflict = False, False
        for mapping in (uio/'maps').glob('map*'):
            known = True
            lo = int((mapping/'addr').read_text(), 0)
            if overlaps(lo, lo + int((mapping/'size').read_text(), 0)):
                conflict = True
                relevant_uio.add('/dev/' + uio.name)
                c._require(not (uio/'device/driver').exists(),
                           'Conflicting UIO driver: ' + uio.name)
        if known and not conflict:
            unrelated_uio.add('/dev/' + uio.name)
    for device in (sys/'bus/platform/devices').iterdir():
        if not (device/'driver').exists():
            continue
        match = re.match(r'^([0-9a-fA-F]+)\.', device.name)
        conflict = bool(match and overlaps(int(match[1], 16), int(match[1], 16) + 1))
        resource = device/'resource'
        if resource.exists():
            for line in resource.read_text().splitlines():
                lo, hi, flags = (int(x, 16) for x in line.split())
                if flags & 0x200 and overlaps(lo, hi + 1):
                    conflict = True
        c._require(not conflict, 'Conflicting platform driver: ' + device.name)
    check_users({'/dev/mem', '/dev/xdevcfg', '/dev/fpga0'} | relevant_uio,
                proc=proc, unrelated_uio=unrelated_uio, profile=profile)


def check_users(nodes: set[str], *, proc: Path = Path('/proc'),
                unrelated_uio: set[str] | None = None,
                profile: HardwareProfile = SWD04_PROFILE) -> None:
    unrelated_uio = unrelated_uio or set()
    def relevant(path):
        return path in nodes or (path.startswith('/dev/uio') and path not in unrelated_uio)
    ranges = tuple((base, base + size) for _, base, size in profile.apertures)
    def overlaps(lo, hi):
        return any(lo < end and hi > start for start, end in ranges)
    for process in proc.iterdir():
        if not process.name.isdigit():
            continue
        try:
            for fd in (process/'fd').iterdir():
                try:
                    target = os.readlink(fd)
                except FileNotFoundError:
                    continue
                c._require(not relevant(target),
                           'Conflicting PL device fd in PID ' + process.name)
            for line in (process/'maps').read_text().splitlines():
                fields = line.split()
                if len(fields) < 6 or not relevant(fields[5]):
                    continue
                lo, hi = (int(x, 16) for x in fields[0].split('-'))
                offset = int(fields[2], 16)
                c._require(fields[5] == '/dev/mem' and not overlaps(offset, offset + hi - lo),
                           'Conflicting retained PL mapping in PID ' + process.name)
        except FileNotFoundError:
            continue


def preflight(receipt: Path, candidate_bin: Path) -> dict:
    """No MMIO access. Called only after exact runtime and explicit live flags."""
    c._require(os.geteuid() == 0, 'Development checks require authorized root')
    for path in (receipt, receipt.parent):
        info = path.stat()
        c._require(info.st_uid == 0 and not info.st_mode & 0o022,
                   'Load receipt and parent must be root-owned and not writable by others')
    c._require(Path('/sys/class/fpga_manager/fpga0/state').read_text().strip() == 'operating',
               'FPGA Manager not operating')
    c._require(Path('/dev/mem').is_char_device(), 'Missing /dev/mem')
    record = json.loads(receipt.read_text())
    log = subprocess.run(['dmesg', '--color=never'], check=True,
                         capture_output=True, text=True, timeout=10).stdout
    verify_receipt(record, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                   load_line=last_load(log))
    c._require(c.sha256_file(candidate_bin) == c.CANDIDATE_BIN_SHA256,
               'Candidate firmware changed')
    clock = Path('/sys/kernel/debug/clk/clk_summary').read_text()
    rows = [line.split() for line in clock.splitlines() if line.split()
            and line.split()[0].lower() in {'fclk0', 'fclk_clk0', 'fclk0_clk'}]
    c._require(fclk0_from_summary(clock) == 100000000 and len(rows) == 1
               and int(rows[0][2]) > 0, 'FCLK0 not enabled at 100MHz')
    check_ownership()
    return record


def record_loaded_image(candidate_bin: Path, output: Path, *,
                        profile: HardwareProfile = SWD04_PROFILE) -> dict:
    """Capture evidence immediately after a supervised load; never loads PL.

    Use the actual firmware file named by FPGA Manager, in a root-owned
    directory. The approved pinned bytes define the internal fixture/ABIs;
    live HIL still checks the actual registers. This is a trusted loader
    record, not cryptographic attestation of FPGA configuration memory.
    """
    c._require(os.geteuid() == 0, 'Recording a load requires authorized root')
    for path in (candidate_bin, candidate_bin.parent, output.parent):
        info = path.stat()
        c._require(info.st_uid == 0 and not info.st_mode & 0o022,
                   'Firmware and receipt directory must be protected root-owned paths')
    c._require(c.sha256_file(candidate_bin) == profile.bin_sha256,
               'Candidate firmware digest mismatch')
    c._require(Path('/sys/class/fpga_manager/fpga0/state').read_text().strip() == 'operating',
               'FPGA Manager not operating')
    log = subprocess.run(['dmesg', '--color=never'], check=True,
                         capture_output=True, text=True, timeout=10).stdout
    line = last_load(log)
    c._require(f': writing {candidate_bin.name} to ' in line,
               'Last FPGA Manager load does not name the candidate firmware')
    record = dict(
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        load_line=line, candidate_bin_sha256=profile.bin_sha256,
        build_id=profile.source[:32], axi_address_map=profile.bases,
        abis=dict(profile.abis), external_pl_io=False,
    )
    # Never replace a receipt for an earlier load.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return record


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=record_loaded_image.__doc__)
    parser.add_argument('--candidate-bin', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        record_loaded_image(args.candidate_bin, args.output)
    except (OSError, ValueError, c.SafetyError, subprocess.SubprocessError) as exc:
        parser.exit(2, 'DEVELOPMENT_LOAD_NOT_VERIFIED: ' + str(exc) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
