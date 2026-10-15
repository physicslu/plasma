#!/usr/bin/env python3
"""Microchip exact MCP x DFP identity archive (legacy PR #909 filename).

Under ADR-0002 a manufacturer DFP support-name match alone is P2
archive-only, not a credible P1 OpenOCD Target/Driver family lead.
The 2,065 DFP-only identities remain Research with provenance.
P0=2,437 and bounded Target-only P1=126 remain frozen.
No software support, Catalog admission, Production or hardware claims.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from microchip_dfp_index_inventory_v1 import archived_inventory
from microchip_openocd_reverse_coverage_v1 import gates
from microchip_phase1_p0_information_ledger_v1 import verify_upstream

SOURCE_SUBSET = 23276
P0_BASELINE = 2437
P1_TARGET_BASELINE = 126
DFP_SUPPORTED_NAMES = 3717
ELIGIBLE_LANE = "32bit-pic-sam"
STATE = "P2_ARCHIVE_DFP_IDENTITY_ONLY_NO_OPENOCD_LEAD"
P2_BASELINE = SOURCE_SUBSET - P0_BASELINE - P1_TARGET_BASELINE
NO_CFG = "NO_DFP_NAME_CFG_CROSSWALK"
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")
MAX_BYTES = 64 * 1024 * 1024


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pack_index(inventory):
    require(inventory.get("source_bytes_sha256") ==
            gates.PINNED_DFP_SOURCE
            and inventory.get("manufacturer") == "Microchip"
            and inventory.get("observed_distinct_device_support_names") ==
            DFP_SUPPORTED_NAMES
            and inventory.get("device_support_list_is_complete_commercial_sku_inventory")
            is False
            and inventory.get("population_boundary_validated") is False
            and inventory.get("production_write_authorized") is False,
            "DFP manufacturer-original index/source identity invalid")
    all_names={}
    eligible={}
    by_lane=Counter()
    for pack in inventory["device_packs"]:
        name=pack["pack_name"]
        lane=pack["discovery_lane"]
        restricted=(lane in gates.ARCHIVAL_LANES
                    or name in gates.ACCESSORY_PACKS)
        for device in pack["device_names"]:
            key=device.upper()
            require(key not in all_names,
                    "ambiguous case-insensitive manufacturer DFP identity")
            all_names[key]=(lane,name)
            by_lane[lane]+=1
            if not restricted and lane==ELIGIBLE_LANE:
                eligible[key]={
                    "dfp_name":device,
                    "manufacturer_pack":name,
                    "pack_version":pack["pack_version"],
                    "original_dfp_index_sha256":gates.PINNED_DFP_SOURCE,
                }
    require(len(all_names)==DFP_SUPPORTED_NAMES and len(eligible)>0,
            "manufacturer DFP 32bit discovery scope missing")
    return eligible,dict(sorted(by_lane.items()))


def classify(source, inventory):
    original=verify_upstream(source)
    require(len(original)==SOURCE_SUBSET and
            source["icpn_denominator_joined_in_this_run"]==SOURCE_SUBSET
            and source["all_icpn_original_bytes_replayed_in_this_command"] is True
            and source["original_dfp_index_sha256_required"] ==
                gates.PINNED_DFP_SOURCE
            and source["production_write_authorized"] is False
            and source["cfg_software_supported_claimed"] is False,
            "must independently replay original MCP/DFP source before P1 discovery")
    eligible, dfp_lanes=pack_index(inventory)
    states=Counter(r["mapping_state"] for r in original)
    require(states["P1_TARGET_ONLY_CFG_CANDIDATE"]==P1_TARGET_BASELINE
            and (states["EXACT_DFP_NAME_CFG_CANDIDATE"]+
                 states["REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE"])
                ==P0_BASELINE
            and sum(states.values())==SOURCE_SUBSET,
            "frozen original source P0/P1 split drift")
    seen=set()
    output=[]
    gaps=Counter()
    for row in original:
        icpn=row["icpn"]
        base=row.get("base_device")
        require(isinstance(icpn,str) and icpn
                and icpn.upper() not in seen,
                "ambiguous or duplicated original MCP commercial identity")
        seen.add(icpn.upper())
        if row["mapping_state"]!=NO_CFG:
            continue
        if not isinstance(base,str) or not base.strip():
            gaps["no_exact_manufacturer_base"]+=1
            continue
        match=eligible.get(base.upper())
        if match is None:
            gaps["no_exact_eligible_32bit_dfp_base"]+=1
            continue
        hashes=row.get("original_mcp_response_sha256_refs")
        require(isinstance(hashes,list) and hashes
                and len(set(hashes))==len(hashes)
                and all(isinstance(x,str) and SHA_RE.fullmatch(x)
                        for x in hashes),
                "original-MCP source hashes missing")
        require(row.get("dfp_device_name") is None
                and row.get("openocd_target_cfg") is None
                and row.get("manufacturer_base_identity_evidence") ==
                "ORIGINAL_MICROCHIP_MCP_RESPONSE_REPLAYED_IN_THIS_COMMAND"
                and row.get("software_supported_claimed") is False
                and row.get("production_write_authorized") is False,
                "false implicit software qualification during DFP discovery")
        output.append({
            "icpn":icpn,
            "manufacturer":"Microchip",
            "base_device":base,
            "manufacturer_dfp_support_name":match["dfp_name"],
            "manufacturer_dfp_pack":match["manufacturer_pack"],
            "manufacturer_dfp_pack_version":match["pack_version"],
            "discovery_lane":ELIGIBLE_LANE,
            "dfp_identity_research_state":STATE,
            "adr0002_research_priority":"P2",
            "counts_as_adr0002_p1_candidate":False,
            "source_mapping_state":NO_CFG,
            "manufacturer_base_exact_dfp_join":True,
            "source_original_mcp_response_sha256_refs":hashes,
            "source_original_dfp_index_sha256":
                gates.PINNED_DFP_SOURCE,
            "openocd_target_cfg":None,
            "openocd_target_cfg_mapping_reviewed":False,
            "phase1_exact_icpn_fields_added_verified":0,
            "phase2_software_supported":False,
            "production_write_authorized":False,
        })
    output.sort(key=lambda x:x["icpn"].upper())
    assert len({r["icpn"].upper() for r in output})==len(output)
    pcounts=Counter(r["manufacturer_dfp_pack"] for r in output)
    bcounts=Counter(r["base_device"] for r in output)
    require(sum(pcounts.values())==sum(bcounts.values())==len(output),
            "DFP archive group totals do not reconcile")
    require(len(output) <= P2_BASELINE,
            "DFP-only subset exceeds ADR-0002 P2 total")
    require(all(r["dfp_identity_research_state"]==STATE
                and r["adr0002_research_priority"]=="P2"
                and r["counts_as_adr0002_p1_candidate"] is False
                and r["source_mapping_state"]==NO_CFG
                and r["openocd_target_cfg"] is None
                and r["phase2_software_supported"] is False
                and r["production_write_authorized"] is False
                for r in output),
            "DFP-only archive must not claim ADR-0002 P1 or software SUPPORTED")
    return {
        "schema_version":1,
        "policy":"ADR-0002 Microchip DFP-only P2 manufacturer identity archive",
        "manufacturer":"Microchip",
        "source_subset_original_mcp_exact_icpns":SOURCE_SUBSET,
        "baseline_p0_exact_icpns_unchanged":P0_BASELINE,
        "baseline_p1_target_only_exact_icpns_unchanged":P1_TARGET_BASELINE,
        "adr0002_p1_openocd_candidate_exact_icpns":P1_TARGET_BASELINE,
        "adr0002_p2_archive_exact_icpns":P2_BASELINE,
        "dfp_only_p2_archive_exact_icpn_subset":len(output),
        "p2_other_archived_exact_icpns":P2_BASELINE-len(output),
        "dfp_only_archive_not_adr0002_p1":True,
        "manufacturer_dfp_original_index_sha256":gates.PINNED_DFP_SOURCE,
        "original_dfp_all_lanes_counts":dfp_lanes,
        "manufacturer_32bit_mcu_dfp_names_in_scope":len(eligible),
        "manufacturer_dfp_matched_distinct_base_names":len(bcounts),
        "dfp_archive_exact_icpn_by_manufacturer_pack":
            dict(sorted(pcounts.items())),
        "dfp_archive_exact_icpn_by_manufacturer_base":
            dict(sorted(bcounts.items())),
        "not_selected_mapping_gap_reasons":dict(sorted(gaps.items())),
        "source_replay_original_sha256_required":True,
        "dfp_archive_all_original_mcp_and_dfp_bytes_replayed":True,
        "baseline_p0_p1_records_reclassified":0,
        "new_phase1_fields_verified":0,
        "openocd_software_supported_count":0,
        "catalog_publication_authorized":False,
        "production_write_authorized":False,
        "phase2_programming_authorized":False,
        "phase3_hil_qualified":False,
        "records":output,
    }


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--upstream-cfg-report",type=Path,required=True)
    cli.add_argument("--dfp-evidence-root",type=Path,required=True)
    cli.add_argument("--output",type=Path,required=True)
    cli.add_argument("--verify",action="store_true")
    args=cli.parse_args()
    require("production" not in {p.casefold()
            for p in args.output.resolve().parts},
            "DFP archive cannot write to Production")
    raw=args.upstream_cfg_report.read_bytes()
    require(0<len(raw)<=MAX_BYTES,"full original-MCP source report unavailable")
    result=classify(json.loads(raw),archived_inventory(args.dfp_evidence_root))
    if args.verify:
        require(json.loads(args.output.read_text(encoding="utf-8"))==result,
                "source-bound P1 discovery report replay mismatch")
        print("MICROCHIP DFP-ONLY P2 ARCHIVE SOURCE REPLAY PASS")
    else:
        require(not args.output.exists(),
                "DFP archive results cannot be silently overwritten")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,indent=2,sort_keys=True)
            f.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k!="records"},
                     indent=2,sort_keys=True))


if __name__=="__main__":
    main()
