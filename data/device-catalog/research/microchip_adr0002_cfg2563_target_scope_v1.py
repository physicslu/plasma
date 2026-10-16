#!/usr/bin/env python3
"""Owner-selected CFG-first Microchip Phase 1 delivery target under ADR-0002.

2,563 is an implementation/engineering target subset of the 23,276 original
manufacturer-confirmed Exact ICPNs, not a second Phase 1 identity predicate.
Do not let CFG eligibility override vendor identity, software qualification,
or the canonical Phase 1 visibility rule.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

TARGET = 2563
SOURCE = 23276
CFG_SHA = "0c37ad68c1db0a4fb50ff5a1d229faaca0ee6eac44cfb9d9b7de4e8a931daf2a"
CFG_COUNTS = {
    "tcl/target/pic32mx.cfg":1241,
    "tcl/target/at91samdXX.cfg":667,
    "tcl/target/atsame5x.cfg":354,
    "tcl/target/atsamv.cfg":175,
    "tcl/target/atsaml1x.cfg":126,
}


def require(test: bool, detail: str) -> None:
    if not test:
        raise ValueError(detail)


def select_target(canonical: dict, cfg_freeze: dict) -> dict:
    require(canonical.get("policy")=="ADR-0002"
            and canonical.get("manufacturer")=="Microchip"
            and canonical.get("phase1_exact_icpn_observed")==SOURCE
            and canonical.get("selector_visible_identified_count")==SOURCE
            and canonical.get("production_write_authorized") is False,
            "canonical source scope or Phase 1 identity changed")
    require(cfg_freeze.get("adr")=="ADR-0002"
            and cfg_freeze.get("manufacturer")=="Microchip"
            and cfg_freeze.get("scope")=="frozen_5cfg_2563_exact_original_manufacturer_icpns"
            and cfg_freeze.get("record_count")==cfg_freeze.get("s1_identified")==TARGET
            and cfg_freeze.get("cfg_identity_freeze_sha256")==CFG_SHA
            and cfg_freeze.get("cfg_counts")==CFG_COUNTS
            and cfg_freeze.get("production_write_authorized") is False
            and cfg_freeze.get("phase2_programming_authorized") is False
            and cfg_freeze.get("phase3_hil_authorized") is False,
            "five-CFG Phase 1 development target scope changed")
    rows=canonical.get("records")
    targets=cfg_freeze.get("records")
    require(isinstance(rows,list) and len(rows)==SOURCE
            and isinstance(targets,list) and len(targets)==TARGET,
            "source or target row count changed")
    by_icpn={r["icpn"].upper():r for r in rows}
    require(len(by_icpn)==SOURCE,"canonical original manufacturer ICPN duplicate")
    found=set()
    by_cfg=Counter()
    for r in targets:
        icpn=r.get("icpn","").upper()
        require(icpn not in found and icpn in by_icpn,
                "CFG target not in independently qualified original-MCP identities")
        found.add(icpn)
        original=by_icpn[icpn]
        assert isinstance(original["phase1"],dict)
        require(r["phase1_identity_status"]=="IDENTIFIED"
                and original["phase1"]["identity_state"]=="IDENTIFIED"
                and original["base_device"].upper()==r["base_device"].upper()
                and original["phase1"]["original_manufacturer_sha256_refs"]==
                    r["source_original_mcp_response_sha256_refs"]
                and original["ic_selector_visible"] is True,
                "CFG candidate illegitimately changed Phase 1 exact identity")
        require(original["phase2"]["programming_state"]=="UNKNOWN"
                and original["phase3"]["compatibility_state"]=="NOT_TESTED"
                and original["execution_authorized"] is False,
                "CFG membership cannot manufacture Phase 2 or HIL readiness")
        cfg=r.get("openocd_target_cfg_research_only")
        require(cfg in CFG_COUNTS,"unreviewed OpenOCD CFG research lead")
        by_cfg[cfg]+=1
    require(dict(by_cfg)==CFG_COUNTS,"five-CFG target distributions drift")
    require(len(found)==TARGET,"CFG-first target identity coverage drift")
    return {
        "schema_version":1,
        "policy":"ADR-0002",
        "manufacturer":"Microchip",
        "engineering_phase1_delivery_scope":"frozen_openocd_cfg_first_5cfg_2563",
        "phase1_delivery_target_exact_icpns":TARGET,
        "source_snapshot_official_identified_exact_icpns":SOURCE,
        "source_confirmed_other_identity_records_outside_current_delivery_scope":SOURCE-TARGET,
        "source_confirmed_other_identity_records_not_disqualified":True,
        "target_identity_freeze_sha256":CFG_SHA,
        "target_cfg_counts":dict(sorted(by_cfg.items())),
        "phase1_target_identified":TARGET,
        "phase2_target_supported":0,
        "phase3_target_passed":0,
        "initial_implementation_batch_proposed":122,
        "remaining_target_after_proposed_batch":TARGET-122,
        "initial_implementation_batch_is_not_qualification_gate":True,
        "all_identified_material_visibility_semantics_unchanged":True,
        "production_write_authorized":False,
        "phase2_qualification_authorized":False,
        "phase3_hil_authorized":False,
        "job_batch_execution_authorized":False,
    }


def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--canonical",type=Path,required=True)
    ap.add_argument("--cfg-frozen",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    require("production" not in {part.lower() for part in args.output.resolve().parts},
            "cannot write source-only target projection to Production")
    result=select_target(json.loads(args.canonical.read_text(encoding="utf-8")),
                         json.loads(args.cfg_frozen.read_text(encoding="utf-8")))
    content=(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode()
    if args.verify:
        require(args.output.read_bytes()==content,
                "frozen CFG-first delivery target not deterministic")
    else:
        require(not args.output.exists(),"refuse overwrite of target scope report")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_bytes(content)
    print(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False))


if __name__=="__main__":
    main()
