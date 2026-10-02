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

import analyze_stm32f7_metadata_replay_v35 as metadata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUTHORITY = HERE / "stm32f7-ordering-authority-v3.5.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
F3_PUBLICATION = HERE / "stm32f3-layer1-production-publication-v3.3.json"

EXPECTED_GAP = 154
EXPECTED_CURRENT_F7 = 19
EXPECTED_ACTIVE_F7 = 173
EXPECTED_PRODUCTION_TOTAL = 4088
EXPECTED_ACTIVE_DENOMINATOR = 4550
EXPECTED_ACTIVE_INTERSECTION = 4009

FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "marketing_status",
    "catalog_resolution", "package", "pin_count", "flash_size", "temperature_grade",
    "option_suffix", "backend_type", "backend_mapping_state", "backend_route_observation",
    "existing_identifier", "existing_identifier_kind", "openocd_target_config",
    "metadata_source_reference", "source_authority", "verification_status",
    "programming_profile_state", "metadata_exception",
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
    f7 = [
        source for source in sources
        if source.get("manufacturer") == "STMicroelectronics"
        and source.get("family") == "STM32F7"
    ]
    req(total == EXPECTED_PRODUCTION_TOTAL, f"Production exact total drift: {total}")
    req(len(f7) == 1 and int(f7[0]["row_count"]) == EXPECTED_CURRENT_F7,
        "STM32F7 Production prestate drift")

    f3 = json.loads(F3_PUBLICATION.read_text(encoding="utf-8"))
    coverage = f3["coverage_effect"]
    req(int(coverage["whole_st_active_exact_denominator"]) == EXPECTED_ACTIVE_DENOMINATOR,
        "whole-ST Active denominator drift")
    req(int(coverage["whole_st_active_intersection_after"]) == EXPECTED_ACTIVE_INTERSECTION,
        "whole-ST Active intersection prestate drift")

    return {
        "production_exact_total": total,
        "production_f7_exact": EXPECTED_CURRENT_F7,
        "whole_st_active_exact_denominator": EXPECTED_ACTIVE_DENOMINATOR,
        "whole_st_active_intersection": EXPECTED_ACTIVE_INTERSECTION,
    }


def row_for(icpn: str, authority: dict[str, Any]) -> dict[str, str]:
    decoded = metadata.decode_one(icpn, authority)
    is_override = decoded["authority_kind"] == "exact_product_override"
    return {
        "manufacturer": "STMicroelectronics",
        "icpn": icpn,
        "family": "STM32F7",
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
        "metadata_source_reference": decoded["authority_url"],
        "source_authority": "STMicroelectronics official",
        "verification_status": (
            "verified_direct_st_exact_product_metadata_override"
            if is_override
            else "verified_st_ordering_information_codes_plus_current_estore_active_identity"
        ),
        "programming_profile_state": "unresolved_no_applicability_binding",
        "metadata_exception": (
            "F750_X8_EXACT_PRODUCT_METADATA_OVERRIDE"
            if is_override else ""
        ),
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
    exact = sorted(metadata.load_gap())

    req(replay["metadata_decodable_exact_count"] == EXPECTED_GAP,
        "STM32F7 metadata replay incomplete")
    req(replay["metadata_blocked_exact_count"] == 0,
        "STM32F7 metadata replay has blocked identities")
    req(replay["direct_ordering_information_exact_count"] == 151,
        "STM32F7 direct Ordering Information count drift")
    req(replay["exact_product_override_count"] == 3,
        "STM32F7 bounded exact-product override count drift")
    req(replay["claims"]["metadata_authority_replay_complete"] is True,
        "STM32F7 metadata replay completion claim missing")
    req(replay["claims"]["backend_scope_evaluated"] is False,
        "backend scope must remain unevaluated")

    rows = [row_for(icpn, authority) for icpn in exact]
    req(len(rows) == EXPECTED_GAP and len({row["icpn"] for row in rows}) == EXPECTED_GAP,
        "STM32F7 proposal row count/uniqueness drift")
    req(all(row["backend_mapping_state"] == "no_mapping" for row in rows),
        "catalog-only proposal must leave all new F7 rows unbound")
    req(all(not row["openocd_target_config"] for row in rows),
        "catalog-only proposal must not synthesize backend routes")

    override_ids = sorted(row["icpn"] for row in rows if row["metadata_exception"])
    req(override_ids == sorted(metadata.EXPECTED_OVERRIDE_IDS),
        "F7 bounded override exact set drift")

    csv_text = render_csv(rows)
    exact_hash = hashlib.sha256(("\n".join(exact) + "\n").encode()).hexdigest()
    csv_hash = hashlib.sha256(csv_text.encode()).hexdigest()
    authority_hash = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()

    proposed_active_intersection = pre["whole_st_active_intersection"] + EXPECTED_GAP
    summary = {
        "schema_version": 1,
        "proposal_id": "stm32f7-layer1-admission-proposal-v3.6",
        "record_state": "RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
        "production_write_authorized": False,
        "production_exact_prestate": pre["production_exact_total"],
        "production_f7_exact_prestate": pre["production_f7_exact"],
        "current_f7_active_exact": EXPECTED_ACTIVE_F7,
        "current_f7_active_intersection_prestate": EXPECTED_CURRENT_F7,
        "proposal_addition_count": EXPECTED_GAP,
        "proposal_exact_set_sha256": exact_hash,
        "proposal_csv_sha256": csv_hash,
        "authority_id": authority["authority_id"],
        "authority_sha256": authority_hash,
        "layer1_catalog_resolution": {"normalized": EXPECTED_GAP},
        "backend_scope_evaluated": False,
        "backend_state_for_new_rows": {"no_mapping": EXPECTED_GAP},
        "backend_state_semantics":
            "no route bound; backend capability not evaluated in catalog-only scope",
        "backend_mapping_required_for_layer1_admission": False,
        "programming_profile_binding_claimed": False,
        "programming_profile_scope_expanded": False,
        "metadata_override_exact_icpns": override_ids,
        "metadata_override_semantics":
            "exact-product-bounded official ST metadata only; no generalized STM32F750 x8 inference",
        "direct_ordering_information_exact_count": 151,
        "exact_product_override_count": 3,
        "series_counts": dict(sorted(Counter(row["series"] for row in rows).items())),
        "package_counts": dict(sorted(Counter(row["package"] for row in rows).items())),
        "production_f7_exact_after_if_approved": EXPECTED_ACTIVE_F7,
        "f7_current_active_identity_coverage_after_if_published": "173/173 = 100%",
        "production_exact_after_if_approved": pre["production_exact_total"] + EXPECTED_GAP,
        "whole_st_active_exact_denominator": pre["whole_st_active_exact_denominator"],
        "whole_st_active_intersection_prestate": pre["whole_st_active_intersection"],
        "whole_st_active_intersection_after_if_approved": proposed_active_intersection,
        "whole_st_active_gap_after_if_approved": (
            pre["whole_st_active_exact_denominator"] - proposed_active_intersection
        ),
        "whole_st_active_coverage_after_if_approved_percent": round(
            proposed_active_intersection / pre["whole_st_active_exact_denominator"] * 100, 4
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

    rows, csv_text, summary = build()
    if args.proposal:
        args.proposal.write_text(csv_text, encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("STM32F7_LAYER1_ADMISSION_PROPOSAL_V36_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
