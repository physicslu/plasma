"""Read-only postrun owner and socket state for the exact Flash experiment."""
import json
from pathlib import Path

names = ('probe', 'read', 'page18', 'program', 'readback', 'reset')
directories = {
    name: Path('/run/plasma-bluepill-flash-' + name + '-20261027')
    for name in names
}
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
print(json.dumps({
    'openocd_or_bridge_pids': owners,
    'sockets': {name: {
        'directory_exists': directory.is_dir(),
        'entries': sorted(p.name for p in directory.iterdir())
            if directory.is_dir() else None,
        'socket_exists': (directory / 'swd.sock').exists(),
    } for name, directory in directories.items()},
}, sort_keys=True))
