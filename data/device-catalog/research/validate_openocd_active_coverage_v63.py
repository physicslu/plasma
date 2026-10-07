#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
PUBLICATION = HERE / "st-final-layer1-production-publication-v6.2.json"
AUDIT = HERE / "openocd-active-coverage-classification-v6.3.json"
NONACTIVE = HERE / "st-production-not-current-active-v6.3.txt"

TIER_B = {"STM32F3", "STM32F7"}
TIER_C = {"STM32N6"}
TIER_D = {"STM32C5", "STM32H5", "STM32WL3", "STM32WB0"}

EXPECTED_TIER_A = {
    "STM32F2":72, "STM32F3":172, "STM32F4":3, "STM32F7":62,
    "STM32G0":42, "STM32G4":1, "STM32C0":17, "STM32L4":3,
    "STM32L1":2, "STM32U3":1, "STM32H7":14,
}
EXPECTED_TIER_B = {"STM32F3":10, "STM32F7":92}
EXPECTED_TIER_C = {"STM32N6":32}
EXPECTED_TIER_D = {"STM32C5":172, "STM32H5":190, "STM32WL3":47, "STM32WB0":24}

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)

def read_rows(path: Path) -> list[dict[str,str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))

def main() -> int:
    audit=json.loads(AUDIT.read_text(encoding="utf-8"))
    pub=json.loads(PUBLICATION.read_text(encoding="utf-8"))
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=manifest["sources"]

    req(len(sources)==28, "Production source count drift")
    req(sum(int(s["row_count"]) for s in sources)==4629, "Production exact total drift")
    req(pub["coverage_effect"]=={
        "whole_st_active_exact_denominator":4550,
        "whole_st_active_intersection_after":4550,
        "whole_st_active_gap_after":0,
        "whole_st_active_identity_coverage_after_percent":100,
    }, "v6.2 Active identity coverage drift")
    req(pub["catalog_backend_state_after"]=={"mapped":3673,"no_mapping":956},
        "v6.2 backend partition drift")

    all_rows=[]
    family_rows=defaultdict(list)
    for src in sources:
        path=(MANIFEST.parent/src["path"]).resolve()
        rows=read_rows(path)
        req(len(rows)==int(src["row_count"]), f"{src['family']}: manifest cardinality drift")
        all_rows.extend(rows)
        family_rows[src["family"]].extend(rows)
    req(len(all_rows)==4629, "Production row cardinality drift")

    mapped=[r for r in all_rows if r["mapping_status"]!="no_mapping"]
    unmapped=[r for r in all_rows if r["mapping_status"]=="no_mapping"]
    req(len(mapped)==3673 and len(unmapped)==956, "current backend partition drift")
    req(all(r["openocd_target_config"] for r in mapped),
        "mapped row without OpenOCD target config")
    req(all(not r["openocd_target_config"] for r in unmapped),
        "no_mapping row unexpectedly has OpenOCD target config")

    nonactive=[x.strip() for x in NONACTIVE.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(nonactive==sorted(nonactive), "79-row non-Active ledger must stay sorted")
    req(len(nonactive)==79 and len(set(nonactive))==79, "79-row non-Active ledger drift")
    req(hashlib.sha256(("\n".join(nonactive)+"\n").encode()).hexdigest()
        =="aa9b3b53e251f90f6026f496e6e571f380377a4eb2d2ee82539e1753eeab661b",
        "79-row non-Active digest drift")
    by={r["icpn"]:r for r in all_rows}
    req(all(x in by for x in nonactive), "historical non-Active identity missing from Production")
    req(all(
        by[x]["mapping_status"]!="no_mapping" and by[x]["openocd_target_config"]
        for x in nonactive
    ), "historical non-Active row is no longer fully OpenOCD-routed")

    active_mapped=len(mapped)-len(nonactive)
    req(active_mapped==3594, "Active OpenOCD route numerator drift")
    req(len(unmapped)==956, "Active no_mapping denominator partition drift")
    req(active_mapped+len(unmapped)==4550, "Active route/no_mapping partition != 4550")

    mapped_series=defaultdict(set)
    for family, rows in family_rows.items():
        for r in rows:
            if r["mapping_status"]!="no_mapping":
                mapped_series[(family,r["series"])].add(r["openocd_target_config"])
    req(all(len(v)==1 for v in mapped_series.values()),
        "mapped series contains conflicting OpenOCD target configs")

    tiers={"A":Counter(),"B":Counter(),"C":Counter(),"D":Counter()}
    for r in unmapped:
        key=(r["family"],r["series"])
        if key in mapped_series:
            tiers["A"][r["family"]]+=1
        elif r["family"] in TIER_B:
            tiers["B"][r["family"]]+=1
        elif r["family"] in TIER_C:
            tiers["C"][r["family"]]+=1
        elif r["family"] in TIER_D:
            tiers["D"][r["family"]]+=1
        else:
            raise SystemExit(f"unclassified no_mapping row: {r['icpn']} {r['family']} {r['series']}")

    req(dict(tiers["A"])==EXPECTED_TIER_A, f"Tier A drift: {dict(tiers['A'])}")
    req(dict(tiers["B"])==EXPECTED_TIER_B, f"Tier B drift: {dict(tiers['B'])}")
    req(dict(tiers["C"])==EXPECTED_TIER_C, f"Tier C drift: {dict(tiers['C'])}")
    req(dict(tiers["D"])==EXPECTED_TIER_D, f"Tier D drift: {dict(tiers['D'])}")
    req(sum(map(sum,(tiers[x].values() for x in tiers)))==956, "tier partition drift")

    req(audit["active_openocd_route_exact_count"]==3594, "audit route numerator drift")
    req(audit["active_no_mapping_exact_count"]==956, "audit route gap drift")
    req(audit["classification"]["tier_a_same_series_existing_route"]["count"]==389,
        "audit Tier A drift")
    req(audit["classification"]["tier_b_family_route_flash_capable_no_series_sibling"]["count"]==102,
        "audit Tier B drift")
    req(audit["classification"]["tier_c_upstream_debug_target_without_flash_bank"]["count"]==32,
        "audit Tier C drift")
    req(audit["classification"]["tier_d_no_direct_upstream_target_config"]["count"]==433,
        "audit Tier D drift")
    req(audit["projection_if_tier_a_qualified"]["active_openocd_route_exact_count"]==3983,
        "Tier A projection drift")
    req(audit["projection_if_tier_a_and_b_qualified"]["active_openocd_route_exact_count"]==4085,
        "Tier A+B projection drift")
    req(audit["upstream_openocd_binding"]["stm32n6x_has_flash_bank"] is False,
        "N6 must remain excluded from programming-route projection")
    req(all(v is False for v in audit["claims"].values()), "v6.3 capability overclaim")

    print("OPENOCD_ACTIVE_COVERAGE_CLASSIFICATION_V63_PASS")
    print("Active route=3594/4550=78.9890%; gap=956")
    print("Tier A=389; Tier B=102; Tier C=32; Tier D=433")
    print("Projected after A+B qualification=4085/4550=89.7802%")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
