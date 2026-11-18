import hashlib
import json
from pathlib import Path

stage = Path('/home/xilinx/plasma-native-c-wordport-1199')
readback = stage / 'readback-v01-native.bin'
image = Path('/home/xilinx/plasma-bluepill-ab-20261028/plasma-blue-pill-cdc.bin')
assert image.is_file() and image.stat().st_size == 18768
data = readback.read_bytes() if readback.is_file() else b''
expected = image.read_bytes()
print(json.dumps({'readback_exists': readback.is_file(), 'bytes': len(data),
                  'sha256': hashlib.sha256(data).hexdigest() if data else None,
                  'prefix_mismatches': sum(a != b for a,b in zip(data, expected)),
                  'prefix_complete': len(data) == len(expected)}))
