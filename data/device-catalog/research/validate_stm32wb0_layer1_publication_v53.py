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
WB0 = HERE / "stm32wb0-commercial-icpn.csv"
EXACT = HERE / "st-stm32wb0-active-exact-mpn-v1.2.txt"
PROPOSAL_LOCK = HERE / "stm32wb0-layer1-admission-proposal-v5.2.json"
AUDIT = HERE / "stm32wb0-layer1-production-publication-v5.3.json"

EXPECTED_WB0_SHA256 = "f9c827037f1471c438fbe91f4959913594d182fe41b601266138614cc34e9f43"
EXPECTED_WB0_BLOB = "b4754420d0a6342f63c3edb368c96fc7f9bf864b"
EXPECTED_EXACT_SHA256 = "5f6adbd574ca751487c256a806764b1046cd5150cba757f73fd9d3269d167447"
EXPECTED_PROPOSAL_SHA256 = "7bec5269ba9a67f4e4a26f7bff61d1116ad713bb97400f9deebcb329749e74f0"
EXPECTED_AUTHORITY_SHA256 = "c8975280bb2d930f64b3e40e385ae4d009f38e3c555578c186e86eada97adaaf"

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
            "backend_route_observation": "backend_not_evaluated_catalog_only",
            "existing_identifier": "",
            "existing_identifier_kind": "",
            "openocd_target_config": "",
            "metadata_source_reference": row["source_reference"],
            "source_authority": row["source_authority"],
            "verification_status": row["verification_status"],
            "programming_profile_state": "unresolved",
            "metadata_exception": "",
        })

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=PROPOSAL_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out)
    return buf.getvalue().encode()

def main() -> int:
    rows = read_rows(WB0)
    exact = exact_lines()
    proposal = json.loads(PROPOSAL_LOCK.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))

    req(len(rows) == 24 and len({r["icpn"] for r in rows}) == 24,
        "WB0 Production count/unique drift")
    req(sorted(r["icpn"] for r in rows) == exact,
        "WB0 Production identities differ from locked Active set")
    req(digest_lines(exact) == EXPECTED_EXACT_SHA256,
        "WB0 exact identity digest drift")

    data = WB0.read_bytes()
    req(hashlib.sha256(data).hexdigest() == EXPECTED_WB0_SHA256,
        "WB0 canonical SHA256 drift")
    req(git_blob(data) == EXPECTED_WB0_BLOB,
        "WB0 canonical Git blob drift")

    req(all(r["mapping_status"] == "no_mapping" for r in rows),
        "WB0 Production contains mapped row without backend qualification")
    req(all(
        not r["cmsis_device_name"]
        and not r["existing_identifier"]
        and not r["existing_identifier_kind"]
        and not r["openocd_target_config"]
        for r in rows
    ), "WB0 no_mapping row carries backend route data")

    network = [r for r in rows if r["series"] == "STM32WB05N"]
    req(len(network) == 4, "WB0 network-coprocessor partition drift")
    req(all(r["flash_size"] == "N/A (network coprocessor)" for r in network),
        "WB05xN network-coprocessor semantic drift")

    wlcsp49 = [r for r in rows if r["icpn"].startswith(("STM32WB06CCF", "STM32WB07CCF"))]
    req(len(wlcsp49) == 4, "WB06/07 WLCSP49 cohort drift")
    req(all(r["package"] == "WLCSP" and r["pin_count"] == "49" for r in wlcsp49),
        "WB06/07 WLCSP49 physical pin-count drift")

    req(hashlib.sha256(reconstruct_proposal(rows)).hexdigest()
        == EXPECTED_PROPOSAL_SHA256,
        "published WB0 rows do not reconstruct approved proposal CSV")

    req(proposal["proposal_id"] == "stm32wb0-layer1-admission-proposal-v5.2",
        "approved proposal id drift")
    req(proposal["proposal_addition_count"] == 24,
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
    wb0s = [
        s for s in sources
        if s["manufacturer"] == "STMicroelectronics"
        and s["family"] == "STM32WB0"
    ]
    req(len(wb0s) == 1, "Production WB0 source missing/duplicated")
    source = wb0s[0]
    req(
        source["row_count"] == 24
        and source["sha256"] == EXPECTED_WB0_SHA256
        and source["git_blob_sha"] == EXPECTED_WB0_BLOB,
        "Production manifest WB0 integrity binding drift",
    )
    req(len(sources) == 28, "Production source count drift")
    req(sum(int(s["row_count"]) for s in sources) == 4589,
        "Production exact total drift")

    backend = Counter()
    for source in sources:
        path = (MANIFEST.parent / source["path"]).resolve()
        for row in read_rows(path):
            backend[
                "no_mapping" if row["mapping_status"] == "no_mapping" else "mapped"
            ] += 1
    req(backend == Counter({"mapped": 3673, "no_mapping": 916}),
        f"Production backend partition drift: {dict(backend)}")

    req(audit["owner_approval_received"] is True,
        "owner approval audit missing")
    req(audit["approved_proposal_pr"] == 736,
        "approved proposal PR drift")
    req(audit["approved_proposal_merge_commit"]
        == "09adf0cf3fce2ec0baaa9ed197a803e941678b7b",
        "approved proposal merge commit drift")
    req(audit["production_prestate"] == {
        "exact_total": 4565, "source_count": 27, "stm32wb0_exact": 0
    }, "publication prestate audit drift")
    req(
        audit["production_poststate"]["exact_total"] == 4589
        and audit["production_poststate"]["source_count"] == 28
        and audit["production_poststate"]["stm32wb0_exact"] == 24,
        "publication poststate audit drift",
    )
    req(audit["stm32wb0_backend_state_after"] == {"mapped": 0, "no_mapping": 24},
        "WB0 backend poststate audit drift")
    req(audit["catalog_backend_state_after"] == {"mapped": 3673, "no_mapping": 916},
        "catalog backend poststate audit drift")
    req(audit["network_coprocessor_semantic_preserved"] is True,
        "WB0 network-coprocessor semantic audit drift")
    req(audit["package_dependent_physical_pin_count_preserved"] is True,
        "WB0 physical pin-count audit drift")
    req(audit["programming_profile_binding_claimed"] is False,
        "WB0 Programming Profile overclaim")
    req(
        audit["coverage_effect"]["whole_st_active_intersection_after"] == 4510
        and audit["coverage_effect"]["whole_st_active_gap_after"] == 40
        and audit["coverage_effect"][
            "whole_st_active_identity_coverage_after_percent"
        ] == 99.1209,
        "coverage effect audit drift",
    )

    print("STM32WB0_LAYER1_PRODUCTION_PUBLICATION_V53_PASS")
    print("STM32WB0=24; mapped=0; no_mapping=24; Production=4589; sources=28")
    print("Production backend partition=3673 mapped / 916 no_mapping")
    print("Whole-ST Active identity coverage=4510/4550=99.1209%")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
