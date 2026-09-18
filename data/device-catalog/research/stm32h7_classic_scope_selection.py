#!/usr/bin/env python3
"""Select STM32H7-classic after STM32H7RS Production publication.

Research-only transaction. It replays the frozen STM32H7 partition decision
against the post-H7RS Production boundary, selects the only remaining bounded
H7 partition, and authorizes only the next manufacturer-evidence accessibility
gate. It does not modify Production or authorize target execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FROZEN_PRODUCTION = HERE / "stm32-post-h7rs-production-prestate.json"
CURRENT_PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
UPSTREAM_SELECTION = HERE / "stm32h7-partitioned-scope-selection.json"

EXPECTED_PRODUCTION_BLOB = "41e795a722a836215b796c5743549a0081d95973"
EXPECTED_UPSTREAM_SELECTION_BLOB = "9f52207a2febb6312649bbf8caace9d79eda5000"
NEXT_GATE = "stm32h7-classic-bounded-official-manufacturer-evidence-accessibility-gate"


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data, usedforsecurity=False).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name}: expected object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _production_boundary() -> tuple[dict[str, Any], int, int]:
    frozen_bytes = FROZEN_PRODUCTION.read_bytes()
    current_bytes = CURRENT_PRODUCTION.read_bytes()
    _require(_git_blob_sha(frozen_bytes) == EXPECTED_PRODUCTION_BLOB, "frozen post-H7RS Production prestate drifted")
    _require(current_bytes == frozen_bytes, "Production changed during STM32H7 classic reselection")
    manifest = _read_json(FROZEN_PRODUCTION)
    sources = manifest.get("sources")
    _require(isinstance(sources, list), "Production sources missing")
    exact = sum(int(source.get("row_count", 0)) for source in sources if isinstance(source, dict))
    _require(exact == 2318, f"post-H7RS Production exact count drifted: {exact}")
    _require(len(sources) == 17, f"post-H7RS Production family count drifted: {len(sources)}")
    h7rs = [source for source in sources if isinstance(source, dict) and source.get("family") == "STM32H7RS"]
    _require(len(h7rs) == 1, "STM32H7RS Production binding missing or duplicated")
    _require(h7rs[0] == {
        "manufacturer": "STMicroelectronics",
        "family": "STM32H7RS",
        "path": "../research/stm32h7rs-commercial-icpn.csv",
        "row_count": 36,
        "git_blob_sha": "c8457006dbe45bef5203ed061b47c2f00224d717",
        "sha256": "e86083329eaceb013aa19ea7fdb85d4b8c55339f7879dc02237c15a549d498a3",
    }, "STM32H7RS Production binding drifted")
    return h7rs[0], exact, len(sources)


def build_selection() -> dict[str, Any]:
    h7rs_source, exact, families = _production_boundary()

    upstream_bytes = UPSTREAM_SELECTION.read_bytes()
    _require(_git_blob_sha(upstream_bytes) == EXPECTED_UPSTREAM_SELECTION_BLOB, "upstream H7 partition selection drifted")
    upstream = _read_json(UPSTREAM_SELECTION)
    _require(upstream.get("selection_id") == "stm32h7-partitioned-scope-selection-v1", "upstream selection id drifted")
    _require(upstream.get("selected_partition") == "STM32H7RS", "historical first partition drifted")
    _require((upstream.get("claims") or {}).get("stm32h7_classic_rejected") is False, "STM32H7-classic was historically rejected")

    partitions = upstream.get("partitions")
    _require(isinstance(partitions, list) and len(partitions) == 2, "upstream partition set drifted")
    by_id = {item.get("partition_id"): item for item in partitions if isinstance(item, dict)}
    _require(set(by_id) == {"STM32H7RS", "STM32H7-classic"}, "upstream partition ids drifted")

    classic = by_id["STM32H7-classic"]
    _require(classic.get("bounded_research_eligible") is True, "STM32H7-classic no longer bounded-research eligible")
    _require(classic.get("admission_ready") is False, "STM32H7-classic unexpectedly admission-ready")
    _require(classic.get("row_count") == 166, "STM32H7-classic row count drifted")
    _require(classic.get("subfamily_count") == 16, "STM32H7-classic subfamily count drifted")
    _require(classic.get("target_config") == "tcl/target/stm32h7x.cfg", "STM32H7-classic target config drifted")
    _require(classic.get("identifier_kind_counts") == {"cmsis_device_name": 28, "ordering_pattern": 138}, "STM32H7-classic identifier mix drifted")

    return {
        "schema_version": 1,
        "selection_id": "stm32h7-classic-scope-selection-v1",
        "scope": "remaining_partition_selection_research_only",
        "status": "selected_for_bounded_manufacturer_evidence_only",
        "production_boundary": {
            "exact_icpns": exact,
            "families": families,
            "frozen_manifest_git_blob_sha": EXPECTED_PRODUCTION_BLOB,
            "stm32h7rs_published": True,
            "stm32h7rs_source": h7rs_source,
        },
        "upstream": {
            "selection_id": upstream["selection_id"],
            "selection_git_blob_sha": EXPECTED_UPSTREAM_SELECTION_BLOB,
            "historical_first_partition": "STM32H7RS",
            "historical_partition_count": 2,
            "classic_rejected": False,
        },
        "selection_basis": [
            "STM32H7RS was the first bounded partition selected by the frozen H7 partition policy",
            "STM32H7RS is now published in Production as 36 exact ICPNs",
            "STM32H7-classic is the only remaining bounded-research-eligible STM32H7 partition",
            "selection is sequencing only and does not claim programming-algorithm equivalence",
        ],
        "selected_partition": "STM32H7-classic",
        "selected_target_config": classic["target_config"],
        "selected_row_count": classic["row_count"],
        "selected_subfamily_count": classic["subfamily_count"],
        "selected_subfamilies": classic["subfamilies"],
        "selected_identifier_kind_counts": classic["identifier_kind_counts"],
        "next_gate": NEXT_GATE,
        "claims": {
            "production_write_authorized": False,
            "exact_icpn_discovery_completed": False,
            "icpn_admission_authorized": False,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_programming_support_claimed": False,
            "security_mutation_authorized": False,
            "debug_attach_supported": False,
            "physical_validation_claimed": False,
            "hil_required_for_catalog_admission": False,
            "stm32h7_classic_admission_ready": False,
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
