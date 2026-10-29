"""Reversibly remove exactly the three unpinned caches blocking Root Entry."""
import hashlib
import json
from pathlib import Path

root = Path('/root/plasma-path2-approved')
quarantine = Path('/root/plasma-path2-bytecode-quarantine-20261027-step12')
expected = {
    'pl/hil/__pycache__/fpga_image_root.cpython-312.pyc',
    'pl/hil/__pycache__/fpga_image_guard.cpython-312.pyc',
    'pl/hil/__pycache__/fpga_image_admission.cpython-312.pyc',
}
found = {str(p.relative_to(root)) for p in root.rglob('*')
         if p.is_file() and p.suffix in {'.pyc', '.pyo'}}
assert found == expected, 'BYTECODE_SET_CHANGED'
assert not quarantine.exists(), 'QUARANTINE_EXISTS'
for name in expected:
    source = root / name
    assert source.is_file() and not source.is_symlink(), 'SOURCE_CHANGED'
quarantine.mkdir(mode=0o700)
receipts = {}
for name in sorted(expected):
    source = root / name
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    target = quarantine / name
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    source.rename(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest, 'MOVED_SHA_CHANGED'
    receipts[name] = digest
assert not any(p.is_file() and p.suffix in {'.pyc', '.pyo'}
               for p in root.rglob('*')), 'BYTECODE_REMAINS'
print(json.dumps({'result': 'QUARANTINED', 'files': receipts,
                  'quarantine': str(quarantine)}, sort_keys=True))
