#!/usr/bin/env python3
import csv, hashlib, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
UFBGA={"STM32F411VEH6","STM32F411VEH6TR","STM32F412VEH3TR","STM32F412VEH6","STM32F412VEH6TR","STM32F412VGH6","STM32F412VGH6TR","STM32F413VGH6"}
LQFP={"STM32F411VET6","STM32F411VET6TR","STM32F412VET3","STM32F412VET3TR","STM32F412VET6","STM32F412VET6TR","STM32F412VGT6","STM32F412VGT6TR","STM32F412VGT7","STM32F413VGT3","STM32F413VGT3TR","STM32F413VGT6","STM32F413VGT6TR"}
EXPECTED=UFBGA|LQFP
plan=HERE/'stm32f4-phase4.2q-vh-admission-batch2-plan.json'; audit=HERE/'stm32f4-phase4.2q-vh-admission-batch2-audit.json'
with (HERE/'stm32f4-commercial-icpn.csv').open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
assert len(rows)>=304 and len(rows)==len({r['icpn'] for r in rows})
by={r['icpn']:r for r in rows}; assert EXPECTED<=set(by); assert 'STM32F413VGH3' not in by
assert all(by[x]['openocd_target_config']=='tcl/target/stm32f4x.cfg' and by[x]['pin_count']=='100' for x in EXPECTED)
assert all(by[x]['package']=='UFBGA' for x in UFBGA) and all(by[x]['package']=='LQFP' for x in LQFP)
p=json.loads(plan.read_text()); assert hashlib.sha256(plan.read_bytes()).hexdigest()=='5e89433425228adf250ceda168eb4030638b9b5e3d07f5b79c1dd6afead9444b'
assert p['decision_counts']=={'admit':21,'already_present':0,'manual_review_required':0,'reject':0} and {x['icpn'] for x in p['candidates']}==EXPECTED
a=json.loads(audit.read_text()); assert a['status']=='published' and set(a['added_exact_icpns'])==EXPECTED and a['lifecycle_exclusions']==['STM32F413VGH3']
print('Phase 4.2Q post-admission closure PASS')
