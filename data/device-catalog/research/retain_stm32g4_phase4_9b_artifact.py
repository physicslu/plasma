#!/usr/bin/env python3
"""Retain a clean STM32G4 Phase 4.9B live artifact without re-acquisition."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent
DISCOVERY_MANIFEST=HERE/'stm32g4-phase4.9b-discovery-manifest.json'
OPENOCD=HERE/'openocd-parts-canonical.csv'
PRODUCTION=HERE.parent/'production/icpn-v1-manifest.json'
BASELINE=HERE/'stm32g4-phase4.9b-discovery-baseline.json'
EVIDENCE_DIR=HERE/'evidence/stm32g4-phase4.9b-official-st-discovery-live-2026-09-10'
PHASE='4.9B'; FAMILY='STM32G4'; PROFILE='stm32g4_dual_surface_v1'; MAX_TARGETS=11
EXPECTED_PRODUCTION_COUNTS={'STM32F0':42,'STM32F1':75,'STM32F2':33,'STM32F3':10,'STM32F4':384,'STM32F7':19,'STM32G0':47}

class RetentionError(RuntimeError): pass
def req(c: bool,m: str):
    if not c: raise RetentionError(m)
def readj(p: Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding='utf-8')); req(isinstance(x,dict),f'{p}: object required'); return x
def sha256(p: Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def blob(p: Path)->str:
    b=p.read_bytes(); return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def writej(p: Path,x: object):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def all_false(x: object)->bool: return isinstance(x,dict) and bool(x) and set(x.values())=={False}

def source_bindings()->dict[str,object]:
    pm=readj(PRODUCTION); sources=pm.get('sources'); req(isinstance(sources,list),'Production sources missing')
    counts={str(x['family']):int(x['row_count']) for x in sources}
    req(counts==EXPECTED_PRODUCTION_COUNTS,f'Production family counts drifted: {counts}')
    req(sum(counts.values())==610,f'Production exact count drifted: {sum(counts.values())}')
    req('STM32G4' not in counts,'G4 must be absent from Production in 4.9B')
    return {
        'discovery_manifest_git_blob_sha':blob(DISCOVERY_MANIFEST),
        'openocd_catalog_git_blob_sha':blob(OPENOCD),
        'production_manifest_git_blob_sha':blob(PRODUCTION),
        'production_exact_icpn_count':610,
        'production_family_counts':counts,
        'stm32g4_production_prestate_count':0,
    }

def retain(*,artifact_root:Path,artifact_id:int,artifact_zip_sha256:str,workflow_run_id:int,executed_git_sha:str)->dict[str,object]:
    req(re.fullmatch(r'[0-9a-f]{64}',artifact_zip_sha256) is not None,'invalid artifact digest')
    req(re.fullmatch(r'[0-9a-f]{40}',executed_git_sha) is not None,'invalid execution SHA')
    summary_path=artifact_root/'live-summary.json'
    rawdir=artifact_root/'evidence'
    req(summary_path.is_file(),'live summary missing'); req(rawdir.is_dir(),'raw evidence dir missing')
    run_file=artifact_root/'workflow-run-id.txt'; sha_file=artifact_root/'executed-git-sha.txt'
    req(run_file.is_file() and run_file.read_text().strip()==str(workflow_run_id),'artifact run-id binding mismatch')
    req(sha_file.is_file() and sha_file.read_text().strip()==executed_git_sha,'artifact execution-SHA binding mismatch')
    live=readj(summary_path)
    req(live.get('phase')==PHASE and live.get('family')==FAMILY,'phase/family mismatch')
    req(live.get('attempted')==MAX_TARGETS and live.get('dispositioned_targets')==MAX_TARGETS,'target accounting mismatch')
    req(live.get('bounded_discovery_clean') is True,'bounded discovery not clean')
    req(live.get('acquisition_failure')==0 and live.get('identity_manual_intervention_required')==0,'manual/technical failure remains')
    req(all_false(live.get('claims')),'claims must remain false')
    req(live['claims'].get('cmsis_alias_is_commercial_identity') is False,'CMSIS alias identity boundary violated')
    browser=live.get('browser'); req(isinstance(browser,dict),'browser binding missing')
    req(browser.get('evidence_profile')==PROFILE and browser.get('playwright_version')=='1.62.0','browser profile mismatch')
    req(browser.get('headless') is False,'retained run must use headed browser')
    manifest=readj(DISCOVERY_MANIFEST); results=live.get('results'); targets=manifest.get('targets')
    req(isinstance(results,list) and isinstance(targets,list) and len(results)==len(targets)==MAX_TARGETS,'result list mismatch')
    compact=[]; active=[]; excluded=[]; unavailable=[]; times=[]
    for src,res in zip(targets,results):
        req(isinstance(src,dict) and isinstance(res,dict),'target/result invalid')
        base=src['base_device']; req(res.get('base_device')==base,'target ordering mismatch')
        req(res.get('source_url')==src['source_url'],f'{base}: source URL drift')
        disp=res.get('disposition')
        if disp=='source_unavailable_excluded':
            req(res.get('source_unavailable_status')=='http_404' and res.get('manual_intervention_required') is False,f'{base}: invalid 404 exclusion')
            req(not (rawdir/f'{base}.json').exists(),f'{base}: 404 cannot have raw evidence')
            compact.append({'subfamily':src['subfamily'],'base_device':base,'source_url':src['source_url'],'disposition':disp,
                            'commercial_identity_status':'unverified','source_unavailable_status':'http_404','routing_gates_commercial_identity':False})
            unavailable.append({'subfamily':src['subfamily'],'base_device':base,'reason':'canonical_product_page_http_404'})
            continue
        req(disp in {'active_candidates','lifecycle_excluded'},f'{base}: unknown disposition')
        ev=res.get('evidence'); req(isinstance(ev,dict),f'{base}: evidence missing')
        rp=rawdir/f'{base}.json'; req(rp.is_file() and readj(rp)==ev,f'{base}: raw/live evidence mismatch')
        exact=ev.get('exact_icpns'); ex=ev.get('excluded_non_active_part_numbers')
        req(isinstance(exact,list) and isinstance(ex,list),f'{base}: identity lists missing')
        req(all(isinstance(x,str) and x.startswith(base) for x in exact),f'{base}: foreign Active ICPN')
        req(all(isinstance(x,dict) and isinstance(x.get('icpn'),str) and x['icpn'].startswith(base) and x.get('marketing_status') for x in ex),f'{base}: invalid lifecycle exclusion')
        if disp=='active_candidates': req(bool(exact) and res.get('commercial_identity_status')=='verified_active',f'{base}: Active disposition inconsistent')
        else: req(not exact and bool(ex) and res.get('commercial_identity_status')=='verified_non_active_only',f'{base}: lifecycle-only inconsistent')
        for k in ('evidence_section_sha256','rendered_dom_sha256'):
            req(isinstance(ev.get(k),str) and re.fullmatch(r'[0-9a-f]{64}',ev[k]),f'{base}: bad {k}')
        t=ev.get('retrieved_at_utc'); req(isinstance(t,str),f'{base}: timestamp missing'); times.append(t)
        routing=res.get('openocd_routing'); req(isinstance(routing,dict) and routing.get('gates_commercial_identity') is False,f'{base}: routing boundary')
        compact.append({'subfamily':src['subfamily'],'base_device':base,'source_url':src['source_url'],'disposition':disp,
                        'commercial_identity_status':res.get('commercial_identity_status'),'exact_icpns':exact,
                        'excluded_non_active_part_numbers':ex,'evidence_section_sha256':ev['evidence_section_sha256'],
                        'rendered_dom_sha256':ev['rendered_dom_sha256'],'retrieved_at_utc':t,
                        'historical_openocd_routing_status':routing.get('status'),'historical_openocd_target_configs':routing.get('target_configs',[]),
                        'routing_gates_commercial_identity':False})
        active.extend(exact); excluded.extend({'base_device':base,**x} for x in ex)
    req(len(active)==live.get('active_exact_icpn_candidates'),'Active aggregate mismatch')
    req(len(excluded)==live.get('excluded_non_active_part_numbers'),'exclusion aggregate mismatch')
    req(len(unavailable)==live.get('source_unavailable_exclusions'),'404 aggregate mismatch')
    req(times,'no manufacturer evidence retained')
    req(len(active)==len(set(active)),'duplicate Active exact ICPNs')
    agg_keys=['attempted','acquisition_success','acquisition_failure','active_candidate_targets','lifecycle_excluded_targets','source_unavailable_exclusions','dispositioned_targets','commercial_identity_verified_targets','commercial_identity_unresolved_targets','active_exact_icpn_candidates','excluded_non_active_part_numbers','commercial_identity_clean','bounded_discovery_clean','identity_manual_intervention_required','openocd_routing','routing_followup_required']
    agg={k:live[k] for k in agg_keys}; bindings=source_bindings(); live_digest=sha256(summary_path)
    baseline={'schema_version':1,'phase':PHASE,'family':FAMILY,'pilot_id':live['pilot_id'],'aggregate':agg,'browser':browser,
              'claims':live['claims'],'targets':compact,'source_unavailable':unavailable,'source_bindings':bindings,
              'discovery_execution':{'workflow_run_id':workflow_run_id,'artifact_id':artifact_id,'artifact_zip_sha256':artifact_zip_sha256,'executed_git_sha':executed_git_sha,'live_summary_sha256':live_digest}}
    writej(BASELINE,baseline); baseline_digest=sha256(BASELINE)
    evidence_id=f"stm32g4-phase4.9b-official-st-discovery-2026-09-10-retained-{times[-1].replace('-','').replace(':','')}-{executed_git_sha[:8]}"
    summary={'schema_version':1,'phase':PHASE,'family':FAMILY,'pilot_id':live['pilot_id'],'aggregate':agg,'claims':live['claims'],'targets':compact,'source_unavailable':unavailable}
    prov={'schema_version':1,'evidence_id':evidence_id,'manufacturer':'STMicroelectronics','source_repository':'physicslu/plasma','acquisition_transport':'chromium_rendered_dom','headed':True,
          'evidence_profile':browser['evidence_profile'],'playwright_version':browser['playwright_version'],'chromium_version':browser.get('browser_version'),
          'acquisition_time_utc':{'first':min(times),'last':max(times)},'workflow_run_id':workflow_run_id,'artifact_id':artifact_id,'artifact_zip_sha256':artifact_zip_sha256,
          'executed_git_sha':executed_git_sha,'live_artifact_summary_sha256':live_digest,'baseline_sha256':baseline_digest,'source_bindings':bindings,
          'target_count':MAX_TARGETS,'acquisition_success':live['acquisition_success'],'acquisition_failure':live['acquisition_failure'],'source_unavailable_exclusion_count':live['source_unavailable_exclusions'],
          'exact_icpn_candidate_count':len(active),'excluded_non_active_part_number_count':len(excluded),'bounded_discovery_clean':True,'commercial_identity_clean':live['commercial_identity_clean'],
          'routing_gates_commercial_identity':False,'canonical_dataset_admission':False,'production_admission_ready':False}
    EVIDENCE_DIR.mkdir(parents=True,exist_ok=True); writej(EVIDENCE_DIR/'pilot-summary.json',summary); writej(EVIDENCE_DIR/'provenance.json',prov)
    readme=f"# STM32G4 Phase 4.9B retained evidence\n\nCompact projection of immutable GitHub Actions artifact {artifact_id} from run {workflow_run_id}. Raw browser evidence remains in the artifact. No canonical admission, Production write, programming-policy equivalence, physical qualification, or runtime-support claim is authorized.\n"
    (EVIDENCE_DIR/'README.md').write_text(readme,encoding='utf-8')
    files={n:sha256(EVIDENCE_DIR/n) for n in ('README.md','pilot-summary.json','provenance.json')}
    writej(EVIDENCE_DIR/'manifest.json',{'schema_version':1,'evidence_id':evidence_id,'files':files})
    print(json.dumps({'evidence_id':evidence_id,'baseline_sha256':baseline_digest,'pilot_summary_sha256':sha256(EVIDENCE_DIR/'pilot-summary.json'),'provenance_sha256':sha256(EVIDENCE_DIR/'provenance.json'),'manifest_sha256':sha256(EVIDENCE_DIR/'manifest.json'),'aggregate':agg},indent=2,sort_keys=True))
    return baseline

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--artifact-root',type=Path,required=True); p.add_argument('--artifact-id',type=int,required=True); p.add_argument('--artifact-zip-sha256',required=True); p.add_argument('--workflow-run-id',type=int,required=True); p.add_argument('--executed-git-sha',required=True); a=p.parse_args()
    retain(artifact_root=a.artifact_root,artifact_id=a.artifact_id,artifact_zip_sha256=a.artifact_zip_sha256,workflow_run_id=a.workflow_run_id,executed_git_sha=a.executed_git_sha); return 0
if __name__=='__main__': raise SystemExit(main())
