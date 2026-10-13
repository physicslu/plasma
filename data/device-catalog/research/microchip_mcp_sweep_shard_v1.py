#!/usr/bin/env python3
"""Shard entire source-pinned Microchip DFP research batch queue, read-only.

Each vendor batch is a separate subprocess with its own immutable archive.
A timeout or NOT_FOUND never becomes an accepted SKU or an EOL assertion.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from time import sleep

import microchip_mcp_batch_plan_v1 as planner
from microchip_dfp_index_inventory_v1 import archived_inventory

HERE = Path(__file__).resolve().parent
CAPTURE = HERE / 'microchip_mcp_plan_capture_v1.py'
# Already captured by historical GitHub run 38348043707; archive remains
# source pinned and independently replayable; no re-query in this sweep.
PREVIOUS_CAPTURED_IDS = frozenset((
    '8bit-0001', '8bit-0037', '8bit-0074', '8bit-0111',
    '16bit-0001', '16bit-0023', '16bit-0046', '16bit-0068',
    '32bit-pic-sam-0001', '32bit-pic-sam-0021',
    '32bit-pic-sam-0041', '32bit-pic-sam-0061',
    'wireless-0001', 'wireless-0002', 'wireless-0003', 'wireless-0004',
))

def require(test, message):
    if not test:
        raise ValueError(message)

def select(plan, inventory, digest, shard, shard_count):
    require(type(shard_count) is int and 1 <= shard_count <= 16,
            'shard count must be 1..16')
    require(type(shard) is int and 0 <= shard < shard_count,
            'invalid shard identity')
    expected = planner.plan_inventory(inventory, digest,
                                      batch_size=plan.get('batch_size'))
    require(expected == plan, 'untrusted batch plan mismatches original DFP bytes')
    require(plan['batch_size'] == 10, 'full sweep requires bounded 10-query batches')
    all_ids = {b['batch_id'] for b in expected['batches']}
    require(PREVIOUS_CAPTURED_IDS <= all_ids, 'previous captures not in source plan')
    batches = [b for index,b in enumerate(plan['batches'])
               if index % shard_count == shard and
               b['batch_id'] not in PREVIOUS_CAPTURED_IDS]
    return batches

def execute(plan, inventory, digest, shard, shard_count,
            evidence_root, plan_path, output_root, log_root,
            per_batch_timeout=180):
    require(type(per_batch_timeout) is int and
            60 <= per_batch_timeout <= 240, 'invalid vendor batch timeout')
    batches = select(plan, inventory, digest, shard, shard_count)
    output_root,log_root = Path(output_root).resolve(),Path(log_root).resolve()
    require('production' not in {p.lower() for p in output_root.parts} and
            'production' not in {p.lower() for p in log_root.parts},
            'Production research output forbidden')
    require(output_root != log_root and
            not output_root.is_relative_to(log_root) and
            not log_root.is_relative_to(output_root),
            'logs cannot contaminate source-attested batch archive')
    require(not output_root.exists() and not log_root.exists(),
            'refuse overwrite of prior live research evidence')
    output_root.mkdir(parents=True)
    log_root.mkdir(parents=True)
    journal=log_root / f'shard-{shard:02d}-attempts.jsonl'
    counts={'fully_replayed_batches':0,
            'partial_or_unverified_batches':0,
            'timed_out_batches':0,
            'attempted_device_names':0}
    for batch in batches:
        batch_id=batch['batch_id']
        command=[sys.executable,str(CAPTURE),
                 '--evidence-root',str(evidence_root),
                 '--plan',str(plan_path),
                 '--batch-id',batch_id,
                 '--output-root',str(output_root),
                 '--workers','1','--capture']
        began=datetime.now(timezone.utc).isoformat()
        state='unverified'
        try:
            completed=subprocess.run(command,text=True,stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT,
                                     timeout=per_batch_timeout,check=False)
            (log_root / (batch_id+'.log')).write_text(completed.stdout,
                                                      encoding='utf-8')
            state=('fully_replayed_batch' if completed.returncode == 0
                   else 'partial_or_unverified_batch')
        except subprocess.TimeoutExpired as error:
            state='timed_out_unverified_batch'
            partial=error.stdout or b''
            if isinstance(partial,bytes):
                partial=partial.decode('utf-8','replace')
            (log_root/(batch_id+'.log')).write_text(partial+'\nTIMEOUT\n',
                                                   encoding='utf-8')
        counts['attempted_device_names']+=len(batch['queries'])
        if state=='fully_replayed_batch':
            counts['fully_replayed_batches']+=1
        elif state=='timed_out_unverified_batch':
            counts['timed_out_batches']+=1
        else:
            counts['partial_or_unverified_batches']+=1
        record={'batch_id':batch_id,'lane':batch['lane'],
                'planned_queries':len(batch['queries']),
                'query_list_sha256':batch['query_list_sha256'],
                'attempted_at_utc':began,'state':state}
        with journal.open('a',encoding='utf-8') as file:
            file.write(json.dumps(record,sort_keys=True)+'\n')
            file.flush()
        print(json.dumps(record,sort_keys=True),flush=True)
        # Conservative inter-batch pacing even when a query returns quickly.
        sleep(2)
    summary={'schema_version':1,'manufacturer':'Microchip',
             'original_dfp_index_sha256':digest,
             'shard':shard,'shard_count':shard_count,
             'planned_batches_this_shard':len(batches),
             'omitted_already_archived_batches':sorted(PREVIOUS_CAPTURED_IDS),
             'claims_complete_global_sku_population':False,
             'population_boundary_validated':False,
             'global_active_denominator':None,
             'production_write_authorized':False,**counts}
    (log_root / f'shard-{shard:02d}-summary.json').write_text(
        json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2,sort_keys=True),flush=True)
    return summary

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence-root',type=Path,required=True)
    ap.add_argument('--plan',type=Path,required=True)
    ap.add_argument('--output-root',type=Path,required=True)
    ap.add_argument('--log-root',type=Path,required=True)
    ap.add_argument('--shard',type=int,required=True)
    ap.add_argument('--shard-count',type=int,default=12)
    ap.add_argument('--batch-timeout',type=int,default=180)
    args=ap.parse_args()
    registry=json.loads(planner.REGISTRY.read_text(encoding='utf-8'))
    digest=registry['gate_1b_surface_audit']['dfp_index_observation']['raw_index_sha256']
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    inventory=archived_inventory(args.evidence_root)
    execute(plan,inventory,digest,args.shard,args.shard_count,
            args.evidence_root,args.plan,args.output_root,args.log_root,
            args.batch_timeout)

if __name__ == '__main__':
    main()
