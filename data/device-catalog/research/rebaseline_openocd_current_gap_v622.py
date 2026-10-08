#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
UPSTREAM_BASELINE = HERE / "openocd-active-coverage-classification-v6.3.json"

EXPECTED_PRODUCTION_TOTAL = 4629
EXPECTED_MAPPED = 4054
EXPECTED_NO_MAPPING = 575
EXPECTED_ACTIVE_ROUTE = 3975
EXPECTED_ACTIVE_DENOMINATOR = 4550

EXPECTED_TIER_COUNTS = {
    "A_residual_same_series_existing_route": 8,
    "B_family_route_flash_capable_no_series_sibling": 102,
    "C_upstream_debug_target_without_flash_bank": 32,
    "D_no_direct_upstream_target_config": 433,
}
EXPECTED_A_FAMILY_COUNTS = {
    "STM32C0": 5,
    "STM32G4": 1,
    "STM32L4": 2,
}

FAMILY_FLASH_TARGET = {
    "STM32F3": "tcl/target/stm32f3x.cfg",
    "STM32F7": "tcl/target/stm32f7x.cfg",
}
DEBUG_ONLY_TARGET = {
    "STM32N6": "tcl/target/stm32n6x.cfg",
}
NO_DIRECT_TARGET_FAMILIES = {"STM32C5", "STM32H5", "STM32WL3", "STM32WB0"}

FIELDS = (
    "manufacturer","icpn","family","series","base_device",
    "tier","tier_reason","candidate_openocd_target_config",
    "same_series_mapped_sibling_count","same_series_mapped_target_config_count",
    "programming_profile_state","production_write_authorized",
)

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)

def read_rows(path: Path) -> list[dict[str,str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))

def build() -> tuple[list[dict[str,str]], str, dict[str,Any]]:
    baseline = json.loads(UPSTREAM_BASELINE.read_text(encoding="utf-8"))
    req(
        baseline["upstream_openocd_binding"]["master_commit"]
        == "8da0578d7bce3e134821ccf10911182788debc32",
        "frozen upstream OpenOCD baseline drift",
    )

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    req(len(sources) == 28, "Production source count drift")
    req(
        sum(int(s["row_count"]) for s in sources) == EXPECTED_PRODUCTION_TOTAL,
        "Production exact total drift",
    )

    all_rows: list[dict[str,str]] = []
    for source in sources:
        path = (MANIFEST.parent / source["path"]).resolve()
        rows = read_rows(path)
        req(len(rows) == int(source["row_count"]), f"{source['family']}: row count drift")
        all_rows.extend(rows)

    mapped = [r for r in all_rows if r["mapping_status"] != "no_mapping"]
    gaps = [r for r in all_rows if r["mapping_status"] == "no_mapping"]
    req(len(mapped) == EXPECTED_MAPPED, f"mapped count drift: {len(mapped)}")
    req(len(gaps) == EXPECTED_NO_MAPPING, f"no_mapping count drift: {len(gaps)}")

    mapped_by_series: dict[tuple[str,str], list[dict[str,str]]] = defaultdict(list)
    configs_by_series: dict[tuple[str,str], set[str]] = defaultdict(set)
    for row in mapped:
        req(row["openocd_target_config"], f"{row['icpn']}: mapped row missing target config")
        key = (row["family"], row["series"])
        mapped_by_series[key].append(row)
        configs_by_series[key].add(row["openocd_target_config"])

    classified: list[dict[str,str]] = []
    for row in gaps:
        key = (row["family"], row["series"])
        siblings = mapped_by_series.get(key, [])
        configs = configs_by_series.get(key, set())

        if siblings:
            req(
                len(configs) == 1,
                f"{row['family']} {row['series']}: conflicting mapped sibling target configs",
            )
            tier = "A_residual_same_series_existing_route"
            reason = "same_series_mapped_siblings_single_consistent_target_config"
            candidate = next(iter(configs))
        elif row["family"] in FAMILY_FLASH_TARGET:
            tier = "B_family_route_flash_capable_no_series_sibling"
            reason = "family_target_has_flash_bank_but_exact_series_has_no_mapped_sibling"
            candidate = FAMILY_FLASH_TARGET[row["family"]]
        elif row["family"] in DEBUG_ONLY_TARGET:
            tier = "C_upstream_debug_target_without_flash_bank"
            reason = "upstream_family_target_exists_without_flash_bank"
            candidate = DEBUG_ONLY_TARGET[row["family"]]
        elif row["family"] in NO_DIRECT_TARGET_FAMILIES:
            tier = "D_no_direct_upstream_target_config"
            reason = "no_direct_family_target_in_frozen_upstream_inventory"
            candidate = ""
        else:
            raise RuntimeError(
                f"{row['icpn']}: unclassified current gap "
                f"family={row['family']} series={row['series']}"
            )

        classified.append({
            "manufacturer": row["manufacturer"],
            "icpn": row["icpn"],
            "family": row["family"],
            "series": row["series"],
            "base_device": row["base_device"],
            "tier": tier,
            "tier_reason": reason,
            "candidate_openocd_target_config": candidate,
            "same_series_mapped_sibling_count": str(len(siblings)),
            "same_series_mapped_target_config_count": str(len(configs)),
            "programming_profile_state": "unresolved",
            "production_write_authorized": "false",
        })

    classified.sort(key=lambda r: r["icpn"])
    req(len(classified) == EXPECTED_NO_MAPPING, "classified gap cardinality drift")
    req(len({r["icpn"] for r in classified}) == EXPECTED_NO_MAPPING, "duplicate classified ICPN")

    tier_counts = dict(sorted(Counter(r["tier"] for r in classified).items()))
    req(tier_counts == EXPECTED_TIER_COUNTS, f"tier partition drift: {tier_counts}")

    family_counts: dict[str, Counter[str]] = defaultdict(Counter)
    series_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in classified:
        family_counts[row["tier"]][row["family"]] += 1
        series_counts[row["tier"]][row["series"]] += 1

    a_family_counts = dict(sorted(
        family_counts["A_residual_same_series_existing_route"].items()
    ))
    req(a_family_counts == EXPECTED_A_FAMILY_COUNTS,
        f"A-residual family partition drift: {a_family_counts}")

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(classified)
    csv_text = buf.getvalue()

    summary = {
        "schema_version": 1,
        "audit_id": "openocd-current-gap-rebaseline-v6.22",
        "record_state": "RESEARCH_ONLY",
        "production_exact_total": EXPECTED_PRODUCTION_TOTAL,
        "production_mapped_total": EXPECTED_MAPPED,
        "production_no_mapping_total": EXPECTED_NO_MAPPING,
        "active_openocd_route_exact_count": EXPECTED_ACTIVE_ROUTE,
        "scoped_active_denominator": EXPECTED_ACTIVE_DENOMINATOR,
        "active_openocd_route_coverage_percent": round(
            EXPECTED_ACTIVE_ROUTE / EXPECTED_ACTIVE_DENOMINATOR * 100, 4
        ),
        "current_gap_exact_count": EXPECTED_NO_MAPPING,
        "current_gap_exact_set_sha256": hashlib.sha256(
            ("\n".join(r["icpn"] for r in classified) + "\n").encode()
        ).hexdigest(),
        "classification_csv_sha256": hashlib.sha256(csv_text.encode()).hexdigest(),
        "tier_counts": tier_counts,
        "tier_family_counts": {
            tier: dict(sorted(counts.items()))
            for tier, counts in sorted(family_counts.items())
        },
        "tier_series_counts": {
            tier: dict(sorted(counts.items()))
            for tier, counts in sorted(series_counts.items())
        },
        "comparison": {
            "v6_17_gap": 592,
            "v6_21_promoted_from_a_residual": 17,
            "current_gap": EXPECTED_NO_MAPPING,
            "v6_17_tier_counts": {
                "A_residual_same_series_existing_route": 25,
                "B_family_route_flash_capable_no_series_sibling": 102,
                "C_upstream_debug_target_without_flash_bank": 32,
                "D_no_direct_upstream_target_config": 433,
            },
        },
        "upstream_openocd_binding": baseline["upstream_openocd_binding"],
        "claims": {
            "production_write_authorized": False,
            "identifier_inferred": False,
            "programming_profile_binding_claimed": False,
            "programming_verified_claimed": False,
            "engineering_verified_claimed": False,
            "hil_verified_claimed": False,
        },
    }
    req(sum(summary["tier_counts"].values()) == EXPECTED_NO_MAPPING, "tier partition sum drift")
    return classified, csv_text, summary

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classified", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    _, csv_text, summary = build()
    if args.classified:
        args.classified.write_text(csv_text, encoding="utf-8")
    if args.summary:
        args.summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("OPENOCD_CURRENT_GAP_REBASELINE_V622_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
