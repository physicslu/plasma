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
EXACT_SNAPSHOT = HERE / "stm32u5-exact-orderable-identity-enumeration.json"
SECURITY = HERE / "stm32u5-security-scope-foundation.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
POLICY = ROOT / "docs/architecture/icpn-catalog-admission-policy.json"

EXPECTED_PRODUCTION = 2017
EXPECTED_EXACT = 266
EXPECTED_EXACT_HASH = "ea5e3edc302a022281618ecfa73af8ac6109ad287dcf36e6f1175d20f567caf3"
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


def validate(discovery: dict, rows: list[dict[str, str]], exact_snapshot: dict, security: dict, production: dict, policy: dict) -> None:
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
    req(exact.get("complete") is True, "exact ICPN enumeration completion regressed")
    req(exact.get("observed_at") == "2026-09-16", "exact ICPN observation date drifted")
    req(exact.get("identity_authority") == "ST Quality & Reliability exact Part Number rows", "exact ICPN authority drifted")
    req(exact.get("snapshot") == EXACT_SNAPSHOT.name, "exact ICPN snapshot binding drifted")
    req(exact.get("exact_icpn_count") == EXPECTED_EXACT, "exact ICPN count drifted")
    req(exact.get("exact_icpn_set_sha256") == EXPECTED_EXACT_HASH, "exact ICPN digest drifted")
    req(exact.get("synthesized_exact_icpns") == 0, "synthetic exact ICPNs admitted")

    req(exact_snapshot.get("transaction") == "stm32u5-exact-orderable-identity-enumeration", "exact snapshot transaction drifted")
    req(exact_snapshot.get("authority") == "research_only", "exact snapshot authority drifted")
    req(exact_snapshot.get("exact_icpn_count") == EXPECTED_EXACT, "exact snapshot count drifted")
    req(exact_snapshot.get("exact_icpn_set_sha256") == EXPECTED_EXACT_HASH, "exact snapshot digest drifted")
    req(exact_snapshot.get("base_device_count") == EXPECTED_BASE_COUNT, "exact snapshot Base Device count drifted")
    req(exact_snapshot.get("result", {}).get("synthesized_exact_icpns") == 0, "exact snapshot synthesized ICPN drifted")

    result = discovery.get("result")
    req(isinstance(result, dict) and result.get("bounded_discovery_clean") is True, "bounded discovery not clean")
    req(result.get("all_12_upstream_subfamilies_have_current_base_device_observation") is True, "12/12 coverage claim missing")
    req(result.get("exact_icpn_enumeration_clean") is True, "exact ICPN enumeration result not clean")
    req(result.get("synthesized_base_devices") == 0, "synthesized base device admitted")
    req(result.get("synthesized_exact_icpns") == 0, "synthesized exact ICPN admitted")

    claims = discovery.get("claims")
    req(isinstance(claims, dict), "claims missing")
    req(claims.get("catalog_admission_blocked_by_hil") is False, "HIL coupling reintroduced")
    req(claims.get("exact_icpn_enumeration_complete") is True, "exact ICPN completion claim missing")
    for key in ("physical_validation_claimed", "security_semantics_supported", "runtime_programming_supported", "debug_attach_supported", "hil_validated"):
        req(claims.get(key) is False, f"{key} must remain false")

    req(discovery.get("next_research_gate") == "stm32u5-metadata-policy", "next gate drifted")


def expect_rejected(name: str, discovery: dict, rows: list[dict[str, str]], exact_snapshot: dict, security: dict, production: dict, policy: dict) -> None:
    try:
        validate(discovery, rows, exact_snapshot, security, production, policy)
    except ValueError:
        return
    raise SystemExit(f"FAIL: negative control admitted: {name}")


def negative_controls(discovery: dict, rows: list[dict[str, str]], exact_snapshot: dict, security: dict, production: dict, policy: dict) -> int:
    rejected = 0
    wrong_count = copy.deepcopy(discovery); wrong_count["base_device_count"] = 73
    expect_rejected("wrong Base Device count", wrong_count, rows, exact_snapshot, security, production, policy); rejected += 1

    duplicate = copy.deepcopy(discovery); duplicate["base_devices"][1] = duplicate["base_devices"][0]
    expect_rejected("duplicate Base Device", duplicate, rows, exact_snapshot, security, production, policy); rejected += 1

    missing = copy.deepcopy(discovery); missing["commercial_subfamilies_observed"].remove("STM32U5G9")
    expect_rejected("missing subfamily", missing, rows, exact_snapshot, security, production, policy); rejected += 1

    incomplete = copy.deepcopy(discovery); incomplete["exact_orderable_identity_enumeration"]["complete"] = False; incomplete["claims"]["exact_icpn_enumeration_complete"] = False
    expect_rejected("exact enumeration completion regression", incomplete, rows, exact_snapshot, security, production, policy); rejected += 1

    exact_count = copy.deepcopy(discovery); exact_count["exact_orderable_identity_enumeration"]["exact_icpn_count"] = 265
    expect_rejected("exact count drift", exact_count, rows, exact_snapshot, security, production, policy); rejected += 1

    hil = copy.deepcopy(discovery); hil["claims"]["catalog_admission_blocked_by_hil"] = True
    expect_rejected("HIL coupling", hil, rows, exact_snapshot, security, production, policy); rejected += 1

    runtime = copy.deepcopy(discovery); runtime["claims"]["runtime_programming_supported"] = True
    expect_rejected("runtime claim", runtime, rows, exact_snapshot, security, production, policy); rejected += 1

    count = copy.deepcopy(discovery); count["production_exact_icpn_count"] = EXPECTED_PRODUCTION + 1
    expect_rejected("Production drift", count, rows, exact_snapshot, security, production, policy); rejected += 1
    return rejected


def main() -> int:
    discovery = load_json(DISCOVERY)
    rows = load_rows()
    exact_snapshot = load_json(EXACT_SNAPSHOT)
    security = load_json(SECURITY)
    production = load_json(PRODUCTION)
    policy = load_json(POLICY)
    validate(discovery, rows, exact_snapshot, security, production, policy)
    rejected = negative_controls(discovery, rows, exact_snapshot, security, production, policy)
    req(rejected == 8, "negative-control count drifted")
    print("STM32U5 manufacturer identity discovery: PASS")
    print("base_devices=74")
    print("commercial_subfamilies_observed=12/12")
    print("exact_icpn_enumeration_complete=true")
    print("exact_icpns=266")
    print("negative_controls_rejected=8")
    print("production_exact_icpn_count=2017")
    print("next_research_gate=stm32u5-metadata-policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
