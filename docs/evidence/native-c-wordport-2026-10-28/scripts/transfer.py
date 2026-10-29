"""Transfer only the approved Blue Pill images or private readbacks to pinned Z2."""
import json
from pathlib import Path
import stat
import subprocess
import sys

mode, name = sys.argv[1:]
assert mode in ('upload', 'download')
assert name in ('source/scripts/bluepill-wordport-session.py', 'source/software/python/plasma_interfaces/native_bluepill_word_port.py', 'libplasma_wordport_armv7.so', 'readback-v01-native.bin', 'readback-v01-native-tail.bin', 'readback-v01-native-600.bin')
assert mode == 'upload' or name in ('readback-v01-native.bin', 'readback-v01-native-tail.bin', 'readback-v01-native-600.bin')
here = Path(__file__).resolve().parent
login = Path.home() / '.config/plasma/z2-login-smoke.json'
assert stat.S_IMODE(login.stat().st_mode) == 0o600
data = json.loads(login.read_text())
assert data['ssh_username'] == 'xilinx'
host = data['ssh_host']
key = Path.home() / '.ssh/plasma_z2_ed25519'
known = Path.home() / '.ssh/known_hosts'
assert subprocess.run(['ssh-keygen', '-F', host, '-f', str(known)], capture_output=True, timeout=5).returncode == 0
local = here / name
remote_name = name.removeprefix('source/')
remote = f'xilinx@{host}:plasma-native-c-wordport-1199/{remote_name}'
src, dst = (str(local), remote) if mode == 'upload' else (remote, str(local))
command = ['scp', '-F', '/dev/null', '-i', str(key), '-o', 'BatchMode=yes',
           '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'UserKnownHostsFile=' + str(known), '-o', 'ConnectTimeout=8',
           src, dst]
result = subprocess.run(command, capture_output=True, text=True, timeout=180)
print(json.dumps({'mode': mode, 'name': name, 'exit': result.returncode,
                  'local_bytes': local.stat().st_size if local.is_file() else None,
                  'stderr_tail': result.stderr[-300:]}))
raise SystemExit(result.returncode)
