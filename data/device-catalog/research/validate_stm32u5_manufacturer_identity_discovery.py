#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DISCOVERY = HERE / "stm32u5-manufacturer-identity-discovery.json"
CSV_PATH = HERE / "stm32u5-base-device-discovery.csv"
SECURITY = HERE / "stm32u5-security-scope-foundation.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
POLICY = ROOT / "docs/architecture/icpn-catalog-admission-policy.json"

EXPECTED_PRODUCTION = 2017
EXPECTED_SUBFAMILIES = {
    "STM32U535", "STM32U545", "STM32U575", "STM32U585",
    "STM32U595", "STM32U599", "STM32U5A5", "STM32U5A9",
    "STM32U5F7", "STM32U5F9", "STM32U5G7", "STM32U5G9",
}
EXPECTED_COUNTS = {
    "STM32U535": 11, "STM32U545": 5, "STM32U575": 14, "STM32U585": 7,
    "STM32U595": 10, "STM32U599": 7, "STM32U5A5": 6, "STM32U5A9": 4,
    "STM32U5F7": 1, "STM32U5F9": 4, "STM32U5G7": 1, "STM32U5G9": 4,
}
EXPECTED_BASE_COUNT = 74
EXPECTED_BASE_HASH = "ab83ea88d30d173e3809b3c1245691a0fb6be4a78f6fa35bd47f6caa8533bcdf"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: root must be object")
    return value


def load_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    req(rows, "base-device CSV is empty")
    req(set(rows[0]) == {"base_device", "subfamily", "manufacturer_url", "observation_scope"}, "CSV schema drifted")
    return rows


def production_count(manifest: dict) -> int:
    sources = manifest.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    return sum(int(row.get("row_count", -1)) for row in sources if isinstance(row, dict))


def validate(discovery: dict, rows: list[dict[str, str]], security: dict, production: dict, policy: dict) -> None:
    req(discovery.get("schema_version") == 1, "schema version drifted")
    req(discovery.get("transaction") == "stm32u5-manufacturer-identity-discovery", "transaction drifted")
    req(discovery.get("authority") == "research_only", "authority escaped research_only")
    req(discovery.get("parent_security_scope") == SECURITY.name, "security parent drifted")
    req(discovery.get("series") == "STM32U5", "series drifted")
    req(discovery.get("manufacturer") == "STMicroelectronics", "manufacturer drifted")
    req(discovery.get("production_exact_icpn_count") == EXPECTED_PRODUCTION, "recorded Production count drifted")
    req(production_count(production) == EXPECTED_PRODUCTION, "Production manifest count drifted")

    req(security.get("transaction") == "stm32u5-security-scope-foundation", "security foundation missing")
    req(security.get("next_research_gate") == "stm32u5-manufacturer-identity-discovery", "security next gate drifted")
    req(security.get("exact_icpn_count") == EXPECTED_PRODUCTION, "security Production count drifted")

    admission = policy.get("catalog_admission")
    physical = policy.get("physical_validation")
    req(isinstance(admission, dict), "catalog admission policy missing")
    req(admission.get("requires_ppu_hil") is False, "PPU HIL leaked into catalog admission")
    req(admission.get("requires_socket_hil") is False, "Socket HIL leaked into catalog admission")
    req(admission.get("requires_physical_programming_success") is False, "physical programming leaked into catalog admission")
    req(isinstance(physical, dict) and physical.get("independent_from_catalog_admission") is True, "physical validation separation drifted")

    candidate = set(discovery.get("candidate_subfamilies") or [])
    observed = set(discovery.get("commercial_subfamilies_observed") or [])
    req(candidate == EXPECTED_SUBFAMILIES, "candidate subfamilies drifted")
    req(observed == EXPECTED_SUBFAMILIES, "commercial subfamily coverage drifted")
    req(discovery.get("candidate_subfamilies_without_current_commercial_identity_observation") == [], "unexpected unobserved U5 subfamily")

    base_devices = discovery.get("base_devices")
    req(isinstance(base_devices, list), "base-device list missing")
    req(discovery.get("base_device_count") == EXPECTED_BASE_COUNT == len(base_devices), "base-device count drifted")
    req(len(set(base_devices)) == EXPECTED_BASE_COUNT, "duplicate base device")
    canonical = "\n".join(sorted(base_devices)) + "\n"
    req(hashlib.sha256(canonical.encode()).hexdigest() == EXPECTED_BASE_HASH, "base-device set hash drifted")
    req(discovery.get("base_device_set_sha256") == EXPECTED_BASE_HASH, "recorded base-device hash drifted")
    req(discovery.get("base_device_counts_by_subfamily") == EXPECTED_COUNTS, "subfamily counts drifted")

    req(len(rows) == EXPECTED_BASE_COUNT, "CSV row count drifted")
    req(sorted(row["base_device"] for row in rows) == sorted(base_devices), "CSV/JSON identity set mismatch")
    req(dict(Counter(row["subfamily"] for row in rows)) == EXPECTED_COUNTS, "CSV subfamily counts drifted")
    for row in rows:
        base = row["base_device"]
        subfamily = row["subfamily"]
        req(base.startswith(subfamily), f"{base}: subfamily mismatch")
        req(row["observation_scope"] == "manufacturer_product_page_present", f"{base}: observation scope drifted")
        parsed = urlparse(row["manufacturer_url"])
        req(parsed.scheme == "https" and (parsed.hostname or "").lower() in {"www.st.com", "st.com"}, f"{base}: non-ST source")
        req(parsed.path.endswith(f"/{base.lower()}.html"), f"{base}: product URL mismatch")

    exact = discovery.get("exact_orderable_identity_enumeration")
    req(isinstance(exact, dict), "exact-identity boundary missing")
    req(exact.get("complete") is False, "exact ICPNs falsely declared complete")
    req(exact.get("exact_icpn_count") is None, "exact ICPN count must remain null before Q&R enumeration")
    req("without synthesis" in str(exact.get("reason", "")).lower(), "no-synthesis rule missing")

    result = discovery.get("result")
    req(isinstance(result, dict) and result.get("bounded_discovery_clean") is True, "bounded discovery not clean")
    req(result.get("all_12_upstream_subfamilies_have_current_base_device_observation") is True, "12/12 coverage claim missing")
    req(result.get("synthesized_base_devices") == 0, "synthesized base device admitted")
    req(result.get("synthesized_exact_icpns") == 0, "synthesized exact ICPN admitted")

    claims = discovery.get("claims")
    req(isinstance(claims, dict), "claims missing")
    req(claims.get("catalog_admission_blocked_by_hil") is False, "HIL coupling reintroduced")
    req(claims.get("exact_icpn_enumeration_complete") is False, "exact ICPN enumeration prematurely claimed")
    for key in ("physical_validation_claimed", "security_semantics_supported", "runtime_programming_supported", "debug_attach_supported", "hil_validated"):
        req(claims.get(key) is False, f"{key} must remain false")

    req(discovery.get("next_research_gate") == "stm32u5-exact-orderable-identity-enumeration", "next gate drifted")


def negative_controls(discovery: dict) -> list[tuple[str, dict]]:
    cases: list[tuple[str, dict]] = []
    wrong_count = copy.deepcopy(discovery); wrong_count["base_device_count"] = 73; cases.append(("wrong count", wrong_count))
    duplicate = copy.deepcopy(discovery); duplicate["base_devices"][1] = duplicate["base_devices"][0]; cases.append(("duplicate", duplicate))
    missing = copy.deepcopy(discovery); missing["commercial_subfamilies_observed"].remove("STM32U5G9"); cases.append(("missing subfamily", missing))
    exact = copy.deepcopy(discovery); exact["exact_orderable_identity_enumeration"]["complete"] = True; exact["exact_orderable_identity_enumeration"]["exact_icpn_count"] = 74; exact["claims"]["exact_icpn_enumeration_complete"] = True; cases.append(("base equals exact", exact))
    hil = copy.deepcopy(discovery); hil["claims"]["catalog_admission_blocked_by_hil"] = True; cases.append(("HIL coupling", hil))
    runtime = copy.deepcopy(discovery); runtime["claims"]["runtime_programming_supported"] = True; cases.append(("runtime claim", runtime))
    count = copy.deepcopy(discovery); count["production_exact_icpn_count"] = EXPECTED_PRODUCTION + 1; cases.append(("Production drift", count))
    return cases


def main() -> int:
    discovery = load_json(DISCOVERY)
    rows = load_rows()
    security = load_json(SECURITY)
    production = load_json(PRODUCTION)
    policy = load_json(POLICY)
    validate(discovery, rows, security, production, policy)
    rejected = 0
    for name, mutated in negative_controls(discovery):
        try:
            validate(mutated, rows, security, production, policy)
        except ValueError:
            rejected += 1
        else:
            raise SystemExit(f"FAIL: negative control admitted: {name}")
    req(rejected == 7, "negative-control count drifted")
    print("STM32U5 manufacturer base-identity discovery: PASS")
    print("base_devices=74")
    print("commercial_subfamilies_observed=12/12")
    print("exact_icpn_enumeration_complete=false")
    print("negative_controls_rejected=7")
    print("production_exact_icpn_count=2017")
    print("next_research_gate=stm32u5-exact-orderable-identity-enumeration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
