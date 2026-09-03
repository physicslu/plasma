#!/usr/bin/env python3
import csv, hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
EXPECTED={"STM32F469IEH6","STM32F469IGH6","STM32F469IGH6TR","STM32F469IGT6","STM32F469IIH6","STM32F469IIT6","STM32F479IGH6","STM32F479IIH6","STM32F479IIH7","STM32F479IIH7TR","STM32F479IIT6"}
plan=HERE/'stm32f4-phase4.2n-f469-f479-i-admission-plan.json'
audit=HERE/'stm32f4-phase4.2n-f469-f479-i-admission-audit.json'
with (HERE/'stm32f4-commercial-icpn.csv').open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
assert len(rows)>=265 and len(rows)==len({r['icpn'] for r in rows})
by={r['icpn']:r for r in rows}; assert EXPECTED<=set(by)
assert all(by[x]['openocd_target_config']=='tcl/target/stm32f4x.cfg' and by[x]['pin_count']=='176' for x in EXPECTED)
p=json.loads(plan.read_text()); assert hashlib.sha256(plan.read_bytes()).hexdigest()=='97dabf192eed56be10b84fa88290007b96e52e97518f371823478a8420f21434'
assert p['decision_counts']=={'admit':11,'already_present':0,'manual_review_required':0,'reject':0} and {x['icpn'] for x in p['candidates']}==EXPECTED
a=json.loads(audit.read_text()); assert a['status']=='published' and set(a['added_exact_icpns'])==EXPECTED and a['lifecycle_exclusions']==[]
print('Phase 4.2N post-admission closure PASS')
