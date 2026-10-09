#!/usr/bin/env python3
from __future__ import annotations

import argparse,csv,hashlib,io,json,re
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
ROUTES=HERE/"openocd-parts-canonical-v627.csv"
RUNTIME=HERE/"openocd-production-runtime-capability-v6.31.json"
F3_AUTH=HERE/"stm32f3-ordering-authority-v3.1.json"
G4_AUTH=HERE/"stm32g4-ordering-authority-v2.0.json"

EXPECTED_TOTAL=4629
EXPECTED_MAPPED=4061
EXPECTED_GAP=568
EXPECTED_ACTIVE_ROUTE=3982
EXPECTED_ACTIVE_DENOM=4550

SAFE_FAMILIES={"STM32F3","STM32F7","STM32G4"}
BLOCKED_FAMILIES={"STM32C5","STM32H5","STM32N6","STM32WB0","STM32WL3"}
TARGETS={
    "STM32F3":"tcl/target/stm32f3x.cfg",
    "STM32F7":"tcl/target/stm32f7x.cfg",
    "STM32G4":"tcl/target/stm32g4x.cfg",
}
EXPECTED_GAP_FAMILY_COUNTS={
    "STM32C5":172,"STM32F3":10,"STM32F7":92,"STM32G4":1,
    "STM32H5":190,"STM32N6":32,"STM32WB0":24,"STM32WL3":47,
}
EXPECTED_DIRECT={"STM32F3":9,"STM32F7":92,"STM32G4":0}
EXPECTED_ROUTE_EXPANSIONS={
    "STM32F378VCH6":{
        "pattern":"STM32F378VCHx","family":"STM32F3 Series","subfamily":"STM32F3x8",
        "plasma_series":"STM32F3","target_config":"tcl/target/stm32f3x.cfg",
        "authority":"stm32f3-ordering-authority-v3.1",
    },
    "STM32G491RCY6TR":{
        "pattern":"STM32G491RCYx","family":"STM32G4 Series","subfamily":"STM32G491",
        "plasma_series":"STM32G4","target_config":"tcl/target/stm32g4x.cfg",
        "authority":"stm32g4-ordering-authority-v2.0",
    },
}
FIELDS=(
    "manufacturer","icpn","family","series","base_device",
    "outcome","reason","existing_identifier","existing_identifier_kind",
    "openocd_target_config","openocd_distribution","route_source",
    "production_runtime_commit","production_write_authorized",
)

def req(ok:bool,msg:str)->None:
    if not ok: raise RuntimeError(msg)

def sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def read_rows(path:Path)->list[dict[str,str]]:
    with path.open(newline="",encoding="utf-8") as h:
        return list(csv.DictReader(h))

def strip_option(row:dict[str,str])->str:
    icpn=row["icpn"]; suffix=row.get("option_suffix","")
    if suffix:
        req(icpn.endswith(suffix),f"{icpn}: option suffix mismatch")
        return icpn[:-len(suffix)]
    return icpn

def pattern_matches(pattern:str,value:str)->bool:
    expr="".join("[A-Z0-9]" if c.lower()=="x" else re.escape(c) for c in pattern)
    return re.fullmatch(expr,value) is not None

def validate_f3_expansion(icpn:str)->None:
    auth=json.loads(F3_AUTH.read_text(encoding="utf-8"))
    req(auth["authority_id"]=="stm32f3-ordering-authority-v3.1","F3 authority drift")
    req(icpn=="STM32F378VCH6","unexpected F3 expansion exact")
    rule=auth["series"]["STM32F378"]["bands"][0]
    req("C" in rule["flash_codes"],"F378 flash C no longer authorized")
    req("V/H" in rule["allowed_pin_package"],"F378 V/H no longer authorized")
    req(auth["common"]["temperature_c"]["6"]=="-40 to 85 C","F378 temperature authority drift")
    req(auth["common"]["pin_package"]["V/H"]=={"package":"UFBGA","pin_count":100},
        "F378 V/H physical authority drift")

def validate_g4_expansion(icpn:str)->None:
    auth=json.loads(G4_AUTH.read_text(encoding="utf-8"))
    req(auth["authority_id"]=="stm32g4-ordering-authority-v2.0","G4 authority drift")
    req(icpn=="STM32G491RCY6TR","unexpected G4 expansion exact")
    rule=next(x for x in auth["records"] if x["series"]=="STM32G491")
    req(rule["pin_count"]["R"]==64,"G491 R pin authority drift")
    req(rule["flash_kib"]["C"]==256,"G491 C flash authority drift")
    req(rule["package"]["Y"]=="WLCSP","G491 Y package authority drift")
    req(rule["temperature_c"]["6"]=="-40 to 85 C","G491 temperature authority drift")

def build():
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    req(len(manifest["sources"])==28,"Production source count drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"])==EXPECTED_TOTAL,
        "Production exact count drift")
    all_rows=[]
    for source in manifest["sources"]:
        path=(MANIFEST.parent/source["path"]).resolve()
        rows=read_rows(path)
        req(len(rows)==int(source["row_count"]),f"{source['family']}: row-count drift")
        all_rows.extend(rows)
    mapped=[r for r in all_rows if r["mapping_status"]!="no_mapping"]
    gaps=[r for r in all_rows if r["mapping_status"]=="no_mapping"]
    req(len(mapped)==EXPECTED_MAPPED,f"mapped drift: {len(mapped)}")
    req(len(gaps)==EXPECTED_GAP,f"gap drift: {len(gaps)}")
    fam_counts=dict(sorted(Counter(r["family"] for r in gaps).items()))
    req(fam_counts==EXPECTED_GAP_FAMILY_COUNTS,f"gap family partition drift: {fam_counts}")

    runtime=json.loads(RUNTIME.read_text(encoding="utf-8"))
    req(runtime["runtime"]["source_commit"]=="9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c",
        "Production runtime commit drift")
    req(runtime["governance"]["production_runtime_is_authority_for_backend_admissibility"] is True,
        "runtime authority policy drift")
    for fam in SAFE_FAMILIES:
        cap=runtime["target_configs"][fam]
        req(cap["present"] is True and cap["flash_bank_present"] is True,
            f"{fam}: Production runtime not flash-capable")
        req(cap["path"]==TARGETS[fam],f"{fam}: Production runtime target path drift")
    for fam in BLOCKED_FAMILIES:
        req(runtime["target_configs"][fam]["present"] is False,
            f"{fam}: Production runtime support changed; rebaseline required")

    routes=read_rows(ROUTES)
    by_key={(r["vendor"],r["part_number"],r["identifier_kind"]):r for r in routes}
    req(len(by_key)==len(routes),"route inventory duplicate key drift")

    results=[]
    direct_counts=Counter()
    expansion_counts=Counter()
    blocked_counts=Counter()
    for row in sorted(gaps,key=lambda r:r["icpn"]):
        fam=row["family"]
        common={
            "manufacturer":row["manufacturer"],"icpn":row["icpn"],"family":fam,
            "series":row["series"],"base_device":row["base_device"],
            "production_runtime_commit":runtime["runtime"]["source_commit"],
            "production_write_authorized":"false",
        }
        if fam in BLOCKED_FAMILIES:
            results.append({
                **common,
                "outcome":"blocked_runtime_target_absent",
                "reason":"target_config_absent_from_pinned_production_runtime",
                "existing_identifier":"","existing_identifier_kind":"",
                "openocd_target_config":"","openocd_distribution":"upstream-openocd",
                "route_source":"production_runtime_capability_v6.31",
            })
            blocked_counts[fam]+=1
            continue

        req(fam in SAFE_FAMILIES,f"{row['icpn']}: unexpected gap family")
        core=strip_option(row)
        matches=[
            r for r in routes
            if r["vendor"]=="STMicroelectronics"
            and r["openocd_distribution"]=="upstream-openocd"
            and r["mapping_status"]=="mapping_candidate"
            and r["validation_status"]=="not_verified"
            and pattern_matches(r["part_number"],core)
        ]
        if len(matches)==1:
            route=matches[0]
            req(route["identifier_kind"]=="ordering_pattern",f"{row['icpn']}: direct route kind drift")
            req(route["target_config"]==TARGETS[fam],f"{row['icpn']}: target config drift")
            results.append({
                **common,
                "outcome":"safe_mapping_candidate",
                "reason":"unique_existing_canonical_ordering_pattern_in_pinned_runtime",
                "existing_identifier":route["part_number"],
                "existing_identifier_kind":"ordering_pattern",
                "openocd_target_config":route["target_config"],
                "openocd_distribution":"upstream-openocd",
                "route_source":"openocd-parts-canonical-v627.csv",
            })
            direct_counts[fam]+=1
            continue

        req(len(matches)==0,f"{row['icpn']}: ambiguous canonical route matches={len(matches)}")
        exp=EXPECTED_ROUTE_EXPANSIONS.get(row["icpn"])
        req(exp is not None,f"{row['icpn']}: unmapped safe-family exact lacks bounded expansion authority")
        if fam=="STM32F3": validate_f3_expansion(row["icpn"])
        elif fam=="STM32G4": validate_g4_expansion(row["icpn"])
        else: raise RuntimeError(f"{row['icpn']}: unexpected expansion family")
        req(pattern_matches(exp["pattern"],core),f"{row['icpn']}: bounded expansion does not match exact core")
        req(exp["target_config"]==TARGETS[fam],f"{row['icpn']}: expansion target drift")
        req(("STMicroelectronics",exp["pattern"],"ordering_pattern") not in by_key,
            f"{row['icpn']}: expansion route already exists; rebaseline required")
        results.append({
            **common,
            "outcome":"safe_mapping_candidate",
            "reason":"bounded_authoritative_route_expansion_in_pinned_runtime",
            "existing_identifier":exp["pattern"],
            "existing_identifier_kind":"ordering_pattern",
            "openocd_target_config":exp["target_config"],
            "openocd_distribution":"upstream-openocd",
            "route_source":"openocd-final-route-delta-v6.31.csv",
        })
        expansion_counts[fam]+=1

    req(dict(direct_counts)==EXPECTED_DIRECT,f"direct route counts drift: {dict(direct_counts)}")
    req(dict(expansion_counts)=={"STM32F3":1,"STM32G4":1},f"expansion counts drift: {dict(expansion_counts)}")
    req(dict(sorted(blocked_counts.items()))=={
        "STM32C5":172,"STM32H5":190,"STM32N6":32,"STM32WB0":24,"STM32WL3":47,
    },f"blocked counts drift: {dict(blocked_counts)}")

    safe=[r for r in results if r["outcome"]=="safe_mapping_candidate"]
    blocked=[r for r in results if r["outcome"].startswith("blocked_")]
    req(len(safe)==103 and len(blocked)==465 and len(results)==568,"closure cardinality drift")
    req(len({r["icpn"] for r in results})==568,"closure duplicate exact identity")

    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader();w.writerows(results)
    csv_text=buf.getvalue()
    exact_digest=sha(("\n".join(r["icpn"] for r in results)+"\n").encode())
    safe_digest=sha(("\n".join(r["icpn"] for r in safe)+"\n").encode())
    blocked_digest=sha(("\n".join(r["icpn"] for r in blocked)+"\n").encode())

    delta=[]
    for icpn in ("STM32F378VCH6","STM32G491RCY6TR"):
        e=EXPECTED_ROUTE_EXPANSIONS[icpn]
        delta.append({
            "vendor":"STMicroelectronics","family":e["family"],"subfamily":e["subfamily"],
            "plasma_series":e["plasma_series"],"part_number":e["pattern"],
            "identifier_kind":"ordering_pattern","cpu_architectures":'["ARM Cortex-M"]',
            "target_config":e["target_config"],"openocd_distribution":"upstream-openocd",
            "mapping_status":"mapping_candidate","validation_status":"not_verified",
            "catalog_origin":"openocd-final-route-delta-v6.31.csv",
        })
    route_fields=list(routes[0])
    dbuf=io.StringIO(newline="")
    dw=csv.DictWriter(dbuf,fieldnames=route_fields,lineterminator="\n")
    dw.writeheader();dw.writerows(delta)
    delta_text=dbuf.getvalue()
    successor_rows=routes+delta
    sbuf=io.StringIO(newline="")
    sw=csv.DictWriter(sbuf,fieldnames=route_fields,lineterminator="\n")
    sw.writeheader();sw.writerows(successor_rows)
    successor_text=sbuf.getvalue()
    req(len(successor_rows)==7663,"route successor row-count drift")
    req(len({(r["vendor"],r["part_number"],r["identifier_kind"]) for r in successor_rows})==7663,
        "route successor duplicate-key drift")

    summary={
        "schema_version":1,
        "audit_id":"openocd-final-coverage-closure-v6.31",
        "record_state":"RESEARCH_ONLY_PREWRITE_NOT_AUTHORIZED",
        "production_prestate":{
            "exact_total":4629,"mapped":4061,"no_mapping":568,
            "active_openocd_route":3982,"active_denominator":4550,
            "coverage_percent":round(3982/4550*100,4),
        },
        "gap_exact_count":568,
        "gap_exact_set_sha256":exact_digest,
        "classification_csv_sha256":sha(csv_text.encode()),
        "safe_mapping_candidate_exact_count":103,
        "safe_mapping_candidate_exact_set_sha256":safe_digest,
        "blocked_exact_count":465,
        "blocked_exact_set_sha256":blocked_digest,
        "safe_by_family":dict(sorted(Counter(r["family"] for r in safe).items())),
        "blocked_by_family":dict(sorted(Counter(r["family"] for r in blocked).items())),
        "direct_existing_route_by_family":dict(sorted(direct_counts.items())),
        "bounded_route_expansion_by_family":dict(sorted(expansion_counts.items())),
        "route_delta":{
            "row_count":2,
            "csv_sha256":sha(delta_text.encode()),
            "patterns":[r["part_number"] for r in delta],
        },
        "route_successor":{
            "source":"openocd-parts-canonical-v627.csv",
            "preimage_row_count":7661,
            "postimage_row_count":7663,
            "csv_sha256":sha(successor_text.encode()),
        },
        "projected_if_103_promoted":{
            "mapped":4164,"no_mapping":465,
            "active_openocd_route":4085,"active_denominator":4550,
            "coverage_percent":round(4085/4550*100,4),
        },
        "claims":{
            "production_write_authorized":False,
            "alternate_openocd_distribution_promoted":False,
            "programming_profile_binding_claimed":False,
            "programming_verified_claimed":False,
            "engineering_verified_claimed":False,
            "hil_verified_claimed":False,
        },
    }
    return results,csv_text,delta_text,successor_text,summary

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--classification",type=Path)
    ap.add_argument("--route-delta",type=Path)
    ap.add_argument("--route-successor",type=Path)
    ap.add_argument("--summary",type=Path)
    args=ap.parse_args()
    _,classification,delta,successor,summary=build()
    if args.classification: args.classification.write_text(classification,encoding="utf-8")
    if args.route_delta: args.route_delta.write_text(delta,encoding="utf-8")
    if args.route_successor: args.route_successor.write_text(successor,encoding="utf-8")
    if args.summary: args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_FINAL_COVERAGE_CLOSURE_V631_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
