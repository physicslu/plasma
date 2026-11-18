"""Bounded, dependency-free USB CDC heartbeat observation (no UART TX)."""
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import sys
import termios
import time

if len(sys.argv) != 2 or sys.argv[1] not in {'before', 'after', 'after_reset'}:
    raise SystemExit('usage: cdc_heartbeat.py before|after|after_reset')
label = sys.argv[1]
here = Path(__file__).resolve().parent
report = here / f'cdc-{label}.json'
assert not report.exists(), 'EVIDENCE_ALREADY_EXISTS'
matches = []
for entry in Path('/sys/class/tty').glob('ttyACM*'):
    resolved = (entry / 'device').resolve()
    for parent in (resolved, *resolved.parents):
        vendor, product = parent / 'idVendor', parent / 'idProduct'
        if vendor.is_file() and product.is_file():
            if (vendor.read_text().strip().lower(),
                product.read_text().strip().lower()) == ('cafe', '4001'):
                node = Path('/dev') / entry.name
                if stat.S_ISCHR(node.stat().st_mode) and os.access(node, os.R_OK | os.W_OK):
                    matches.append(node)
            break
assert len(matches) == 1, 'BLUE_PILL_CDC_NOT_UNIQUE_OR_ACCESS_DENIED'
node = matches[0]
busy = subprocess.run(['fuser', '-s', str(node)], capture_output=True, timeout=4)
assert busy.returncode == 1, 'BLUE_PILL_CDC_BUSY_OR_UNCERTAIN'
pattern = re.compile(r'^HB version=0\.1 seq=(\d+) uptime_ms=(\d+)$')
fd = os.open(node, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
try:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    opened_ns = time.time_ns()
    deadline = time.monotonic() + 6.0
    buf = bytearray()
    samples = []
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], max(0.0, min(0.25, deadline-time.monotonic())))
        if not ready:
            continue
        block = os.read(fd, 4096)
        if not block:
            continue
        buf.extend(block)
        while b'\n' in buf:
            raw, _, rest = buf.partition(b'\n')
            buf = bytearray(rest)
            line = raw.decode('ascii', errors='replace').strip()
            match = pattern.fullmatch(line)
            if match:
                samples.append({'host_unix_ns': time.time_ns(),
                                'seq': int(match.group(1)),
                                'uptime_ms': int(match.group(2))})
    result = {'label': label, 'device': node.name, 'opened_unix_ns': opened_ns,
              'closed_unix_ns': time.time_ns(), 'heartbeat_count': len(samples),
              'samples': samples,
              'strictly_increasing_seq': all(b['seq'] > a['seq'] for a,b in zip(samples,samples[1:])),
              'strictly_increasing_uptime': all(b['uptime_ms'] > a['uptime_ms'] for a,b in zip(samples,samples[1:]))}
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if len(samples) >= 3 and result['strictly_increasing_seq']
                     and result['strictly_increasing_uptime'] else 1)
finally:
    os.close(fd)
