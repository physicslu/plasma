#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent

def main()->int:
    c=json.loads((HERE/'stm32g0-phase4.8b-live-evidence-contract.json').read_text())
    assert c['phase']=='4.8B' and c['family']=='STM32G0'
    assert c['workflow_run_id']==34369661142
    assert c['executed_git_sha']=='233e9300bfac96f868e4d4c372246a3e02ff541b'
    assert c['artifact_id']==10111790513
    assert c['artifact_zip_sha256']=='2d261efb10ec0840208337edf8a3d2ebd1d0dc3aeb5effd78af735dd30dac36f'
    assert c['aggregate']=={'targets':12,'active_target_groups':12,'active_exact_icpns':49,'proposal_exclusions':3,'source_unavailable':0,'manual_review':0,'routing_unique_target_groups':11,'routing_unmapped_target_groups':1}
    assert set(c['claims'].values())=={False}
    print('STM32G0 Phase 4.8B live evidence contract: PASS')
    return 0
if __name__=='__main__': raise SystemExit(main())
