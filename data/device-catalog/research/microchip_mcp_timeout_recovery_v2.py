#!/usr/bin/env python3
"""Recover eight interrupted original-DFP Research batches, no Production writes.

Each query executes in a separate bounded subprocess; the original DFP
attestation is fsynced BEFORE any vendor traffic. Preserve all negative
HTTP/error transcripts, while offline ledger replays only complete raw bytes.
This does NOT establish orderable-SKU population or programming support.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from time import sleep

from microchip_dfp_index_inventory_v1 import archived_inventory
import microchip_mcp_batch_plan_v1 as planner
import microchip_mcp_plan_capture_v1 as capture
import microchip_mcp_evidence_ledger_v1 as ledger

HERE=Path(__file__).resolve().parent
V2=HERE/'microchip_mcp_paged_probe_v2.py'
RECOVERY=frozenset(('8bit-0004','8bit-0005','8bit-0013',
                    '8bit-0048','8bit-0071','8bit-0072',
                    '8bit-0082','8bit-0105'))

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def select(source_plan, inventory, digest, batch_id):
    require(batch_id in RECOVERY, 'batch was not a quarantined original-source timeout')
    expected=planner.plan_inventory(inventory,digest,batch_size=10)
    require(source_plan==expected,'frozen source plan mismatch')
    record=capture.select_batch(expected,inventory,digest,batch_id)
    require(len(record['queries'])==10 and record['lane']=='8bit',
            'unexpected original timeout batch')
    return record

def capture_one(plan, inventory, digest, batch_id, output_root, log_root,
                query_timeout=85, gap_seconds=3):
    require(type(query_timeout) is int and 30<=query_timeout<=120,
            'query timeout must be 30..120 seconds')
    require(type(gap_seconds) is int and 2<=gap_seconds<=20,
            'minimum inter-query pacing is required')
    selected=select(plan,inventory,digest,batch_id)
    root,logs=Path(output_root).resolve(),Path(log_root).resolve()
    require('production' not in {p.lower() for p in root.parts+logs.parts},
            'Production evidence path is forbidden')
    require(root!=logs and not root.is_relative_to(logs) and
            not logs.is_relative_to(root),'logs must not contaminate archive')
    batch_dir=root/batch_id
    require(not batch_dir.exists() and not batch_dir.is_symlink() and
            not (logs/batch_id).exists(),'never overwrite vendor archives or logs')
    root.mkdir(parents=True,exist_ok=True)
    logs.mkdir(parents=True,exist_ok=True)
    batch_dir.mkdir(exist_ok=False)
    log_dir=logs/batch_id
    log_dir.mkdir(exist_ok=False)
    claim=capture.attestation(plan,selected)
    # Filesystem durability BEFORE opening a vendor session. The eight
    # original failed batches lack proof because it was previously written
    # only after the final network request had completed.
    with (batch_dir/'batch-source.json').open('x',encoding='utf-8') as fd:
        fd.write(json.dumps(claim,sort_keys=True,indent=2)+'\n')
        fd.flush()
        os.fsync(fd.fileno())

    result=[]
    for query in selected['queries']:
        proof=json.loads((batch_dir/'batch-source.json').read_text(encoding='utf-8'))
        require(proof==claim,'source attestation changed during live capture')
        begun=datetime.now(timezone.utc).isoformat()
        cmd=[sys.executable,str(V2),'--query',query,
             '--output-dir',str(batch_dir/query)]
        try:
            reply=subprocess.run(cmd,capture_output=True,text=True,
                                 timeout=query_timeout,check=False)
            state='captured_and_replayed' if reply.returncode==0 else 'unverified_vendor_response'
            output=(reply.stdout or '')+'\n'+(reply.stderr or '')
        except subprocess.TimeoutExpired as error:
            state='query_timed_out'
            raw=error.stdout or b''
            if isinstance(raw,bytes):
                raw=raw.decode('utf-8','replace')
            output=raw+'\nTIMEOUT: this query was NOT fully replayed\n'
        (log_dir/(query+'.txt')).write_text(output,encoding='utf-8')
        record={'query':query,'capture_state':state,'attempted_at_utc':begun}
        result.append(record)
        with (log_dir/'attempts.jsonl').open('a',encoding='utf-8') as fd:
            fd.write(json.dumps(record,sort_keys=True)+'\n')
            fd.flush()
        print(json.dumps(record,sort_keys=True),flush=True)
        sleep(gap_seconds)
    (log_dir/'capture-summary.json').write_text(json.dumps({
        'batch_id':batch_id,'original_dfp_index_sha256':digest,
        'batch_source_attestation_before_network':True,
        'queries':result,'global_active_denominator':None,
        'production_write_authorized':False,
    },indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return result

def replay_one(plan, inventory, digest, batch_id, output_root):
    selected=select(plan,inventory,digest,batch_id)
    folder=Path(output_root).resolve()/batch_id
    require(folder.is_dir() and not folder.is_symlink() and
            'production' not in {p.lower() for p in folder.parts},
            'unsafe/missing archived batch directory')
    require(json.loads((folder/'batch-source.json').read_text(encoding='utf-8'))==
            capture.attestation(plan,selected),'source provenance mismatch')
    result=ledger.build(folder,list(selected['queries']))
    require(result['production_write_authorized'] is False and
            result['global_active_denominator'] is None and
            result['manufacturer_population_complete'] is False and
            result['selected_queries']==10,'research-only evidence contract violated')
    return {
        'batch_id':batch_id,'original_dfp_index_sha256':digest,
        'query_count':10,
        'fully_replayed_queries':result['fully_replayed_queries'],
        'positive_exact_prefix_queries':result['positive_exact_prefix_queries'],
        'fully_replayed_zero_prefix_queries':
            result['replayed_zero_exact_prefix_queries'],
        'unverified_queries':[
            x['query'] for x in result['queries'] if x['state']=='unverified'],
        'unique_exact_ordering_candidates':result['unique_exact_ordering_candidates'],
        'global_active_denominator':None,
        'production_write_authorized':False
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence-root',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--batch-id',choices=sorted(RECOVERY),required=True)
    p.add_argument('--output-root',type=Path,required=True)
    p.add_argument('--log-root',type=Path)
    p.add_argument('--query-timeout',type=int,default=85)
    p.add_argument('--capture',action='store_true')
    args=p.parse_args()
    source=json.loads(planner.REGISTRY.read_text(encoding='utf-8'))
    digest=source['gate_1b_surface_audit']['dfp_index_observation']['raw_index_sha256']
    inventory=archived_inventory(args.evidence_root)
    plan=json.loads(args.plan.read_text(encoding='utf-8'))
    if args.capture:
        require(args.log_root is not None,'live capture requires separate log root')
        result=capture_one(plan,inventory,digest,args.batch_id,args.output_root,
                           args.log_root,args.query_timeout)
        print(json.dumps({'captured':len(result),
                          'not_fully_captured':sum(x['capture_state']!='captured_and_replayed'
                                                   for x in result)},
                         sort_keys=True))
    else:
        print(json.dumps(replay_one(plan,inventory,digest,args.batch_id,
                                    args.output_root),sort_keys=True,indent=2))
if __name__=='__main__':
    main()
