"""Remove SWDIO data from the unknown-content Flash-page read trace."""
import hashlib
from pathlib import Path
import re
import zipfile

source = Path('.work/bluepill-flash-20261027/read.sr')
target = Path('.work/bluepill-pr-archive/last-page-read-clock-only.sr')
assert not target.exists(), 'SANITIZED_WAVE_ALREADY_EXISTS'
expected = '93ba903a2f1a733a4d7e68ff502d035aa6b68f4ee0e218238d3669aa1ac9bbf8'
assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, 'SOURCE_WAVE_CHANGED'
with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(target, 'w') as outgoing:
    for name in incoming.namelist():
        info = incoming.getinfo(name)
        data = incoming.read(name)
        if re.fullmatch(r'logic-1-[0-9]+', name):
            assert len(data) % 2 == 0
            modified = bytearray(data)
            for offset in range(0, len(modified), 2):
                modified[offset] &= ~0x02  # Clear CH1/SWDIO; retain clock/reference.
            data = bytes(modified)
        outgoing.writestr(info, data)
print({'source_sha256': expected,
       'sanitized_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
       'sanitized_bytes': target.stat().st_size})
