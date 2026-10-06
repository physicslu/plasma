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
N6 = HERE / "stm32n6-commercial-icpn.csv"
EXACT = HERE / "st-stm32n6-active-exact-mpn-v1.2.txt"
PROPOSAL_LOCK = HERE / "stm32n6-layer1-admission-proposal-v4.9.json"
AUDIT = HERE / "stm32n6-layer1-production-publication-v5.0.json"

EXPECTED_N6_SHA256 = "ef43825a35e7cc2b4548c9fe050ade05f8149253b4c7da055a89e057965dbfc7"
EXPECTED_N6_BLOB = "937aeb4468fa7babd0c7b84d0bee72468d445002"
EXPECTED_EXACT_SHA256 = "f3ae0640f7e28c14b40b7b2ff83570e0bd95c7d0bd3bd98baac6edbcfc78bd50"
EXPECTED_PROPOSAL_SHA256 = "af1badb6c8ae555b0364421c1e88b7117d07a8e0bc362e6bce71f3df02c8a81e"
EXPECTED_AUTHORITY_SHA256 = "a1abca6e300936583198e73053d1894496fb1764a2fb7874a489f9e5cc3dbe2f"

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
    return sorted(
        x.strip()
        for x in EXACT.read_text(encoding="utf-8").splitlines()
        if x.strip()
    )

def digest_lines(rows: list[str]) -> str:
    return hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()

def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}".encode("ascii") + bytes([0]) + data
    ).hexdigest()

def reconstruct_proposal(rows: list[dict[str, str]]) -> bytes:
    out: list[dict[str, str]] = []
    for row in sorted(rows, key=lambda r: r["icpn"]):
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
            "backend_type": "",
            "backend_mapping_state": "no_mapping",
            "backend_route_observation":
                "backend_not_evaluated_catalog_only_external_memory_profile_unresolved",
            "existing_identifier": "",
            "existing_identifier_kind": "",
            "openocd_target_config": "",
            "metadata_source_reference": row["source_reference"],
            "source_authority": row["source_authority"],
            "verification_status": row["verification_status"],
            "programming_profile_state":
                "unresolved_external_memory_programming_profile_boundary",
            "metadata_exception": "",
        })

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=PROPOSAL_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out)
    return buf.getvalue().encode()

def main() -> int:
    rows = read_rows(N6)
    exact = exact_lines()
    proposal = json.loads(PROPOSAL_LOCK.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))

    req(len(rows) == 32 and len({r["icpn"] for r in rows}) == 32,
        "N6 Production count/unique drift")
    req(sorted(r["icpn"] for r in rows) == exact,
        "N6 Production identities differ from locked Active set")
    req(digest_lines(exact) == EXPECTED_EXACT_SHA256,
        "N6 exact identity digest drift")

    data = N6.read_bytes()
    req(hashlib.sha256(data).hexdigest() == EXPECTED_N6_SHA256,
        "N6 canonical SHA256 drift")
    req(git_blob(data) == EXPECTED_N6_BLOB,
        "N6 canonical Git blob drift")

    req(all(r["mapping_status"] == "no_mapping" for r in rows),
        "N6 Production contains mapped row without backend qualification")
    req(all(
        not r["cmsis_device_name"]
        and not r["existing_identifier"]
        and not r["existing_identifier_kind"]
        and not r["openocd_target_config"]
        for r in rows
    ), "N6 no_mapping row carries backend route data")

    for row in rows:
        req(
            row["manufacturer"] == "STMicroelectronics"
            and row["family"] == "STM32N6",
            f'{row["icpn"]}: identity scope drift',
        )
        req(row["package"] == "VFBGA",
            f'{row["icpn"]}: package drift')
        req(row["flash_size"] == "0-1 KiB",
            f'{row["icpn"]}: N6 flash metadata drift')
        req(row["temperature_grade"] == "-40 to 125 C",
            f'{row["icpn"]}: temperature grade drift')
        req(
            row["source_type"]
            == "official_st_ordering_information_plus_current_active_exact_identity",
            f'{row["icpn"]}: source type drift',
        )
        req(row["source_reference"]
            == "https://www.st.com/resource/en/datasheet/stm32n657a0.pdf",
            f'{row["icpn"]}: source reference drift')
        req(row["source_authority"] == "STMicroelectronics official",
            f'{row["icpn"]}: source authority drift')
        req(
            row["verification_status"]
            == "verified_st_ordering_information_codes_plus_current_active_exact_identity",
            f'{row["icpn"]}: verification status drift',
        )

    req(hashlib.sha256(reconstruct_proposal(rows)).hexdigest()
        == EXPECTED_PROPOSAL_SHA256,
        "published N6 rows do not reconstruct approved proposal CSV")

    req(proposal["proposal_id"] == "stm32n6-layer1-admission-proposal-v4.9",
        "approved proposal id drift")
    req(proposal["proposal_addition_count"] == 32,
        "approved proposal count drift")
    req(proposal["proposal_exact_set_sha256"] == EXPECTED_EXACT_SHA256,
        "approved exact-set lock drift")
    req(proposal["proposal_csv_sha256"] == EXPECTED_PROPOSAL_SHA256,
        "approved proposal CSV digest drift")
    req(proposal["authority_sha256"] == EXPECTED_AUTHORITY_SHA256,
        "approved metadata authority digest drift")
    req(proposal["production_write_authorized"] is False,
        "research proposal unexpectedly self-authorized Production")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    n6s = [
        s for s in sources
        if s["manufacturer"] == "STMicroelectronics"
        and s["family"] == "STM32N6"
    ]
    req(len(n6s) == 1, "Production N6 source missing/duplicated")
    source = n6s[0]
    req(
        source["row_count"] == 32
        and source["sha256"] == EXPECTED_N6_SHA256
        and source["git_blob_sha"] == EXPECTED_N6_BLOB,
        "Production manifest N6 integrity binding drift",
    )
    req(len(sources) == 27, "Production source count drift")
    req(sum(int(s["row_count"]) for s in sources) == 4565,
        "Production exact total drift")

    backend = Counter()
    for source in sources:
        path = (MANIFEST.parent / source["path"]).resolve()
        for row in read_rows(path):
            backend[
                "no_mapping" if row["mapping_status"] == "no_mapping" else "mapped"
            ] += 1
    req(backend == Counter({"mapped": 3673, "no_mapping": 892}),
        f"Production backend partition drift: {dict(backend)}")

    req(audit["owner_approval_received"] is True,
        "owner approval audit missing")
    req(audit["approved_proposal_pr"] == 733,
        "approved proposal PR drift")
    req(audit["approved_proposal_merge_commit"]
        == "b0231e2a520897b962036ebee7a67d5ed689e7c2",
        "approved proposal merge commit drift")
    req(audit["production_prestate"] == {
        "exact_total": 4533, "source_count": 26, "stm32n6_exact": 0
    }, "publication prestate audit drift")
    req(
        audit["production_poststate"]["exact_total"] == 4565
        and audit["production_poststate"]["source_count"] == 27
        and audit["production_poststate"]["stm32n6_exact"] == 32,
        "publication poststate audit drift",
    )
    req(audit["stm32n6_backend_state_after"] == {"mapped": 0, "no_mapping": 32},
        "N6 backend poststate audit drift")
    req(audit["catalog_backend_state_after"] == {"mapped": 3673, "no_mapping": 892},
        "catalog backend poststate audit drift")
    req(audit["external_memory_programming_profile_boundary"] is True,
        "N6 external-memory boundary audit drift")
    req(audit["programming_profile_binding_claimed"] is False,
        "N6 Programming Profile overclaim")
    req(
        audit["coverage_effect"]["whole_st_active_intersection_after"] == 4486
        and audit["coverage_effect"]["whole_st_active_gap_after"] == 64
        and audit["coverage_effect"][
            "whole_st_active_identity_coverage_after_percent"
        ] == 98.5934,
        "coverage effect audit drift",
    )

    print("STM32N6_LAYER1_PRODUCTION_PUBLICATION_V50_PASS")
    print("STM32N6=32; mapped=0; no_mapping=32; Production=4565; sources=27")
    print("Production backend partition=3673 mapped / 892 no_mapping")
    print("Whole-ST Active identity coverage=4486/4550=98.5934%")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
