#!/usr/bin/env python3
"""Hard-lock and semantically replay retained STM32G0 Phase 4.8B evidence."""
from __future__ import annotations
import hashlib, json, re
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASELINE=HERE/'stm32g0-phase4.8b-discovery-baseline.json'
DISCOVERY=HERE/'stm32g0-phase4.8b-discovery-manifest.json'
EVIDENCE=HERE/'evidence/stm32g0-phase4.8b-official-st-discovery-live-2026-09-09'
EXPECTED_EVIDENCE_ID='stm32g0-phase4.8b-official-st-discovery-2026-09-09-retained-20260909T153114Z-233e9300'
EXPECTED_BASELINE_SHA='ef059c3226b506aa0ff739abf8c6bf3e0f525ceaefb571693458dad6b706f10a'
EXPECTED_SUMMARY_SHA='061922f1a1af9a71a0614dc4f19c9f56c6823503b20d076ab0f6d4a742e45594'
EXPECTED_PROVENANCE_SHA='b5ea18c91af8b8166901bd44879944cb95e0f8cfe22712c757c6991dceb692c8'
EXPECTED_MANIFEST_SHA='ff90c6ab4b3adb8bf9c87d5b0321ec3b29eab32f9854b38e566c09d7ffb39469'
EXPECTED_LIVE_SHA='9b7cd31d1b0b37cb2960f34edef980159133028c0df9916909be8a0833eaf50d'
EXPECTED_EXEC_SHA='233e9300bfac96f868e4d4c372246a3e02ff541b'
EXPECTED_RUN=34369661142
EXPECTED_ARTIFACT=10111790513
EXPECTED_ARTIFACT_SHA='2d261efb10ec0840208337edf8a3d2ebd1d0dc3aeb5effd78af735dd30dac36f'
EXPECTED_AGG={
'acquisition_failure':0,'acquisition_success':12,'active_candidate_targets':12,
'active_exact_icpn_candidates':49,'attempted':12,'bounded_discovery_clean':True,
'commercial_identity_clean':True,'commercial_identity_unresolved_targets':0,
'commercial_identity_verified_targets':12,'dispositioned_targets':12,
'excluded_non_active_part_numbers':3,'identity_manual_intervention_required':0,
'lifecycle_excluded_targets':0,'openocd_routing':{'ambiguous':0,'gates_commercial_identity':False,'not_applicable':0,'unique':11,'unmapped':1},
'routing_followup_required':1,'source_unavailable_exclusions':0}
EXPECTED_BINDINGS={'discovery_manifest_git_blob_sha':'a2836b04f91631e0f0454cf503d76d2a11de2643','openocd_catalog_git_blob_sha':'0ef056e3363e20bb527590c4a4cc1cc0d7afb810','production_exact_icpn_count':563,'production_family_counts':{'STM32F0':42,'STM32F1':75,'STM32F2':33,'STM32F3':10,'STM32F4':384,'STM32F7':19},'production_manifest_git_blob_sha':'3f8ab8b9b90edc399ad2d0a798115fffe3ba9063','stm32g0_production_prestate_count':0}
EXPECTED_TARGETS=['STM32G030C6','STM32G031C4','STM32G041C6','STM32G050C6','STM32G051C6','STM32G061C6','STM32G070CB','STM32G071C8','STM32G081CB','STM32G0B0CE','STM32G0B1CB','STM32G0C1CC']
EXPECTED_PROPOSAL={'STM32G0C1CCT6','STM32G0C1CCT6N','STM32G0C1CCU6N'}
EXPECTED_UNMAPPED_ACTIVE={'STM32G0B1CBT6N','STM32G0B1CBU6N'}

class Error(RuntimeError): pass
def req(c:bool,m:str):
    if not c: raise Error(m)
def readj(p:Path):
    x=json.loads(p.read_text(encoding='utf-8')); req(isinstance(x,dict),f'{p}: object required'); return x
def sha(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def all_false(x): return isinstance(x,dict) and bool(x) and set(x.values())=={False}
def main()->int:
    b=readj(BASELINE); s=readj(EVIDENCE/'pilot-summary.json'); p=readj(EVIDENCE/'provenance.json'); m=readj(EVIDENCE/'manifest.json'); d=readj(DISCOVERY)
    req(sha(BASELINE)==EXPECTED_BASELINE_SHA,'baseline byte drift')
    req(sha(EVIDENCE/'pilot-summary.json')==EXPECTED_SUMMARY_SHA,'summary byte drift')
    req(sha(EVIDENCE/'provenance.json')==EXPECTED_PROVENANCE_SHA,'provenance byte drift')
    req(sha(EVIDENCE/'manifest.json')==EXPECTED_MANIFEST_SHA,'manifest byte drift')
    req(m.get('evidence_id')==EXPECTED_EVIDENCE_ID and p.get('evidence_id')==EXPECTED_EVIDENCE_ID,'evidence ID drift')
    req(b.get('aggregate')==EXPECTED_AGG and s.get('aggregate')==EXPECTED_AGG,'aggregate drift')
    req(b.get('source_bindings')==EXPECTED_BINDINGS and p.get('source_bindings')==EXPECTED_BINDINGS,'historical source bindings drift')
    ex=b.get('discovery_execution'); req(ex=={'artifact_id':EXPECTED_ARTIFACT,'artifact_zip_sha256':EXPECTED_ARTIFACT_SHA,'executed_git_sha':EXPECTED_EXEC_SHA,'live_summary_sha256':EXPECTED_LIVE_SHA,'workflow_run_id':EXPECTED_RUN},'execution binding drift')
    req(p.get('workflow_run_id')==EXPECTED_RUN and p.get('artifact_id')==EXPECTED_ARTIFACT and p.get('artifact_zip_sha256')==EXPECTED_ARTIFACT_SHA and p.get('executed_git_sha')==EXPECTED_EXEC_SHA,'provenance execution drift')
    req(p.get('live_artifact_summary_sha256')==EXPECTED_LIVE_SHA,'live summary digest drift')
    req(p.get('evidence_profile')=='stm32g0_dual_surface_v1' and p.get('playwright_version')=='1.62.0' and p.get('chromium_version')=='151.0.7922.34' and p.get('headed') is True,'browser binding drift')
    req(p.get('acquisition_time_utc')=={'first':'2026-09-09T15:22:04Z','last':'2026-09-09T15:31:14Z'},'acquisition time drift')
    req(all_false(b.get('claims')) and all_false(s.get('claims')),'claims must stay false')
    req(b['claims'].get('cmsis_alias_is_commercial_identity') is False,'CMSIS alias boundary violated')
    targets=b.get('targets'); src=d.get('targets'); req(isinstance(targets,list) and isinstance(src,list) and len(targets)==len(src)==12,'target count drift')
    req([x.get('base_device') for x in targets]==EXPECTED_TARGETS==[x.get('base_device') for x in src],'target ordering drift')
    active=[]; proposals=[]; routing=Counter()
    for t in targets:
        base=t.get('base_device'); req(t.get('disposition')=='active_candidates' and t.get('commercial_identity_status')=='verified_active',f'{base}: non-Active target disposition')
        exact=t.get('exact_icpns'); excluded=t.get('excluded_non_active_part_numbers'); req(isinstance(exact,list) and exact and isinstance(excluded,list),f'{base}: identity projection missing')
        req(all(isinstance(x,str) and x.startswith(base) for x in exact),f'{base}: foreign Active identity')
        req(t.get('routing_gates_commercial_identity') is False,f'{base}: routing improperly gates identity')
        routing[str(t.get('historical_openocd_routing_status'))]+=1; active.extend(exact)
        for x in excluded:
            req(isinstance(x,dict) and isinstance(x.get('icpn'),str) and x['icpn'].startswith(base),'bad lifecycle exclusion')
            req(str(x.get('marketing_status','')).startswith('Proposal'),'unexpected non-Active lifecycle state')
            proposals.append(x['icpn'])
        for k in ('evidence_section_sha256','rendered_dom_sha256'):
            req(re.fullmatch(r'[0-9a-f]{64}',str(t.get(k,''))) is not None,f'{base}: invalid digest')
    req(len(active)==len(set(active))==49,'Active ICPN count/uniqueness drift')
    req(set(proposals)==EXPECTED_PROPOSAL and len(proposals)==3,'Proposal exclusion set drift')
    req(routing==Counter({'unique':11,'unmapped':1}),f'routing target-count drift: {routing}')
    g0b1=next(x for x in targets if x['base_device']=='STM32G0B1CB')
    req(g0b1['historical_openocd_routing_status']=='unmapped','G0B1 routing gap disappeared without policy review')
    req(EXPECTED_UNMAPPED_ACTIVE.issubset(set(g0b1['exact_icpns'])),'N-suffix Active ICPNs were dropped')
    req(b.get('source_unavailable')==[],'unexpected source-unavailable exclusions')
    req(p.get('target_count')==12 and p.get('exact_icpn_candidate_count')==49 and p.get('excluded_non_active_part_number_count')==3,'provenance counts drift')
    req(p.get('canonical_dataset_admission') is False and p.get('production_admission_ready') is False and p.get('routing_gates_commercial_identity') is False,'retained evidence overclaims capability')
    print('STM32G0 Phase 4.8B retained evidence validation: PASS')
    print(json.dumps({'active_exact_icpns':49,'proposal_exclusions':3,'routing_unique_targets':11,'routing_unmapped_targets':1,'unmapped_active_n_suffixes':sorted(EXPECTED_UNMAPPED_ACTIVE)},indent=2))
    return 0
if __name__=='__main__': raise SystemExit(main())
