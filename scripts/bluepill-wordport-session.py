#!/usr/bin/env python3
"""One local Blue Pill WordPort session; no FPGA load, reset or auto-restore.

Development-only Z2 PS programmer-engine glue. OpenOCD must execute on
Z2 PS and connect to this process through a PS-local UNIX socket; SWPC is
only the Web/Controller/BFF control station and development/CI host.
The supervisor must qualify the pinned Z2 ARMv7 OpenOCD, perform protected
Download/Identity, and reap local OpenOCD and this bridge after DPIDR.
No cross-host Remote Bitbang forwarding or SWPC OpenOCD live execution.
On normal success the SWD FPGA Image remains loaded after socket/MMIO cleanup.
Golden Restore is a separate, explicitly selected protected Root operation;
uncertain hardware state still requires guarded recovery decisions.
This script never installs or extends the protected Root executor. Electrical
conditions are owner-attested, not measured by this program.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import importlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
PROTECTED = Path('/root/plasma-path2-approved')
BASE = 0x40008000


def need(ok: bool, code: str) -> None:
    if not ok:
        raise RuntimeError(code)


def validate_checkpoint(record: dict, manifest, *, boot_id: str,
                        manifest_sha: str) -> None:
    """Reject Golden, stale, in-flight or changed-image checkpoints."""
    need(record.get('schema') == 'plasma.fpga.image-deployment.v3' and
         record.get('status') == 'IMAGE' and
         record.get('boot_id') == boot_id and
         record.get('image') == manifest.firmware_name and
         record.get('image_id') == manifest.image_id and
         record.get('manifest_sha256') == manifest_sha and
         record.get('firmware_sha256') == manifest.firmware_sha256 and
         type(record.get('test_count')) is int and record['test_count'] > 0,
         'HELD_TESTED_IMAGE_CHECKPOINT_REQUIRED')
    need(manifest.axi_base == BASE and manifest.axi_bytes == 4096 and
         manifest.abi_version == 0x10000 and
         manifest.identity_words == ((0, 0x50425357, 0xffffffff),
                                    (4, 0x10000, 0xffffffff),
                                    (12, 8, 0xfffffffe)),
         'BLUEPILL_IMAGE_ABI_REQUIRED')


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root-source-sha', required=True)
    p.add_argument('--boot-id', required=True)
    p.add_argument('--barrier', required=True)
    p.add_argument('--barrier-sha256', required=True)
    p.add_argument('--native', required=True,
                   help='Absolute SHA-pinned ARMv7 Native C WordPort shared library')
    p.add_argument('--native-sha256', required=True)
    p.add_argument('--socket', required=True)
    p.add_argument('--stage-evidence',
                   help='Private JSONL evidence file for synchronized stage snapshots')
    p.add_argument('--owner-attested', action='store_true', required=True,
                   help='Current approved wiring, isolated debugger, 3.3V VTref, common ground')
    return p


def run(args) -> dict:
    need(args.owner_attested and os.geteuid() == 0, 'ROOT_AND_OWNER_ATTESTATION_REQUIRED')
    need(re.fullmatch(r'[a-f0-9]{40}', args.root_source_sha) is not None,
         'ROOT_SOURCE_SHA_REQUIRED')
    need((PROTECTED / '.plasma-path2-source-commit').read_text().strip() ==
         args.root_source_sha, 'ROOT_SOURCE_PIN_CHANGED')
    subprocess.run(['sha256sum', '--check', '--status', '.plasma-path2-source-sha256'],
                   cwd=PROTECTED, check=True, timeout=15)
    # Protected guard and admission code remain installed and unchanged.
    sys.path.insert(0, str(PROTECTED))
    root = importlib.import_module('pl.hil.fpga_image_root')
    root.trusted_local()
    root.native_runtime_preflight()
    release = root.read_image_manifest()
    port = root.guard.RootZ2TargetPort(release=release)
    # Load current main MMIO/DMB and reviewed PR 1142 WordPort/algorithm.
    sys.path.insert(0, str(REPO / 'software/python'))
    from plasma_interfaces.fixed_abi_mmio_port import ARMv7DMBBarrier
    from plasma_interfaces.linux_mmio import LinuxMMIO
    from plasma_interfaces.bluepill_z2_word_port import BluepillZ2WordPort, bluepill_z2_aperture
    from plasma_interfaces.bluepill_remote_bitbang import SocketCallCounters, serve_local_unix_once
    from plasma_interfaces.native_bluepill_word_port import (
        NativeBluepillWordPort, qualify_native_bridge_library)
    from plasma_interfaces.wordport_stage_monitor import StageMonitor

    barrier = ARMv7DMBBarrier(args.barrier, sha256=args.barrier_sha256)
    barrier()  # Qualify native execution before opening any device.
    qualify_native_bridge_library(args.native, args.native_sha256)
    with port.exclusive():
        record = root.read_state(release)
        need(isinstance(record, dict), 'IMAGE_CHECKPOINT_REQUIRED')
        validate_checkpoint(record, release, boot_id=args.boot_id,
                            manifest_sha=root.manifest_sha256())
        # An additional device-scoped check INSIDE the exclusive FPGA lock;
        # this is not a global /proc census and cannot replace device ACLs.
        for device in ('/dev/mem', '/dev/uio1'):
            probe = subprocess.run(['fuser', '-s', device],
                                   capture_output=True, timeout=5)
            need(probe.returncode == 1, 'EXTERNAL_MMIO_CONSUMER_OR_UNKNOWN')
        # Program-only admission: maintain Root/Image/Boot/UIO/IRQ checks,
        # but do not require a census of every short-lived Linux process.
        facts = root.live_program_session_report(port, release)
        need(facts['target_boot_id'] == args.boot_id, 'BOOT_CHANGED')
        # The same global FPGA lock spans admission, MMIO, socket and close.
        with ExitStack() as stack:
            mmio = stack.enter_context(LinuxMMIO((bluepill_z2_aperture(),)))
            lease = stack.enter_context(mmio.claim_site(1, BASE))
            bridge = NativeBluepillWordPort(
                BluepillZ2WordPort(lease, barrier=barrier),
                library=args.native, sha256=args.native_sha256)
            counters = SocketCallCounters()
            if args.stage_evidence:
                stage_socket = Path(args.socket + '.stage')
                stage_evidence = Path(args.stage_evidence)
                need(stage_evidence.is_absolute() and not stage_evidence.exists() and
                     not stage_evidence.is_symlink() and
                     stage_evidence.parent.is_dir() and
                     stage_evidence.parent.stat().st_uid == os.getuid() and
                     not stage_evidence.parent.stat().st_mode & 0o077,
                     'PRIVATE_FRESH_STAGE_EVIDENCE_REQUIRED')
                with StageMonitor(stage_socket, stage_evidence, bridge, counters):
                    count = serve_local_unix_once(args.socket, bridge, idle_timeout_s=60,
                                                  counters=counters)
            else:
                count = serve_local_unix_once(args.socket, bridge, idle_timeout_s=60,
                                              counters=counters)
            native_counts = bridge.counter_snapshot()
            stats = mmio.stats()
        return {'result': 'BRIDGE_CLOSED', 'boot_id': args.boot_id,
                'lease_id': record['session_id'], 'wire_bytes': count,
                'read32': stats.read32, 'write32': stats.write32,
                'socket_counters': counters.snapshot(),
                'native_counters': {**native_counts,
                    'dmb_count_derived': native_counts['mmio_writes'] +
                                         native_counts['mmio_reads'] - 3},
                'electrical': 'OWNER_ATTESTED', 'dpidr': 'REQUIRES_OPENOCD_RECEIPT'}


def deadline_expired(_signum, _frame) -> None:
    raise TimeoutError('BOUNDED_SESSION_INTERRUPTED')


def main() -> int:
    args = parser().parse_args()
    signal.signal(signal.SIGTERM, deadline_expired)
    signal.signal(signal.SIGALRM, deadline_expired)
    signal.alarm(600)
    try:
        result = run(args)
    finally:
        signal.alarm(0)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
