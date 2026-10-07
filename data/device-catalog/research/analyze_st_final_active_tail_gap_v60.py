#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GAP = HERE / "st-final-active-tail-gap-v6.0.txt"
LOCK = HERE / "st-final-active-tail-gap-lock-v6.0.json"
AUTHORITY = HERE / "st-final-active-tail-gap-metadata-authority-v6.0.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_GAP = 9
EXPECTED_SHA = "891831ec21f6f65e5332667bf30440f321039740709d697312afd38a821ac801"
EXPECTED_FAMILIES = {"STM32F4":3,"STM32L4":3,"STM32L1":2,"STM32U3":1}
EXPECTED_PROD = {"STM32F4":384,"STM32L4":446,"STM32L1":144,"STM32U3":106}

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)

def load_gap() -> list[str]:
    rows=[x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(rows==sorted(rows), "tail gap must remain sorted")
    req(len(rows)==EXPECTED_GAP and len(set(rows))==EXPECTED_GAP, "tail gap cardinality drift")
    req(hashlib.sha256(("\n".join(rows)+"\n").encode()).hexdigest()==EXPECTED_SHA,
        "tail gap digest drift")
    return rows

def production_prestate() -> dict[str,int]:
    m=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=m["sources"]
    req(len(sources)==28, "Production source count drift")
    req(sum(int(s["row_count"]) for s in sources)==4620, "Production exact total drift")
    counts={s["family"]:int(s["row_count"]) for s in sources}
    for fam,count in EXPECTED_PROD.items():
        req(counts.get(fam)==count, f"{fam}: Production prestate drift")
    return counts

def analyze() -> dict[str,Any]:
    gap=load_gap()
    production_prestate()
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    authority=json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(lock["tail_gap_exact_count"]==9, "tail-gap lock count drift")
    req(lock["tail_gap_exact_set_sha256"]==EXPECTED_SHA, "tail-gap lock hash drift")
    req(lock["family_gap_counts"]==EXPECTED_FAMILIES, "tail-gap family lock drift")

    records=authority["records"]
    req(len(records)==9, "tail authority record count drift")
    by={r["icpn"]:r for r in records}
    req(set(by)==set(gap), "tail authority exact set drift")
    req(all(r["family"] in EXPECTED_FAMILIES for r in records), "foreign family in tail authority")
    req(Counter(r["family"] for r in records)==Counter(EXPECTED_FAMILIES),
        "tail authority family distribution drift")
    req(Counter(r["metadata_authority_mode"] for r in records)==Counter({
        "official_exact_product":5,
        "existing_ordering_grammar":4,
    }), "metadata authority partition drift")
    req(all(r["metadata_source_url"] for r in records), "metadata source missing")
    req(all(r["lifecycle_source_url"] for r in records), "lifecycle source missing")
    req(all(
        r["option_semantics"]=="opaque_manufacturer_suffix_preserved_literal"
        for r in records if r["metadata_authority_mode"]=="official_exact_product"
    ), "opaque exact-product suffix semantics were inferred")

    gov=authority["governance"]
    req(gov["decode_only_locked_tail_gap"] is True, "tail authority scope drift")
    req(gov["opaque_option_suffixes_are_not_semantically_inferred"] is True,
        "opaque suffix fail-closed guard opened")
    for key in (
        "backend_scope_evaluated",
        "existing_family_backend_mapping_inherited",
        "programming_profile_scope_expanded",
        "engineering_verified",
        "field_evidence_claimed",
        "ps_hil_qualification",
        "production_write_authorized",
    ):
        req(gov[key] is False, f"tail-gap overclaim: {key}")

    # Verify none are already published.
    m=json.loads(MANIFEST.read_text(encoding="utf-8"))
    published=set()
    for src in m["sources"]:
        if src["family"] not in EXPECTED_FAMILIES:
            continue
        path=(MANIFEST.parent/src["path"]).resolve()
        with path.open(newline="",encoding="utf-8") as stream:
            published.update(r["icpn"] for r in csv.DictReader(stream))
    req(not (set(gap)&published), "tail-gap identity already in Production")

    discrepancy=authority["lifecycle_policy"]["f4_current_authority_conflict"]
    req(set(discrepancy["affected_exact_icpns"])=={
        "STM32F405OGY6VTR","STM32F405OGY6WTR","STM32F437VIT6WTR"
    }, "F4 lifecycle discrepancy set drift")
    req(discrepancy["current_estore_status"]=="Active", "F4 eStore lifecycle authority drift")
    req(discrepancy["current_st_product_page_status"]=="NRND", "F4 product-page finding drift")

    return {
        "audit_id":"st-final-active-tail-gap-metadata-replay-v6.0",
        "input_active_gap_count":9,
        "metadata_ready_exact_count":9,
        "metadata_blocked_exact_count":0,
        "ordering_grammar_exact_count":4,
        "official_exact_product_authority_count":5,
        "opaque_option_suffix_exact_count":5,
        "metadata_exception_exact_count":0,
        "family_counts":dict(sorted(EXPECTED_FAMILIES.items())),
        "exact_set_sha256":EXPECTED_SHA,
        "f4_lifecycle_authority_conflict_count":3,
        "claims":{
            "backend_scope_evaluated":False,
            "existing_family_backend_mapping_inherited":False,
            "programming_profile_scope_expanded":False,
            "engineering_verified":False,
            "field_evidence_claimed":False,
            "ps_hil_qualification":False,
            "production_write_authorized":False,
        }
    }

if __name__=="__main__":
    print(json.dumps(analyze(),indent=2,sort_keys=True))
