#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
C5 = HERE / "stm32c5-commercial-icpn.csv"
EXACT = HERE / "st-c5-estore-172-active-exact-mpn-v0.7.txt"
AUTHORITY = HERE / "stm32c5-ordering-authority-v4.2.json"
PROPOSAL_LOCK = HERE / "stm32c5-layer1-admission-proposal-v4.3.json"
AUDIT = HERE / "stm32c5-layer1-production-publication-v4.4.json"
BACKEND_GATE = HERE / "st-c5-ps-backend-static-gate-v1.1.json"

EXPECTED_C5_SHA256 = "23ab7db39a1ebc8d1c4d4f90f042d695e77533f35206454a737d9dfd31579069"
EXPECTED_C5_BLOB = "1e0559ded8cde86a210097d9bcfce34708978e5c"
EXPECTED_EXACT_SHA256 = "32d81e2491f1c8973a778cf62828a0c76662f4fb1813bc611d8b8959607b36a3"
EXPECTED_PROPOSAL_SHA256 = "4cfb9cc166c395e6b2f402c8c1e8b30a452467b9de4e1c2e90996617b54d0ded"
EXPECTED_AUTHORITY_SHA256 = "59cc5b9b36c95de56a34dba68300e66bf31aa6fe155a11ada11d4feb5cf1e7e9"
EXCEPTIONS = {"STM32C551CCT7", "STM32C551CCT7TR"}

PROPOSAL_FIELDS = (
    "manufacturer","icpn","family","series","base_device","marketing_status",
    "catalog_resolution","package","pin_count","flash_size","temperature_grade",
    "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
    "existing_identifier","existing_identifier_kind","openocd_target_config",
    "metadata_source_reference","source_authority","verification_status",
    "programming_profile_state","metadata_exception",
)

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)

def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

def exact_lines() -> list[str]:
    return sorted(x.strip() for x in EXACT.read_text(encoding="utf-8").splitlines() if x.strip())

def digest_lines(rows: list[str]) -> str:
    return hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()

def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}".encode("ascii") + bytes([0]) + data).hexdigest()

def reconstruct_proposal(rows: list[dict[str, str]]) -> bytes:
    out = []
    for row in sorted(rows, key=lambda r: r["icpn"]):
        exception = (
            "C551_TEMP7_EXACT_ESTORE_EXCEPTION"
            if row["icpn"] in EXCEPTIONS else ""
        )
        out.append({
            "manufacturer": row["manufacturer"],
            "icpn": row["icpn"],
            "family": row["family"],
            "series": row["series"],
            "base_device": row["base_device"],
            "marketing_status": "Active",
            "catalog_resolution": "normalized",
            "package": row["package"],
            "pin_count": row["pin_count"],
            "flash_size": row["flash_size"],
            "temperature_grade": row["temperature_grade"],
            "option_suffix": row["option_suffix"],
            "backend_type": "openocd",
            "backend_mapping_state": "no_mapping",
            "backend_route_observation": "backend_not_evaluated_for_layer1_catalog_only_scope",
            "existing_identifier": "",
            "existing_identifier_kind": "",
            "openocd_target_config": "",
            "metadata_source_reference": row["source_reference"],
            "source_authority": row["source_authority"],
            "verification_status": row["verification_status"],
            "programming_profile_state": "unresolved_no_applicability_binding",
            "metadata_exception": exception,
        })
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=PROPOSAL_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out)
    return buf.getvalue().encode()

def main() -> int:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    req(audit["owner_approval_received"] is True, "owner approval missing")
    req(audit["approved_proposal_id"] == "stm32c5-layer1-admission-proposal-v4.3",
        "approved proposal id drift")
    req(audit["approved_proposal_pr"] == 727, "approved proposal PR drift")
    req(audit["approved_proposal_head_sha"] ==
        "e808392fbeccb9704ab43dc7d9d05e239b174168", "approved proposal head drift")
    req(audit["approved_proposal_merge_commit"] ==
        "3d2f24c7ab07b6e6aeb2099b0c3088b8875d654d", "approved proposal merge drift")
    req(audit["proposal_artifact_source_pr"] == 726, "proposal artifact source PR drift")
    req(audit["approved_proposal_workflow_run_id"] == 37423885129,
        "approved proposal workflow run drift")
    req(audit["approved_proposal_artifact_id"] == 11394182599,
        "approved proposal artifact id drift")
    req(audit["approved_proposal_artifact_zip_sha256"] ==
        "7099190da75462276a28887d4ce45e79a1cac1b0f4521faddbeb1b1be106e772",
        "approved proposal artifact digest drift")
    req(audit["approved_candidate_exact_count"] == 172, "approved exact count drift")
    req(audit["approved_candidate_exact_set_sha256"] == EXPECTED_EXACT_SHA256,
        "approved exact-set digest drift")
    req(audit["approved_candidate_csv_sha256"] == EXPECTED_PROPOSAL_SHA256,
        "approved proposal CSV digest drift")
    req(audit["approved_authority_sha256"] == EXPECTED_AUTHORITY_SHA256,
        "approved authority digest drift")

    claims = audit["claims"]
    req(claims["layer1_catalog_publication_authorized"] is True,
        "publication authorization missing")
    for key in (
        "backend_scope_evaluated_for_172_additions",
        "backend_route_claimed_for_no_mapping_rows",
        "programming_profile_scope_expanded",
        "engineering_verified_claimed",
        "field_evidence_claimed",
        "ps_hil_qualification_claimed",
        "c5_stldr_backend_promoted",
    ):
        req(claims[key] is False, f"{key} overclaim")

    proposal = json.loads(PROPOSAL_LOCK.read_text(encoding="utf-8"))
    req(proposal["proposal_exact_set_sha256"] == EXPECTED_EXACT_SHA256,
        "proposal exact-set drift")
    req(proposal["proposal_csv_sha256"] == EXPECTED_PROPOSAL_SHA256,
        "proposal CSV drift")
    req(proposal["authority_sha256"] == EXPECTED_AUTHORITY_SHA256,
        "proposal authority drift")
    req(proposal["backend_scope_evaluated"] is False,
        "proposal backend scope drift")
    req(proposal["backend_state_for_new_rows"] == {"no_mapping": 172},
        "proposal backend state drift")
    req(proposal["metadata_exception_exact_icpns"] == sorted(EXCEPTIONS),
        "proposal exception set drift")
    req(proposal["production_write_authorized"] is False,
        "research proposal self-authorized")

    req(hashlib.sha256(AUTHORITY.read_bytes()).hexdigest() == EXPECTED_AUTHORITY_SHA256,
        "C5 authority file drift")
    exact = exact_lines()
    req(len(exact) == 172 and len(set(exact)) == 172, "C5 exact set count/unique drift")
    req(digest_lines(exact) == EXPECTED_EXACT_SHA256, "C5 exact set digest drift")

    data = C5.read_bytes()
    req(hashlib.sha256(data).hexdigest() == EXPECTED_C5_SHA256,
        "C5 Production SHA256 drift")
    req(git_blob(data) == EXPECTED_C5_BLOB, "C5 Production git blob drift")
    rows = read_rows(C5)
    req(len(rows) == 172 and len({r["icpn"] for r in rows}) == 172,
        "C5 Production count/unique drift")
    req(sorted(r["icpn"] for r in rows) == exact,
        "C5 Production identities differ from locked Active set")
    req(all(r["mapping_status"] == "no_mapping" for r in rows),
        "C5 Production contains mapped row without backend qualification")
    req(all(
        not r["cmsis_device_name"]
        and not r["existing_identifier"]
        and not r["existing_identifier_kind"]
        and not r["openocd_target_config"]
        for r in rows
    ), "C5 no_mapping row carries backend route data")

    exceptions = {r["icpn"] for r in rows
                  if r["verification_status"] == "verified_direct_st_exact_product_metadata_override"}
    req(exceptions == EXCEPTIONS, "C5 exact metadata exception set drift")
    for row in rows:
        req(row["family"] == "STM32C5" and row["manufacturer"] == "STMicroelectronics",
            f'{row["icpn"]}: identity scope drift')
        req(row["source_type"] ==
            "official_st_ordering_information_plus_estore_active_exact_identity",
            f'{row["icpn"]}: source type drift')
        req(row["source_authority"] == "STMicroelectronics official",
            f'{row["icpn"]}: source authority drift')
        expected = (
            "verified_direct_st_exact_product_metadata_override"
            if row["icpn"] in EXCEPTIONS
            else "verified_st_ordering_information_codes_plus_current_estore_active_identity"
        )
        req(row["verification_status"] == expected,
            f'{row["icpn"]}: verification status drift')

    req(hashlib.sha256(reconstruct_proposal(rows)).hexdigest() == EXPECTED_PROPOSAL_SHA256,
        "published C5 rows do not reconstruct approved proposal CSV")

    backend_gate = json.loads(BACKEND_GATE.read_text(encoding="utf-8"))
    gates = backend_gate["gates"]
    req(gates["source_only_candidate_executable"] is False,
        "historical C5 backend source-only candidate became executable")
    req(gates["production_programming_authorized"] is False,
        "historical C5 backend unexpectedly authorizes programming")
    req(gates["plasma_target_cfg_deployed_and_loader_map_populated"] is False,
        "historical C5 backend unexpectedly claims deployed route")
    req(gates["real_dev_id_flash_geometry_readback_verified"] is False,
        "historical C5 backend unexpectedly claims hardware readback")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    c5s = [s for s in sources
           if s["manufacturer"] == "STMicroelectronics" and s["family"] == "STM32C5"]
    req(len(c5s) == 1, "Production C5 source missing/duplicated")
    source = c5s[0]
    req(source["row_count"] == 172
        and source["sha256"] == EXPECTED_C5_SHA256
        and source["git_blob_sha"] == EXPECTED_C5_BLOB,
        "Production manifest C5 integrity binding drift")
    current_total = sum(int(s["row_count"]) for s in sources)
    req(len(sources) >= 25, "Production source count regressed below C5 publication poststate")
    req(current_total >= 4486, "Production exact total regressed below C5 publication poststate")

    backend = Counter()
    for source in sources:
        path = (MANIFEST.parent / source["path"]).resolve()
        for row in read_rows(path):
            backend["no_mapping" if row["mapping_status"] == "no_mapping" else "mapped"] += 1
    req(backend["mapped"] >= 3673,
        f"Production mapped coverage regressed below C5 publication poststate: {dict(backend)}")
    req(backend["mapped"] + backend["no_mapping"] == current_total,
        "current Production backend partition does not equal current exact total")

    req(audit["production_prestate"] == {
        "exact_total": 4314, "source_count": 24, "stm32c5_exact": 0
    }, "publication prestate audit drift")
    req(audit["production_poststate"]["exact_total"] == 4486
        and audit["production_poststate"]["source_count"] == 25
        and audit["production_poststate"]["stm32c5_exact"] == 172,
        "publication poststate audit drift")
    req(audit["stm32c5_backend_state_after"] == {"mapped": 0, "no_mapping": 172},
        "C5 backend poststate audit drift")
    req(audit["catalog_backend_state_after"] == {"mapped": 3673, "no_mapping": 813},
        "catalog backend poststate audit drift")
    req(audit["metadata_exception_exact_icpns"] == sorted(EXCEPTIONS),
        "publication metadata exception audit drift")
    req(audit["coverage_effect"]["whole_st_active_intersection_after"] == 4407
        and audit["coverage_effect"]["whole_st_active_gap_after"] == 143
        and audit["coverage_effect"]["whole_st_active_identity_coverage_after_percent"] == 96.8571,
        "coverage effect audit drift")

    print("STM32C5_LAYER1_PRODUCTION_PUBLICATION_V44_PASS")
    print(f"STM32C5=172; mapped=0; no_mapping=172; current_Production={current_total}; current_sources={len(sources)}")
    print("Production backend partition=3673 mapped / 813 no_mapping")
    print("Whole-ST Active identity coverage=4407/4550=96.8571%")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
