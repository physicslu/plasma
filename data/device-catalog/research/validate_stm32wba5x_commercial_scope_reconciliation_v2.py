#!/usr/bin/env python3
"""Validate STM32WBA5X current commercial-scope reconciliation v2."""
from __future__ import annotations

import json
from pathlib import Path

from stm32wba5x_commercial_scope_reconciliation_v2 import render

HERE = Path(__file__).resolve().parent
OUT = HERE / "stm32wba5x-commercial-scope-reconciliation-v2.json"

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)

def main() -> int:
    checked = json.loads(OUT.read_text(encoding="utf-8"))
    expected = render()
    req(checked == expected, "checked-in v2 reconciliation differs from deterministic renderer")
    req(checked.get("decision") == "current_commercial_scope_reconciled_v2", "decision drifted")
    source = checked.get("source_surface") or {}
    prior = checked.get("prior_reconciled_surface") or {}
    reconciled = checked.get("reconciled_surface") or {}
    req(source.get("source_rows") == 34, "source row count drifted")
    req(prior == {
        "retained_rows": 32,
        "ordering_pattern_rows": 16,
        "cmsis_device_name_rows": 16,
        "base_device_count": 16,
    }, "prior surface drifted")
    req(reconciled.get("retained_rows") == 31, "v2 retained row count drifted")
    req(reconciled.get("ordering_pattern_rows") == 15, "v2 ordering count drifted")
    req(reconciled.get("cmsis_device_name_rows") == 16, "v2 CMSIS count drifted")
    req(reconciled.get("base_device_count") == 15, "v2 Base Device count drifted")
    req("STM32WBA55HE" not in reconciled.get("base_devices", []), "STM32WBA55HE leaked into current commercial scope")
    req("STM32WBA55HG" in reconciled.get("base_devices", []), "STM32WBA55HG missing")
    excluded = checked.get("excluded_research_candidates")
    req(
        isinstance(excluded, list)
        and {(x.get("part_number"), x.get("identifier_kind")) for x in excluded}
        == {
            ("STM32WBA50KEUx", "ordering_pattern"),
            ("STM32WBA50KEUxT", "cmsis_device_name"),
            ("STM32WBA55HEFx", "ordering_pattern"),
        },
        "excluded candidate set drifted",
    )
    evidence = checked.get("official_manufacturer_evidence") or {}
    blocked = evidence.get("blocked_product") or {}
    sibling = evidence.get("active_sibling_product") or {}
    req(blocked.get("base_device") == "STM32WBA55HE", "blocked identity drifted")
    req(blocked.get("live_discovery_result") == "browser navigation returned HTTP 404", "blocked result drifted")
    req(sibling.get("base_device") == "STM32WBA55HG", "active sibling identity drifted")
    req(sibling.get("observed_active_exact_icpns") == ["STM32WBA55HGF6TR", "STM32WBA55HGF7TR"], "active sibling exact identities drifted")
    req(checked.get("next_gate") == "stm32wba5x-bounded-exact-icpn-discovery-gate", "discovery gate drifted")
    claims = checked.get("claims") or {}
    req(claims and all(v is False for v in claims.values()), "fail-closed claim escaped")
    print("STM32WBA5X current commercial-scope reconciliation v2: PASS")
    print("source=34 retained=31 excluded=3 ordering=15 cmsis=16 bases=15")
    print("new_exclusion=STM32WBA55HEFx next=exact-discovery")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
