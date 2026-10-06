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

import analyze_stm32wb0_metadata_replay_v51 as metadata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUTHORITY = HERE / "stm32wb0-ordering-authority-v5.1.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
N6_PUBLICATION = HERE / "stm32n6-layer1-production-publication-v5.0.json"

EXPECTED_ACTIVE = 24
EXPECTED_PRODUCTION_TOTAL = 4565
EXPECTED_SOURCE_COUNT = 27
EXPECTED_ACTIVE_DENOMINATOR = 4550
EXPECTED_ACTIVE_INTERSECTION = 4486

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

    wb0 = [
        s for s in sources
        if s.get("manufacturer") == "STMicroelectronics"
        and s.get("family") == "STM32WB0"
    ]
    req(wb0 == [], "STM32WB0 unexpectedly already present in Production")

    n6 = json.loads(N6_PUBLICATION.read_text(encoding="utf-8"))
    cov = n6["coverage_effect"]
    req(
        int(cov["whole_st_active_exact_denominator"]) == EXPECTED_ACTIVE_DENOMINATOR,
        "whole-ST Active denominator drift",
    )
    req(
        int(cov["whole_st_active_intersection_after"]) == EXPECTED_ACTIVE_INTERSECTION,
        "whole-ST Active intersection prestate drift",
    )
    req(int(cov["whole_st_active_gap_after"]) == 64, "whole-ST Active gap prestate drift")

    return {
        "production_exact_total": total,
        "production_source_count": len(sources),
        "whole_st_active_exact_denominator": EXPECTED_ACTIVE_DENOMINATOR,
        "whole_st_active_intersection": EXPECTED_ACTIVE_INTERSECTION,
    }

def row_for(decoded: dict[str, Any]) -> dict[str, str]:
    return {
        "manufacturer": "STMicroelectronics",
        "icpn": decoded["icpn"],
        "family": "STM32WB0",
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
        "verification_status": (
            "verified_st_ordering_information_codes_plus_current_active_exact_identity"
        ),
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
    authority = metadata.load_authority()
    exact = metadata.load_exact()
    exact_set = set(exact)

    req(replay["metadata_decodable_exact_count"] == EXPECTED_ACTIVE,
        "WB0 metadata replay incomplete")
    req(replay["metadata_blocked_exact_count"] == 0,
        "WB0 metadata replay blocked identities")
    req(replay["direct_ordering_information_exact_count"] == EXPECTED_ACTIVE,
        "WB0 direct decode count drift")
    req(replay["bounded_exact_exception_count"] == 0,
        "WB0 metadata exception count drift")
    req(replay["network_coprocessor_exact_count"] == 4,
        "WB0 network-coprocessor partition drift")
    req(replay["claims"]["backend_scope_evaluated"] is False,
        "backend scope overclaim")
    req(replay["claims"]["backend_route_ready"] is False,
        "backend route overclaim")
    req(replay["claims"]["programming_profile_scope_expanded"] is False,
        "Programming Profile scope overclaim")

    decoded = [metadata.decode_one(icpn, authority, exact_set) for icpn in exact]
    rows = [row_for(item) for item in decoded]
    req(
        len(rows) == EXPECTED_ACTIVE
        and len({row["icpn"] for row in rows}) == EXPECTED_ACTIVE,
        "WB0 proposal count/unique drift",
    )
    req(
        all(
            row["backend_mapping_state"] == "no_mapping"
            and row["backend_type"] == ""
            and row["openocd_target_config"] == ""
            for row in rows
        ),
        "WB0 proposal synthesized backend capability",
    )
    req(
        sum(1 for row in rows if row["flash_size"] == "N/A (network coprocessor)") == 4,
        "WB0 network-coprocessor semantic boundary drift",
    )

    csv_text = render_csv(rows)
    exact_hash = hashlib.sha256(("\n".join(exact) + "\n").encode()).hexdigest()
    csv_hash = hashlib.sha256(csv_text.encode()).hexdigest()
    authority_hash = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    intersection = pre["whole_st_active_intersection"] + EXPECTED_ACTIVE

    summary = {
        "schema_version": 1,
        "proposal_id": "stm32wb0-layer1-admission-proposal-v5.2",
        "record_state": "RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
        "production_write_authorized": False,
        "production_exact_prestate": pre["production_exact_total"],
        "production_source_count_prestate": pre["production_source_count"],
        "production_wb0_exact_prestate": 0,
        "current_wb0_active_exact": EXPECTED_ACTIVE,
        "current_wb0_active_intersection_prestate": 0,
        "proposal_addition_count": EXPECTED_ACTIVE,
        "proposal_exact_set_sha256": exact_hash,
        "proposal_csv_sha256": csv_hash,
        "authority_id": authority["authority_id"],
        "authority_sha256": authority_hash,
        "layer1_catalog_resolution": {"normalized": EXPECTED_ACTIVE},
        "metadata_direct_ordering_information_exact_count": EXPECTED_ACTIVE,
        "metadata_bounded_exception_exact_count": 0,
        "metadata_exception_exact_icpns": [],
        "network_coprocessor_exact_count": 4,
        "network_coprocessor_semantic_preserved": True,
        "package_dependent_physical_pin_count_preserved": True,
        "backend_scope_evaluated": False,
        "backend_type_claimed": False,
        "backend_state_for_new_rows": {"no_mapping": EXPECTED_ACTIVE},
        "backend_state_semantics": (
            "no route or backend type bound; backend capability not evaluated "
            "in catalog-only scope"
        ),
        "backend_mapping_required_for_layer1_admission": False,
        "programming_profile_binding_claimed": False,
        "programming_profile_scope_expanded": False,
        "series_counts": dict(sorted(Counter(row["series"] for row in rows).items())),
        "package_counts": dict(sorted(Counter(row["package"] for row in rows).items())),
        "production_wb0_exact_after_if_approved": EXPECTED_ACTIVE,
        "production_source_count_after_if_approved": pre["production_source_count"] + 1,
        "wb0_current_active_identity_coverage_after_if_published": "24/24 = 100%",
        "production_exact_after_if_approved": pre["production_exact_total"] + EXPECTED_ACTIVE,
        "whole_st_active_exact_denominator": pre["whole_st_active_exact_denominator"],
        "whole_st_active_intersection_prestate": pre["whole_st_active_intersection"],
        "whole_st_active_intersection_after_if_approved": intersection,
        "whole_st_active_gap_after_if_approved": (
            pre["whole_st_active_exact_denominator"] - intersection
        ),
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
    print("STM32WB0_LAYER1_ADMISSION_PROPOSAL_V52_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
