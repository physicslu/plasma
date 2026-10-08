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
WL3 = HERE / "stm32wl3-commercial-icpn.csv"
EXACT = HERE / "st-stm32wl3-active-exact-mpn-v1.2.txt"
AUTHORITY = HERE / "stm32wl3-ordering-authority-v4.5.json"
PROPOSAL_LOCK = HERE / "stm32wl3-layer1-admission-proposal-v4.6.json"
AUDIT = HERE / "stm32wl3-layer1-production-publication-v4.7.json"

EXPECTED_WL3_SHA256 = "5278dfabde948987619881393c7c8db897499ec1647659076da120224b65f671"
EXPECTED_WL3_BLOB = "0a774823e5236e011a105cde355942821e9ebe48"
EXPECTED_EXACT_SHA256 = "4d7a67a26dbe6fe65ed492f0143116ae1898e183c9f57001f724a12af654b60d"
EXPECTED_PROPOSAL_SHA256 = "843d081c6905a2fc01b0c7efcad7bd6d88a126cfbcf545686a6eb4b8ce568686"
EXPECTED_AUTHORITY_SHA256 = "0e3f67d00af87d74052cfdb06ee38d94d324d263d0ddf0aa9b51fdcf38b11d75"
EXCEPTIONS = {"STM32WL31C8V6", "STM32WL31CBV6"}

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
            "WL31_C_PIN48_EXACT_PRODUCT_EXCEPTION"
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
    req(audit["approved_proposal_id"] == "stm32wl3-layer1-admission-proposal-v4.6",
        "approved proposal id drift")
    req(audit["approved_proposal_pr"] == 730, "approved proposal PR drift")
    req(audit["approved_proposal_head_sha"] ==
        "26aeb50707e9c4983bd8251c6a988b5845ca0970",
        "approved proposal head drift")
    req(audit["approved_proposal_merge_commit"] ==
        "f4474e5deb8f9285d533333b9dbd68223dd0d2e6",
        "approved proposal merge drift")
    req(audit["approved_proposal_workflow_run_id"] == 37426648748,
        "approved proposal workflow run drift")
    req(audit["approved_proposal_artifact_id"] == 11395307934,
        "approved proposal artifact id drift")
    req(audit["approved_proposal_artifact_zip_sha256"] ==
        "9bc906cb2fca075a8802bad476363337829506233dd9231856242d07d6fcbb07",
        "approved proposal artifact digest drift")
    req(audit["approved_candidate_exact_count"] == 47, "approved exact count drift")
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
        "backend_scope_evaluated_for_47_additions",
        "backend_route_claimed_for_no_mapping_rows",
        "programming_profile_scope_expanded",
        "engineering_verified_claimed",
        "field_evidence_claimed",
        "ps_hil_qualification_claimed",
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
    req(proposal["backend_state_for_new_rows"] == {"no_mapping": 47},
        "proposal backend state drift")
    req(proposal["metadata_exception_exact_icpns"] == sorted(EXCEPTIONS),
        "proposal exception set drift")
    req(proposal["production_write_authorized"] is False,
        "research proposal self-authorized")

    req(hashlib.sha256(AUTHORITY.read_bytes()).hexdigest() == EXPECTED_AUTHORITY_SHA256,
        "WL3 authority file drift")
    exact = exact_lines()
    req(len(exact) == 47 and len(set(exact)) == 47, "WL3 exact-set count/unique drift")
    req(digest_lines(exact) == EXPECTED_EXACT_SHA256, "WL3 exact-set digest drift")

    data = WL3.read_bytes()
    req(hashlib.sha256(data).hexdigest() == EXPECTED_WL3_SHA256,
        "WL3 Production SHA256 drift")
    req(git_blob(data) == EXPECTED_WL3_BLOB, "WL3 Production git blob drift")
    rows = read_rows(WL3)
    req(len(rows) == 47 and len({r["icpn"] for r in rows}) == 47,
        "WL3 Production count/unique drift")
    req(sorted(r["icpn"] for r in rows) == exact,
        "WL3 Production identities differ from locked Active set")
    req(all(r["mapping_status"] == "no_mapping" for r in rows),
        "WL3 Production contains mapped row without backend qualification")
    req(all(
        not r["cmsis_device_name"]
        and not r["existing_identifier"]
        and not r["existing_identifier_kind"]
        and not r["openocd_target_config"]
        for r in rows
    ), "WL3 no_mapping row carries backend route data")

    exceptions = {
        r["icpn"] for r in rows
        if r["verification_status"] == "verified_direct_st_exact_product_metadata_override"
    }
    req(exceptions == EXCEPTIONS, "WL3 exact metadata exception set drift")
    for row in rows:
        req(row["manufacturer"] == "STMicroelectronics" and row["family"] == "STM32WL3",
            f'{row["icpn"]}: identity scope drift')
        req(row["source_type"] ==
            "official_st_ordering_information_plus_current_active_exact_identity",
            f'{row["icpn"]}: source type drift')
        req(row["source_authority"] == "STMicroelectronics official",
            f'{row["icpn"]}: source authority drift')
        expected = (
            "verified_direct_st_exact_product_metadata_override"
            if row["icpn"] in EXCEPTIONS
            else "verified_st_ordering_information_codes_plus_current_active_exact_identity"
        )
        req(row["verification_status"] == expected,
            f'{row["icpn"]}: verification status drift')

    req(hashlib.sha256(reconstruct_proposal(rows)).hexdigest() == EXPECTED_PROPOSAL_SHA256,
        "published WL3 rows do not reconstruct approved proposal CSV")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    wl3s = [
        s for s in sources
        if s["manufacturer"] == "STMicroelectronics" and s["family"] == "STM32WL3"
    ]
    req(len(wl3s) == 1, "Production WL3 source missing/duplicated")
    source = wl3s[0]
    req(source["row_count"] == 47
        and source["sha256"] == EXPECTED_WL3_SHA256
        and source["git_blob_sha"] == EXPECTED_WL3_BLOB,
        "Production manifest WL3 integrity binding drift")
    current_total = sum(int(s["row_count"]) for s in sources)
    req(len(sources) >= 26, "Production source count regressed below WL3 publication poststate")
    req(current_total >= 4533, "Production exact total regressed below WL3 publication poststate")

    backend = Counter()
    for source in sources:
        path = (MANIFEST.parent / source["path"]).resolve()
        for row in read_rows(path):
            backend["no_mapping" if row["mapping_status"] == "no_mapping" else "mapped"] += 1
    req(backend["mapped"] >= 3673,
        f"Production mapped coverage regressed below WL3 publication poststate: {dict(backend)}")
    req(backend["mapped"] + backend["no_mapping"] == current_total,
        "current Production backend partition does not equal current exact total")

    req(audit["production_prestate"] == {
        "exact_total": 4486, "source_count": 25, "stm32wl3_exact": 0
    }, "publication prestate audit drift")
    req(audit["production_poststate"]["exact_total"] == 4533
        and audit["production_poststate"]["source_count"] == 26
        and audit["production_poststate"]["stm32wl3_exact"] == 47,
        "publication poststate audit drift")
    req(audit["stm32wl3_backend_state_after"] == {"mapped": 0, "no_mapping": 47},
        "WL3 backend poststate audit drift")
    req(audit["catalog_backend_state_after"] == {"mapped": 3673, "no_mapping": 860},
        "catalog backend poststate audit drift")
    req(audit["metadata_exception_exact_icpns"] == sorted(EXCEPTIONS),
        "publication metadata exception audit drift")
    req(audit["coverage_effect"]["whole_st_active_intersection_after"] == 4454
        and audit["coverage_effect"]["whole_st_active_gap_after"] == 96
        and audit["coverage_effect"]["whole_st_active_identity_coverage_after_percent"] == 97.8901,
        "coverage effect audit drift")

    print("STM32WL3_LAYER1_PRODUCTION_PUBLICATION_V47_PASS")
    print(f"STM32WL3=47; mapped=0; no_mapping=47; current_Production={current_total}; current_sources={len(sources)}")
    print(f"Current Production backend partition={backend['mapped']} mapped / {backend['no_mapping']} no_mapping")
    print("Whole-ST Active identity coverage=4454/4550=97.8901%")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
