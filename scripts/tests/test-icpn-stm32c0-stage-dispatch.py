#!/usr/bin/env python3
"""Offline positive/negative stage routing checks."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location("c0stage",ROOT/"scripts/ci/icpn_stm32c0_stage_dispatch.py")
assert s and s.loader
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)
m.self_test()
for event in ("pull_request","push"):
    assert m.affected(["docs/README.md"],event)==[]
    assert m.affected([m.WF],event)==list(m.STAGES)
    assert m.affected(["data/device-catalog/research/openocd-parts-canonical.csv"],event)==["c01","c02","c04"]
    assert m.affected(["data/device-catalog/research/evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11/raw.json"],event)==["c02","c03","c04"]
    assert m.affected(["data/device-catalog/research/stm32c0-phase-c0.5-publication-abc.json"],event)==["c05"]
try: m.affected([],"workflow_dispatch")
except ValueError: pass
else: raise AssertionError("manual entry allowed")
print("C0 stage positive and negative routing PASS")
