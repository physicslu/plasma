#!/usr/bin/env python3
"""Select the first bounded STM32H7 research partition.

This transaction is research-only. It partitions the already-selected STM32H7
frontier by retained target-config/family boundaries. It does not discover or
admit exact commercial ICPNs, modify Production, define programming behavior,
or authorize target execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "stm32h7-partition-source.json"
UPSTREAM = HERE / "stm32-post-u5-frontier-selection.json"
NEXT_GATE = "stm32h7rs-bounded-official-manufacturer-evidence-accessibility-gate"

PARTITIONS = {
    "tcl/target/stm32h7x.cfg": {
        "partition_id": "STM32H7-classic",
        "family_label": "STM32H7 Series",
    },
    "tcl/target/stm32h7rsx.cfg": {
        "partition_id": "STM32H7RS",
        "family_label": "STM32H7RS Series",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def build_selection() -> dict[str, Any]:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    upstream = json.loads(UPSTREAM.read_text(encoding="utf-8"))

    _require(upstream.get("selected_next_research_frontier") == "STM32H7", "upstream frontier is not STM32H7")
    _require(upstream.get("next_gate") == "stm32h7-partitioned-scope-selection-gate", "upstream next gate drifted")
    _require((upstream.get("claims") or {}).get("stm32h7_admission_ready") is False, "upstream H7 admission boundary drifted")

    _require(source.get("source_id") == "stm32h7-partition-source-v1", "partition source id drifted")
    rows = source.get("rows") or []
    _require(len(rows) == 200, "STM32H7 frozen source must contain 200 rows")
    _require(source.get("row_count") == 200, "STM32H7 frozen source row_count drifted")
    _require(all(row.get("vendor") == "STMicroelectronics" for row in rows), "non-ST row in H7 source")
    _require(all(row.get("plasma_series") == "STM32H7" for row in rows), "non-H7 row in H7 source")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("target_config"))].append(row)
    _require(set(grouped) == set(PARTITIONS), "H7 target-config partition set drifted")

    duplicate_rows = source.get("duplicate_resolutions") or []
    _require(len(duplicate_rows) == 34, "H7R/S duplicate-resolution count drifted")
    _require(all(row.get("vendor") == "STMicroelectronics" for row in duplicate_rows), "non-ST duplicate resolution")
    _require(all(row.get("superseded_target_config") == "tcl/target/stm32h7x.cfg" for row in duplicate_rows), "unexpected superseded H7 target")
    _require(all(row.get("selected_target_config") == "tcl/target/stm32h7rsx.cfg" for row in duplicate_rows), "unexpected selected H7R/S target")
    _require(all(row.get("resolution") == "prefer_specific_expansion_mapping" for row in duplicate_rows), "H7R/S conflict policy drifted")

    partitions: list[dict[str, Any]] = []
    for target_config, policy in sorted(PARTITIONS.items()):
        part_rows = grouped[target_config]
        families = sorted({str(row.get("family")) for row in part_rows})
        subfamilies = sorted({str(row.get("subfamily")) for row in part_rows if row.get("subfamily")})
        kinds = Counter(str(row.get("identifier_kind")) for row in part_rows)
        _require(families == [policy["family_label"]], f"{policy['partition_id']}: family boundary drifted")
        _require(all(row.get("openocd_distribution") == "upstream-openocd" for row in part_rows), "OpenOCD distribution drifted")
        _require(all(row.get("mapping_status") == "mapping_candidate" for row in part_rows), "mapping status drifted")
        _require(all(row.get("validation_status") == "not_verified" for row in part_rows), "validation status drifted")
        partitions.append({
            "partition_id": policy["partition_id"],
            "family_label": policy["family_label"],
            "target_config": target_config,
            "row_count": len(part_rows),
            "subfamily_count": len(subfamilies),
            "subfamilies": subfamilies,
            "identifier_kind_counts": dict(sorted(kinds.items())),
            "duplicate_resolution_count": len(duplicate_rows) if target_config == "tcl/target/stm32h7rsx.cfg" else 0,
            "bounded_research_eligible": True,
            "admission_ready": False,
        })

    _require(sum(item["row_count"] for item in partitions) == 200, "partition row total drifted")
    _require(sum(item["subfamily_count"] for item in partitions) == 20, "partition subfamily total drifted")

    ranked = sorted(partitions, key=lambda item: (item["row_count"], item["subfamily_count"], item["partition_id"]))
    selected = ranked[0]
    _require(selected["partition_id"] == "STM32H7RS", "bounded-first partition selection drifted")
    _require(selected["row_count"] == 34, "STM32H7RS row count drifted")
    _require(selected["subfamily_count"] == 4, "STM32H7RS subfamily count drifted")
    _require(selected["duplicate_resolution_count"] == 34, "STM32H7RS conflict-resolution count drifted")

    return {
        "schema_version": 1,
        "selection_id": "stm32h7-partitioned-scope-selection-v1",
        "scope": "partition_selection_research_only",
        "status": "selected_for_bounded_manufacturer_evidence_only",
        "upstream": {
            "frontier_selection_id": upstream.get("selection_id"),
            "selected_frontier": "STM32H7",
            "frontier_row_count": 200,
            "frontier_subfamily_count": 20,
        },
        "source": {
            "frozen_partition_source_sha256": _sha256(SOURCE),
            "canonical_source_sha256": source.get("canonical_source_sha256"),
            "duplicate_resolution_source_sha256": source.get("duplicate_resolution_source_sha256"),
            "frozen_row_count": 200,
            "frozen_duplicate_resolution_count": 34,
        },
        "partition_policy": {
            "primary_boundary": "target_config_and_family_label",
            "selection_order": [
                "fewest frozen source rows",
                "fewest subfamilies",
                "lexical partition_id tie-break",
            ],
            "reason": "one OpenOCD target config per bounded research partition; smaller bounded surface first",
        },
        "partitions": ranked,
        "selected_partition": selected["partition_id"],
        "selected_target_config": selected["target_config"],
        "next_gate": NEXT_GATE,
        "claims": {
            "production_write_authorized": False,
            "exact_icpn_discovery_completed": False,
            "icpn_admission_authorized": False,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_programming_support_claimed": False,
            "physical_validation_claimed": False,
            "hil_required_for_catalog_admission": False,
            "stm32h7rs_admission_ready": False,
            "stm32h7_classic_rejected": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(build_selection(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
