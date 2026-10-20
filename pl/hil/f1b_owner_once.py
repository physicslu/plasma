"""Owner-directive 2026-10-20 one-shot only. No general admission bypass.

AXI isolation is NOT established. Owner accepts hang/manual recovery risk.
Reuses existing FPGA Manager loader and native three-word read-only child.
"""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import platform
import importlib.util
from pl.hil import f1b
from pl.hil.swd04 import one_shot as s, development as d

ACK = 'F1B_ONE_SHOT_BOUND_PASSIVE_UIO'
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence'
CANDIDATE = Path('/lib/firmware/plasma-f1b-owner-20261020-once.bin')
RECOVERY = Path('/lib/firmware/base.bin')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def accept_exact(facts, ack):
    require(ack == ACK, 'explicit one-shot owner risk acknowledgment missing')
    require(facts == {'uio': 'uio1', 'driver': 'uio_pdrv_genirq',
                       'maps': [[0x40000000, 0x10000]],
                       'runtime': 'suspended', 'irq_counts': [0, 0]},
            'owner exception does not cover changed UIO condition')


def ownership():
    u = Path('/sys/class/uio/uio1')
    device = (u / 'device').resolve(strict=True)
    maps = [[int((p/'addr').read_text(), 0), int((p/'size').read_text(), 0)]
            for p in sorted((u/'maps').glob('map*'))]
    irq = [line for line in Path('/proc/interrupts').read_text().splitlines()
           if line.split() and line.split()[-1] == 'fabric']
    require(len(irq) == 1, 'fabric IRQ visibility changed')
    facts = dict(uio=u.name, driver=(device/'driver').resolve(strict=True).name,
                 maps=maps, runtime=(device/'power/runtime_status').read_text().strip(),
                 irq_counts=[int(v) for v in irq[0].split()[1:3]])
    accept_exact(facts, os.environ.get('OWNER_DEV_RISK_ACK'))
    # Every other overlapping bound platform/UIO owner remains denied.
    overlap = lambda a,b: a < 0x40010000 and b > 0x40000000
    for item in Path('/sys/class/uio').glob('uio*'):
        for p in (item/'maps').glob('map*'):
            a = int((p/'addr').read_text(), 0)
            if overlap(a, a+int((p/'size').read_text(), 0)):
                require(item == u, 'other overlapping UIO owner')
    for item in Path('/sys/bus/platform/devices').iterdir():
        if not (item/'driver').exists():
            continue
        match = re.match(r'^([0-9a-fA-F]+)\.', item.name)
        conflict = bool(match and overlap(int(match[1],16), int(match[1],16)+1))
        if (item/'resource').exists():
            for line in (item/'resource').read_text().splitlines():
                a,b,flags = (int(x,16) for x in line.split())
                conflict |= bool(flags & 0x200 and overlap(a,b+1))
        require(not conflict or item.resolve() == device, 'other bound platform owner')
    # No exceptions for ANY UIO or /dev/mem FD or VMA. Require full visibility.
    seen = 0
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            targets = []
            for fd in (p/'fd').iterdir():
                try:
                    targets.append(os.readlink(fd).split(' (deleted)')[0])
                except FileNotFoundError:
                    continue
            f1b.reject_retained_fds(targets)
            text = (p/'maps').read_text()
            for line in text.splitlines():
                fields = line.split()
                if len(fields) >= 6:
                    f1b.reject_retained_fds([fields[5]])
            seen += 1
        except FileNotFoundError:
            require(not p.exists(), 'live process incompletely observed')
    require(seen > 0, 'no proc visibility')
    return dict(exact_owner=facts, processes_observed=seen, complete_visibility=True,
                axi_isolation='UNPROVEN_OWNER_ACCEPTED_RISK')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot():
    return dict(boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                manager=s.MANAGER.joinpath('state').read_text().strip(),
                trace=s.manager_last_load(), services=s.service_snapshot(),
                owners=s.uio_snapshot())


def runtime():
    require(tuple(sys.version_info[:3]) == (3, 12, 13) and platform.machine() == 'armv7l'
            and sys.byteorder == 'little'
            and Path(sys.executable).resolve().is_relative_to('/opt/plasma/python/3.12.13'),
            'exact native CPython runtime required')


def identity_child():
    runtime()
    # Load the reviewed backend directly, avoiding unrelated package __init__/mock imports.
    path = ROOT/'software/python/plasma_interfaces/linux_mmio.py'
    spec = importlib.util.spec_from_file_location('f1b_native_mmio', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    aperture = module.MMIOAperture(f1b.BASE, frozenset(f1b.IDENTITY), frozenset(), f1b.LENGTH)
    with module.LinuxMMIO((aperture,), readonly=True) as mmio:
        observed = f1b.read_identity(mmio.read32)
        require(mmio.stats().read32 == 3 and mmio.stats().write32 == 0, 'access count')
    s.record_json(OUT/'identity.json', {'observed': observed})


def main():
    require(os.geteuid() == 0, 'root required')
    require(os.environ.get('OWNER_DEV_RISK_ACK') == ACK, 'owner ack required')
    runtime()
    from pl.hil.swd04.collect import fclk0_from_summary
    require(fclk0_from_summary(Path('/sys/kernel/debug/clk/clk_summary').read_text()) == 100000000, 'FCLK0 changed')
    require(b'xlnx,zynq-7000' in Path('/proc/device-tree/compatible').read_bytes().split(b'\0'), 'wrong board family')
    for path in (ROOT, CANDIDATE, RECOVERY):
        s.protected(path, file=path != ROOT)
    # Persistent one-shot claim: never retry this candidate write, including failure.
    lock = os.open(ROOT/'one-shot.claim', os.O_CREAT|os.O_EXCL|os.O_RDWR, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    OUT.mkdir(mode=0o700)
    result = dict(candidate_write_attempts=0, restore_write_attempts=0,
                  identity='NOT_RUN', restore='NOT_RUN', overall='NOT_RUN')
    def record(name, value):
        s.record_json(OUT/name, value)
        print(json.dumps({'event': name, 'data': value}), flush=True)
    try:
        require(sha(CANDIDATE) == f1b.BIN_SHA and CANDIDATE.stat().st_size == 4045568,
                'candidate bytes mismatch')
        require(sha(RECOVERY) == f1b.BASE_SHA, 'recovery bytes mismatch')
        before = snapshot()
        require(before['manager'] == 'operating' and ': writing base.bin to ' in before['trace'],
                'original manager provenance missing')
        record('original.json', before)
        record('ownership-before.json', ownership())
        record('intent.json', dict(status='RESTORE_REQUIRED', snapshot=before,
                                  candidate_sha=f1b.BIN_SHA, recovery_sha=f1b.BASE_SHA,
                                  owner_risk_ack=ACK, axi_isolation='UNPROVEN'))
        result['candidate_write_attempts'] = 1
        record('candidate-write-attempt.json', result.copy())
        # If this call fails/hangs, no blind finally restore is permitted.
        s.manager_write(CANDIDATE.name)
        record('candidate-loaded.json', dict(manager='operating', trace=s.manager_last_load()))
        s.run_child([sys.executable, '-m', 'pl.hil.f1b_owner_once', '--identity-child'])
        result['identity'] = json.loads((OUT/'identity.json').read_text())
        require(result['identity'] == {'observed': {str(k): v for k,v in f1b.IDENTITY.items()}},
                'three-word evidence mismatch')
        record('ownership-before-restore.json', ownership())
        require(snapshot()['boot'] == before['boot'], 'boot changed')
        require(s.MANAGER.joinpath('state').read_text().strip() == 'operating', 'manager changed')
        require(sha(RECOVERY) == f1b.BASE_SHA, 'recovery changed')
        result['restore_write_attempts'] = 1
        record('restore-write-attempt.json', result.copy())
        s.manager_write(RECOVERY.name)
        after = snapshot()
        require(after['boot'] == before['boot'] and after['owners'] == before['owners']
                and after['services'] == before['services'] and after['manager'] == 'operating'
                and ': writing base.bin to ' in after['trace'], 'restoration proof incomplete')
        record('restored.json', after)
        result.update(restore='PASS', overall='PASS_DEVELOPMENT_IDENTITY_LOAD_RESTORE')
    except BaseException as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        result['overall'] = ('UNKNOWN_MANUAL_RECOVERY' if result['candidate_write_attempts'] else 'NOT_RUN')
    record('result.json', result)
    return 0 if result['overall'].startswith('PASS') else 2


if __name__ == '__main__':
    if sys.argv[1:] == ['--identity-child']:
        require(os.environ.get('OWNER_DEV_RISK_ACK') == ACK and (OUT/'candidate-loaded.json').exists(), 'loaded receipt required')
        identity_child()
    else:
        raise SystemExit(main())
