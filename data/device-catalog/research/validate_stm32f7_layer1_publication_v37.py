#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from openocd_backend_evolution_v616 import rewind_v616_backend

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
F7 = HERE / "stm32f7-commercial-icpn.csv"
GAP = HERE / "stm32f7-active-exact-gap-v3.4.txt"
AUTHORITY = HERE / "stm32f7-ordering-authority-v3.5.json"
PROPOSAL_LOCK = HERE / "stm32f7-layer1-admission-proposal-v3.6.json"
AUDIT = HERE / "stm32f7-layer1-production-publication-v3.7.json"

EXPECTED_F7_SHA256 = "cb23c11bcdb166ad7bb083d98ec0e19a2117a8d923bf23382a19747f7bf60538"
EXPECTED_F7_BLOB = "b2367ac8b8120f86ef4da33966f08c9e80955305"
EXPECTED_ACTIVE_SHA256 = "1b4b4692ed4a4f98984d2474e498ed8593739c093e7fb403bb966fcf70f7a736"
EXPECTED_GAP_SHA256 = "ec93408ecec154bf40a6fcd4d5ddb063e5e36cb023bc19bbed13b306a3b4a931"
EXPECTED_PROPOSAL_SHA256 = "bde4bbf82b4a528a18eb6d4d298b06cf8df9bbc7918150bfb9ed510cdbfe3170"
EXPECTED_AUTHORITY_SHA256 = "9828220050adfa19c7c6c6ff74a863ab2d3583d13258b6d286c3b831975129c6"

LEGACY_MAPPED = {
    "STM32F722ICK6",
    "STM32F722ICT6",
    "STM32F723ICK6",
    "STM32F723ICT6",
    "STM32F730I8K6",
    "STM32F730I8K6TR",
    "STM32F732IEK6",
    "STM32F732IET6",
    "STM32F733IEK6",
    "STM32F733IET6",
    "STM32F745IEK6",
    "STM32F745IEK6TR",
    "STM32F745IEK7",
    "STM32F745IEK7TR",
    "STM32F745IET6",
    "STM32F745IET7",
    "STM32F750N8H6",
    "STM32F778AIY6TR",
    "STM32F779AIY6TR",
}
OVERRIDES = {"STM32F750V8T6", "STM32F750V8T7", "STM32F750Z8T6"}

PROPOSAL_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "marketing_status",
    "catalog_resolution", "package", "pin_count", "flash_size", "temperature_grade",
    "option_suffix", "backend_type", "backend_mapping_state", "backend_route_observation",
    "existing_identifier", "existing_identifier_kind", "openocd_target_config",
    "metadata_source_reference", "source_authority", "verification_status",
    "programming_profile_state", "metadata_exception",
)


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}".encode("ascii") + bytes([0]) + data).hexdigest()


def digest_lines(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def reconstruct_proposal(rows: list[dict[str, str]]) -> bytes:
    proposal = []
    for row in sorted(rows, key=lambda r: r["icpn"]):
        proposal.append({
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
            "metadata_exception": (
                "F750_X8_EXACT_PRODUCT_METADATA_OVERRIDE"
                if row["icpn"] in OVERRIDES else ""
            ),
        })
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=PROPOSAL_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(proposal)
    return buf.getvalue().encode()


def main() -> int:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    req(audit["owner_approval_received"] is True, "owner approval missing")
    req(audit["approved_proposal_id"] == "stm32f7-layer1-admission-proposal-v3.6",
        "approved proposal id drift")
    req(audit["approved_proposal_pr"] == 716, "approved proposal PR drift")
    req(audit["approved_proposal_head_sha"] ==
        "5ecbce7032c01c49b147f038f78bcb8341ad01c4",
        "approved proposal head drift")
    req(audit["approved_proposal_merge_commit"] ==
        "a426c4075db8196b96d06123cd55375d10d6b203",
        "approved proposal merge commit drift")
    req(audit["approved_proposal_workflow_run_id"] == 36986283218,
        "approved proposal workflow run drift")
    req(audit["approved_proposal_artifact_id"] == 11217666554,
        "approved proposal artifact id drift")
    req(audit["approved_proposal_artifact_zip_sha256"] ==
        "41c5a63784d5c98b99c99c6c4c246dfeefd1b72a938394e7ff4290aeb23abc15",
        "approved proposal artifact digest drift")
    req(audit["approved_candidate_exact_count"] == 154, "approved exact count drift")
    req(audit["approved_candidate_exact_set_sha256"] == EXPECTED_GAP_SHA256,
        "approved exact-set digest drift")
    req(audit["approved_candidate_csv_sha256"] == EXPECTED_PROPOSAL_SHA256,
        "approved proposal CSV digest drift")
    req(audit["approved_authority_sha256"] == EXPECTED_AUTHORITY_SHA256,
        "approved authority digest drift")

    claims = audit["claims"]
    req(claims["layer1_catalog_publication_authorized"] is True,
        "publication authorization missing")
    req(claims["backend_scope_evaluated_for_154_additions"] is False,
        "backend-scope overclaim")
    req(claims["backend_route_claimed_for_no_mapping_rows"] is False,
        "backend route overclaim")
    req(claims["programming_profile_scope_expanded"] is False,
        "programming-profile overclaim")
    req(claims["engineering_verified_claimed"] is False, "engineering overclaim")
    req(claims["field_evidence_claimed"] is False, "field-evidence overclaim")
    req(claims["ps_hil_qualification_claimed"] is False, "HIL overclaim")

    proposal = json.loads(PROPOSAL_LOCK.read_text(encoding="utf-8"))
    req(proposal["proposal_exact_set_sha256"] == EXPECTED_GAP_SHA256,
        "proposal exact-set drift")
    req(proposal["proposal_csv_sha256"] == EXPECTED_PROPOSAL_SHA256,
        "proposal CSV drift")
    req(proposal["authority_sha256"] == EXPECTED_AUTHORITY_SHA256,
        "proposal authority drift")
    req(proposal["backend_scope_evaluated"] is False,
        "proposal backend scope drift")
    req(proposal["backend_state_for_new_rows"] == {"no_mapping": 154},
        "proposal backend state drift")
    req(proposal["metadata_override_exact_icpns"] == sorted(OVERRIDES),
        "proposal bounded override set drift")
    req(proposal["production_write_authorized"] is False,
        "research proposal self-authorized")

    req(hashlib.sha256(AUTHORITY.read_bytes()).hexdigest() == EXPECTED_AUTHORITY_SHA256,
        "F7 authority file drift")

    gap = sorted(x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip())
    req(len(gap) == 154 and len(set(gap)) == 154, "F7 gap exact-set count/unique drift")
    req(digest_lines(gap) == EXPECTED_GAP_SHA256, "F7 gap exact-set digest drift")
    active = sorted(LEGACY_MAPPED | set(gap))
    req(len(active) == 173, "F7 reconstructed Active exact count drift")
    req(digest_lines(active) == EXPECTED_ACTIVE_SHA256, "F7 Active exact-set digest drift")

    data = F7.read_bytes()
    req(hashlib.sha256(data).hexdigest() == EXPECTED_F7_SHA256,
        "F7 Production SHA256 drift")
    req(git_blob(data) == EXPECTED_F7_BLOB, "F7 Production git blob drift")
    rows = read_rows(F7)
    publication_rows = rewind_v616_backend(rows, "STM32F7")
    req(len(rows) == 173 and len({r["icpn"] for r in rows}) == 173,
        "F7 Production count/unique drift")
    req(sorted(r["icpn"] for r in rows) == active,
        "F7 Production exact identities differ from locked current-Active set")

    mapped = [r for r in publication_rows if r["mapping_status"] != "no_mapping"]
    unmapped = [r for r in publication_rows if r["mapping_status"] == "no_mapping"]
    req(len(mapped) == 19 and {r["icpn"] for r in mapped} == LEGACY_MAPPED,
        "legacy mapped F7 set drift")
    req(len(unmapped) == 154 and sorted(r["icpn"] for r in unmapped) == gap,
        "new F7 no_mapping set differs from approved additions")

    for row in mapped:
        req(row["existing_identifier_kind"] == "ordering_pattern",
            f'{row["icpn"]}: legacy mapping kind drift')
        req(row["mapping_status"] == "deterministic_ordering_pattern",
            f'{row["icpn"]}: legacy mapping status drift')
        req(row["openocd_target_config"] == "tcl/target/stm32f7x.cfg",
            f'{row["icpn"]}: legacy OpenOCD route drift')

    for row in unmapped:
        req(row["manufacturer"] == "STMicroelectronics" and row["family"] == "STM32F7",
            f'{row["icpn"]}: identity scope drift')
        req(not row["cmsis_device_name"]
            and not row["existing_identifier"]
            and not row["existing_identifier_kind"]
            and not row["openocd_target_config"],
            f'{row["icpn"]}: no_mapping row carries a backend route')
        req(row["source_type"] ==
            "official_st_ordering_information_plus_estore_active_exact_identity",
            f'{row["icpn"]}: source type drift')
        req(row["source_authority"] == "STMicroelectronics official",
            f'{row["icpn"]}: source authority drift')
        expected_verification = (
            "verified_direct_st_exact_product_metadata_override"
            if row["icpn"] in OVERRIDES
            else "verified_st_ordering_information_codes_plus_current_estore_active_identity"
        )
        req(row["verification_status"] == expected_verification,
            f'{row["icpn"]}: verification status drift')

    req(hashlib.sha256(reconstruct_proposal(unmapped)).hexdigest() == EXPECTED_PROPOSAL_SHA256,
        "published F7 additions do not reconstruct approved proposal CSV")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    req(manifest.get("status") == "production", "Production manifest status drift")
    sources = manifest["sources"]
    f7_sources = [
        s for s in sources
        if s["manufacturer"] == "STMicroelectronics" and s["family"] == "STM32F7"
    ]
    req(len(f7_sources) == 1, "Production F7 source missing/duplicated")
    source = f7_sources[0]
    req(source["row_count"] == 173
        and source["sha256"] == EXPECTED_F7_SHA256
        and source["git_blob_sha"] == EXPECTED_F7_BLOB,
        "Production manifest F7 integrity binding drift")
    current_total = sum(int(s["row_count"]) for s in sources)
    req(len(sources) >= 24, "Production source count regressed below F7 publication poststate")
    req(current_total >= 4242, "Production exact total regressed below F7 publication poststate")

    backend = Counter()
    for source in sources:
        path = (MANIFEST.parent / source["path"]).resolve()
        for row in read_rows(path):
            backend["no_mapping" if row["mapping_status"] == "no_mapping" else "mapped"] += 1
    req(backend["mapped"] >= 3673,
        f"Production mapped coverage regressed below F7 publication poststate: {dict(backend)}")
    req(backend["mapped"] + backend["no_mapping"] == current_total,
        "current Production backend partition does not equal current exact total")

    req(audit["production_prestate"] == {
        "exact_total": 4088, "source_count": 24, "stm32f7_exact": 19
    }, "publication prestate audit drift")
    req(audit["production_poststate"]["exact_total"] == 4242
        and audit["production_poststate"]["source_count"] == 24
        and audit["production_poststate"]["stm32f7_exact"] == 173,
        "publication poststate audit drift")
    req(audit["stm32f7_backend_state_after"] == {"mapped": 19, "no_mapping": 154},
        "F7 backend poststate audit drift")
    req(audit["approved_addition_backend_state"]["mapped"] == 0
        and audit["approved_addition_backend_state"]["no_mapping"] == 154,
        "approved addition backend poststate audit drift")
    req(audit["catalog_backend_state_after"] == {"mapped": 3673, "no_mapping": 569},
        "catalog backend poststate audit drift")
    req(audit["metadata_override_exact_icpns"] == sorted(OVERRIDES),
        "publication bounded override audit drift")
    req(audit["coverage_effect"]["whole_st_active_intersection_after"] == 4163
        and audit["coverage_effect"]["whole_st_active_gap_after"] == 387
        and audit["coverage_effect"]["whole_st_active_identity_coverage_after_percent"] == 91.4945,
        "coverage effect audit drift")

    print("STM32F7_LAYER1_PRODUCTION_PUBLICATION_V37_PASS")
    print(f"STM32F7=173; mapped=19; no_mapping=154; current_Production={current_total}; current_sources={len(sources)}")
    print("Production backend partition=3673 mapped / 569 no_mapping")
    print("Whole-ST Active identity coverage=4163/4550=91.4945%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
