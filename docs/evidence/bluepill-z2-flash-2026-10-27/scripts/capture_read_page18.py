"""Passively capture Z2 PS OpenOCD reading one STM32F1 Flash page."""
import base64
import fcntl
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WAVE = HERE / 'page18-read.sr'
REPORT = HERE / 'page18-read-report.json'
BACKUP = HERE / 'page18-backup.bin'
assert not WAVE.exists() and not REPORT.exists() and not BACKUP.exists(), 'EVIDENCE_ALREADY_EXISTS'
APP = Path('/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage')
assert hashlib.sha256(APP.read_bytes()).hexdigest() == \
    'b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475', \
    'APPIMAGE_SHA_CHANGED'
matches = []
for entry in Path('/sys/bus/usb/devices').iterdir():
    try:
        if ((entry / 'idVendor').read_text().strip().lower(),
            (entry / 'idProduct').read_text().strip().lower()) != ('77a1', '01a2'):
            continue
        bus, dev = (int((entry / field).read_text()) for field in ('busnum', 'devnum'))
        node = Path(f'/dev/bus/usb/{bus:03}/{dev:03}')
        assert stat.S_ISCHR(node.stat().st_mode) and os.access(node, os.R_OK | os.W_OK)
        matches.append((f'{bus}.{dev}', node))
    except (FileNotFoundError, PermissionError):
        continue
assert len(matches) == 1, 'LA_NOT_UNIQUE_OR_ACCESS_DENIED'
conn, node = matches[0]
lock = Path('/run/lock/plasma-la2016.lock')
assert lock.is_file() and not lock.is_symlink(), 'LA_LOCK_INVALID'
with lock.open('rb') as held:
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    busy = subprocess.run(['fuser', '-s', str(node)], capture_output=True, timeout=4)
    assert busy.returncode == 1, 'LA_BUSY_OR_UNCERTAIN'
    argv = [str(APP), '--appimage-extract-and-run', '--loglevel', '3',
            '--driver', 'kingst-la2016:conn=' + conn,
            '--config', 'samplerate=5m', '--channels', 'CH0,CH1,CH2,CH3',
            '--samples', '200000000', '--output-file', str(WAVE)]
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
    remote = None
    trigger_ns = None
    capture_start_ns = time.time_ns()
    try:
        if ready.wait(12) and capture.poll() is None:
            trigger_ns = time.time_ns()
            remote = subprocess.run([
                sys.executable,
                str(REPO / '.work/bluepill-dpidr-direct-20261027/remote.py'),
                str(HERE / 'run_read_page18.py')],
                capture_output=True, text=True, timeout=75)
        try:
            capture.wait(timeout=65)
        except subprocess.TimeoutExpired:
            os.killpg(capture.pid, signal.SIGTERM)
            capture.wait(timeout=4)
    finally:
        if capture.poll() is None:
            os.killpg(capture.pid, signal.SIGTERM)
            try:
                capture.wait(timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(capture.pid, signal.SIGKILL)
                capture.wait(timeout=2)
    reader.join(timeout=1)
    remote_summary = None
    backup_saved = False
    if remote and remote.stdout:
        try:
            remote_summary = json.loads(remote.stdout)
            encoded = remote_summary.pop('page_base64', None)
            if encoded:
                payload = base64.b64decode(encoded, validate=True)
                if len(payload) == 1024 and hashlib.sha256(payload).hexdigest() == remote_summary.get('page_sha256'):
                    BACKUP.write_bytes(payload)
                    backup_saved = True
        except (ValueError, TypeError):
            remote_summary = {'parse_error': True}
    result = {
        'capture_start_unix_ns': capture_start_ns,
        'la_session_start_observed': ready.is_set(),
        'remote_trigger_unix_ns': trigger_ns,
        'capture_finish_unix_ns': time.time_ns(),
        'la_connection': conn,
        'la_exit': capture.returncode,
        'la_log_tail': ''.join(lines)[-2500:],
        'remote_exit': remote.returncode if remote else None,
        'remote_stdout': remote_summary,
        'backup_saved': backup_saved,
        'backup_sha256': hashlib.sha256(BACKUP.read_bytes()).hexdigest() if backup_saved else None,
        'remote_stderr': remote.stderr[-1500:] if remote else '',
        'wave_sha256': hashlib.sha256(WAVE.read_bytes()).hexdigest() if WAVE.is_file() else None,
        'wave_bytes': WAVE.stat().st_size if WAVE.is_file() else None,
    }
    REPORT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: result[key] for key in (
        'la_session_start_observed', 'remote_trigger_unix_ns', 'la_exit',
        'remote_exit', 'remote_stdout', 'remote_stderr', 'backup_saved',
        'backup_sha256', 'wave_sha256', 'wave_bytes')}, sort_keys=True))
    raise SystemExit(0 if capture.returncode == 0 and remote and remote.returncode == 0
                     and backup_saved else 1)
