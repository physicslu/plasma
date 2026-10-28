import json
import os
from pathlib import Path
import pwd
import shutil

source = Path('/opt/plasma/bluepill-direct-20261026')
target = Path('/home/xilinx/plasma-native-c-wordport-1199')
assert source.is_dir() and not source.is_symlink()
assert target.is_dir() or not target.exists()
assert (source / 'scripts/bluepill-wordport-session.py').is_file()
assert (source / 'software/python/plasma_interfaces/bluepill_remote_bitbang.py').is_file()
if not target.exists():
    shutil.copytree(source, target, symlinks=False)
assert (target / 'scripts/bluepill-wordport-session.py').is_file()
user = pwd.getpwnam('xilinx')
for entry in (target, *target.rglob('*')):
    if entry.is_symlink():
        raise RuntimeError('UNEXPECTED_SYMLINK')
    os.chown(entry, user.pw_uid, user.pw_gid)
print(json.dumps({'stage':str(target),'base':str(source),'result':'STAGED'}))
