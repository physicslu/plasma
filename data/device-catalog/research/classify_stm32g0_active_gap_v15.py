#!/usr/bin/env python3
"""Classify the 359 current Active STM32G0 Catalog gaps.

Layer-1 Catalog identity is authoritative from the locked ST eStore v1.3 result.
OpenOCD mapping is measured only as an independent Layer-2 observation and
must not reject a manufacturer Active identity candidate.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from stm32g0_foundation import EXPECTED_SUBFAMILIES, read_catalog
from stm32g0_phase4_8b_discovery import resolve_mapping

HERE = Path(__file__).resolve().parent
GAPS = HERE / "stm32g0-active-exact-gap-v1.5.txt"
PRODUCTION_G0 = HERE / "stm32g0-commercial-icpn.csv"
COVERAGE_LOCK = HERE / "st-estore-active-exact-coverage-lock-v1.4.json"

EXPECTED_GAP_COUNT = 359
EXPECTED_GAP_SHA256 = "a6240e4a34e3834cba7195be306d449386dcac1b3e66189f6bfac8fdc7557a5d"
EXPECTED_PRODUCTION_G0 = 47
EXPECTED_ACTIVE_G0 = 406

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)

def load_gap() -> list[str]:
    raw = GAPS.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == EXPECTED_GAP_SHA256,
            "G0 gap exact-set bytes drifted")
    names = [x.strip() for x in raw.decode().splitlines() if x.strip()]
    require(len(names) == EXPECTED_GAP_COUNT and len(set(names)) == EXPECTED_GAP_COUNT,
            "G0 gap count/uniqueness drifted")
    require(names == sorted(names), "G0 gap ledger must remain sorted")
    require(all(name.startswith("STM32G0") and name.isalnum() for name in names),
            "invalid G0 exact identity")
    return names

def load_production() -> tuple[set[str], set[str]]:
    with PRODUCTION_G0.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    require(len(rows) == EXPECTED_PRODUCTION_G0, "Production G0 count drifted")
    exact = {r["icpn"] for r in rows}
    bases = {r["base_device"] for r in rows}
    require(len(exact) == EXPECTED_PRODUCTION_G0 and len(bases) == 12,
            "Production G0 identity/base scope drifted")
    return exact, bases

def subfamily_and_base(icpn: str) -> tuple[str, str]:
    matches = [sub for sub in EXPECTED_SUBFAMILIES if icpn.startswith(sub)]
    require(len(matches) == 1, f"{icpn}: cannot resolve one G0 subfamily")
    sub = matches[0]
    base_len = len(sub) + 2
    require(len(icpn) > base_len, f"{icpn}: exact identity shorter than Base Device")
    return sub, icpn[:base_len]

def classify() -> dict:
    coverage = json.loads(COVERAGE_LOCK.read_text(encoding="utf-8"))
    require(coverage["audit_id"] == "st-estore-active-exact-coverage-lock-v1.4",
            "coverage authority drifted")
    require(coverage["estore_active_exact_denominator"] == 4550 and
            coverage["active_exact_missing_from_production"] == 1946,
            "whole-ST coverage baseline drifted")

    gaps = load_gap()
    production, published_bases = load_production()
    require(not (set(gaps) & production), "gap intersects Production G0")
    require(len(gaps) + len(production) == EXPECTED_ACTIVE_G0,
            "G0 Active arithmetic drifted")

    catalog = read_catalog()
    route_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    subfamily_counts: Counter[str] = Counter()
    gap_base_counts: Counter[str] = Counter()
    route_examples: dict[str, list[str]] = defaultdict(list)

    for icpn in gaps:
        subfamily, base = subfamily_and_base(icpn)
        subfamily_counts[subfamily] += 1
        gap_base_counts[base] += 1
        scope = "existing_published_base_variant_gap" if base in published_bases else "new_base_device_gap"
        scope_counts[scope] += 1

        mapping = resolve_mapping(icpn, catalog)
        status = str(mapping.get("status"))
        require(status in {"unique", "ambiguous", "unmapped"},
                f"{icpn}: unexpected mapping status {status}")
        route_counts[status] += 1
        if len(route_examples[status]) < 12:
            route_examples[status].append(icpn)

    unique_bases = set(gap_base_counts)
    new_bases = unique_bases - published_bases
    shared_bases = unique_bases & published_bases

    result = {
        "audit_id": "stm32g0-active-gap-layered-triage-v1.5",
        "authority": {
            "source_pr": 685,
            "source_workflow_run_id": 36797087427,
            "source_result_artifact_id": 11134202297,
            "whole_st_missing_active_set_sha256":
                coverage["missing_active_exact_set_sha256"],
            "g0_gap_set_sha256": EXPECTED_GAP_SHA256,
        },
        "layer1_catalog": {
            "official_active_exact_total": EXPECTED_ACTIVE_G0,
            "production_exact_current": EXPECTED_PRODUCTION_G0,
            "active_exact_gap": EXPECTED_GAP_COUNT,
            "catalog_identity_candidate_count": EXPECTED_GAP_COUNT,
            "production_coverage_percent": round(
                EXPECTED_PRODUCTION_G0 / EXPECTED_ACTIVE_G0 * 100, 4),
            "identity_is_not_rejected_by_backend_state": True,
        },
        "historical_scope": {
            "published_base_device_count": len(published_bases),
            "gap_unique_base_device_count": len(unique_bases),
            "gap_existing_published_base_count": len(shared_bases),
            "gap_new_base_device_count": len(new_bases),
            "exact_gap_scope_counts": dict(sorted(scope_counts.items())),
        },
        "layer2_route_observation": {
            "route_counts": dict(sorted(route_counts.items())),
            "route_examples": dict(sorted(route_examples.items())),
            "route_state_gates_layer1_identity": False,
        },
        "subfamily_gap_counts": {
            sub: subfamily_counts[sub] for sub in EXPECTED_SUBFAMILIES
        },
        "largest_gap_bases": [
            {"base_device": base, "gap_exact_count": count}
            for base, count in gap_base_counts.most_common(20)
        ],
        "claims": {
            "production_write_authorized": False,
            "metadata_complete_for_all_gap_identities": False,
            "backend_support_claimed_for_all_gap_identities": False,
            "physical_validation_claimed": False,
        },
        "next_gate":
            "Acquire authoritative metadata for the new Base Device set and "
            "promote Layer-1 identities independently of Layer-2 route state; "
            "Production write requires explicit owner approval.",
    }
    return result

def main() -> int:
    result = classify()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
