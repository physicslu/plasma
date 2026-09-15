#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "stm32u3-commercial-identity-discovery.csv"
BASELINE_PATH = ROOT / "stm32u3-manufacturer-identity-discovery.json"
SECURITY_PATH = ROOT / "stm32u3-security-scope-foundation.json"

BASE_RE = re.compile(r"^STM32U(?:375|385|3B5|3C5)[A-Z]{2}$")
ICPN_RE = re.compile(r"^STM32U(?:375|385|3B5|3C5)[A-Z0-9]+$")
EXPECTED_COLUMNS = [
    "manufacturer",
    "family",
    "base_device",
    "icpn",
    "marketing_status",
    "source_url",
    "observed_at",
    "authority",
]
ALLOWED_STATUS = {"Active", "Evaluation"}
EXPECTED_CANDIDATE_SUBFAMILIES = {
    "STM32U335", "STM32U345", "STM32U356", "STM32U366",
    "STM32U375", "STM32U385", "STM32U3B5", "STM32U3C5",
}
EXPECTED_COMMERCIAL_SUBFAMILIES = {"STM32U375", "STM32U385", "STM32U3B5", "STM32U3C5"}
EXPECTED_UNOBSERVED_SUBFAMILIES = {"STM32U335", "STM32U345", "STM32U356", "STM32U366"}


def digest(values: list[str]) -> str:
    payload = "\n".join(sorted(values)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def read_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        require(reader.fieldnames == EXPECTED_COLUMNS, "STM32U3 discovery CSV schema drift")
        return list(reader)


def commercial_subfamily(base: str) -> str:
    for prefix in ("STM32U375", "STM32U385", "STM32U3B5", "STM32U3C5"):
        if base.startswith(prefix):
            return prefix
    raise SystemExit(f"unrecognized STM32U3 commercial base device: {base}")


def validate_rows(rows: list[dict[str, str]], baseline: dict) -> None:
    require(len(rows) == baseline.get("exact_icpn_count") == 106, "STM32U3 exact ICPN count drift")
    require(baseline.get("production_exact_icpn_count") == 1862, "Production exact ICPN count drift")

    bases = sorted({row["base_device"] for row in rows})
    icpns = [row["icpn"] for row in rows]
    require(len(bases) == baseline.get("base_device_count") == 33, "STM32U3 base-device count drift")
    require(len(icpns) == len(set(icpns)), "duplicate STM32U3 exact ICPN")
    require(bases == baseline.get("base_devices"), "STM32U3 base-device set drift")
    require(digest(bases) == baseline.get("base_device_set_sha256"), "STM32U3 base-device digest drift")
    require(digest(icpns) == baseline.get("exact_icpn_set_sha256"), "STM32U3 exact ICPN digest drift")

    status_counts = Counter(row["marketing_status"] for row in rows)
    require(dict(sorted(status_counts.items())) == baseline.get("marketing_status_counts"), "marketing-status snapshot drift")
    require(status_counts == Counter({"Active": 100, "Evaluation": 6}), "unexpected STM32U3 marketing-status counts")

    observed_subfamilies: set[str] = set()
    for row in rows:
        base = row["base_device"]
        icpn = row["icpn"]
        require(row["manufacturer"] == "STMicroelectronics", f"manufacturer drift: {icpn}")
        require(row["family"] == "STM32U3", f"family drift: {icpn}")
        require(bool(BASE_RE.fullmatch(base)), f"invalid STM32U3 base device: {base}")
        require(bool(ICPN_RE.fullmatch(icpn)), f"invalid STM32U3 exact ICPN: {icpn}")
        require(icpn.startswith(base), f"base-device/ICPN mismatch: {base} -> {icpn}")
        require(row["marketing_status"] in ALLOWED_STATUS, f"unrecognized marketing status: {icpn}")
        require(row["observed_at"] == baseline.get("observed_at") == "2026-09-15", f"observation date drift: {icpn}")
        require(row["authority"] == "ST Quality & Reliability", f"authority drift: {icpn}")
        expected_url = f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html"
        require(row["source_url"] == expected_url, f"source URL drift: {icpn}")
        observed_subfamilies.add(commercial_subfamily(base))

    require(observed_subfamilies == EXPECTED_COMMERCIAL_SUBFAMILIES, "commercial subfamily observation drift")
    require(set(baseline.get("commercial_subfamilies_observed", [])) == EXPECTED_COMMERCIAL_SUBFAMILIES, "baseline commercial subfamilies drift")
    require(set(baseline.get("candidate_subfamilies", [])) == EXPECTED_CANDIDATE_SUBFAMILIES, "candidate subfamily scope drift")
    require(set(baseline.get("candidate_subfamilies_without_current_commercial_identity_observation", [])) == EXPECTED_UNOBSERVED_SUBFAMILIES, "bounded no-observation set drift")
    require(baseline.get("absence_semantics") == "no_current_manufacturer_commercial_identity_observed_in_bounded_selector_snapshot", "absence semantics drift")

    result = baseline.get("result", {})
    require(result.get("commercial_identity_clean") is True, "commercial identity result not clean")
    require(result.get("bounded_discovery_clean") is True, "bounded discovery result not clean")
    require(result.get("all_observed_marketing_status_active") is False, "Evaluation identities must not be rewritten as Active")
    require(result.get("evaluation_identities_retained_as_observed_identity_evidence") is True, "Evaluation identity evidence retention drift")
    require(result.get("synthesized_exact_icpns") == 0, "synthetic exact ICPNs are forbidden")
    require(result.get("manual_intervention") == 0, "manual intervention count drift")


def validate_security_fence(baseline: dict, security: dict) -> None:
    require(baseline.get("schema_version") == 1, "schema version drift")
    require(baseline.get("transaction") == "stm32u3-manufacturer-identity-discovery", "transaction drift")
    require(baseline.get("authority") == "research_only", "STM32U3 identity discovery must remain research-only")
    require(baseline.get("parent_security_scope") == SECURITY_PATH.name, "security-scope binding drift")
    require(baseline.get("series") == "STM32U3", "series drift")
    require(baseline.get("manufacturer") == "STMicroelectronics", "manufacturer authority drift")
    require(baseline.get("identity_authority") == "ST Quality & Reliability exact Part Number rows", "identity authority drift")
    require(baseline.get("family_product_selector_url") == "https://www.st.com/en/microcontrollers-microprocessors/stm32u3-series/products.html", "product selector URL drift")
    require(baseline.get("next_research_gate") == "stm32u3-metadata-policy", "next research gate drift")

    require(security.get("authority") == "research_only", "security foundation authority drift")
    require(security.get("series") == "STM32U3", "security foundation family drift")
    require(security.get("status") == "eligible_for_identity_discovery_under_security_fence", "security foundation no longer permits bounded identity discovery")
    require(security.get("next_research_gate") == "stm32u3-manufacturer-identity-discovery", "security foundation transaction continuity drift")
    require(set(security.get("subfamily_scope", [])) == EXPECTED_CANDIDATE_SUBFAMILIES, "security foundation candidate scope drift")
    require(security.get("exact_icpn_count") == 1862, "security foundation Production count drift")

    partition = security.get("research_partition", {})
    require(partition.get("manufacturer_identity_discovery_allowed") is True, "security fence no longer permits identity discovery")
    require(partition.get("commercial_icpn_discovery_allowed") is True, "security fence no longer permits commercial discovery")
    for key in (
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
    ):
        require(partition.get(key) is False, f"security fence unexpectedly open: {key}")

    claims = baseline.get("claims", {})
    for key in (
        "production_admission_authorized",
        "lifecycle_permanent",
        "unobserved_subfamily_unsupported",
        "security_semantics_supported",
        "option_byte_semantics_supported",
        "oem_key_semantics_supported",
        "flash_geometry_validated",
        "programming_algorithm_equivalence",
        "runtime_programming_supported",
        "hil_validated",
    ):
        require(claims.get(key) is False, f"forbidden capability claim enabled: {key}")


def expect_rejected(name: str, rows: list[dict[str, str]], baseline: dict, security: dict) -> None:
    try:
        validate_rows(rows, baseline)
        validate_security_fence(baseline, security)
    except SystemExit:
        return
    raise SystemExit(f"negative control failed: {name}")


def negative_controls(rows: list[dict[str, str]], baseline: dict, security: dict) -> int:
    rejected = 0

    duplicate = copy.deepcopy(rows)
    duplicate[-1]["icpn"] = duplicate[0]["icpn"]
    expect_rejected("duplicate exact ICPN admitted", duplicate, copy.deepcopy(baseline), copy.deepcopy(security)); rejected += 1

    bad_status = copy.deepcopy(rows)
    bad_status[0]["marketing_status"] = "NRND"
    expect_rejected("unknown marketing status admitted", bad_status, copy.deepcopy(baseline), copy.deepcopy(security)); rejected += 1

    synthesized = copy.deepcopy(rows)
    synthesized[0]["base_device"] = "STM32U335AA"
    synthesized[0]["icpn"] = "STM32U335AAT6"
    synthesized[0]["source_url"] = "https://www.st.com/en/microcontrollers-microprocessors/stm32u335aa.html"
    expect_rejected("unobserved U335 exact identity synthesized", synthesized, copy.deepcopy(baseline), copy.deepcopy(security)); rejected += 1

    bad_source = copy.deepcopy(rows)
    bad_source[0]["source_url"] = "https://example.com/stm32u3"
    expect_rejected("non-ST identity source admitted", bad_source, copy.deepcopy(baseline), copy.deepcopy(security)); rejected += 1

    production = copy.deepcopy(baseline)
    production["claims"]["production_admission_authorized"] = True
    expect_rejected("Production admission inferred from identity evidence", copy.deepcopy(rows), production, copy.deepcopy(security)); rejected += 1

    count_drift = copy.deepcopy(baseline)
    count_drift["production_exact_icpn_count"] = 1968
    expect_rejected("Production exact ICPN count drift admitted", copy.deepcopy(rows), count_drift, copy.deepcopy(security)); rejected += 1

    return rejected


def main() -> int:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    security = json.loads(SECURITY_PATH.read_text(encoding="utf-8"))
    rows = read_rows()
    validate_rows(rows, baseline)
    validate_security_fence(baseline, security)
    rejected = negative_controls(rows, baseline, security)
    require(rejected == 6, "negative-control rejection count drift")
    print(json.dumps({
        "base_devices": baseline["base_device_count"],
        "research_exact_icpns": baseline["exact_icpn_count"],
        "active": baseline["marketing_status_counts"]["Active"],
        "evaluation": baseline["marketing_status_counts"]["Evaluation"],
        "negative_controls_rejected": rejected,
        "production_exact_icpn_count": baseline["production_exact_icpn_count"],
        "production_admission_authorized": baseline["claims"]["production_admission_authorized"],
    }, sort_keys=True))
    print("STM32U3 manufacturer identity discovery: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
