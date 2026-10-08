#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from openocd_backend_evolution_v616 import rewind_v616_backend

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CSV_PATH = HERE / "stm32h7-classic-commercial-icpn.csv"
GAP = HERE / "st-stm32h7-active-gap-v5.7.txt"
PROPOSAL = HERE / "stm32h7-layer1-admission-proposal-v5.8.json"
PUBLICATION = HERE / "stm32h7-layer1-production-publication-v5.9.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_CURRENT_SHA256 = "47ff2d7d19de3e21ecaba9ade44280d99657749def23c3c37bf79ad075ccb2c6"
EXPECTED_CURRENT_BLOB = "511840493c716016cddc99ac6c71f34196479d11"
EXPECTED_HISTORICAL_SHA256 = "35b9d2bc13da3a01809ea62b62557f5419b8d6f7139574ca4715a127f1e86465"
EXPECTED_HISTORICAL_BLOB = "fda7d9a4eaa9978d0a67416e8b339fc9aab4e5cc"
EXPECTED_GAP_SHA256 = "22587c53a237fe3d2d4a208641e6109dd4d1b67bab1e39c9da86c4233b76b834"

def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)

def main() -> int:
    raw = CSV_PATH.read_bytes()
    req(hashlib.sha256(raw).hexdigest() == EXPECTED_CURRENT_SHA256, "H7 v5.9 CSV SHA drift")
    req(git_blob(raw) == EXPECTED_CURRENT_BLOB, "H7 v5.9 CSV blob drift")
    text = raw.decode("utf-8")
    lines = text.splitlines()
    header = lines[0]
    rows = list(csv.DictReader(io.StringIO(text)))
    publication_rows = rewind_v616_backend(rows, "STM32H7")
    req(len(rows) == 205 and len({r["icpn"] for r in rows}) == 205, "H7 v5.9 cardinality drift")

    gap = [x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(gap == sorted(gap) and len(gap) == 14, "H7 v5.9 gap ledger drift")
    req(hashlib.sha256(("\n".join(gap)+"\n").encode()).hexdigest() == EXPECTED_GAP_SHA256,
        "H7 v5.9 gap digest drift")
    gap_set = set(gap)
    by = {r["icpn"]: r for r in publication_rows}
    delta = [by.get(x) for x in gap]
    req(all(delta), "H7 v5.9 approved identity missing")
    req(all(
        r["mapping_status"] == "no_mapping"
        and r["existing_identifier"] == ""
        and r["existing_identifier_kind"] == ""
        and r["openocd_target_config"] == ""
        for r in delta
    ), "H7 v5.9 delta inherited backend mapping")
    req(all(
        r["source_authority"] == "STMicroelectronics official"
        and r["verification_status"] ==
          "verified_st_ordering_information_codes_plus_current_active_exact_identity"
        for r in delta
    ), "H7 v5.9 delta metadata provenance drift")

    historical_lines = [
        line for line in lines[1:]
        if line.split(",", 2)[1] not in gap_set
    ]
    historical_raw = (header + "\n" + "\n".join(historical_lines) + "\n").encode()
    req(len(historical_lines) == 191, "H7 historical subset cardinality drift")
    req(hashlib.sha256(historical_raw).hexdigest() == EXPECTED_HISTORICAL_SHA256,
        "H7 historical 191-row bytes drifted")
    req(git_blob(historical_raw) == EXPECTED_HISTORICAL_BLOB,
        "H7 historical 191-row Git blob drifted")
    historical = list(csv.DictReader(io.StringIO(historical_raw.decode())))
    req(all(r["openocd_target_config"] == "tcl/target/stm32h7x.cfg" for r in historical),
        "H7 historical backend target drift")
    req(Counter(r["mapping_status"] for r in historical) == Counter({
        "deterministic_ordering_pattern":177,
        "deterministic_ordering_pattern_via_functional_option_bridge":1,
        "deterministic_cmsis_device_name":13,
    }), "H7 historical mapping partition drift")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    req(len(sources) == 28, "H7 v5.9 Production source-count drift")
    req(sum(int(s["row_count"]) for s in sources) >= 4620, "H7 v5.9 Production total regressed below publication poststate")
    h7 = [s for s in sources if s.get("manufacturer")=="STMicroelectronics" and s.get("family")=="STM32H7"]
    req(len(h7)==1, "H7 v5.9 manifest source missing/duplicated")
    req(h7[0] == {
        "manufacturer":"STMicroelectronics",
        "family":"STM32H7",
        "path":"../research/stm32h7-classic-commercial-icpn.csv",
        "row_count":205,
        "git_blob_sha":EXPECTED_CURRENT_BLOB,
        "sha256":EXPECTED_CURRENT_SHA256,
    }, "H7 v5.9 manifest binding drift")

    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    publication = json.loads(PUBLICATION.read_text(encoding="utf-8"))
    req(proposal["proposal_id"]=="stm32h7-layer1-admission-proposal-v5.8", "H7 proposal id drift")
    req(proposal["proposal_addition_count"]==14, "H7 proposal count drift")
    req(proposal["proposal_exact_set_sha256"]==EXPECTED_GAP_SHA256, "H7 proposal exact-set drift")
    req(proposal["backend_state_for_new_rows"]=={"no_mapping":14}, "H7 proposal backend state drift")
    req(proposal["existing_family_backend_mapping_inherited"] is False, "H7 proposal mapping inheritance drift")

    req(publication["owner_approval_received"] is True, "H7 owner approval missing")
    req(publication["production_poststate"]["exact_total"]==4620, "H7 publication total drift")
    req(publication["production_poststate"]["stm32h7_exact"]==205, "H7 publication H7 count drift")
    req(publication["stm32h7_backend_state_after"]=={"mapped":191,"no_mapping":14}, "H7 backend poststate drift")
    req(publication["catalog_backend_state_after"]=={"mapped":3673,"no_mapping":947}, "catalog backend partition drift")
    cov=publication["coverage_effect"]
    req(cov["whole_st_active_intersection_after"]==4541, "H7 coverage intersection drift")
    req(cov["whole_st_active_gap_after"]==9, "H7 residual gap drift")
    req(cov["whole_st_active_identity_coverage_after_percent"]==99.8022, "H7 coverage percent drift")
    for key in (
        "backend_scope_evaluated_for_14_additions",
        "historical_h7_mapping_inherited_by_14_additions",
        "backend_type_claimed_for_no_mapping_rows",
        "backend_route_claimed_for_no_mapping_rows",
        "programming_profile_scope_expanded",
        "engineering_verified_claimed",
        "field_evidence_claimed",
        "ps_hil_qualification_claimed",
    ):
        req(publication["claims"][key] is False, f"H7 v5.9 overclaim: {key}")

    print("STM32H7_LAYER1_PRODUCTION_PUBLICATION_V59_PASS")
    print("STM32H7=205; historical_mapped=191; delta_no_mapping=14")
    print("Production=4620; sources=28; backend=3673 mapped / 947 no_mapping")
    print("Whole-ST Active identity coverage=4541/4550=99.8022%")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
