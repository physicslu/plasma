#!/usr/bin/env python3
"""ADR-0002 three implementation requirements: source-only NXP Core/Transport/Driver/ICPN.

This NEVER publishes a product-visible ICPN nor claims usable erase/program/verify.
Core/family research metadata cannot promote exact part applicability.
"""
import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
from nxp_adr0002_openocd_triage_v9 import (
    build as build_v9, serialize as serialize_v9,
    LEDGER as V9_LEDGER, blob, upstream_source as verify_upstream,
)

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LOCK=HERE/"nxp-adr0002-core-source-v10.json"
LEDGER=HERE/"nxp-501-adr0002-core-transport-qualification-v10.csv"
SUMMARY=HERE/"nxp-adr0002-core-aware-metrics-v10.json"
ADR=ROOT/"docs/adr/0002-openocd-software-qualified-catalog-visibility.md"
COLUMNS=(
"icpn manufacturer core_architecture core_model core_evidence_level core_evidence_uri "
"debug_transport debug_transport_evidence openocd_provider openocd_version "
"openocd_source_commit openocd_target_core_model target_config flash_bank_driver "
"flash_driver_source target_driver_link_state operation_probe_source "
"operation_erase_source operation_program_write_source operation_read_verify_qualification "
"exact_icpn_applicability exact_icpn_to_silicon_revision physical_validation "
"research_priority software_support_qualification identity_scope production_identity_admitted "
"public_catalog_visibility_authorized required_next_evidence"
).split()
EXPECTED_PRIORITY={"P0":27,"P1":38,"P2":436}
EXPECTED_CORE={"Cortex-M0+":65,"UNKNOWN":436}
EXPECTED_TRANSPORT={"UNKNOWN":468,"SWD":33}
EXPECTED_SOFTWARE={"CANDIDATE":65,"UNKNOWN":436}
EXPECTED_GROUPS=("KL25","LPC84x","LPC80x","K32L2")
ALLOWED_TRANSPORT=("SWD","JTAG","UNKNOWN")
P0_P1_ROUTES={
"KL25":("PINNED_TARGET_FLASH_BANK_DRIVER_SOURCE","kinetis","tcl/target/kl25.cfg"),
"LPC84x":("PINNED_TARGET_FLASH_BANK_DRIVER_SOURCE","lpc2000","tcl/target/lpc84x.cfg"),
"LPC80x":("GENERIC_TARGET_BANK_DRIVER_SOURCE_ONLY","lpc2000","tcl/target/lpc8xx.cfg"),
"K32L2":("FLASH_DRIVER_FAMILY_CLUE_ONLY","kinetis",""),
}
REQUIRED_RULE_HEADINGS=(
"Core-first Research Classification",
"Driver-first Software Qualification",
"Core-aware Coverage Metrics",
)

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def load_lock():
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock["schema_version"]==10 and lock["adr"]=="ADR-0002","ADR v10 schema drift")
    adrtxt=ADR.read_text(encoding="utf-8")
    adr_blob=blob(ADR.read_bytes())
    require(adr_blob in (lock["adr_git_blob"],lock["phase1_adr_git_blob"]),
            "ADR-0002 source revision is not reviewed/approved")
    if adr_blob==lock["phase1_adr_git_blob"]:
        require("## Implementation Phases — three IC detail sections" in adrtxt
                and "**Phase 1 — CURRENT**" in adrtxt
                and "**Phase 2 — DEFERRED**" in adrtxt,
                "Phased ADR contract changed: archived v10 cannot reauthorize Phase2")
    for heading in REQUIRED_RULE_HEADINGS:
        require(heading in adrtxt,"ADR-0002 approved implementation rule missing: "+heading)
    require(blob(V9_LEDGER.read_bytes())==lock["input_v9_git_blob"],"v9 501 source ledger changed")
    require(V9_LEDGER.read_bytes()==serialize_v9(build_v9()),"v9 original 501 source replay mismatch")
    require(lock["source_commit"]=="9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c","OpenOCD provider source changed")
    rules=lock["group_rules"]
    require(set(rules)==set(EXPECTED_GROUPS),"Core-family source authority changed")
    for name,rule in rules.items():
        require(rule["core"]=="Cortex-M0+" and rule["architecture"]=="ARM"
                and rule["vendor_url"].startswith("https://www.nxp.com/")
                and rule["transport"] in ALLOWED_TRANSPORT,
                "unsupported or ungrounded group Core assertion: "+name)
        expected=P0_P1_ROUTES[name]
        require((rule["route"],)==(expected[0],),"Target-driver chain state changed")
    require(len(lock["sources"])==4
            and {s["group"] for s in lock["sources"]}==set(rules),
            "NXP family core source ledger incomplete")
    return lock

def build():
    lock=load_lock()
    output=[]
    for row in build_v9():
        rules=lock["group_rules"].get(row["silicon_group"])
        driver=bool(row["driver_name"])
        if rules:
            expected=P0_P1_ROUTES[row["silicon_group"]]
            require(row["driver_name"]==expected[1]
                    and row["target_tcl_evidence"]==expected[2],
                    "Pinned target+driver chain mismatch "+row["icpn"])
        v={
            "icpn":row["icpn"],"manufacturer":"NXP",
            "core_architecture":rules["architecture"] if rules else "UNKNOWN",
            "core_model":rules["core"] if rules else "UNKNOWN",
            "core_evidence_level":"NXP_FAMILY_PAGE_NOT_EXACT_VARIANT" if rules else "UNKNOWN",
            "core_evidence_uri":rules["vendor_url"] if rules else "",
            "debug_transport":rules["transport"] if rules else "UNKNOWN",
            "debug_transport_evidence":rules["transport_evidence"] if rules else "UNKNOWN",
            "openocd_provider":row["provider"],"openocd_version":"0.12.0",
            "openocd_source_commit":lock["source_commit"],
            "openocd_target_core_model":rules["target_model"] if rules else "UNKNOWN",
            "target_config":row["target_tcl_evidence"],
            "flash_bank_driver":row["driver_name"] if driver else "UNKNOWN",
            "flash_driver_source":row["driver_c_evidence"],
            "target_driver_link_state":rules["route"] if rules else "NO_PINNED_PROGRAMMING_ROUTE_ESTABLISHED",
            "operation_probe_source":"DRIVER_SYMBOL_PRESENT" if driver else "UNKNOWN",
            "operation_erase_source":"DRIVER_SYMBOL_PRESENT" if driver else "UNKNOWN",
            "operation_program_write_source":"DRIVER_SYMBOL_PRESENT" if driver else "UNKNOWN",
            "operation_read_verify_qualification":"UNKNOWN",
            "exact_icpn_applicability":"UNVERIFIED",
            "exact_icpn_to_silicon_revision":"UNKNOWN",
            "physical_validation":"NO_CONFIGURATION_HIL_EVIDENCE_IN_THIS_RESEARCH",
            "research_priority":row["research_priority"],
            "software_support_qualification":row["openocd_software_state"],
            "identity_scope":row["identity_scope"],
            "production_identity_admitted":row["production_identity_admitted"],
            "public_catalog_visibility_authorized":"false",
            "required_next_evidence":rules["stop"] if rules else row["missing_next_evidence"]
        }
        require(v["debug_transport"] in ALLOWED_TRANSPORT,"invalid debug transport")
        require(v["software_support_qualification"] in ("UNKNOWN","CANDIDATE"),
                "unreviewed supported software classification")
        require(v["exact_icpn_applicability"]=="UNVERIFIED"
                and v["public_catalog_visibility_authorized"]=="false"
                and v["operation_read_verify_qualification"]=="UNKNOWN",
                "Core, CFG, source-driver or prioritization promoted support")
        if not rules:
            require(v["core_model"]==v["core_architecture"]=="UNKNOWN"
                    and v["debug_transport"]=="UNKNOWN",
                    "P2 unknown cores forced into ARM")
        output.append(v)
    require(len(output)==501 and len({r["icpn"] for r in output})==501,"501 exact ICPNs changed")
    require(Counter(r["research_priority"] for r in output)==EXPECTED_PRIORITY,"priority changed")
    require(Counter(r["core_model"] for r in output)==EXPECTED_CORE,"Core classification changed")
    require(Counter(r["debug_transport"] for r in output)==EXPECTED_TRANSPORT,"Transport classification changed")
    return output

def to_csv(rows):
    result=io.StringIO(newline="")
    writer=csv.DictWriter(result,fieldnames=COLUMNS,lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return result.getvalue().encode("utf-8")

def summary(rows):
    priority=Counter(r["research_priority"] for r in rows)
    core=Counter(r["core_model"] for r in rows)
    transport=Counter(r["debug_transport"] for r in rows)
    sw=Counter(r["software_support_qualification"] for r in rows)
    require(priority==EXPECTED_PRIORITY and core==EXPECTED_CORE
            and transport==EXPECTED_TRANSPORT and sw==EXPECTED_SOFTWARE,
            "Core-aware source metrics drift")
    profile_keys={}
    groupcounts=Counter()
    for r in rows:
        key=" | ".join((r["manufacturer"],r["core_architecture"],r["core_model"],
            r["debug_transport"],r["openocd_provider"]+"@"+r["openocd_version"],
            r["flash_bank_driver"]))
        groupcounts[key]+=1
        if r["target_driver_link_state"] in (
            "PINNED_TARGET_FLASH_BANK_DRIVER_SOURCE",
            "GENERIC_TARGET_BANK_DRIVER_SOURCE_ONLY"):
            pkey=r["target_config"]+"|"+r["flash_bank_driver"]
            profile_keys[pkey]={"target_config":r["target_config"],
                "flash_driver":r["flash_bank_driver"],
                "source_backed":"SOURCE_BLOB_ONLY",
                "device_profile_software_qualified":False}
    require(len(profile_keys)==3,"Cannot fabricate source-backed device profiles")
    return {
        "schema_version":10,"adr":"ADR-0002","manufacturer":"NXP",
        "metadata_granularity":"exact commercial ICPNs, bounded original 501 identities",
        "provider":"openocd-upstream","version":"0.12.0",
        "source_commit":"9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c",
        "original_research_exact_icpns":501,
        "production_identity_admitted_exact":224,"research_pending_exact":277,
        "source_backed_target_driver_research_profiles":len(profile_keys),
        "source_backed_target_driver_profile_keys":list(profile_keys.values()),
        "verified_exact_supported_by_this_new_research":0,
        "actual_product_supported_exact_denominator":None,
        "actual_user_facing_catalog_visible_exact":None,
        "physical_hil_tested_configuration_count":None,
        "unknown_is_not_zero":True,
        "priority_counts":dict(priority),"software_qualification_counts":dict(sw),
        "core_counts":dict(core),"debug_transport_counts":dict(transport),
        "core_unknown_exact":core["UNKNOWN"],
        "transport_unknown_exact":transport["UNKNOWN"],
        "by_manufacturer_core_transport_provider_driver":[
            {"key":key,"exact_icpn_count":count} for key,count in sorted(groupcounts.items())
        ],
        "denominator_warning":"501=bounded manufacturer source observation, NOT entire NXP population, OpenOCD supported total, or physically qualified population",
        "evidence_policy":"Core group classification is NXP family-level and never exact IC applicability or flash support. No ARM-majority claim from source target-config counts.",
        "operation_policy":"Source-level erase/write/probe symbol does not qualify target flash operations; read/verify is unknown until independently assessed.",
        "publication_or_runtime_modified":False
    }

def verify():
    rows=build()
    require(LEDGER.read_bytes()==to_csv(rows),"v10 501-row immutable Core-aware ledger mismatch")
    expect=json.loads(SUMMARY.read_text(encoding="utf-8"))
    require(expect==summary(rows),"Core-aware multi-denominator metrics mismatch")
    print("NXP_ADR0002_V10_PASS 501 ICPN; CORE_KNOWN=65 UNKNOWN=436; P0=27 P1=38 P2=436; SOURCE_TARGET_DRIVER_PROFILES=3; newly supported=0",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--upstream-root",type=Path)
    args=parser.parse_args()
    if args.upstream_root:
        from nxp_adr0002_openocd_triage_v9 import LOCK as V9_LOCK
        verify_upstream(args.upstream_root,json.loads(V9_LOCK.read_text(encoding="utf-8")))
    verify()
