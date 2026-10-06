#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import analyze_stm32c0_active_gap_v54 as metadata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
BASE_AUTHORITY = HERE / "stm32c0-phase-c0.3-ordering-authority.json"
DELTA_AUTHORITY = HERE / "stm32c0-active-gap-ordering-authority-v5.4.json"
WB0_PUBLICATION = HERE / "stm32wb0-layer1-production-publication-v5.3.json"

EXPECTED_ACTIVE_DELTA = 17
EXPECTED_PRODUCTION_TOTAL = 4589
EXPECTED_SOURCE_COUNT = 28
EXPECTED_C0_PRODUCTION = 209
EXPECTED_ACTIVE_DENOMINATOR = 4550
EXPECTED_ACTIVE_INTERSECTION = 4510

FIELDS = (
    "manufacturer","icpn","family","series","base_device","marketing_status",
    "catalog_resolution","package","pin_count","flash_size","temperature_grade",
    "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
    "existing_identifier","existing_identifier_kind","openocd_target_config",
    "metadata_source_reference","source_authority","verification_status",
    "programming_profile_state","metadata_exception",
)

class ProposalError(RuntimeError):
    pass

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ProposalError(msg)

def production_prestate() -> dict[str, int]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    total = sum(int(s["row_count"]) for s in sources)
    req(total == EXPECTED_PRODUCTION_TOTAL, f"Production exact total drift: {total}")
    req(len(sources) == EXPECTED_SOURCE_COUNT, f"Production source count drift: {len(sources)}")

    c0 = [
        s for s in sources
        if s.get("manufacturer") == "STMicroelectronics"
        and s.get("family") == "STM32C0"
    ]
    req(len(c0) == 1, "STM32C0 Production source missing/duplicated")
    req(int(c0[0]["row_count"]) == EXPECTED_C0_PRODUCTION,
        "STM32C0 Production prestate row-count drift")

    wb0 = json.loads(WB0_PUBLICATION.read_text(encoding="utf-8"))
    cov = wb0["coverage_effect"]
    req(int(cov["whole_st_active_exact_denominator"]) == EXPECTED_ACTIVE_DENOMINATOR,
        "whole-ST Active denominator drift")
    req(int(cov["whole_st_active_intersection_after"]) == EXPECTED_ACTIVE_INTERSECTION,
        "whole-ST Active intersection prestate drift")
    req(int(cov["whole_st_active_gap_after"]) == 40,
        "whole-ST Active gap prestate drift")

    return {
        "production_exact_total": total,
        "production_source_count": len(sources),
        "production_c0_exact": int(c0[0]["row_count"]),
        "whole_st_active_exact_denominator": EXPECTED_ACTIVE_DENOMINATOR,
        "whole_st_active_intersection": EXPECTED_ACTIVE_INTERSECTION,
    }

def row_for(decoded: dict[str, Any]) -> dict[str, str]:
    return {
        "manufacturer": "STMicroelectronics",
        "icpn": decoded["icpn"],
        "family": "STM32C0",
        "series": decoded["series"],
        "base_device": decoded["base_device"],
        "marketing_status": "Active",
        "catalog_resolution": "normalized",
        "package": decoded["package"],
        "pin_count": str(decoded["pin_count"]),
        "flash_size": decoded["flash_size"],
        "temperature_grade": decoded["temperature_grade"],
        "option_suffix": decoded["option_suffix"],
        "backend_type": "",
        "backend_mapping_state": "no_mapping",
        "backend_route_observation": "backend_not_evaluated_catalog_only",
        "existing_identifier": "",
        "existing_identifier_kind": "",
        "openocd_target_config": "",
        "metadata_source_reference": decoded["metadata_source_url"],
        "source_authority": "STMicroelectronics official",
        "verification_status":
            "verified_st_ordering_information_codes_plus_current_active_exact_identity",
        "programming_profile_state": "unresolved",
        "metadata_exception": "",
    }

def render_csv(rows: list[dict[str, str]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

def build() -> tuple[list[dict[str, str]], str, dict[str, Any]]:
    pre = production_prestate()
    replay = metadata.analyze()
    gap = metadata.load_gap()
    authority = metadata.load_authority()
    gap_set = set(gap)

    req(replay["metadata_decodable_exact_count"] == EXPECTED_ACTIVE_DELTA,
        "C0 delta metadata replay incomplete")
    req(replay["metadata_blocked_exact_count"] == 0,
        "C0 delta metadata replay blocked identities")
    req(replay["bounded_exact_exception_count"] == 0,
        "C0 delta metadata exception count drift")
    req(replay["claims"]["backend_scope_evaluated"] is False,
        "C0 delta backend scope overclaim")
    req(replay["claims"]["programming_profile_scope_expanded"] is False,
        "C0 delta Programming Profile scope overclaim")

    decoded = [metadata.decode_one(icpn, authority, gap_set) for icpn in gap]
    rows = [row_for(item) for item in decoded]
    req(len(rows) == EXPECTED_ACTIVE_DELTA
        and len({row["icpn"] for row in rows}) == EXPECTED_ACTIVE_DELTA,
        "C0 delta proposal count/unique drift")
    req(all(
        row["backend_mapping_state"] == "no_mapping"
        and row["backend_type"] == ""
        and row["openocd_target_config"] == ""
        for row in rows
    ), "C0 delta proposal synthesized backend capability")
    req(any(row["icpn"] == "STM32C091KBT3" for row in rows),
        "C0 Preview-to-Active lifecycle delta missing")

    csv_text = render_csv(rows)
    exact_hash = hashlib.sha256(("\n".join(gap) + "\n").encode()).hexdigest()
    csv_hash = hashlib.sha256(csv_text.encode()).hexdigest()
    base_authority_hash = hashlib.sha256(BASE_AUTHORITY.read_bytes()).hexdigest()
    delta_authority_hash = hashlib.sha256(DELTA_AUTHORITY.read_bytes()).hexdigest()
    intersection = pre["whole_st_active_intersection"] + EXPECTED_ACTIVE_DELTA

    summary = {
        "schema_version": 1,
        "proposal_id": "stm32c0-layer1-admission-proposal-v5.5",
        "record_state": "RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
        "production_write_authorized": False,
        "production_exact_prestate": pre["production_exact_total"],
        "production_source_count_prestate": pre["production_source_count"],
        "production_c0_exact_prestate": pre["production_c0_exact"],
        "current_c0_active_exact": 226,
        "current_c0_active_intersection_prestate": 209,
        "proposal_addition_count": EXPECTED_ACTIVE_DELTA,
        "proposal_exact_set_sha256": exact_hash,
        "proposal_csv_sha256": csv_hash,
        "base_authority_sha256": base_authority_hash,
        "delta_authority_id": "stm32c0-active-gap-ordering-authority-v5.4",
        "delta_authority_sha256": delta_authority_hash,
        "layer1_catalog_resolution": {"normalized": EXPECTED_ACTIVE_DELTA},
        "metadata_direct_ordering_information_exact_count": EXPECTED_ACTIVE_DELTA,
        "metadata_bounded_exception_exact_count": 0,
        "metadata_exception_exact_icpns": [],
        "lifecycle_delta_exact_icpns": ["STM32C091KBT3"],
        "new_package_semantics": {
            "STM32C011_D_Y": "WLCSP12",
            "STM32C051_D_Y": "WLCSP15"
        },
        "backend_scope_evaluated": False,
        "backend_type_claimed": False,
        "backend_state_for_new_rows": {"no_mapping": EXPECTED_ACTIVE_DELTA},
        "backend_state_semantics":
            "no route or backend type bound; backend capability not evaluated in catalog-only scope",
        "backend_mapping_required_for_layer1_admission": False,
        "programming_profile_binding_claimed": False,
        "programming_profile_scope_expanded": False,
        "series_counts": dict(sorted(Counter(row["series"] for row in rows).items())),
        "package_counts": dict(sorted(Counter(row["package"] for row in rows).items())),
        "production_c0_exact_after_if_approved": 226,
        "production_source_count_after_if_approved": pre["production_source_count"],
        "c0_current_active_identity_coverage_after_if_published": "226/226 = 100%",
        "production_exact_after_if_approved":
            pre["production_exact_total"] + EXPECTED_ACTIVE_DELTA,
        "catalog_backend_partition_after_if_approved": {
            "mapped": 3673,
            "no_mapping": 933
        },
        "whole_st_active_exact_denominator": pre["whole_st_active_exact_denominator"],
        "whole_st_active_intersection_prestate": pre["whole_st_active_intersection"],
        "whole_st_active_intersection_after_if_approved": intersection,
        "whole_st_active_gap_after_if_approved":
            pre["whole_st_active_exact_denominator"] - intersection,
        "whole_st_active_coverage_after_if_approved_percent": round(
            intersection / pre["whole_st_active_exact_denominator"] * 100, 4
        ),
        "engineering_verified_claimed": False,
        "field_evidence_claimed": False,
        "ps_hil_claimed": False,
    }
    return rows, csv_text, summary

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    _, csv_text, summary = build()
    if args.proposal:
        args.proposal.write_text(csv_text, encoding="utf-8")
    if args.summary:
        args.summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(summary, indent=2, sort_keys=True))
    print("STM32C0_LAYER1_ADMISSION_PROPOSAL_V55_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
