#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HISTORICAL=ROOT/"data/device-catalog/research/stm32f1-phase2.9-post-admission-canonical.csv"
LEGACY_VALIDATOR=ROOT/"data/ic-support/benchmarks/stm32f103c/validate_source_lock.py"
LEGACY_PATH=Path("data/device-catalog/research/stm32f1-commercial-icpn.csv")

def main()->int:
    spec=importlib.util.spec_from_file_location("stm32f103c_legacy_source_lock",LEGACY_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load historical STM32F103C source-lock validator")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with tempfile.TemporaryDirectory() as temp:
        overlay=Path(temp)
        target=overlay/LEGACY_PATH
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(HISTORICAL.read_bytes())
        module.REPO_ROOT=overlay
        return int(module.main())

if __name__=="__main__":
    raise SystemExit(main())
