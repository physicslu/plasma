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

import analyze_stm32c5_metadata_replay_v42 as metadata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUTHORITY = HERE / "stm32c5-ordering-authority-v4.2.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
F2_PUBLICATION = HERE / "stm32f2-layer1-production-publication-v4.1.json"

EXPECTED_ACTIVE = 172
EXPECTED_PRODUCTION_TOTAL = 4314
EXPECTED_SOURCE_COUNT = 24
EXPECTED_ACTIVE_DENOMINATOR = 4550
EXPECTED_ACTIVE_INTERSECTION = 4235

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
    total = sum(int(source["row_count"]) for source in sources)
    req(total == EXPECTED_PRODUCTION_TOTAL, f"Production exact total drift: {total}")
    req(len(sources) == EXPECTED_SOURCE_COUNT, f"Production source count drift: {len(sources)}")
    c5 = [
        source for source in sources
        if source.get("manufacturer") == "STMicroelectronics"
        and source.get("family") == "STM32C5"
    ]
    req(c5 == [], "STM32C5 unexpectedly already present in Production")

    f2 = json.loads(F2_PUBLICATION.read_text(encoding="utf-8"))
    cov = f2["coverage_effect"]
    req(int(cov["whole_st_active_exact_denominator"]) == EXPECTED_ACTIVE_DENOMINATOR,
        "whole-ST Active denominator drift")
    req(int(cov["whole_st_active_intersection_after"]) == EXPECTED_ACTIVE_INTERSECTION,
        "whole-ST Active intersection prestate drift")
    req(int(cov["whole_st_active_gap_after"]) == 315,
        "whole-ST Active gap prestate drift")

    return {
        "production_exact_total": total,
        "production_source_count": len(sources),
        "production_c5_exact": 0,
        "whole_st_active_exact_denominator": EXPECTED_ACTIVE_DENOMINATOR,
        "whole_st_active_intersection": EXPECTED_ACTIVE_INTERSECTION,
    }


def row_for(decoded: dict[str, Any]) -> dict[str, str]:
    exception = decoded["metadata_exception"]
    return {
        "manufacturer": "STMicroelectronics",
        "icpn": decoded["icpn"],
        "family": "STM32C5",
        "series": decoded["series"],
        "base_device": decoded["base_device"],
        "marketing_status": "Active",
        "catalog_resolution": "normalized",
        "package": decoded["package"],
        "pin_count": str(decoded["pin_count"]),
        "flash_size": f'{decoded["flash_kib"]} KiB',
        "temperature_grade": decoded["temperature_grade"],
        "option_suffix": decoded["option_suffix"],
        "backend_type": "openocd",
        "backend_mapping_state": "no_mapping",
        "backend_route_observation": "backend_not_evaluated_for_layer1_catalog_only_scope",
        "existing_identifier": "",
        "existing_identifier_kind": "",
        "openocd_target_config": "",
        "metadata_source_reference": decoded["metadata_source_url"],
        "source_authority": "STMicroelectronics official",
        "verification_status": (
            "verified_direct_st_exact_product_metadata_override"
            if exception
            else "verified_st_ordering_information_codes_plus_current_estore_active_identity"
        ),
        "programming_profile_state": "unresolved_no_applicability_binding",
        "metadata_exception": exception,
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
        "STM32C5 metadata replay incomplete")
    req(replay["metadata_blocked_exact_count"] == 0,
        "STM32C5 metadata replay has blocked identities")
    req(replay["direct_ordering_information_exact_count"] == 170,
        "STM32C5 direct Ordering Information count drift")
    req(replay["bounded_exact_exception_count"] == 2,
        "STM32C5 bounded exception count drift")
    req(replay["dfp_parent_only_metadata_decodable_count"] == 33,
        "STM32C5 DFP parent-only metadata cohort incomplete")
    req(replay["claims"]["backend_scope_evaluated"] is False,
        "backend scope must remain unevaluated")
    req(replay["claims"]["backend_route_ready"] is False,
        "backend route readiness must remain false")

    decoded = [metadata.decode_one(icpn, authority, exact_set) for icpn in exact]
    rows = [row_for(item) for item in decoded]
    req(len(rows) == EXPECTED_ACTIVE and len({row["icpn"] for row in rows}) == EXPECTED_ACTIVE,
        "STM32C5 proposal row count/uniqueness drift")
    req(all(row["backend_mapping_state"] == "no_mapping" for row in rows),
        "catalog-only proposal must leave all C5 rows unbound")
    req(all(not row["openocd_target_config"] for row in rows),
        "catalog-only proposal must not synthesize backend routes")

    csv_text = render_csv(rows)
    exact_hash = hashlib.sha256(("\n".join(exact) + "\n").encode()).hexdigest()
    csv_hash = hashlib.sha256(csv_text.encode()).hexdigest()
    authority_hash = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()

    proposed_intersection = pre["whole_st_active_intersection"] + EXPECTED_ACTIVE
    summary = {
        "schema_version": 1,
        "proposal_id": "stm32c5-layer1-admission-proposal-v4.3",
        "record_state": "RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
        "production_write_authorized": False,
        "production_exact_prestate": pre["production_exact_total"],
        "production_source_count_prestate": pre["production_source_count"],
        "production_c5_exact_prestate": 0,
        "current_c5_active_exact": EXPECTED_ACTIVE,
        "current_c5_active_intersection_prestate": 0,
        "proposal_addition_count": EXPECTED_ACTIVE,
        "proposal_exact_set_sha256": exact_hash,
        "proposal_csv_sha256": csv_hash,
        "authority_id": authority["authority_id"],
        "authority_sha256": authority_hash,
        "layer1_catalog_resolution": {"normalized": EXPECTED_ACTIVE},
        "metadata_direct_ordering_information_exact_count": 170,
        "metadata_bounded_exception_exact_count": 2,
        "metadata_exception_exact_icpns": replay["bounded_exact_exception_icpns"],
        "dfp_exact_variant_observed_count": 139,
        "dfp_parent_only_count": 33,
        "backend_scope_evaluated": False,
        "backend_state_for_new_rows": {"no_mapping": EXPECTED_ACTIVE},
        "backend_state_semantics":
            "no route bound; backend capability not evaluated in catalog-only scope",
        "backend_mapping_required_for_layer1_admission": False,
        "programming_profile_binding_claimed": False,
        "programming_profile_scope_expanded": False,
        "series_counts": dict(sorted(Counter(row["series"] for row in rows).items())),
        "package_counts": dict(sorted(Counter(row["package"] for row in rows).items())),
        "production_c5_exact_after_if_approved": EXPECTED_ACTIVE,
        "production_source_count_after_if_approved": pre["production_source_count"] + 1,
        "c5_current_active_identity_coverage_after_if_published": "172/172 = 100%",
        "production_exact_after_if_approved": pre["production_exact_total"] + EXPECTED_ACTIVE,
        "whole_st_active_exact_denominator": pre["whole_st_active_exact_denominator"],
        "whole_st_active_intersection_prestate": pre["whole_st_active_intersection"],
        "whole_st_active_intersection_after_if_approved": proposed_intersection,
        "whole_st_active_gap_after_if_approved": (
            pre["whole_st_active_exact_denominator"] - proposed_intersection
        ),
        "whole_st_active_coverage_after_if_approved_percent": round(
            proposed_intersection / pre["whole_st_active_exact_denominator"] * 100, 4
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
        args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("STM32C5_LAYER1_ADMISSION_PROPOSAL_V43_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
