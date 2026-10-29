"""Passive LA2016 capture overlapping page-0 erase/program/verify."""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import threading
import time

here = Path(__file__).resolve().parent
wave = here / 'native-v01-erase-program.sr'
report = here / 'native-v01-erase-program-report.json'
assert not wave.exists() and not report.exists(), 'EVIDENCE_ALREADY_EXISTS'
app = Path('/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage')
assert hashlib.sha256(app.read_bytes()).hexdigest() == 'b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475', 'APPIMAGE_SHA_CHANGED'
matches = []
for entry in Path('/sys/bus/usb/devices').iterdir():
    try:
        vid = (entry / 'idVendor').read_text().strip().lower()
        pid = (entry / 'idProduct').read_text().strip().lower()
    except (FileNotFoundError, PermissionError):
        continue
    if (vid,pid) != ('77a1','01a2'):
        continue
    bus = int((entry / 'busnum').read_text())
    dev = int((entry / 'devnum').read_text())
    node = Path(f'/dev/bus/usb/{bus:03}/{dev:03}')
    assert stat.S_ISCHR(node.stat().st_mode) and os.access(node, os.R_OK | os.W_OK), 'LA_USB_ACCESS_DENIED'
    matches.append(f'{bus}.{dev}')
assert len(matches) == 1, 'LA_NOT_UNIQUE'
conn = matches[0]
argv = [str(app), '--appimage-extract-and-run', '--loglevel', '3',
        '--driver', 'kingst-la2016:conn=' + conn,
        '--config', 'samplerate=5m', '--channels', 'CH0,CH1,CH2,CH3',
        '--samples', '200000000', '--output-file', str(wave)]
capture = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, bufsize=1, start_new_session=True)
lines = []
ready = threading.Event()

def drain():
    assert capture.stdout is not None
    for line in capture.stdout:
        lines.append(line)
        if 'session: Starting.' in line:
            ready.set()

reader = threading.Thread(target=drain, daemon=True)
reader.start()
capture_start_ns = time.time_ns()
remote_start_ns = remote_end_ns = None
remote = None
try:
    if ready.wait(15) and capture.poll() is None:
        remote_start_ns = time.time_ns()
        remote = subprocess.run([sys.executable, str(here.parent / 'bluepill-ab-20261028' / 'remote_long.py'),
                                 str(here / 'z2_native_flash.py'), 'program_v01'],
                                capture_output=True, text=True, timeout=7200)
        remote_end_ns = time.time_ns()
    if capture.poll() is None:
        capture.wait(timeout=60)
finally:
    if capture.poll() is None:
        os.killpg(capture.pid, signal.SIGTERM)
        try:
            capture.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(capture.pid, signal.SIGKILL)
            capture.wait(timeout=3)
reader.join(timeout=2)
data = {
    'capture_start_unix_ns': capture_start_ns,
    'capture_finish_unix_ns': time.time_ns(),
    'la_connection': conn,
    'la_session_start_observed': ready.is_set(),
    'la_exit': capture.returncode,
    'la_log_tail': ''.join(lines)[-1800:],
    'remote_start_unix_ns': remote_start_ns,
    'remote_finish_unix_ns': remote_end_ns,
    'remote_exit': remote.returncode if remote else None,
    'remote_stdout': remote.stdout if remote else None,
    'remote_stderr': remote.stderr if remote else None,
    'wave_bytes': wave.stat().st_size if wave.is_file() else None,
    'wave_sha256': hashlib.sha256(wave.read_bytes()).hexdigest() if wave.is_file() else None,
}
report.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
print(json.dumps({key:data[key] for key in ('la_session_start_observed','la_exit','remote_exit',
    'remote_stdout','remote_stderr','wave_bytes','wave_sha256','remote_start_unix_ns',
    'remote_finish_unix_ns','capture_start_unix_ns','capture_finish_unix_ns')}, sort_keys=True))
raise SystemExit(0 if ready.is_set() and capture.returncode == 0 and remote and remote.returncode == 0 else 1)
