#!/usr/bin/env python3
import json
from pathlib import Path
from stm32f4_admission_policy import _package_and_pins
from stm32f4_coverage_gap_inventory import build_inventory

HERE=Path(__file__).resolve().parent
READY={"STM32F401VB","STM32F401VC","STM32F401VD","STM32F401VE","STM32F411VC","STM32F411VE","STM32F412VE","STM32F412VG","STM32F413VG"}
BLOCKED={"STM32F413VH","STM32F423VH"}
assert _package_and_pins('V','H')==('UFBGA','100')
e=json.loads((HERE/'stm32f4-phase4.2o-vh-ufbga100-policy-evidence.json').read_text())
assert set(e['immediately_policy_ready'])==READY and set(e['still_fail_closed'])==BLOCKED and e['production_write_applied'] is False
i=build_inventory(catalog_path=HERE/'openocd-parts-canonical.csv',canonical_path=HERE/'stm32f4-commercial-icpn.csv')
ready={x['base_device'] for x in i['gap']['policy_ready']}; blocked={x['base_device'] for x in i['gap']['policy_blocked']}
assert READY<=ready and BLOCKED<=blocked and READY.isdisjoint(blocked)
assert i['production']['exact_icpn_rows']==265
print('Phase 4.2O V/H UFBGA100 policy PASS')
