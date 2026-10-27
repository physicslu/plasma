"""Manual guarded Z2 PS SWCLK/SWDIO 3-second diagnostic, with Blue Pill removed."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PROTECTED = Path('/root/plasma-path2-approved')
BUNDLE = Path('/opt/plasma/bluepill-direct-20261026')
BASE = 0x40008000
BOOT = '4cefdc0c-f586-4d19-b126-1d8e1108c8f1'
PIN = '55f6db3bc5fa866135e5a9070175928d044e53ce'
IMAGE_SHA = 'bfbd3d872caeff05a8f9daa0829b6292e5b5036c6c6b927d6c779e13fe9ec1a1'
MANIFEST_SHA = '5f5fa580e9b437ce3a9377313bdfb4fc6012031270e1544c12034ccf3ca0fb98'
BARRIER_SHA = '260d17d87e2edc5a6c97757b47a6ede78fa024d9ac19fbb9020ac257600a6555'


def need(condition, code):
    if not condition:
        raise RuntimeError(code)


def run():
    need(os.geteuid() == 0, 'ROOT_REQUIRED')
    need(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT, 'BOOT_CHANGED')
    need((PROTECTED / '.plasma-path2-source-commit').read_text().strip() == PIN, 'ROOT_PIN_CHANGED')
    subprocess.run(['sha256sum', '--check', '--status', '.plasma-path2-source-sha256'],
                   cwd=PROTECTED, check=True, timeout=15)
    sys.path.insert(0, str(PROTECTED))
    root = importlib.import_module('pl.hil.fpga_image_root')
    root.trusted_local()
    root.native_runtime_preflight()
    release = root.read_image_manifest()
    need(root.manifest_sha256() == MANIFEST_SHA, 'MANIFEST_CHANGED')
    need(release.firmware_sha256 == IMAGE_SHA and release.axi_base == BASE,
         'IMAGE_OR_BASE_CHANGED')
    port = root.guard.RootZ2TargetPort(release=release)
    sys.path.insert(0, str(BUNDLE / 'software/python'))
    from plasma_interfaces.fixed_abi_mmio_port import ARMv7DMBBarrier
    from plasma_interfaces.linux_mmio import LinuxMMIO
    from plasma_interfaces.bluepill_z2_word_port import BluepillZ2WordPort, bluepill_z2_aperture
    barrier_path = BUNDLE / 'software/python/native/libplasma_mmio_barrier.so'
    need(hashlib.sha256(barrier_path.read_bytes()).hexdigest() == BARRIER_SHA,
         'BARRIER_CHANGED')
    barrier = ARMv7DMBBarrier(str(barrier_path), sha256=BARRIER_SHA)
    barrier()
    with port.exclusive():
        state = root.read_state(release)
        need(isinstance(state, dict) and state.get('status') == 'IMAGE' and
             state.get('boot_id') == BOOT and state.get('firmware_sha256') == IMAGE_SHA and
             state.get('manifest_sha256') == MANIFEST_SHA and state.get('test_count', 0) >= 3,
             'IMAGE_CHECKPOINT_CHANGED')
        facts = root.live_report(port, release, release.firmware_name)
        need(facts['target_boot_id'] == BOOT, 'LIVE_BOOT_CHANGED')
        for node in ('/dev/mem', '/dev/uio1'):
            check = subprocess.run(['fuser', '-s', node], capture_output=True, timeout=4)
            need(check.returncode == 1, 'MMIO_BUSY_OR_UNKNOWN')
        records = []
        with ExitStack() as stack:
            mmio = stack.enter_context(LinuxMMIO((bluepill_z2_aperture(),)))
            lease = stack.enter_context(mmio.claim_site(1, BASE))
            word = BluepillZ2WordPort(lease, barrier=barrier)
            ident = [word.read32(BASE), word.read32(BASE + 4)]
            need(ident == [0x50425357, 0x10000], 'GPIO_ABI_MISMATCH')
            baseline = word.read32(BASE + 12)
            need(baseline & 0x0E == 0x08, 'NOT_RESET_SAFE_HIZ_LOW')
            last_confirmed_drive = None
            try:
                # OE=1 only while the Blue Pill is physically removed.
                # 0x04: CLK=0 DIO=0 OE=1; 0x07: CLK=1 DIO=1 OE=1.
                for value, hold_s in ((0x04, 3.0), (0x07, 3.0), (0x04, 3.0)):
                    before_ns = time.time_ns()
                    word.write32(BASE + 8, value)
                    word.write_barrier()
                    last_confirmed_drive = value
                    after_ns = time.time_ns()
                    sample = word.read32(BASE + 12)
                    records.append({'drive': value, 'write_before_unix_ns': before_ns,
                                    'barrier_after_unix_ns': after_ns, 'sample': sample,
                                    'sample_swclk_bit1': (sample >> 1) & 1,
                                    'sample_swdio_oe_bit2': (sample >> 2) & 1,
                                    'sample_swdio_out_bit3': (sample >> 3) & 1,
                                    'sample_swdio_pad_bit0': sample & 1})
                    time.sleep(hold_s)
            finally:
                # Release SWDIO output and return CLOCK low even on interruption.
                if last_confirmed_drive is not None:
                    word.write32(BASE + 8, 0x02)
                    word.write_barrier()
            final_sample = word.read32(BASE + 12)
            stats = mmio.stats()
        return {'boot_id': BOOT, 'image_sha256': IMAGE_SHA,
                'baseline_sample': baseline, 'identity_words': ident,
                'writes': records, 'mmio_read32': stats.read32,
                'mmio_write32': stats.write32,
                'final_sample': final_sample,
                'internal_swclk_pass': [r['sample_swclk_bit1'] for r in records] == [0, 1, 0]
                    and all(r['sample_swdio_oe_bit2'] == 1 for r in records),
                'swdio_output_state_pass': [r['sample_swdio_out_bit3'] for r in records] == [0, 1, 0],
                'swdio_pad_feedback_pass': [r['sample_swdio_pad_bit0'] for r in records] == [0, 1, 0],
                'final_hiz_low_pass': final_sample & 0x0e == 0x08}


def timeout(_signum, _frame):
    raise TimeoutError('STAGE_A_DEADLINE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bluepill-removed', action='store_true',
                        help='Attest PmodBB P1/P2 are disconnected from Blue Pill and any other driver')
    args = parser.parse_args()
    if not args.bluepill_removed:
        parser.error('Blue Pill must be removed before DIO output enable')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(25)
    try:
        result = run()
    finally:
        signal.alarm(0)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if all(result[key] for key in ('internal_swclk_pass',
                 'swdio_output_state_pass', 'swdio_pad_feedback_pass',
                 'final_hiz_low_pass')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
