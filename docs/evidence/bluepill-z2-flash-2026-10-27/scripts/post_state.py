"""Read-only post-DPIDR check for the exact Z2 PS session."""
import json
from pathlib import Path

directory = Path('/run/plasma-bluepill-step5-20261027')
socket = directory / 'swd.sock'
bridge_arg = b'/opt/plasma/bluepill-direct-20261026/scripts/bluepill-wordport-session.py'
owners = []
for proc in Path('/proc').iterdir():
    if not proc.name.isdecimal():
        continue
    try:
        argv = (proc / 'cmdline').read_bytes().split(b'\0')
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    if argv and (Path(argv[0].decode(errors='replace')).name == 'openocd' or
                 bridge_arg in argv):
        owners.append(int(proc.name))
print(json.dumps({'socket_dir_exists': directory.is_dir(),
                  'socket_dir_entries': sorted(p.name for p in directory.iterdir())
                      if directory.is_dir() else None,
                  'socket_exists': socket.exists(),
                  'openocd_or_bridge_pids': owners}, sort_keys=True))
