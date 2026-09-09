#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
p=json.loads(Path(__file__).with_name('stm32g0-phase4.8b-routing-followup.json').read_text())
assert p['base_device']=='STM32G0B1CB'
assert set(p['active_exact_icpns_not_matched_by_current_openocd_ordering_surface'])=={'STM32G0B1CBT6N','STM32G0B1CBU6N'}
assert p['commercial_identity_verified'] is True
assert p['routing_gates_commercial_identity'] is False
print('STM32G0 Phase 4.8B routing follow-up contract: PASS')
