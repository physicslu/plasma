#!/usr/bin/env python3
import csv, hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
UFBGA={"STM32F401VBH3","STM32F401VBH6","STM32F401VCH6","STM32F401VCH7","STM32F401VDH6","STM32F401VEH6","STM32F401VEH6TR","STM32F401VEH7"}
LQFP={"STM32F401VBT6","STM32F401VBT6TR","STM32F401VCT6","STM32F401VCT7","STM32F401VDT6","STM32F401VDT6TR","STM32F401VET6","STM32F401VET6TR","STM32F411VCT6","STM32F411VCT6TR"}
EXPECTED=UFBGA|LQFP
plan=HERE/'stm32f4-phase4.2p-vh-admission-batch1-plan.json'
audit=HERE/'stm32f4-phase4.2p-vh-admission-batch1-audit.json'
with (HERE/'stm32f4-commercial-icpn.csv').open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
assert len(rows)>=283 and len(rows)==len({r['icpn'] for r in rows})
by={r['icpn']:r for r in rows}; assert EXPECTED<=set(by)
assert all(by[x]['openocd_target_config']=='tcl/target/stm32f4x.cfg' and by[x]['pin_count']=='100' for x in EXPECTED)
assert all(by[x]['package']=='UFBGA' for x in UFBGA) and all(by[x]['package']=='LQFP' for x in LQFP)
p=json.loads(plan.read_text()); assert hashlib.sha256(plan.read_bytes()).hexdigest()=='415a96e772bb422b0af02795f32034fc738d3a0af1198f3a9e9669496c6f07f6'
assert p['decision_counts']=={'admit':18,'already_present':0,'manual_review_required':0,'reject':0} and {x['icpn'] for x in p['candidates']}==EXPECTED
a=json.loads(audit.read_text()); assert a['status']=='published' and set(a['added_exact_icpns'])==EXPECTED and a['lifecycle_exclusions']==[]
print('Phase 4.2P post-admission closure PASS')
