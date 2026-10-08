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
H5 = HERE / "stm32h5-commercial-icpn.csv"
EXACT = HERE / "st-stm32h5-active-exact-mpn-v1.2.txt"
AUTHORITY = HERE / "stm32h5-ordering-authority-v2.7.json"
PROPOSAL_LOCK = HERE / "stm32h5-layer1-admission-proposal-v2.8.json"
AUDIT = HERE / "stm32h5-layer1-production-publication-v2.9.json"

EXPECTED_H5_SHA256 = "cdee4a1f765b3f345e89dc21d2b56d5344dd6345973a1013ec45feffebeec194"
EXPECTED_H5_BLOB = "5d95f712445e94ef800dd54a26739203b2f2b412"
EXPECTED_EXACT_SHA256 = "33b3d084b635a39f71e9d724aae3456bfb65c1e7e904b0b6547a849bd9dbee9b"
EXPECTED_PROPOSAL_SHA256 = "07e1c05a60e0eb19d00b61fa9a092e754752aeb9475a4fe7f3403eab7a0749cd"
EXPECTED_AUTHORITY_SHA256 = "2cd9372151db5997adaf44aaf5e029a0f8c566a3fa09daa0095fbeea258454a6"
EXPECTED_EXCEPTION_IDS = {
    "STM32H5E4ZJJ6",
    "STM32H5E4ZJJ7Q",
    "STM32H5E4ZKJ6",
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


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}".encode("ascii") + bytes([0]) + data).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def reconstruct_proposal(rows: list[dict[str, str]]) -> bytes:
    proposal = []
    for row in sorted(rows, key=lambda r: r["icpn"]):
        icpn = row["icpn"]
        proposal.append({
            "manufacturer": row["manufacturer"],
            "icpn": icpn,
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
            "backend_route_observation": "no_stm32h5_target_in_current_plasma_openocd_catalog",
            "existing_identifier": row["existing_identifier"],
            "existing_identifier_kind": row["existing_identifier_kind"],
            "openocd_target_config": row["openocd_target_config"],
            "metadata_source_reference": row["source_reference"],
            "source_authority": row["source_authority"],
            "verification_status": row["verification_status"],
            "programming_profile_state": "unresolved_no_applicability_binding",
            "metadata_exception": (
                "H5E4_PACKAGE_J_ORDERING_TABLE_OMISSION_EXACT_ST_QR_ROW"
                if icpn in EXPECTED_EXCEPTION_IDS else ""
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
    req(audit["approved_proposal_id"] == "stm32h5-layer1-admission-proposal-v2.8",
        "approved proposal id drift")
    req(audit["approved_proposal_pr"] == 705, "approved proposal PR drift")
    req(audit["approved_proposal_head_sha"] == "3ffdd336928d6e56e0860b1fd7ee2404c1d31750",
        "approved proposal head drift")
    req(audit["approved_candidate_exact_count"] == 190, "approved exact count drift")
    req(audit["approved_candidate_exact_set_sha256"] == EXPECTED_EXACT_SHA256,
        "approved exact-set digest drift")
    req(audit["approved_candidate_csv_sha256"] == EXPECTED_PROPOSAL_SHA256,
        "approved proposal CSV digest drift")
    req(audit["approved_authority_sha256"] == EXPECTED_AUTHORITY_SHA256,
        "approved authority digest drift")
    req(audit["claims"]["layer1_catalog_publication_authorized"] is True,
        "publication authorization missing")
    req(audit["claims"]["backend_route_claimed_for_no_mapping_rows"] is False,
        "backend route overclaim")
    req(audit["claims"]["programming_profile_scope_expanded"] is False,
        "programming profile overclaim")
    req(audit["claims"]["engineering_verified_claimed"] is False,
        "engineering verification overclaim")
    req(audit["claims"]["field_evidence_claimed"] is False,
        "field evidence overclaim")
    req(audit["claims"]["ps_hil_qualification_claimed"] is False,
        "HIL overclaim")

    proposal_lock = json.loads(PROPOSAL_LOCK.read_text(encoding="utf-8"))
    req(proposal_lock["proposal_exact_set_sha256"] == EXPECTED_EXACT_SHA256,
        "proposal lock exact-set drift")
    req(proposal_lock["proposal_csv_sha256"] == EXPECTED_PROPOSAL_SHA256,
        "proposal lock CSV drift")
    req(proposal_lock["authority_sha256"] == EXPECTED_AUTHORITY_SHA256,
        "proposal lock authority drift")
    req(proposal_lock["backend_state_counts"] == {"mapping_candidate": 0, "no_mapping": 190},
        "proposal backend partition drift")
    req(proposal_lock["production_write_authorized"] is False,
        "research proposal must not self-authorize Production")

    req(hashlib.sha256(AUTHORITY.read_bytes()).hexdigest() == EXPECTED_AUTHORITY_SHA256,
        "STM32H5 authority file drift")

    exact = sorted(x.strip() for x in EXACT.read_text(encoding="utf-8").splitlines() if x.strip())
    req(len(exact) == 190 and len(set(exact)) == 190, "H5 exact ledger count/unique drift")
    req(hashlib.sha256(("\n".join(exact) + "\n").encode()).hexdigest() == EXPECTED_EXACT_SHA256,
        "H5 exact ledger digest drift")

    data = H5.read_bytes()
    req(hashlib.sha256(data).hexdigest() == EXPECTED_H5_SHA256, "H5 Production SHA256 drift")
    req(git_blob(data) == EXPECTED_H5_BLOB, "H5 Production git blob drift")
    rows = read_rows(H5)
    req(len(rows) == 190 and len({r["icpn"] for r in rows}) == 190,
        "H5 Production count/unique drift")
    req(sorted(r["icpn"] for r in rows) == exact,
        "H5 Production exact identities differ from approved exact set")

    for row in rows:
        req(row["manufacturer"] == "STMicroelectronics" and row["family"] == "STM32H5",
            f'{row["icpn"]}: identity scope drift')
        req(row["mapping_status"] == "no_mapping", f'{row["icpn"]}: backend state drift')
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

    exception_rows = {r["icpn"]: r for r in rows if ";" in r["source_reference"]}
    req(set(exception_rows) == EXPECTED_EXCEPTION_IDS,
        f"bounded metadata exception set drift: {sorted(exception_rows)}")

    proposal_bytes = reconstruct_proposal(rows)
    req(hashlib.sha256(proposal_bytes).hexdigest() == EXPECTED_PROPOSAL_SHA256,
        "published H5 rows do not reconstruct the approved proposal CSV")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    req(manifest.get("status") == "production", "Production manifest status drift")
    sources = manifest["sources"]
    h5_sources = [
        s for s in sources
        if s["manufacturer"] == "STMicroelectronics" and s["family"] == "STM32H5"
    ]
    req(len(h5_sources) == 1, "Production H5 source missing/duplicated")
    source = h5_sources[0]
    req(source["row_count"] == 190
        and source["sha256"] == EXPECTED_H5_SHA256
        and source["git_blob_sha"] == EXPECTED_H5_BLOB,
        "Production manifest H5 integrity binding drift")
    current_total = sum(int(s["row_count"]) for s in sources)
    req(len(sources) >= 24, "Production source count regressed below H5 publication poststate")
    req(current_total >= 3906, "Production exact total regressed below H5 publication poststate")

    backend = Counter()
    for source in sources:
        path = (MANIFEST.parent / source["path"]).resolve()
        for row in read_rows(path):
            backend["no_mapping" if row["mapping_status"] == "no_mapping" else "mapped"] += 1
    req(backend["mapped"] >= 3673,
        f"Production mapped coverage regressed below H5 publication poststate: {dict(backend)}")
    req(backend["mapped"] + backend["no_mapping"] == current_total,
        "current Production backend partition does not equal current exact total")

    req(audit["production_prestate"] == {
        "exact_total": 3716, "source_count": 23, "stm32h5_exact": 0
    }, "publication prestate audit drift")
    req(audit["production_poststate"]["exact_total"] == 3906
        and audit["production_poststate"]["source_count"] == 24
        and audit["production_poststate"]["stm32h5_exact"] == 190,
        "publication poststate audit drift")
    req(audit["coverage_effect"]["whole_st_active_intersection_after"] == 3827
        and audit["coverage_effect"]["whole_st_active_gap_after"] == 723
        and audit["coverage_effect"]["whole_st_active_identity_coverage_after_percent"] == 84.1099,
        "coverage effect audit drift")

    print("STM32H5_LAYER1_PRODUCTION_PUBLICATION_V29_PASS")
    print(f"STM32H5=190; mapped=0; no_mapping=190; current_Production={current_total}; current_sources={len(sources)}")
    print("Whole-ST Active identity coverage=3827/4550=84.1099%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
