#!/usr/bin/env python3
"""Merge disjoint Microchip DFP research source directories by original bytes.

Runs independently verified source-bound partial rollups for every directory.
This is query observation aggregation, NOT commercial Active SKU coverage.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re

import microchip_mcp_batch_plan_v1 as planner
import microchip_mcp_partial_rollup_v2 as partial
from microchip_dfp_index_inventory_v1 import archived_inventory

def require(condition, message):
    if not condition:
        raise ValueError(message)

def build(plan, inventory, digest, sources):
    expected=planner.plan_inventory(inventory,digest,batch_size=plan.get('batch_size'))
    require(plan==expected,'untrusted source-pinned DFP batch plan')
    require(isinstance(sources,list) and 1 <= len(sources) <= 16,
            'invalid evidence source count')
    planned={b['batch_id']:b for b in expected['batches']}
    named=set()
    captured={}
    counts={'replayed':0,'zero':0,'positive':0}
    candidates={}
    conflicts={}
    batches={}
    roots=[]
    for label,dir_path in sources:
        require(isinstance(label,str) and
                re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,50}',label) and
                label not in named,'duplicate or unsafe source name')
        named.add(label)
        root=Path(dir_path).resolve()
        require(root.is_dir() and
                'production' not in {p.lower() for p in root.parts},
                'unsafe or missing evidence root')
        present={p.name for p in root.iterdir() if p.is_dir() or p.is_symlink()}
        require(present<=set(planned),'unexpected batch directory or symlink')
        require(not present.intersection(captured),
                'duplicate batch across source roots')
        for batch_id in present:
            captured[batch_id]=label
        result=partial.build(expected,inventory,digest,root)
        require(result['production_write_authorized'] is False and
                result['global_active_denominator'] is None and
                result['manufacturer_population_complete'] is False and
                not result['unexpected_batch_directories_or_symlinks'],
                'unsafe or unproven partial evidence')
        replayed=0
        for rec in result['batch_reports']:
            batch_id=rec['batch_id']
            if batch_id not in present:
                require(rec['state']=='not_archived',
                        'uncaptured batch emitted data')
                continue
            require(batch_id not in batches,'duplicate recorded batch')
            allowed=set(planned[batch_id]['queries'])
            empty=rec.get('replayed_zero_exact_prefix_queries',[])
            require(isinstance(empty,list) and len(empty)==len(set(empty)) and
                    set(empty)<=allowed,
                    'invalid zero-prefix query identities')
            count=rec.get('fully_replayed_queries',0)
            require(type(count) is int and len(empty)<=count<=len(allowed),
                    'invalid validated query count')
            counts['replayed']+=count
            counts['zero']+=len(empty)
            counts['positive']+=count-len(empty)
            replayed+=count
            batches[batch_id]=dict(rec,source_dataset=label)
        require(replayed==result['independently_replayed_queries'],
                'partial rollup replay total does not match batches')
        roots.append({'source_dataset':label,'observed_batch_archives':len(present),
                      'replayed_queries':replayed})
        for raw in result['ordering_candidates']:
            name=raw['icpn']
            current={'icpn':name,'rawLifecycleStatus':raw['rawLifecycleStatus'],
                     'sources':[dict(s,source_dataset=label)
                                for s in raw['sources']]}
            if name in conflicts:
                conflicts[name]['observations'].append(current)
            elif name not in candidates:
                candidates[name]=current
            elif candidates[name]['rawLifecycleStatus']==current['rawLifecycleStatus']:
                candidates[name]['sources'].extend(current['sources'])
            else:
                conflicts[name]={'icpn':name,
                                 'observations':[candidates.pop(name),current]}
        for conflict in result['conflicting_ordering_identities']:
            name=conflict['icpn']
            current=[dict(row,source_dataset=label)
                     for row in conflict['observations']]
            if name in candidates:
                current.insert(0,candidates.pop(name))
            conflicts.setdefault(name,{'icpn':name,'observations':[]})[
                'observations'].extend(current)
    require(counts['replayed']<=expected['supported_text_search_seeds'],
            'replayed query count exceeds DFP query plan')
    return {
        'schema_version':1,
        'type':'microchip-source-pinned-disjoint-dfp-evidence-merger',
        'manufacturer':'Microchip',
        'original_dfp_index_sha256':digest,
        'planned_batches':len(planned),
        'observed_batch_archives':len(captured),
        'not_archived_batch_ids':sorted(set(planned)-set(captured)),
        'planned_text_search_queries':expected['supported_text_search_seeds'],
        'replayed_queries':counts['replayed'],
        'replayed_positive_exact_prefix_queries':counts['positive'],
        'replayed_zero_exact_prefix_queries':counts['zero'],
        'unverified_or_unattempted_queries':
            expected['supported_text_search_seeds']-counts['replayed'],
        'unique_exact_prefix_research_candidates':len(candidates),
        'conflicting_lifecycle_identity_count':len(conflicts),
        'source_summaries':roots,
        'batch_reports':[batches[k] for k in sorted(batches)],
        'ordering_candidates':[candidates[k] for k in sorted(candidates)],
        'conflicting_ordering_identities':[conflicts[k] for k in sorted(conflicts)],
        'manufacturer_population_complete':False,
        'commercial_sku_denominator_established':False,
        'global_active_denominator':None,
        'production_write_authorized':False,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence-root',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--source',action='append',required=True,
                   help='label=/path/to/unmodified-raw-batches; repeat')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    inputs=[]
    for entry in args.source:
        require('=' in entry,'source must be label=directory')
        label,path=entry.split('=',1)
        inputs.append((label,Path(path)))
    reg=json.loads(planner.REGISTRY.read_text(encoding='utf-8'))
    digest=reg['gate_1b_surface_audit']['dfp_index_observation']['raw_index_sha256']
    result=build(json.loads(args.plan.read_text(encoding='utf-8')),
                 archived_inventory(args.evidence_root),digest,inputs)
    out=args.output.resolve()
    require('production' not in {p.lower() for p in out.parts},
            'Production output path forbidden')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',
                   encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in
        ('ordering_candidates','batch_reports','conflicting_ordering_identities',
         'not_archived_batch_ids')},indent=2,sort_keys=True))

if __name__=='__main__':
    main()
