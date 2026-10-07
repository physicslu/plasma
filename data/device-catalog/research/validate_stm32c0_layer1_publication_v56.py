#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CSV = HERE / "stm32c0-commercial-icpn.csv"
GAP = HERE / "st-stm32c0-active-gap-v5.4.txt"
PROPOSAL = HERE / "stm32c0-layer1-admission-proposal-v5.5.json"
PUBLICATION = HERE / "stm32c0-layer1-production-publication-v5.6.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_CSV_SHA256 = "ee05c901a6783afc65c1c0725c9cfeb27d934173805ec5a4d92bd09b18747a90"
EXPECTED_CSV_BLOB = "89108ae968cbc6c351f6b8854b888b465c51aae1"
EXPECTED_GAP_SHA256 = "03b7202842b52aaa6362386864d60c62f64d9cefea74d2d039691ea170b79097"

def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def require(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)

def main() -> int:
    raw = CSV.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == EXPECTED_CSV_SHA256, "C0 v5.6 CSV SHA-256 drift")
    require(git_blob(raw) == EXPECTED_CSV_BLOB, "C0 v5.6 CSV Git blob drift")

    with CSV.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 226, "C0 v5.6 row count drift")
    by = {r["icpn"]: r for r in rows}
    require(len(by) == 226, "C0 v5.6 duplicate exact identity")

    gap = [x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip()]
    require(len(gap) == 17, "C0 v5.6 gap count drift")
    require(hashlib.sha256(("\n".join(gap) + "\n").encode()).hexdigest() == EXPECTED_GAP_SHA256,
            "C0 v5.6 gap digest drift")
    additions = [by.get(x) for x in gap]
    require(all(additions), "C0 v5.6 approved identity missing")
    require(all(
        r["mapping_status"] == "no_mapping"
        and r["existing_identifier"] == ""
        and r["existing_identifier_kind"] == ""
        and r["openocd_target_config"] == ""
        for r in additions
    ), "C0 v5.6 backend boundary drift")
    require(all(
        r["source_authority"] == "STMicroelectronics official"
        and r["verification_status"] ==
            "verified_st_ordering_information_codes_plus_current_active_exact_identity"
        for r in additions
    ), "C0 v5.6 metadata authority drift")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    require(len(sources) == 28, "C0 v5.6 Production source-count drift")
    require(sum(int(s["row_count"]) for s in sources) == 4606,
            "C0 v5.6 Production exact-total drift")
    c0 = [s for s in sources if s.get("manufacturer") == "STMicroelectronics"
          and s.get("family") == "STM32C0"]
    require(len(c0) == 1, "C0 v5.6 manifest source missing/duplicated")
    require(c0[0] == {
        "manufacturer": "STMicroelectronics",
        "family": "STM32C0",
        "path": "../research/stm32c0-commercial-icpn.csv",
        "row_count": 226,
        "git_blob_sha": EXPECTED_CSV_BLOB,
        "sha256": EXPECTED_CSV_SHA256,
    }, "C0 v5.6 manifest binding drift")

    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    publication = json.loads(PUBLICATION.read_text(encoding="utf-8"))
    require(proposal["proposal_id"] == "stm32c0-layer1-admission-proposal-v5.5",
            "C0 v5.6 proposal identity drift")
    require(proposal["proposal_addition_count"] == 17, "C0 v5.6 proposal cardinality drift")
    require(publication["owner_approval_received"] is True, "C0 v5.6 owner approval missing")
    require(publication["approved_candidate_exact_count"] == 17, "C0 v5.6 approved count drift")
    require(publication["approved_candidate_exact_set_sha256"] == EXPECTED_GAP_SHA256,
            "C0 v5.6 approved set drift")
    require(publication["production_poststate"]["exact_total"] == 4606,
            "C0 v5.6 publication poststate drift")
    require(publication["catalog_backend_state_after"] == {"mapped": 3673, "no_mapping": 933},
            "C0 v5.6 catalog backend partition drift")
    cov = publication["coverage_effect"]
    require(cov["whole_st_active_exact_denominator"] == 4550, "C0 denominator drift")
    require(cov["whole_st_active_intersection_after"] == 4527, "C0 intersection drift")
    require(cov["whole_st_active_gap_after"] == 23, "C0 residual gap drift")
    require(cov["whole_st_active_identity_coverage_after_percent"] == 99.4945,
            "C0 coverage drift")
    claims = publication["claims"]
    require(claims["layer1_catalog_publication_authorized"] is True, "C0 publication authorization drift")
    for key in (
        "backend_scope_evaluated_for_17_additions",
        "backend_type_claimed_for_no_mapping_rows",
        "backend_route_claimed_for_no_mapping_rows",
        "programming_profile_scope_expanded",
        "engineering_verified_claimed",
        "field_evidence_claimed",
        "ps_hil_qualification_claimed",
    ):
        require(claims[key] is False, f"C0 v5.6 overclaim: {key}")

    print("STM32C0_LAYER1_PRODUCTION_PUBLICATION_V56_PASS")
    print("C0_ROWS 226")
    print("PRODUCTION_TOTAL 4606")
    print("WHOLE_ST_ACTIVE 4527/4550")
    print("WHOLE_ST_GAP 23")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
