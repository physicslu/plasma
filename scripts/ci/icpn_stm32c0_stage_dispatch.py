#!/usr/bin/env python3
"""Select C0 validation stages without losing original PR/push test coverage."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ".github/workflows/device-catalog-stm32c0-stage-dispatch.yml"
SCRIPT = "scripts/ci/icpn_stm32c0_stage_dispatch.py"
TEST = "scripts/tests/test-icpn-stm32c0-stage-dispatch.py"
PROFILES = json.loads(r'''{"c01":{"original":".github/workflows/device-catalog-stm32c0-c01-foundation-validation.yml","archive":"docs/archive/ci-workflows/stm32c0-stages/device-catalog-stm32c0-c01-foundation-validation.yml","sha":"ffad7b733511469408c1db6c4a8662ec644c883b","pull_request":["data/device-catalog/research/stm32c0_phase_c0_1_foundation.py","data/device-catalog/research/stm32c0-phase-c0.1-foundation-baseline.json","data/device-catalog/research/test_stm32c0_phase_c0_1_foundation.py","data/device-catalog/research/validate_stm32c0_phase_c0_1_foundation.py","data/device-catalog/research/stm32-post-u0-next-family-selection.json","data/device-catalog/research/stm32-c0-l0-post-u0-ordering-authority-review.json","data/device-catalog/research/evidence/stm32-c0-l1-l0-post-u0-live-2026-09-11/**","data/device-catalog/research/openocd-parts-canonical.csv",".github/workflows/device-catalog-stm32c0-c01-foundation-validation.yml"],"push":["data/device-catalog/research/stm32c0_phase_c0_1_foundation.py","data/device-catalog/research/stm32c0-phase-c0.1-foundation-baseline.json","data/device-catalog/research/test_stm32c0_phase_c0_1_foundation.py","data/device-catalog/research/validate_stm32c0_phase_c0_1_foundation.py","data/device-catalog/research/stm32-post-u0-next-family-selection.json","data/device-catalog/research/stm32-c0-l0-post-u0-ordering-authority-review.json","data/device-catalog/research/evidence/stm32-c0-l1-l0-post-u0-live-2026-09-11/**","data/device-catalog/research/openocd-parts-canonical.csv",".github/workflows/device-catalog-stm32c0-c01-foundation-validation.yml"]},"c02":{"original":".github/workflows/device-catalog-stm32c0-c02-discovery-validation.yml","archive":"docs/archive/ci-workflows/stm32c0-stages/device-catalog-stm32c0-c02-discovery-validation.yml","sha":"d519ef07b0bcb3665b683a4d533b52d8d28bdca3","pull_request":["data/device-catalog/research/stm32c0_phase_c0_2_discovery.py","data/device-catalog/research/run_stm32c0_phase_c0_2_discovery.py","data/device-catalog/research/test_stm32c0_phase_c0_2_discovery.py","data/device-catalog/research/validate_stm32c0_phase_c0_2_retained_evidence.py","data/device-catalog/research/stm32c0-phase-c0.2-discovery-baseline.json","data/device-catalog/research/stm32c0-phase-c0.2-discovery-manifest.json","data/device-catalog/research/evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11/**","data/device-catalog/research/stm32c0-phase-c0.1-foundation-baseline.json","data/device-catalog/research/openocd-parts-canonical.csv",".github/workflows/device-catalog-stm32c0-c02-discovery-validation.yml"],"push":["data/device-catalog/research/stm32c0_phase_c0_2_discovery.py","data/device-catalog/research/run_stm32c0_phase_c0_2_discovery.py","data/device-catalog/research/test_stm32c0_phase_c0_2_discovery.py","data/device-catalog/research/validate_stm32c0_phase_c0_2_retained_evidence.py","data/device-catalog/research/stm32c0-phase-c0.2-discovery-baseline.json","data/device-catalog/research/stm32c0-phase-c0.2-discovery-manifest.json","data/device-catalog/research/evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11/**","data/device-catalog/research/stm32c0-phase-c0.1-foundation-baseline.json","data/device-catalog/research/openocd-parts-canonical.csv",".github/workflows/device-catalog-stm32c0-c02-discovery-validation.yml"]},"c03":{"original":".github/workflows/device-catalog-stm32c0-c03-metadata-validation.yml","archive":"docs/archive/ci-workflows/stm32c0-stages/device-catalog-stm32c0-c03-metadata-validation.yml","sha":"6a3843d9dc477831e8768eca345c9ef49fab2f86","pull_request":["data/device-catalog/research/stm32c0_metadata_policy.py","data/device-catalog/research/stm32c0_phase_c0_3_policy.py","data/device-catalog/research/test_stm32c0_phase_c0_3_policy.py","data/device-catalog/research/stm32c0-phase-c0.3-ordering-authority.json","data/device-catalog/research/stm32c0-phase-c0.3-policy-baseline.json","data/device-catalog/research/stm32c0-phase-c0.3-production-manifest-prestate.json","data/device-catalog/research/stm32c0-phase-c0.2-discovery-baseline.json","data/device-catalog/research/stm32c0-phase-c0.2-discovery-manifest.json","data/device-catalog/research/validate_stm32c0_phase_c0_2_retained_evidence.py","data/device-catalog/research/evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11/**",".github/workflows/device-catalog-stm32c0-c03-metadata-validation.yml"],"push":["data/device-catalog/research/stm32c0_metadata_policy.py","data/device-catalog/research/stm32c0_phase_c0_3_policy.py","data/device-catalog/research/test_stm32c0_phase_c0_3_policy.py","data/device-catalog/research/stm32c0-phase-c0.3-ordering-authority.json","data/device-catalog/research/stm32c0-phase-c0.3-policy-baseline.json","data/device-catalog/research/stm32c0-phase-c0.3-production-manifest-prestate.json","data/device-catalog/research/stm32c0-phase-c0.2-discovery-baseline.json","data/device-catalog/research/stm32c0-phase-c0.2-discovery-manifest.json","data/device-catalog/research/validate_stm32c0_phase_c0_2_retained_evidence.py","data/device-catalog/research/evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11/**",".github/workflows/device-catalog-stm32c0-c03-metadata-validation.yml"]},"c04":{"original":".github/workflows/device-catalog-stm32c0-c04-admission-validation.yml","archive":"docs/archive/ci-workflows/stm32c0-stages/device-catalog-stm32c0-c04-admission-validation.yml","sha":"e612c76d94ba2ed5714d807ea515054a88ea9cc6","pull_request":["data/device-catalog/research/stm32c0_admission_policy.py","data/device-catalog/research/stm32c0_phase_c0_4_admission.py","data/device-catalog/research/test_stm32c0_phase_c0_4_admission.py","data/device-catalog/research/validate_stm32c0_phase_c0_4_admission_plan.py","data/device-catalog/research/stm32c0-phase-c0.4-admission-plan.json","data/device-catalog/research/device-catalog-stm32c0-phase-c0.4-admission-plan.md","data/device-catalog/research/stm32c0_phase_c0_3_policy.py","data/device-catalog/research/stm32c0_metadata_policy.py","data/device-catalog/research/stm32c0-phase-c0.3-policy-baseline.json","data/device-catalog/research/openocd-parts-canonical.csv","data/device-catalog/research/validate_stm32c0_phase_c0_2_retained_evidence.py","data/device-catalog/research/evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11/**",".github/workflows/device-catalog-stm32c0-c04-admission-validation.yml"],"push":["data/device-catalog/research/stm32c0_admission_policy.py","data/device-catalog/research/stm32c0_phase_c0_4_admission.py","data/device-catalog/research/test_stm32c0_phase_c0_4_admission.py","data/device-catalog/research/validate_stm32c0_phase_c0_4_admission_plan.py","data/device-catalog/research/stm32c0-phase-c0.4-admission-plan.json","data/device-catalog/research/device-catalog-stm32c0-phase-c0.4-admission-plan.md","data/device-catalog/research/stm32c0_phase_c0_3_policy.py","data/device-catalog/research/stm32c0_metadata_policy.py","data/device-catalog/research/stm32c0-phase-c0.3-policy-baseline.json","data/device-catalog/research/openocd-parts-canonical.csv","data/device-catalog/research/validate_stm32c0_phase_c0_2_retained_evidence.py","data/device-catalog/research/evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11/**",".github/workflows/device-catalog-stm32c0-c04-admission-validation.yml"]},"c05":{"original":".github/workflows/device-catalog-stm32c0-c05-publication-validation.yml","archive":"docs/archive/ci-workflows/stm32c0-stages/device-catalog-stm32c0-c05-publication-validation.yml","sha":"29723d8a14188f24ef8cfa2390ac1628d0101a52","pull_request":["data/device-catalog/research/stm32c0-commercial-icpn.csv","data/device-catalog/research/stm32c0-phase-c0.2-production-manifest-prestate.json","data/device-catalog/research/stm32c0-phase-c0.3-production-manifest-prestate.json","data/device-catalog/research/stm32c0-phase-c0.4-admission-plan.json","data/device-catalog/research/stm32c0-phase-c0.5-publication-*.json","data/device-catalog/research/publish_stm32c0_phase_c0_5.py","data/device-catalog/research/stm32c0_phase_c0_4_admission.py","data/device-catalog/research/test_stm32c0_phase_c0_5_publication.py",".github/workflows/device-catalog-stm32c0-c05-publication-validation.yml"],"push":["data/device-catalog/research/stm32c0-commercial-icpn.csv","data/device-catalog/research/stm32c0-phase-c0.2-production-manifest-prestate.json","data/device-catalog/research/stm32c0-phase-c0.3-production-manifest-prestate.json","data/device-catalog/research/stm32c0-phase-c0.4-admission-plan.json","data/device-catalog/research/stm32c0-phase-c0.5-publication-*.json","data/device-catalog/research/publish_stm32c0_phase_c0_5.py","data/device-catalog/research/stm32c0_phase_c0_4_admission.py","data/device-catalog/research/test_stm32c0_phase_c0_5_publication.py",".github/workflows/device-catalog-stm32c0-c05-publication-validation.yml"]}}''')
STAGES = tuple(PROFILES)
CONTROL = frozenset((WF, SCRIPT, TEST))

def blob_hash(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def event_paths(yaml, event):
    m = re.search(r"(?m)^  " + event + r": *$", yaml)
    if not m:
        raise ValueError("Missing event: "+event)
    body=yaml[m.end():]
    e=re.search(r"(?m)^(?:  (?:pull_request|push):|permissions:|jobs:)",body)
    section=body[:e.start()] if e else body
    m=re.search(r"(?m)^    paths: *$",section)
    if not m:
        raise ValueError("Missing path list: "+event)
    rows=[]
    for line in section[m.end():].splitlines():
        s=line.strip()
        if s.startswith("- "):
            rows.append(s[2:].strip().strip("'\""))
        elif s and not s.startswith("#"):
            break
    if not rows or len(rows)!=len(set(rows)):
        raise ValueError("Duplicate/empty path list: "+event)
    return rows

def expected(event):
    paths=set(CONTROL)
    for p in PROFILES.values():
        paths.update(p[event])
        paths.add(p["archive"])
    return paths

def affected(paths,event):
    if event not in ("pull_request","push"):
        raise ValueError("Unsupported event")
    if set(paths)&CONTROL:
        return list(STAGES)
    return [stage for stage,p in PROFILES.items() if any(
        fnmatch.fnmatchcase(path, pattern) for path in paths
        for pattern in (*p[event],p["archive"]))]

def self_test():
    if STAGES != ("c01","c02","c03","c04","c05"):
        raise ValueError("Unexpected stage set")
    for stage,p in PROFILES.items():
        raw=(ROOT/p["archive"]).read_bytes()
        if blob_hash(raw)!=p["sha"]:
            raise ValueError(stage+" original content modified")
        text=raw.decode()
        if "runs-on: ubuntu-24.04" not in text or "  contents: read" not in text:
            raise ValueError(stage+" runner/permissions drift")
        if not re.search(r"(?m)^    branches: \[main\] *$",text):
            raise ValueError(stage+" push branch drift")
        if "workflow_dispatch:" in text or "workflow_call:" in text:
            raise ValueError(stage+" unexpected runtime entry")
        for event in ("pull_request","push"):
            if event_paths(text,event)!=p[event]:
                raise ValueError(stage+" original trigger drift")
    new=(ROOT/WF).read_text()
    if "  workflow_dispatch:" in new or "  workflow_call:" in new:
        raise ValueError("Interactive entry not authorized")
    for event in ("pull_request","push"):
        rows=event_paths(new,event)
        if len(rows)!=len(expected(event)) or set(rows)!=expected(event):
            raise ValueError("Missing/extra consolidated paths: "+event)
    for stage,p in PROFILES.items():
        if stage not in affected([p["original"]],"pull_request"):
            raise ValueError("Missing original removal trigger")
        if stage not in affected([p["archive"]],"push"):
            raise ValueError("Missing archival trigger")
    assert affected(["data/device-catalog/production/icpn-v1-manifest.json"],"push")==[]
    assert affected([WF],"pull_request")==list(STAGES)
    print("C0 original Git SHA, trigger union and stage routing PASS")

def git_changes(base,head):
    r=subprocess.run(["git","diff","--name-only","--diff-filter=ACDMRT",base,head],
                     cwd=ROOT,check=True,capture_output=True,text=True)
    return r.stdout.splitlines()

def main():
    a=argparse.ArgumentParser()
    s=a.add_subparsers(dest="command",required=True)
    s.add_parser("self-test")
    d=s.add_parser("select")
    d.add_argument("--event",required=True,choices=("pull_request","push"))
    d.add_argument("--base",required=True)
    d.add_argument("--head",required=True)
    args=a.parse_args()
    self_test()
    if args.command=="select":
        matching=affected(git_changes(args.base,args.head),args.event)
        for stage in STAGES:
            print(stage+"="+str(stage in matching).lower())

if __name__=="__main__":
    main()
