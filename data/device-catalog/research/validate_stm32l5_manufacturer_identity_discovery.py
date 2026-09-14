#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "stm32l5-commercial-identity-discovery.csv"
BASELINE_PATH = ROOT / "stm32l5-manufacturer-identity-discovery.json"
SECURITY_PATH = ROOT / "stm32l5-security-scope-foundation.json"

BASE_RE = re.compile(r"^STM32L(?:552|562)[A-Z]{2}$")
ICPN_RE = re.compile(r"^STM32L(?:552|562)[A-Z0-9]+$")
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


def digest(values: list[str]) -> str:
    payload = "\n".join(sorted(values)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def read_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        require(reader.fieldnames == EXPECTED_COLUMNS, "STM32L5 discovery CSV schema drift")
        return list(reader)


def validate_rows(rows: list[dict[str, str]], baseline: dict) -> None:
    require(len(rows) == baseline["exact_icpn_count"] == 49, "STM32L5 exact ICPN count drift")

    bases = sorted({row["base_device"] for row in rows})
    icpns = [row["icpn"] for row in rows]
    require(len(bases) == baseline["base_device_count"] == 17, "STM32L5 base-device count drift")
    require(len(icpns) == len(set(icpns)), "duplicate STM32L5 exact ICPN")
    require(bases == baseline["base_devices"], "STM32L5 base-device set drift")
    require(digest(bases) == baseline["base_device_set_sha256"], "STM32L5 base-device digest drift")
    require(digest(icpns) == baseline["exact_icpn_set_sha256"], "STM32L5 exact ICPN digest drift")

    for row in rows:
        base = row["base_device"]
        icpn = row["icpn"]
        require(row["manufacturer"] == "STMicroelectronics", f"manufacturer drift: {icpn}")
        require(row["family"] == "STM32L5", f"family drift: {icpn}")
        require(bool(BASE_RE.fullmatch(base)), f"invalid STM32L5 base device: {base}")
        require(bool(ICPN_RE.fullmatch(icpn)), f"invalid STM32L5 exact ICPN: {icpn}")
        require(icpn.startswith(base), f"base-device/ICPN mismatch: {base} -> {icpn}")
        require(row["marketing_status"] == "Active", f"non-Active retained identity: {icpn}")
        require(row["observed_at"] == baseline["observed_at"] == "2026-09-14", f"observation date drift: {icpn}")
        require(row["authority"] == "ST Quality & Reliability", f"authority drift: {icpn}")
        expected_url = f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html"
        require(row["source_url"] == expected_url, f"source URL drift: {icpn}")


def validate_security_fence(baseline: dict, security: dict) -> None:
    require(baseline["authority"] == "research_only", "STM32L5 discovery authority must remain research-only")
    claims = baseline["claims"]
    for key in (
        "production_admission_authorized",
        "lifecycle_permanent",
        "security_semantics_supported",
        "option_byte_semantics_supported",
        "flash_geometry_validated",
        "programming_algorithm_equivalence",
        "runtime_programming_supported",
        "hil_validated",
    ):
        require(claims.get(key) is False, f"STM32L5 forbidden claim enabled: {key}")

    partition = security["research_partition"]
    require(partition["manufacturer_identity_discovery_allowed"] is True, "security foundation no longer permits identity discovery")
    require(partition["commercial_icpn_discovery_allowed"] is True, "security foundation no longer permits commercial discovery")
    for key in (
        "production_admission_allowed",
        "security_semantics_supported",
        "option_byte_writes_allowed",
        "rdp_regression_allowed",
        "mass_erase_allowed",
        "flash_geometry_validated",
        "programming_algorithm_equivalence",
        "runtime_programming_supported",
        "hil_validated",
    ):
        require(partition.get(key) is False, f"security fence unexpectedly open: {key}")


def negative_controls(rows: list[dict[str, str]], baseline: dict) -> None:
    duplicate = [dict(r) for r in rows]
    duplicate[-1]["icpn"] = duplicate[0]["icpn"]
    try:
        validate_rows(duplicate, baseline)
    except SystemExit:
        pass
    else:
        raise SystemExit("negative control failed: duplicate exact ICPN admitted")

    bad_status = [dict(r) for r in rows]
    bad_status[0]["marketing_status"] = "NRND"
    try:
        validate_rows(bad_status, baseline)
    except SystemExit:
        pass
    else:
        raise SystemExit("negative control failed: non-Active identity admitted")


def main() -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    security = json.loads(SECURITY_PATH.read_text(encoding="utf-8"))
    rows = read_rows()
    validate_rows(rows, baseline)
    validate_security_fence(baseline, security)
    negative_controls(rows, baseline)
    print(json.dumps({
        "base_devices": baseline["base_device_count"],
        "exact_icpns": baseline["exact_icpn_count"],
        "observed_at": baseline["observed_at"],
        "commercial_identity_clean": baseline["result"]["commercial_identity_clean"],
        "bounded_discovery_clean": baseline["result"]["bounded_discovery_clean"],
        "production_admission_authorized": baseline["claims"]["production_admission_authorized"],
    }, sort_keys=True))
    print("STM32L5 manufacturer identity discovery: PASS")


if __name__ == "__main__":
    main()
