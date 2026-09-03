#!/usr/bin/env python3
import csv
import json
import tempfile
from pathlib import Path
from stm32f4_admission_policy import _package_and_pins
from stm32f4_coverage_gap_inventory import build_inventory
from stm32f4_historical_replay import admitted_after_phase42

HERE=Path(__file__).resolve().parent
READY={"STM32F401VB","STM32F401VC","STM32F401VD","STM32F401VE","STM32F411VC","STM32F411VE","STM32F412VE","STM32F412VG","STM32F413VG"}
HISTORICALLY_BLOCKED={"STM32F413VH","STM32F423VH"}
assert _package_and_pins('V','H')==('UFBGA','100')
e=json.loads((HERE/'stm32f4-phase4.2o-vh-ufbga100-policy-evidence.json').read_text())
assert set(e['immediately_policy_ready'])==READY and set(e['still_fail_closed'])==HISTORICALLY_BLOCKED and e['production_write_applied'] is False
with tempfile.TemporaryDirectory() as tmp:
    with (HERE/'stm32f4-commercial-icpn.csv').open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f); fields=list(reader.fieldnames or [])
        rows=[row for row in reader if not admitted_after_phase42(row,'o')]
    historical=Path(tmp)/'stm32f4-commercial-icpn.csv'
    with historical.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n'); writer.writeheader(); writer.writerows(rows)
    i=build_inventory(catalog_path=HERE/'openocd-parts-canonical.csv',canonical_path=historical)
    ready={x['base_device'] for x in i['gap']['policy_ready']}; blocked={x['base_device'] for x in i['gap']['policy_blocked']}
    assert READY<=ready and READY.isdisjoint(blocked)
    # Phase 4.2O evidence remains immutable, while later policy may legitimately
    # retire the H flash-size blocker for these two Base Devices.
    assert HISTORICALLY_BLOCKED<=ready and HISTORICALLY_BLOCKED.isdisjoint(blocked)
    assert i['production']['exact_icpn_rows']==265
print('Phase 4.2O V/H UFBGA100 policy PASS')
