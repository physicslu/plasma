#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
p=json.loads(Path(__file__).with_name('stm32g0-phase4.8b-policy-boundary.json').read_text())
assert p['manufacturer_identity_authority']=='official_st_dual_surface_browser_evidence'
assert p['openocd_authority']=='routing_only'
assert p['cmsis_alias_authority']=='routing_name_only'
for key in ('metadata_policy_defined','canonical_admission_authorized','production_write_authorized','programming_policy_defined','hil_qualified','runtime_support_claimed'):
    assert p[key] is False
print('STM32G0 Phase 4.8B policy boundary: PASS')
