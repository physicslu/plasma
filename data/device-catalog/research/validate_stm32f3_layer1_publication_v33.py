#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from openocd_backend_evolution_v616 import rewind_v616_backend
from openocd_backend_evolution_v621 import rewind_v621_backend
from openocd_backend_evolution_v631 import rewind_v631_backend

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
F3 = HERE / "stm32f3-commercial-icpn.csv"
ACTIVE = HERE / "st-stm32f3-active-exact-mpn-v3.0.txt"
GAP = HERE / "stm32f3-active-exact-gap-v3.0.txt"
AUTHORITY = HERE / "stm32f3-ordering-authority-v3.1.json"
PROPOSAL_LOCK = HERE / "stm32f3-layer1-admission-proposal-v3.2.json"
AUDIT = HERE / "stm32f3-layer1-production-publication-v3.3.json"

EXPECTED_F3_SHA256 = "3761e2e2552d9801ba16e185ea243e43b4eef916ee34d173ec57813bf71c0922"
EXPECTED_F3_BLOB = "b8c5566e99fca66dad402a01d9fc0d97922bb127"
EXPECTED_ACTIVE_SHA256 = "e3149bf214375dd50c20919fb2b42ec127626ba6440f62ea90f62e7fe6cde641"
EXPECTED_GAP_SHA256 = "1514c8edd3d190a8fd2bc9c27960c47f05ab4536640e008d73e4d5ab2f5a01d7"
EXPECTED_PROPOSAL_SHA256 = "de8938da114c261b55aee191a6d0916f4ef8e7d0f1cc16f08d3b870074fe3e47"
EXPECTED_AUTHORITY_SHA256 = "5d1f2d565450387b3e4c4074483dea40bfd8c9576e75df88c862da9790c03137"

LEGACY_MAPPED = {
    "STM32F301C6T6",
    "STM32F301C6T6TR",
    "STM32F301C6T7",
    "STM32F302C6T6",
    "STM32F303C6T6",
    "STM32F318C8T6",
    "STM32F318C8Y6TR",
    "STM32F334C4T6",
    "STM32F373C8T6",
    "STM32F373C8T6TR",
}

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
            "metadata_exception": "",
        })
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=PROPOSAL_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(proposal)
    return buf.getvalue().encode()


def main() -> int:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    req(audit["owner_approval_received"] is True, "owner approval missing")
    req(audit["approved_proposal_id"] == "stm32f3-layer1-admission-proposal-v3.2",
        "approved proposal id drift")
    req(audit["approved_proposal_pr"] == 710, "approved proposal PR drift")
    req(audit["approved_proposal_head_sha"] == "26a61f4548d3936c34a353ccf3679cd22fee9df9",
        "approved proposal head drift")
    req(audit["approved_candidate_exact_count"] == 182, "approved exact count drift")
    req(audit["approved_candidate_exact_set_sha256"] == EXPECTED_GAP_SHA256,
        "approved exact-set digest drift")
    req(audit["approved_candidate_csv_sha256"] == EXPECTED_PROPOSAL_SHA256,
        "approved proposal CSV digest drift")
    req(audit["approved_authority_sha256"] == EXPECTED_AUTHORITY_SHA256,
        "approved authority digest drift")

    claims = audit["claims"]
    req(claims["layer1_catalog_publication_authorized"] is True, "publication authorization missing")
    req(claims["backend_scope_evaluated_for_182_additions"] is False, "backend-scope overclaim")
    req(claims["backend_route_claimed_for_no_mapping_rows"] is False, "backend route overclaim")
    req(claims["programming_profile_scope_expanded"] is False, "programming-profile overclaim")
    req(claims["engineering_verified_claimed"] is False, "engineering overclaim")
    req(claims["field_evidence_claimed"] is False, "field-evidence overclaim")
    req(claims["ps_hil_qualification_claimed"] is False, "HIL overclaim")

    proposal = json.loads(PROPOSAL_LOCK.read_text(encoding="utf-8"))
    req(proposal["proposal_exact_set_sha256"] == EXPECTED_GAP_SHA256, "proposal exact-set drift")
    req(proposal["proposal_csv_sha256"] == EXPECTED_PROPOSAL_SHA256, "proposal CSV drift")
    req(proposal["authority_sha256"] == EXPECTED_AUTHORITY_SHA256, "proposal authority drift")
    req(proposal["backend_scope_evaluated"] is False, "proposal backend scope drift")
    req(proposal["backend_state_for_new_rows"] == {"no_mapping": 182}, "proposal backend state drift")
    req(proposal["production_write_authorized"] is False, "research proposal self-authorized")

    req(hashlib.sha256(AUTHORITY.read_bytes()).hexdigest() == EXPECTED_AUTHORITY_SHA256,
        "F3 authority file drift")

    active = sorted(x.strip() for x in ACTIVE.read_text(encoding="utf-8").splitlines() if x.strip())
    gap = sorted(x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip())
    req(len(active) == 192 and len(set(active)) == 192, "F3 Active exact-set count/unique drift")
    req(len(gap) == 182 and len(set(gap)) == 182, "F3 gap exact-set count/unique drift")
    req(digest_lines(active) == EXPECTED_ACTIVE_SHA256, "F3 Active exact-set digest drift")
    req(digest_lines(gap) == EXPECTED_GAP_SHA256, "F3 gap exact-set digest drift")

    data = F3.read_bytes()
    rows = read_rows(F3)
    v631_historical_rows = rewind_v631_backend(rows, "STM32F3")
    v616_current_rows = rewind_v621_backend(v631_historical_rows, "STM32F3")
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(v616_current_rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(v616_current_rows)
    v616_current_data = buf.getvalue().encode()
    req(hashlib.sha256(v616_current_data).hexdigest() == EXPECTED_F3_SHA256,
        "F3 post-v6.16 historical snapshot SHA256 drift")
    req(git_blob(v616_current_data) == EXPECTED_F3_BLOB,
        "F3 post-v6.16 historical snapshot git blob drift")
    publication_rows = rewind_v616_backend(v616_current_rows, "STM32F3")
    req(len(rows) == 192 and len({r["icpn"] for r in rows}) == 192,
        "F3 Production count/unique drift")
    req(sorted(r["icpn"] for r in rows) == active,
        "F3 Production exact identities differ from locked current-Active set")

    mapped = [r for r in publication_rows if r["mapping_status"] != "no_mapping"]
    unmapped = [r for r in publication_rows if r["mapping_status"] == "no_mapping"]
    req(len(mapped) == 10 and {r["icpn"] for r in mapped} == LEGACY_MAPPED,
        "legacy mapped F3 set drift")
    req(len(unmapped) == 182 and sorted(r["icpn"] for r in unmapped) == gap,
        "new F3 no_mapping set differs from approved additions")

    for row in mapped:
        req(row["existing_identifier_kind"] == "ordering_pattern",
            f'{row["icpn"]}: legacy mapping kind drift')
        req(row["mapping_status"] == "deterministic_ordering_pattern",
            f'{row["icpn"]}: legacy mapping status drift')
        req(row["openocd_target_config"] == "tcl/target/stm32f3x.cfg",
            f'{row["icpn"]}: legacy OpenOCD route drift')

    for row in unmapped:
        req(row["manufacturer"] == "STMicroelectronics" and row["family"] == "STM32F3",
            f'{row["icpn"]}: identity scope drift')
        req(not row["cmsis_device_name"]
            and not row["existing_identifier"]
            and not row["existing_identifier_kind"]
            and not row["openocd_target_config"],
            f'{row["icpn"]}: no_mapping row carries a backend route')
        req(row["source_type"] == "official_st_ordering_information_plus_estore_active_exact_identity",
            f'{row["icpn"]}: source type drift')
        req(row["source_authority"] == "STMicroelectronics official",
            f'{row["icpn"]}: source authority drift')
        req(row["verification_status"] ==
            "verified_st_ordering_information_codes_plus_current_estore_active_identity",
            f'{row["icpn"]}: verification status drift')

    req(hashlib.sha256(reconstruct_proposal(unmapped)).hexdigest() == EXPECTED_PROPOSAL_SHA256,
        "published F3 additions do not reconstruct approved proposal CSV")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    req(manifest.get("status") == "production", "Production manifest status drift")
    sources = manifest["sources"]
    f3_sources = [
        s for s in sources
        if s["manufacturer"] == "STMicroelectronics" and s["family"] == "STM32F3"
    ]
    req(len(f3_sources) == 1, "Production F3 source missing/duplicated")
    source = f3_sources[0]
    req(source["row_count"] == 192
        and source["sha256"] == hashlib.sha256(data).hexdigest()
        and source["git_blob_sha"] == git_blob(data),
        "Production manifest F3 current integrity binding drift")
    current_total = sum(int(s["row_count"]) for s in sources)
    req(len(sources) >= 24, "Production source count regressed below F3 publication poststate")
    req(current_total >= 4088, "Production exact total regressed below F3 publication poststate")

    backend = Counter()
    for source in sources:
        path = (MANIFEST.parent / source["path"]).resolve()
        for row in read_rows(path):
            backend["no_mapping" if row["mapping_status"] == "no_mapping" else "mapped"] += 1
    req(backend["mapped"] >= 3673,
        f"Production mapped coverage regressed below F3 publication poststate: {dict(backend)}")
    req(backend["mapped"] + backend["no_mapping"] == current_total,
        "current Production backend partition does not equal current exact total")

    req(audit["production_prestate"] == {
        "exact_total": 3906, "source_count": 24, "stm32f3_exact": 10
    }, "publication prestate audit drift")
    req(audit["production_poststate"]["exact_total"] == 4088
        and audit["production_poststate"]["source_count"] == 24
        and audit["production_poststate"]["stm32f3_exact"] == 192,
        "publication poststate audit drift")
    req(audit["stm32f3_backend_state_after"] == {"mapped": 10, "no_mapping": 182},
        "F3 backend poststate audit drift")
    req(audit["coverage_effect"]["whole_st_active_intersection_after"] == 4009
        and audit["coverage_effect"]["whole_st_active_gap_after"] == 541
        and audit["coverage_effect"]["whole_st_active_identity_coverage_after_percent"] == 88.1099,
        "coverage effect audit drift")

    print("STM32F3_LAYER1_PRODUCTION_PUBLICATION_V33_PASS")
    print(f"STM32F3=192; mapped=10; no_mapping=182; current_Production={current_total}; current_sources={len(sources)}")
    print("Whole-ST Active identity coverage=4009/4550=88.1099%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
