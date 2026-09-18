#!/usr/bin/env python3
"""Fail-closed validation for STM32H7-classic remaining-scope selection."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from stm32h7_classic_scope_selection import build_selection

HERE = Path(__file__).resolve().parent
SELECTION = HERE / "stm32h7-classic-scope-selection.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate(value: dict) -> None:
    req(value.get("selection_id") == "stm32h7-classic-scope-selection-v1", "selection id drifted")
    req(value.get("scope") == "remaining_partition_selection_research_only", "scope drifted")
    req(value.get("status") == "selected_for_bounded_manufacturer_evidence_only", "status drifted")
    req(value.get("selected_partition") == "STM32H7-classic", "selected partition drifted")
    req(value.get("selected_target_config") == "tcl/target/stm32h7x.cfg", "selected target config drifted")
    req(value.get("selected_row_count") == 166, "selected row count drifted")
    req(value.get("selected_subfamily_count") == 16, "selected subfamily count drifted")
    req(value.get("selected_identifier_kind_counts") == {"cmsis_device_name": 28, "ordering_pattern": 138}, "identifier mix drifted")
    req(value.get("next_gate") == "stm32h7-classic-bounded-official-manufacturer-evidence-accessibility-gate", "next gate drifted")

    prod = value.get("production_boundary") or {}
    req(prod.get("exact_icpns") == 2318, "Production exact count drifted")
    req(prod.get("families") == 17, "Production family count drifted")
    req(prod.get("stm32h7rs_published") is True, "STM32H7RS publication boundary missing")
    req((prod.get("stm32h7rs_source") or {}).get("row_count") == 36, "STM32H7RS Production row count drifted")

    upstream = value.get("upstream") or {}
    req(upstream.get("historical_first_partition") == "STM32H7RS", "historical first partition drifted")
    req(upstream.get("historical_partition_count") == 2, "historical partition count drifted")
    req(upstream.get("classic_rejected") is False, "classic partition was rejected")

    claims = value.get("claims") or {}
    for key in (
        "production_write_authorized",
        "exact_icpn_discovery_completed",
        "icpn_admission_authorized",
        "programming_algorithm_equivalence_claimed",
        "runtime_programming_support_claimed",
        "security_mutation_authorized",
        "debug_attach_supported",
        "physical_validation_claimed",
        "hil_required_for_catalog_admission",
        "stm32h7_classic_admission_ready",
    ):
        req(claims.get(key) is False, f"fail-closed claim opened: {key}")


def expect_rejected(name: str, mutate) -> None:
    candidate = copy.deepcopy(json.loads(SELECTION.read_text(encoding="utf-8")))
    mutate(candidate)
    try:
        validate(candidate)
    except AssertionError:
        return
    raise AssertionError(f"negative control was accepted: {name}")


def main() -> int:
    frozen = json.loads(SELECTION.read_text(encoding="utf-8"))
    validate(frozen)
    req(build_selection() == frozen, "frozen classic selection does not deterministically replay")

    controls = [
        ("reselect-h7rs", lambda v: v.__setitem__("selected_partition", "STM32H7RS")),
        ("wrong-target-config", lambda v: v.__setitem__("selected_target_config", "tcl/target/stm32h7rsx.cfg")),
        ("drop-h7rs-publication", lambda v: v["production_boundary"].__setitem__("stm32h7rs_published", False)),
        ("claim-exact-discovery", lambda v: v["claims"].__setitem__("exact_icpn_discovery_completed", True)),
        ("authorize-production", lambda v: v["claims"].__setitem__("production_write_authorized", True)),
        ("claim-algorithm-equivalence", lambda v: v["claims"].__setitem__("programming_algorithm_equivalence_claimed", True)),
        ("open-classic-admission", lambda v: v["claims"].__setitem__("stm32h7_classic_admission_ready", True)),
        ("skip-accessibility-gate", lambda v: v.__setitem__("next_gate", "stm32h7-classic-bounded-exact-icpn-discovery-gate")),
    ]
    for name, mutate in controls:
        expect_rejected(name, mutate)

    print("STM32H7-classic scope selection: PASS")
    print("selected=STM32H7-classic rows=166 subfamilies=16 target=tcl/target/stm32h7x.cfg")
    print(f"negative_controls={len(controls)} rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
