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

import analyze_stm32h5_layered_gap_v26 as layered
import analyze_stm32h5_metadata_replay_v27 as metadata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUTHORITY = HERE / "stm32h5-ordering-authority-v2.7.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
F1_PUBLICATION = HERE / "stm32f1-layer1-production-publication-v2.5.json"

EXPECTED_EXACT = 190
EXPECTED_PRODUCTION_TOTAL = 3716
EXPECTED_ACTIVE_DENOMINATOR = 4550
EXPECTED_ACTIVE_INTERSECTION = 3637
EXPECTED_H5_PRODUCTION = 0

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
    total = sum(int(s["row_count"]) for s in sources)
    h5 = [
        s for s in sources
        if s.get("manufacturer") == "STMicroelectronics" and s.get("family") == "STM32H5"
    ]
    req(total == EXPECTED_PRODUCTION_TOTAL, f"Production exact total drift: {total}")
    req(not h5, "STM32H5 unexpectedly already exists in Production manifest")

    f1 = json.loads(F1_PUBLICATION.read_text(encoding="utf-8"))
    post = f1["production_poststate"]
    coverage = f1["coverage_effect"]
    req(int(post["exact_total_at_publication"]) == EXPECTED_PRODUCTION_TOTAL,
        "F1 publication no longer anchors current Production prestate")
    req(int(coverage["whole_st_active_exact_denominator"]) == EXPECTED_ACTIVE_DENOMINATOR,
        "whole-ST Active denominator drift")
    req(int(coverage["whole_st_active_intersection_after"]) == EXPECTED_ACTIVE_INTERSECTION,
        "whole-ST Active intersection prestate drift")
    return {
        "production_exact_total": total,
        "whole_st_active_exact_denominator": EXPECTED_ACTIVE_DENOMINATOR,
        "whole_st_active_intersection": EXPECTED_ACTIVE_INTERSECTION,
    }


def row_for(icpn: str, authority: dict[str, Any]) -> dict[str, str]:
    authorities = authority["subfamilies"]
    subfamily = metadata.resolve_subfamily(icpn, authorities)
    decoded = metadata.decode_one(icpn, authority)
    codes = metadata.parse_shape(icpn, subfamily)
    series = "STM32H" + subfamily
    base_device = series + codes["pin_code"] + codes["flash_code"]
    source = authorities[subfamily]["url"]
    exception = authority["bounded_exact_exceptions"].get(icpn)
    metadata_exception = ""
    if exception:
        source += ";" + exception["source_url"]
        metadata_exception = "H5E4_PACKAGE_J_ORDERING_TABLE_OMISSION_EXACT_ST_QR_ROW"

    option_suffix = codes["dedicated_code"] + codes["packing_code"]
    return {
        "manufacturer": "STMicroelectronics",
        "icpn": icpn,
        "family": "STM32H5",
        "series": series,
        "base_device": base_device,
        "marketing_status": "Active",
        "catalog_resolution": "normalized",
        "package": str(decoded["package"]),
        "pin_count": str(decoded["pin_count"]),
        "flash_size": f'{decoded["flash_kib"]} KiB',
        "temperature_grade": str(decoded["temperature"]),
        "option_suffix": option_suffix,
        "backend_type": "openocd",
        "backend_mapping_state": "no_mapping",
        "backend_route_observation": "no_stm32h5_target_in_current_plasma_openocd_catalog",
        "existing_identifier": "",
        "existing_identifier_kind": "",
        "openocd_target_config": "",
        "metadata_source_reference": source,
        "source_authority": "STMicroelectronics official",
        "verification_status": (
            "verified_st_ordering_information_codes_plus_current_estore_active_identity"
        ),
        "programming_profile_state": "unresolved_no_applicability_binding",
        "metadata_exception": metadata_exception,
    }


def render_csv(rows: list[dict[str, str]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def build() -> tuple[list[dict[str, str]], str, dict[str, Any]]:
    pre = production_prestate()
    layer = layered.analyze()
    replay = metadata.analyze()
    authority = metadata.load_authority()
    exact = sorted(metadata.load_exact())

    req(layer["layer1"]["official_active_exact_mpn_count"] == EXPECTED_EXACT,
        "H5 Active exact count drift")
    req(layer["layer2"]["current_plasma_target_catalog_h5_entry_count"] == 0,
        "H5 backend target appeared; proposal must be requalified")
    req(layer["layer2"]["no_mapping_exact_count"] == EXPECTED_EXACT,
        "H5 no_mapping partition drift")
    req(replay["metadata_decodable_exact_count"] == EXPECTED_EXACT,
        "H5 metadata replay incomplete")
    req(replay["metadata_blocked_exact_count"] == 0,
        "H5 metadata replay now has blocked identities")
    req(replay["claims"]["metadata_authority_replay_complete"] is True,
        "H5 metadata replay completion claim missing")

    rows = [row_for(icpn, authority) for icpn in exact]
    req(len(rows) == EXPECTED_EXACT and len({r["icpn"] for r in rows}) == EXPECTED_EXACT,
        "H5 proposal row count/uniqueness drift")
    req(all(r["backend_mapping_state"] == "no_mapping" for r in rows),
        "H5 proposal must preserve no_mapping for all rows")
    req(all(not r["openocd_target_config"] for r in rows),
        "H5 proposal must not synthesize an OpenOCD target")

    csv_text = render_csv(rows)
    exact_hash = hashlib.sha256(("\n".join(exact) + "\n").encode()).hexdigest()
    csv_hash = hashlib.sha256(csv_text.encode()).hexdigest()
    authority_hash = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()

    series_counts = dict(sorted(Counter(r["series"] for r in rows).items()))
    package_counts = dict(sorted(Counter(r["package"] for r in rows).items()))
    exception_ids = sorted(r["icpn"] for r in rows if r["metadata_exception"])
    req(exception_ids == [
        "STM32H5E4ZJJ6",
        "STM32H5E4ZJJ7Q",
        "STM32H5E4ZKJ6",
    ], f"H5 metadata exception set drift: {exception_ids}")

    proposed_active_intersection = pre["whole_st_active_intersection"] + EXPECTED_EXACT
    summary = {
        "schema_version": 1,
        "proposal_id": "stm32h5-layer1-admission-proposal-v2.8",
        "record_state": "RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
        "production_write_authorized": False,
        "production_exact_prestate": pre["production_exact_total"],
        "production_h5_exact_prestate": EXPECTED_H5_PRODUCTION,
        "current_h5_active_exact": EXPECTED_EXACT,
        "current_h5_active_intersection_prestate": 0,
        "proposal_addition_count": EXPECTED_EXACT,
        "proposal_exact_set_sha256": exact_hash,
        "proposal_csv_sha256": csv_hash,
        "authority_id": authority["authority_id"],
        "authority_sha256": authority_hash,
        "layer1_catalog_resolution": {"normalized": EXPECTED_EXACT},
        "backend_state_counts": {"mapping_candidate": 0, "no_mapping": EXPECTED_EXACT},
        "backend_mapping_required_for_layer1_admission": False,
        "programming_profile_binding_claimed": False,
        "programming_profile_scope_expanded": False,
        "metadata_exception_exact_icpns": exception_ids,
        "series_counts": series_counts,
        "package_counts": package_counts,
        "production_h5_exact_after_if_approved": EXPECTED_EXACT,
        "h5_current_active_identity_coverage_after_if_published": "190/190 = 100%",
        "production_exact_after_if_approved": pre["production_exact_total"] + EXPECTED_EXACT,
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--proposal", type=Path)
    ap.add_argument("--summary", type=Path)
    args = ap.parse_args()
    rows, csv_text, summary = build()
    if args.proposal:
        args.proposal.write_text(csv_text, encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("STM32H5_LAYER1_ADMISSION_PROPOSAL_V28_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
