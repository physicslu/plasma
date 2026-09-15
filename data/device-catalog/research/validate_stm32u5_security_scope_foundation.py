#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FOUNDATION = HERE / "stm32u5-security-scope-foundation.json"
UPSTREAM = HERE / "stm32-trustzone-cohort-gate1-qualification.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
CATALOG_POLICY = ROOT / "docs/architecture/icpn-catalog-admission-policy.json"
TRANSACTION = "stm32u5-security-scope-foundation"
EXPECTED_PRODUCTION_EXACT = 2017
EXPECTED_SUBFAMILIES = {
    "STM32U535", "STM32U545", "STM32U575", "STM32U585",
    "STM32U595", "STM32U599", "STM32U5A5", "STM32U5A9",
    "STM32U5F7", "STM32U5F9", "STM32U5G7", "STM32U5G9",
}
REQUIRED_CONTROLS = {
    "TZEN", "RDP", "secure_nonsecure_execution_state", "debug_interface_state",
    "OEM1KEY", "OEM1LOCK", "OEM2KEY", "OEM2LOCK",
}
REQUIRED_TRUE = {
    "manufacturer_identity_discovery_allowed",
    "commercial_icpn_discovery_allowed",
    "catalog_admission_governed_separately",
}
REQUIRED_FALSE = {
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


def req(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: root must be object")
    return value


def validate_catalog_policy(policy: dict) -> None:
    admission = policy.get("catalog_admission")
    physical = policy.get("physical_validation")
    execution = policy.get("execution_policy")
    req(policy.get("policy_id") == "icpn-catalog-admission-separation", "catalog policy identity drifted")
    req(isinstance(admission, dict), "catalog admission policy missing")
    req(admission.get("requires_ppu_hil") is False, "PPU HIL leaked into catalog admission")
    req(admission.get("requires_socket_hil") is False, "Socket HIL leaked into catalog admission")
    req(admission.get("requires_physical_programming_success") is False, "physical programming leaked into catalog admission")
    req(admission.get("admits_not_verified_physical_state") is True, "not-verified catalog admission no longer allowed")
    req(isinstance(physical, dict) and physical.get("independent_from_catalog_admission") is True, "physical validation separation drifted")
    req(isinstance(execution, dict) and execution.get("catalog_presence_does_not_authorize_target_execution") is True, "execution separation drifted")


def validate_production(manifest: dict) -> None:
    sources = manifest.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    exact = sum(source.get("row_count", -1) for source in sources if isinstance(source, dict))
    families = {source.get("family") for source in sources if isinstance(source, dict)}
    req(exact == EXPECTED_PRODUCTION_EXACT, f"Production exact ICPN count drifted: {exact}")
    req({"STM32L5", "STM32U3"}.issubset(families), "prior TrustZone catalog admissions missing")
    req("STM32U5" not in families, "STM32U5 is already present in Production unexpectedly")


def validate(foundation: dict, upstream: dict, production: dict, policy: dict) -> None:
    req(foundation.get("schema_version") == 1, "schema version drifted")
    req(foundation.get("transaction") == TRANSACTION, "transaction drifted")
    req(foundation.get("authority") == "research_only", "authority escaped research_only")
    req(foundation.get("upstream_selection") == UPSTREAM.name, "upstream binding drifted")
    req(foundation.get("exact_icpn_count") == EXPECTED_PRODUCTION_EXACT, "foundation Production count drifted")
    req(foundation.get("series") == "STM32U5", "series drifted")
    req(set(foundation.get("subfamily_scope") or []) == EXPECTED_SUBFAMILIES, "subfamily scope drifted")

    validate_catalog_policy(policy)
    validate_production(production)

    req(upstream.get("authority") == "research_only", "upstream authority drifted")
    candidates = upstream.get("candidates")
    req(isinstance(candidates, list), "upstream candidates missing")
    u5 = [row for row in candidates if isinstance(row, dict) and row.get("plasma_series") == "STM32U5"]
    req(len(u5) == 1, "upstream STM32U5 candidate missing/duplicated")
    candidate = u5[0]
    req(candidate.get("rank") == 3, "STM32U5 TrustZone rank drifted")
    req(candidate.get("subfamily_count") == 12, "STM32U5 subfamily count drifted")
    req(candidate.get("row_count") == 162, "STM32U5 upstream row count drifted")
    req(candidate.get("ordering_pattern_rows") == 63, "STM32U5 ordering-pattern count drifted")
    req(candidate.get("target_config") == "tcl/target/stm32u5x.cfg", "STM32U5 target config drifted")

    sources = foundation.get("manufacturer_sources")
    req(isinstance(sources, list) and len(sources) >= 4, "manufacturer evidence incomplete")
    ids: set[str] = set()
    observations: list[str] = []
    for source in sources:
        req(isinstance(source, dict), "manufacturer source must be object")
        source_id = source.get("id")
        req(isinstance(source_id, str) and source_id and source_id not in ids, "manufacturer source id invalid")
        ids.add(source_id)
        req(source.get("authority") == "STMicroelectronics", f"{source_id}: authority drifted")
        url = source.get("url")
        req(isinstance(url, str) and urlparse(url).scheme == "https", f"{source_id}: URL must be HTTPS")
        req((urlparse(url).hostname or "").lower() in {"www.st.com", "st.com", "wiki.st.com"}, f"{source_id}: non-ST source")
        values = source.get("observations")
        req(isinstance(values, list) and values, f"{source_id}: observations missing")
        observations.extend(str(value).lower() for value in values)

    joined = "\n".join(observations)
    for token in ("cortex-m33", "trustzone", "rdp level 0.5", "rdp level 2", "oem1", "oem2", "debug"):
        req(token in joined, f"manufacturer evidence misses security concept: {token}")

    controls = set(foundation.get("security_sensitive_controls") or [])
    req(REQUIRED_CONTROLS.issubset(controls), "security-sensitive controls incomplete")

    invariants = foundation.get("u5_specific_security_invariants")
    req(isinstance(invariants, dict), "U5 security invariants missing")
    for key in (
        "rdp0_5_requires_trustzone",
        "rdp2_debug_closed",
        "rdp2_to_rdp1_requires_oem2_unlock_mechanism",
        "oem_key_lock_state_affects_regression_policy",
        "rdp_regressions_may_have_destructive_flash_effects",
        "plasma_may_not_infer_oem_key_state",
        "plasma_may_not_mutate_security_state_for_discovery",
        "catalog_admission_independent_from_hil",
        "catalog_membership_does_not_authorize_execution",
    ):
        req(invariants.get(key) is True, f"required U5 invariant missing: {key}")
    req(invariants.get("rdp2_is_unconditionally_terminal") is False, "U5 RDP2 must not be modeled as unconditionally terminal")

    partition = foundation.get("research_partition")
    req(isinstance(partition, dict), "research partition missing")
    req("production_admission_allowed" not in partition, "legacy security/HIL gate must not control catalog admission")
    for key in REQUIRED_TRUE:
        req(partition.get(key) is True, f"{key} must remain true")
    for key in REQUIRED_FALSE:
        req(partition.get(key) is False, f"{key} must remain false")

    req(foundation.get("status") == "eligible_for_identity_discovery_under_security_fence", "foundation status drifted")
    req(foundation.get("next_research_gate") == "stm32u5-manufacturer-identity-discovery", "next gate drifted")


def negative_controls(foundation: dict) -> list[tuple[str, dict]]:
    cases: list[tuple[str, dict]] = []
    terminal = copy.deepcopy(foundation)
    terminal["u5_specific_security_invariants"]["rdp2_is_unconditionally_terminal"] = True
    cases.append(("model RDP2 as unconditionally terminal", terminal))
    infer_key = copy.deepcopy(foundation)
    infer_key["u5_specific_security_invariants"]["plasma_may_not_infer_oem_key_state"] = False
    cases.append(("infer OEM key state", infer_key))
    unlock = copy.deepcopy(foundation)
    unlock["research_partition"]["oem_unlock_execution_allowed"] = True
    cases.append(("authorize OEM unlock", unlock))
    runtime = copy.deepcopy(foundation)
    runtime["research_partition"]["runtime_programming_supported"] = True
    cases.append(("claim runtime programming", runtime))
    hil_coupling = copy.deepcopy(foundation)
    hil_coupling["u5_specific_security_invariants"]["catalog_admission_independent_from_hil"] = False
    cases.append(("couple catalog admission to HIL", hil_coupling))
    execution = copy.deepcopy(foundation)
    execution["u5_specific_security_invariants"]["catalog_membership_does_not_authorize_execution"] = False
    cases.append(("let catalog membership authorize execution", execution))
    legacy = copy.deepcopy(foundation)
    legacy["research_partition"]["production_admission_allowed"] = False
    cases.append(("reintroduce legacy production-admission security fence", legacy))
    count = copy.deepcopy(foundation)
    count["exact_icpn_count"] = EXPECTED_PRODUCTION_EXACT + 1
    cases.append(("Production ICPN count drift", count))
    return cases


def main() -> int:
    foundation = read_json(FOUNDATION)
    upstream = read_json(UPSTREAM)
    production = read_json(PRODUCTION)
    policy = read_json(CATALOG_POLICY)
    validate(foundation, upstream, production, policy)
    rejected = 0
    for name, mutated in negative_controls(foundation):
        try:
            validate(mutated, upstream, production, policy)
        except ValueError:
            rejected += 1
        else:
            raise SystemExit(f"FAIL: negative control admitted: {name}")
    req(rejected == 8, "negative-control count drifted")
    print("STM32U5 security-scope foundation: PASS")
    print("subfamilies=12")
    print("rdp2_unconditionally_terminal=false")
    print("catalog_admission_independent_from_hil=true")
    print("negative_controls_rejected=8")
    print(f"exact_icpn_count={EXPECTED_PRODUCTION_EXACT}")
    print("next_research_gate=stm32u5-manufacturer-identity-discovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
