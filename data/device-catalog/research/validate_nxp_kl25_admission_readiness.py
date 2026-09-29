#!/usr/bin/env python3
"""Fail-closed NXP KL25 12-exact-ICPN catalog admission-readiness validation."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from nxp_kl25_admission_readiness import (
  PRODUCTION_FIELDS, EXPECTED_COUNT, EXPECTED_EXACT_SHA, EXPECTED_PRODUCTION_BLOB,
  PRODUCTION, canonical_csv, build_rows, build_readiness, blob_bytes,
)

HERE=Path(__file__).resolve().parent
CANONICAL=HERE/"nxp-kl25-commercial-icpn.csv"
READINESS=HERE/"nxp-kl25-admission-readiness.json"
AUTHORITY=HERE/"nxp-kl25-metadata-authority.json"
EXPECTED_CANONICAL_SHA256="73876af1a6344c298dd98559f2ea824362b8ce4935308e7b598d842d537bab95"
EXPECTED_CANONICAL_BLOB="53087e9082445e7948f88e688ecd890b0454d788"

def req(ok:bool,msg:str)->None:
    if not ok:raise SystemExit(msg)

def main()->int:
    rows=build_rows()
    candidate=canonical_csv(rows)
    candidate_bytes=candidate.encode("utf-8")
    readiness=build_readiness(rows,candidate)

    req(CANONICAL.read_bytes()==candidate_bytes,"retained canonical CSV differs from deterministic renderer")
    req(hashlib.sha256(candidate_bytes).hexdigest()==EXPECTED_CANONICAL_SHA256,"canonical CSV SHA256 drifted")
    req(blob_bytes(candidate_bytes)==EXPECTED_CANONICAL_BLOB,"canonical CSV Git blob drifted")
    checked=json.loads(READINESS.read_text(encoding="utf-8"))
    req(checked==readiness,"checked-in readiness differs from deterministic renderer")
    req(readiness["readiness_id"]=="nxp-kl25-bounded-exact-icpn-admission-readiness-v1","readiness id drifted")
    req(readiness["catalog_admission_ready"] is True,"catalog readiness not open")
    req(readiness["next_gate"]=="nxp-kl25-production-publication-gate","publication gate drifted")
    req(readiness["canonical_candidate_sha256"]==EXPECTED_CANONICAL_SHA256,"readiness canonical SHA drifted")
    req(readiness["canonical_candidate_git_blob_sha"]==EXPECTED_CANONICAL_BLOB,"readiness canonical blob drifted")
    for fld in ("identity_ready_count","lifecycle_ready_count","metadata_ready_count","route_ready_count","frozen_exact_icpn_count"):
        req(readiness[fld]==EXPECTED_COUNT==12,f"{fld} drifted")
    req(readiness["frozen_exact_icpn_set_sha256"]==EXPECTED_EXACT_SHA,"exact identity digest drifted")
    for fld in ("excluded_non_active_part_number_count","manual_review_count","metadata_exception_count","route_bridge_count"):
        req(readiness[fld]==0,f"{fld}: unresolved admission blocker")
    req(readiness["excluded_non_active_part_numbers"]==[],"excluded identity set drifted")
    req(readiness["route_assignment_kind_counts"]=={"ordering_pattern":12},"route-kind counts drifted")
    req(readiness["mapping_status_counts"]=={"deterministic_ordering_pattern":12},"mapping counts drifted")
    req(readiness["flash_size_counts"]=={"32 KiB":4,"64 KiB":4,"128 KiB":4},"Flash size counts drifted")
    req(readiness["package_counts"]=={"HVQFN":6,"LQFP":6},"package counts drifted")
    req(readiness["pin_count_counts"]=={"32":3,"48":3,"64":3,"80":3},"pin count distribution drifted")
    req(readiness["temperature_grade_counts"]=={"-40..105 C":12},"temperature authority drifted")
    req(readiness["target_config"]=="tcl/target/kl25.cfg","target config drifted")
    req(readiness["claims"] and all(value is False for value in readiness["claims"].values()),"readiness safety claims escaped")

    parsed=list(csv.DictReader(io.StringIO(candidate)))
    req(len(parsed)==12 and tuple(parsed[0])==PRODUCTION_FIELDS,"canonical schema/cardinality drifted")
    parts=[r["icpn"] for r in parsed]
    req(parts==sorted(set(parts)),"canonical exact identities unsorted/duplicated")
    req(hashlib.sha256(("\n".join(parts)+"\n").encode("utf-8")).hexdigest()==EXPECTED_EXACT_SHA,"canonical identity digest differs from retained live discovery")
    req(Counter(r["existing_identifier"] for r in parsed)==Counter({
      "MKL25Z128xxx4":4,"MKL25Z32xxx4":4,"MKL25Z64xxx4":4}),"commercial-to-frozen pattern routing drifted")
    req(all(r["manufacturer"]=="NXP" and r["family"]=="KL25" and r["series"]=="KL25"
            and r["openocd_target_config"]=="tcl/target/kl25.cfg"
            and r["existing_identifier_kind"]=="ordering_pattern"
            and r["mapping_status"]=="deterministic_ordering_pattern"
            and r["cmsis_device_name"]==""
            and r["option_suffix"]==""
            and r["verification_status"]=="verified_nxp_manufacturer_documents_and_retained_active_commercial_identity"
            for r in parsed),"canonical route/metadata admission fields drifted")

    authority=json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(authority["authority_id"]=="nxp-kl25-commercial-metadata-authority-v1","metadata authority ID drifted")
    req(authority["documents"][0]["document"]=="KL25P80M48SF0" and
        authority["documents"][0]["revision"]=="5" and
        authority["documents"][1]["document"]=="KL25P80M48SF0RM" and
        authority["documents"][1]["revision"]=="3","manufacturer documents drifted")
    req(authority["claims"] and all(v is False for v in authority["claims"].values()),"metadata authority trust boundary escaped")

    req(blob_bytes(PRODUCTION.read_bytes())==EXPECTED_PRODUCTION_BLOB,"Production manifest changed during research-only readiness")
    production=json.loads(PRODUCTION.read_text(encoding="utf-8"))
    req(len(production["sources"])==23 and sum(int(s["row_count"]) for s in production["sources"])==2683,"Production boundary counts changed")
    req(all(s["manufacturer"]!="NXP" for s in production["sources"]),"NXP catalog identity leaked into Production")

    print("NXP KL25 admission readiness validation: PASS")
    print("12 Active; 12 metadata; 12 direct routes; 0 CMSIS bridge; 0 exceptions")
    print("Production unchanged=2683/23; next=nxp-kl25-production-publication-gate")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
