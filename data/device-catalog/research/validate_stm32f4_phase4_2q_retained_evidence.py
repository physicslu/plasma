#!/usr/bin/env python3
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
SRC=HERE/'evidence/stm32f4-phase4.2q-vh-admission-batch2-live-2026-09-03'
BASELINE=HERE/'stm32f4-phase4.2q-vh-admission-batch2-baseline.json'
VALIDATOR=HERE/'validate_stm32f4_retained_evidence.py'
manifest=json.loads((SRC/'manifest.json').read_text())
with tempfile.TemporaryDirectory(prefix='phase42q-retained-') as td:
    dst=Path(td)
    shutil.copy2(SRC/'manifest.json',dst/'manifest.json')
    for entry in manifest['files']:
        rel=Path(entry['path']); target=dst/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(SRC/rel,target)
    subprocess.run([sys.executable,str(VALIDATOR),'--evidence-dir',str(dst),'--baseline',str(BASELINE)],check=True)
print('Phase 4.2Q retained-evidence replay PASS')
