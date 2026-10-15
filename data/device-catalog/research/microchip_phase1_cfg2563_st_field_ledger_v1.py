#!/usr/bin/env python3
"""ADR-0002 Microchip 5-CFG 2,563 exact ICPNs: ST-style Phase 1 field ledger.

Consumes CI original-byte-replayed manufacturer MCP/DFP/Chart projections,
does not acquire new vendor bytes, infer SKU package or claim software
qualification, Production identity admission, Selector publication or HIL.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from microchip_phase1_information_v1 import FIELDS, STATUSES
import microchip_phase1_p0_information_ledger_v1 as p0

EXPECTED_BY_CFG = {
    "tcl/target/pic32mx.cfg": 1241,
    "tcl/target/at91samdXX.cfg": 667,
    "tcl/target/atsame5x.cfg": 354,
    "tcl/target/atsamv.cfg": 175,
    "tcl/target/atsaml1x.cfg": 126,
}
EXPECTED = 2563
FROZEN_IDENTITY_SHA256 = "0c37ad68c1db0a4fb50ff5a1d229faaca0ee6eac44cfb9d9b7de4e8a931daf2a"
ST_FIELDS = (
    "manufacturer", "icpn", "base_device", "package", "pin_count",
    "flash", "ram", "working_vdd", "io_supply", "vdda", "temperature",
    "core_architecture", "core_model",
)
FROM_MICROCHIP = {k: ("vdd" if k == "working_vdd" else k) for k in ST_FIELDS}
REQUIRED = ST_FIELDS[:11]  # optional two Core fields stay independent.
CFG_FAMILY_HINT = {
    "tcl/target/pic32mx.cfg": "PIC32MX",
    "tcl/target/at91samdXX.cfg": "SAM D research grouping",
    "tcl/target/atsame5x.cfg": "SAM E5x research grouping",
    "tcl/target/atsamv.cfg": "SAM V research grouping",
    "tcl/target/atsaml1x.cfg": "SAM L10/L11 research grouping",
}
SHA = "0123456789abcdef"
MAX_INPUT_BYTES = 64 * 1024 * 1024


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def is_sha(x):
    return type(x) is str and len(x) == 64 and set(x) <= set(SHA)


def freeze_digest(records):
    """Stable exact-manufacturer-identity+CFG digest, independent of chart fields."""
    canonical = [
        [r["icpn"].upper(), r["base_device"].upper(),
         r["openocd_target_cfg_research_only"]]
        for r in sorted(records, key=lambda x: x["icpn"].upper())
    ]
    return hashlib.sha256(json.dumps(canonical, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def normalize_field(old):
    state = old.get("status")
    require(state in STATUSES, "unrecognized Phase 1 field state")
    value = old.get("value")
    locator = old.get("source_locator")
    scope = old.get("evidence_scope")
    hashes = old.get("original_response_sha256_refs")
    unit = old.get("unit")
    if state == "UNKNOWN":
        require(value is None and locator is None and scope is None
                and hashes is None and unit is None,
                "UNKNOWN field must not carry fabricated evidence")
    elif state in ("VERIFIED", "PARTIAL"):
        require(value is not None
                and isinstance(locator, str) and bool(locator)
                and isinstance(scope, str) and bool(scope)
                and isinstance(hashes, list) and len(hashes) > 0
                and all(is_sha(s) for s in hashes),
                "field lacks independently cited official source evidence")
        if state == "PARTIAL":
            require(scope.startswith("official_"),
                    "family-scope PARTIAL lacks official Chart evidence")
        if state == "VERIFIED":
            require(scope == "exact_mcp_response_row",
                    "family/CFG evidence cannot be promoted to VERIFIED")
    else:
        # Conflict remains unresolved; do not select a winning value.
        require(value is None, "unresolved CONFLICT may not claim numeric value")
    return {
        "value": value,
        "state": state,
        "unit": unit,
        "source_authority": "Microchip Technology official" if hashes else None,
        "source_scope": scope or "none",
        "source_locator": locator,
        "source_sha256_refs": hashes or [],
        "notes": old.get("notes"),
    }


def from_ledgers(source, p0_info, p1_info, s1_info, upstream_sha):
    """Fail closed on source/projection drift before creating the frozen subset."""
    upstream_rows = p0.verify_upstream(source)
    require(is_sha(upstream_sha), "upstream SHA absent")
    require(len(upstream_rows) == 23276, "source population mismatch")
    require(s1_info.get("schema_version") == 1
            and s1_info.get("source_subset_observed_distinct_commercial_icpns")==23276
            and s1_info.get("phase1_s1_identified")==23276
            and s1_info.get("upstream_full_original_mcp_report_sha256")==upstream_sha
            and s1_info.get("production_write_authorized") is False
            and s1_info.get("catalog_publication_authorized") is False,
            "Phase 1 S1 original-source cohort unavailable")
    s1_rows = s1_info.get("records")
    require(isinstance(s1_rows, list) and len(s1_rows)==23276,
            "S1 row ledger incomplete")
    s1 = {}
    for rec in s1_rows:
        icpn = rec.get("icpn")
        require(isinstance(icpn, str) and icpn
                and icpn.upper() not in s1,
                "duplicate or invalid S1 material identity")
        s1[icpn.upper()] = rec
    for group, expected, src in (
        ("P0", 2437, p0_info),
        ("P1", 126, p1_info),
    ):
        require(src.get("manufacturer") == "Microchip"
                and src.get("schema_version")==1
                and src.get("original_cfg_reverse_source_report_sha256")==upstream_sha
                and src.get("phase1_field_contract")==list(FIELDS)
                and src.get("source_replayed_research_icpn_denominator")==23276
                and src.get("production_write_authorized") is False
                and src.get("catalog_publication_authorized") is False
                and src.get("phase2_programming_authorized") is False
                and src.get("phase3_compatibility_authorized") is False
                and len(src.get("records", []))==expected,
                group+" Phase 1 field ledger missing/altered")
    upstream = {r["icpn"].upper():r for r in upstream_rows}
    require(len(upstream)==23276, "duplicate upstream commercial ICPN")
    selected = []
    count = Counter()
    coverage = {f:Counter() for f in ST_FIELDS}
    by_cfg = defaultdict(lambda:{f:Counter() for f in ST_FIELDS})
    partial_locators = Counter()
    seen = set()
    for group, source_ledger in (("P0",p0_info),("P1",p1_info)):
        for row in source_ledger["records"]:
            code = row["icpn"].upper()
            require(code not in seen and code in upstream and code in s1,
                    "duplicate or outside original Phase 1 source identity")
            seen.add(code)
            original = upstream[code]
            info = s1[code]
            cfg = row.get("openocd_target_cfg_research_only")
            require(cfg in EXPECTED_BY_CFG and (
                group=="P0" or cfg=="tcl/target/atsaml1x.cfg"),
                "unreviewed CFG inclusion")
            require(row["base_device"].upper()==original["base_device"].upper()
                    and cfg==original["openocd_target_cfg"]
                    and row["source_original_mcp_response_sha256_refs"]==
                        original["original_mcp_response_sha256_refs"]
                    and info["phase1_identity_status"]=="IDENTIFIED"
                    and info["base_device"].upper()==row["base_device"].upper()
                    and info["research_priority_separate_from_phase"]==group
                    and info["original_mcp_response_sha256_refs"]==
                        original["original_mcp_response_sha256_refs"],
                    "Phase 1 identity/CFG/manufacturer evidence mismatch")
            require(row["internal_identity_admission"]=="NOT_ADMITTED"
                    and row["software_supported_claimed"] is False
                    and row["production_write_authorized"] is False
                    and info["internal_identity_admitted"] is False
                    and info["openocd_software_supported_asserted"] is False
                    and info["physical_hil_passed_asserted"] is False,
                    "Phase 1 sources contain qualification/admission overclaims")
            require(set(row["fields"]) == set(FIELDS),
                    "Microchip field contract drift")
            fields = {}
            for name in ST_FIELDS:
                old = row["fields"][FROM_MICROCHIP[name]]
                normalized = normalize_field(old)
                fields[name]=normalized
                coverage[name][normalized["state"]]+=1
                by_cfg[cfg][name][normalized["state"]]+=1
                if normalized["state"]=="PARTIAL":
                    partial_locators[name]+=1
            for name, expected_value in (("manufacturer","Microchip"),
                                         ("icpn",row["icpn"]),
                                         ("base_device",row["base_device"])):
                require(fields[name]["state"]=="VERIFIED"
                        and fields[name]["value"]==expected_value,
                        "original exact manufacturer identity not verified")
            count[cfg]+=1
            complete = all(fields[name]["state"]=="VERIFIED" for name in REQUIRED)
            selected.append({
                "adr":"ADR-0002",
                "phase":"IC_INFORMATION",
                "manufacturer":"Microchip",
                "icpn":row["icpn"],
                "base_device":row["base_device"],
                "family_research_hint":CFG_FAMILY_HINT[cfg],
                "openocd_target_cfg_research_only":cfg,
                "openocd_research_priority":group,
                "phase1_identity_status":"IDENTIFIED",
                "phase1_information_status":(
                    "INFORMATION_COMPLETE" if complete else "INFORMATION_INCOMPLETE"),
                "source_original_mcp_response_sha256_refs":
                    row["source_original_mcp_response_sha256_refs"],
                "source_original_mcp_observed_at_utc":
                    info["observed_at_utc_from_original_responses"],
                "fields":fields,
                "non_claims":{
                    "production_admission_changed":False,
                    "public_selector_eligibility_changed":False,
                    "openocd_software_supported":False,
                    "programming_profile_authority":False,
                    "physical_hil_passed":False,
                },
            })
    require(dict(count)==EXPECTED_BY_CFG and len(selected)==EXPECTED
            and len(seen)==EXPECTED, "five CFG frozen exact ICPN counts drift")
    selected.sort(key=lambda r:r["icpn"].upper())
    require(freeze_digest(selected)==FROZEN_IDENTITY_SHA256,
            "frozen 2563 exact ICPN / manufacturer Base / CFG membership changed")
    for f in ST_FIELDS:
        require(sum(coverage[f].values())==EXPECTED,"field denominator drift")
    s1_complete = sum(
        r["phase1_information_status"]=="INFORMATION_COMPLETE" for r in selected)
    chart_sha = p0_info.get("p0_family_chart_evidence",{}).get(
        "source_chart_original_sha256")
    p1_chart_sha = p1_info.get("p1_official_chart_evidence",{}).get(
        "official_original_chart_sha256")
    require(is_sha(chart_sha) and p1_chart_sha==chart_sha,
            "Microchip manufacturer Chart original byte SHA mismatch")
    require(s1_complete==0, "unexpected entire IC Information completion")
    return {
        "schema_version":1,
        "manufacturer":"Microchip",
        "adr":"ADR-0002",
        "phase":"01_IC_INFORMATION",
        "scope":"frozen_5cfg_2563_exact_original_manufacturer_icpns",
        "record_count":EXPECTED,
        "source_s1_identified_population":23276,
        "cfg_counts":dict(sorted(count.items())),
        "cfg_identity_freeze_sha256":freeze_digest(selected),
        "source_original_mcp_report_sha256":upstream_sha,
        "source_original_microchip_chart_sha256":chart_sha,
        "field_contract":list(ST_FIELDS),
        "field_coverage":{
            f:{state:coverage[f][state] for state in STATUSES}
            for f in ST_FIELDS},
        "per_cfg_field_coverage":{
            cfg:{f:{state:by_cfg[cfg][f][state] for state in STATUSES}
                 for f in ST_FIELDS}
            for cfg in sorted(count)},
        "s1_identified":EXPECTED,
        "s1_complete":s1_complete,
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "phase2_programming_authorized":False,
        "phase3_hil_authorized":False,
        "records":selected,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream-cfg-report",type=Path,required=True)
    p.add_argument("--p0-information-ledger",type=Path,required=True)
    p.add_argument("--p1-information-ledger",type=Path,required=True)
    p.add_argument("--s1-funnel",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--verify",action="store_true")
    args=p.parse_args()
    require("production" not in {part.casefold() for part in args.output.resolve().parts},
            "Phase 1 Research must not write Production")
    original=args.upstream_cfg_report.read_bytes()
    require(0<len(original)<=MAX_INPUT_BYTES,"invalid original replay report size")
    def read(path):
        raw=path.read_bytes()
        require(0<len(raw)<=MAX_INPUT_BYTES,"missing/oversized source ledger")
        return json.loads(raw)
    report=from_ledgers(
        json.loads(original),read(args.p0_information_ledger),
        read(args.p1_information_ledger),read(args.s1_funnel),
        hashlib.sha256(original).hexdigest())
    if args.verify:
        require(read(args.output)==report,"ST-style frozen 2563 Phase1 replay mismatch")
        print("MICROCHIP ST-STYLE 5CFG 2563 PHASE1 REPLAY PASS")
    else:
        require(not args.output.exists(),"refuse overwrite of research frozen report")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True,
                                          ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in
                     ("records","per_cfg_field_coverage")},indent=2,sort_keys=True,
                     ensure_ascii=False))


if __name__=="__main__":
    main()
