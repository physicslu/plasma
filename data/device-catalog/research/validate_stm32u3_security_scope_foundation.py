#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
FOUNDATION = HERE / "stm32u3-security-scope-foundation.json"
UPSTREAM = HERE / "stm32-trustzone-cohort-succession-after-l5-blocker.json"
TRANSACTION = "stm32u3-security-scope-foundation"
EXPECTED_SUBFAMILIES = {
    "STM32U335", "STM32U345", "STM32U356", "STM32U366",
    "STM32U375", "STM32U385", "STM32U3B5", "STM32U3C5",
}
REQUIRED_CONTROLS = {
    "TZEN", "RDP", "secure_nonsecure_execution_state", "debug_interface_state",
    "OEM1KEY", "OEM1LOCK", "OEM2KEY", "OEM2LOCK",
}
REQUIRED_TRUE = {
    "manufacturer_identity_discovery_allowed",
    "commercial_icpn_discovery_allowed",
}
REQUIRED_FALSE = {
    "production_admission_allowed",
    "security_semantics_supported",
    "option_byte_writes_allowed",
    "oem_key_provisioning_allowed",
    "oem_unlock_execution_allowed",
    "rdp_regression_allowed",
    "mass_erase_allowed",
    "flash_geometry_validated",
    "programming_algorithm_equivalence",
    "runtime_programming_supported",
    "debug_attach_supported",
    "hil_validated",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path.name}: root must be object")
    return value


def validate(foundation: dict, upstream: dict) -> None:
    _require(foundation.get("schema_version") == 1, "schema version drifted")
    _require(foundation.get("transaction") == TRANSACTION, "transaction drifted")
    _require(foundation.get("authority") == "research_only", "authority escaped research_only")
    _require(foundation.get("upstream_selection") == UPSTREAM.name, "upstream binding drifted")
    _require(foundation.get("exact_icpn_count") == 1862, "Production exact ICPN count drifted")
    _require(foundation.get("series") == "STM32U3", "series drifted")
    _require(set(foundation.get("subfamily_scope") or []) == EXPECTED_SUBFAMILIES, "subfamily scope drifted")

    _require(upstream.get("authority") == "research_only", "upstream authority drifted")
    _require(upstream.get("exact_icpn_count") == 1862, "upstream Production count drifted")
    policy = upstream.get("succession_policy")
    _require(isinstance(policy, dict), "upstream succession policy missing")
    _require(policy.get("selected_series") == "STM32U3", "upstream no longer selects STM32U3")
    _require(policy.get("selected_rank") == 2, "STM32U3 succession rank drifted")
    selected = upstream.get("selected_candidate")
    _require(isinstance(selected, dict), "upstream selected candidate missing")
    _require(set(selected.get("subfamilies") or []) == EXPECTED_SUBFAMILIES, "upstream U3 subfamily set drifted")
    _require(selected.get("target_config") == "tcl/target/stm32u3x.cfg", "upstream target config drifted")
    _require(upstream.get("next_research_gate") == TRANSACTION, "upstream next gate drifted")

    sources = foundation.get("manufacturer_sources")
    _require(isinstance(sources, list) and len(sources) >= 4, "manufacturer evidence set incomplete")
    source_ids: set[str] = set()
    observations: list[str] = []
    for source in sources:
        source_id = source.get("id")
        _require(isinstance(source_id, str) and source_id and source_id not in source_ids, "source ids must be unique and nonblank")
        source_ids.add(source_id)
        _require(source.get("authority") == "STMicroelectronics", f"{source_id}: source authority drifted")
        url = source.get("url")
        _require(isinstance(url, str) and urlparse(url).scheme == "https", f"{source_id}: URL must be HTTPS")
        host = (urlparse(url).hostname or "").lower()
        _require(host in {"www.st.com", "st.com", "wiki.st.com"}, f"{source_id}: source is not ST-controlled")
        source_observations = source.get("observations")
        _require(isinstance(source_observations, list) and source_observations, f"{source_id}: observations missing")
        observations.extend(str(item).lower() for item in source_observations)

    joined = "\n".join(observations)
    for token in ("cortex-m33", "trustzone", "rdp level 0.5", "rdp level 2", "oem1lock", "oem2lock", "debug"):
        _require(token in joined, f"manufacturer evidence misses required security concept: {token}")

    controls = set(foundation.get("security_sensitive_controls") or [])
    _require(REQUIRED_CONTROLS.issubset(controls), "security-sensitive control set incomplete")

    invariants = foundation.get("u3_specific_security_invariants")
    _require(isinstance(invariants, dict), "U3 security invariants missing")
    for key in (
        "rdp0_5_requires_trustzone",
        "rdp2_debug_closed",
        "rdp2_to_rdp1_requires_oem2_unlock_mechanism",
        "oem_key_lock_state_affects_regression_policy",
        "plasma_may_not_infer_oem_key_state",
        "plasma_may_not_mutate_security_state_for_discovery",
    ):
        _require(invariants.get(key) is True, f"required U3 invariant missing: {key}")
    _require(invariants.get("rdp2_is_unconditionally_terminal") is False, "U3 RDP2 must not be modeled as unconditionally terminal")

    partition = foundation.get("research_partition")
    _require(isinstance(partition, dict), "research partition missing")
    for key in REQUIRED_TRUE:
        _require(partition.get(key) is True, f"{key} must remain true")
    for key in REQUIRED_FALSE:
        _require(partition.get(key) is False, f"{key} must remain false")

    _require(foundation.get("status") == "eligible_for_identity_discovery_under_security_fence", "foundation status drifted")
    _require(foundation.get("next_research_gate") == "stm32u3-manufacturer-identity-discovery", "next research gate drifted")


def negative_controls(foundation: dict) -> list[tuple[str, dict]]:
    cases: list[tuple[str, dict]] = []

    terminal = copy.deepcopy(foundation)
    terminal["u3_specific_security_invariants"]["rdp2_is_unconditionally_terminal"] = True
    cases.append(("copy L5 terminal-RDP2 semantics into U3", terminal))

    infer_key = copy.deepcopy(foundation)
    infer_key["u3_specific_security_invariants"]["plasma_may_not_infer_oem_key_state"] = False
    cases.append(("infer unknown OEM key state", infer_key))

    unlock = copy.deepcopy(foundation)
    unlock["research_partition"]["oem_unlock_execution_allowed"] = True
    cases.append(("authorize OEM unlock execution", unlock))

    runtime = copy.deepcopy(foundation)
    runtime["research_partition"]["runtime_programming_supported"] = True
    cases.append(("claim runtime programming", runtime))

    production = copy.deepcopy(foundation)
    production["research_partition"]["production_admission_allowed"] = True
    cases.append(("claim Production admission", production))

    count = copy.deepcopy(foundation)
    count["exact_icpn_count"] = 1863
    cases.append(("Production ICPN count drift", count))
    return cases


def main() -> int:
    foundation = _read(FOUNDATION)
    upstream = _read(UPSTREAM)
    validate(foundation, upstream)
    rejected = 0
    for name, mutated in negative_controls(foundation):
        try:
            validate(mutated, upstream)
        except ValueError:
            rejected += 1
        else:
            raise SystemExit(f"FAIL: negative control admitted: {name}")
    _require(rejected == 6, "negative-control rejection count drifted")
    print("STM32U3 security-scope foundation: PASS")
    print("subfamilies=8")
    print("rdp2_unconditionally_terminal=false")
    print("negative_controls_rejected=6")
    print("exact_icpn_count=1862")
    print("next_research_gate=stm32u3-manufacturer-identity-discovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
