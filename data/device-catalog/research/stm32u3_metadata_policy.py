"""Fail-closed STM32U3 manufacturer-authoritative metadata policy.

Exact commercial identity remains the retained 106 ICPNs from manufacturer identity
discovery. Official ST Ordering Information decodes metadata only; syntax never expands
identity scope and does not authorize Production, security mutation, or runtime support.
"""
from __future__ import annotations

import csv
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject

HERE = Path(__file__).resolve().parent
DEFAULT_AUTHORITY = HERE / "stm32u3-metadata-authority.json"
DISCOVERY = HERE / "stm32u3-manufacturer-identity-discovery.json"
DISCOVERY_CSV = HERE / "stm32u3-commercial-identity-discovery.csv"
SECURITY = HERE / "stm32u3-security-scope-foundation.json"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32U3"
TRANSACTION = "stm32u3-metadata-policy"
EXPECTED_BASE_COUNT = 33
EXPECTED_EXACT_COUNT = 106
EXPECTED_BASE_SET_SHA256 = "33229786ea06e3d78a15a68fab98ff2fe45707e397d364c0f2d2fe75d5e69320"
EXPECTED_EXACT_SET_SHA256 = "6ff4f01a009e28aff1a6ebf3f74544c973ce9e2a229bc72f4574f71c47ea4918"
EXPECTED_SERIES = {"STM32U375", "STM32U385", "STM32U3B5", "STM32U3C5"}
DISCOVERY_COLUMNS = [
    "manufacturer", "family", "base_device", "icpn", "marketing_status",
    "source_url", "observed_at", "authority",
]
METADATA_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "marketing_status_observed",
    "package", "pin_count", "flash_size", "temperature_grade", "dedicated_pinout",
    "packing", "option_suffix", "source_type", "source_reference", "source_authority",
    "verification_status",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path.name}: root must be object")
    return value


def _set_sha(values: set[str] | frozenset[str]) -> str:
    payload = "\n".join(sorted(values)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _series_for_base(base: str) -> str | None:
    return next((series for series in sorted(EXPECTED_SERIES, key=len, reverse=True) if base.startswith(series)), None)


def load_security_fence(path: Path = SECURITY) -> dict[str, Any]:
    payload = _read_json(path)
    if payload.get("transaction") != "stm32u3-security-scope-foundation" or payload.get("authority") != "research_only":
        raise AdmissionError("STM32U3 security foundation identity drifted")
    partition = payload.get("research_partition")
    if not isinstance(partition, dict):
        raise AdmissionError("STM32U3 security research partition missing")
    for key in ("manufacturer_identity_discovery_allowed", "commercial_icpn_discovery_allowed"):
        if partition.get(key) is not True:
            raise AdmissionError(f"STM32U3 security foundation no longer permits {key}")
    for key in (
        "production_admission_allowed", "security_semantics_supported", "option_byte_writes_allowed",
        "oem_key_provisioning_allowed", "oem_unlock_execution_allowed", "rdp_regression_allowed",
        "mass_erase_allowed", "flash_geometry_validated", "programming_algorithm_equivalence",
        "runtime_programming_supported", "debug_attach_supported", "hil_validated",
    ):
        if partition.get(key) is not False:
            raise AdmissionError(f"STM32U3 security fence unexpectedly open: {key}")
    return payload


def load_authority(path: Path = DEFAULT_AUTHORITY) -> dict[str, Any]:
    payload = _read_json(path)
    if (
        payload.get("schema_version") != 1
        or payload.get("transaction") != TRANSACTION
        or payload.get("authority") != "research_only"
        or payload.get("authority_version") != "stm32u3-metadata-retained106-v1"
        or payload.get("manufacturer") != MANUFACTURER
        or payload.get("family") != FAMILY
    ):
        raise AdmissionError("STM32U3 metadata authority identity/schema drifted")
    if payload.get("expected_base_devices") != EXPECTED_BASE_COUNT or payload.get("expected_exact_icpns") != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32U3 metadata authority cardinality drifted")
    if payload.get("expected_base_device_set_sha256") != EXPECTED_BASE_SET_SHA256 or payload.get("expected_exact_icpn_set_sha256") != EXPECTED_EXACT_SET_SHA256:
        raise AdmissionError("STM32U3 metadata authority retained-set digest drifted")
    governance = payload.get("governance")
    if not isinstance(governance, dict) or not governance or set(governance.values()) != {False}:
        raise AdmissionError("STM32U3 metadata authority escaped fail-closed governance")
    grammar = payload.get("suffix_grammar")
    if not isinstance(grammar, dict) or grammar.get("packing_codes") != {"TR": "tape_and_reel"}:
        raise AdmissionError("STM32U3 suffix/packing grammar drifted")
    if grammar.get("programmed_parts_wildcard_admission_authorized") is not False:
        raise AdmissionError("STM32U3 programmed-parts wildcard unexpectedly authorized")

    expected_docs = {
        "STM32U375": ("DS14861", 3),
        "STM32U385": ("DS14830", 3),
        "STM32U3B5": ("DS15097", 1),
        "STM32U3C5": ("DS15096", 1),
    }
    records = payload.get("records")
    if not isinstance(records, list) or len(records) != 4:
        raise AdmissionError("STM32U3 metadata authority requires four commercial-series records")
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise AdmissionError("STM32U3 authority record must be object")
        series = record.get("series")
        if series not in EXPECTED_SERIES or series in seen:
            raise AdmissionError(f"invalid/duplicate STM32U3 series authority: {series}")
        seen.add(series)
        if (record.get("document_id"), record.get("revision")) != expected_docs[series]:
            raise AdmissionError(f"{series}: datasheet authority drifted")
        url = record.get("datasheet_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/resource/en/datasheet/") or not url.endswith(".pdf"):
            raise AdmissionError(f"{series}: invalid official ST datasheet URL")
        for field in ("pin_codes", "flash", "package_codes", "temperature_codes", "dedicated_pinout_codes"):
            value = record.get(field)
            if not isinstance(value, dict):
                raise AdmissionError(f"{series}: invalid {field} authority")
        tails = record.get("retained_allowed_tails")
        if not isinstance(tails, list) or "" not in tails:
            raise AdmissionError(f"{series}: retained tail allowlist missing")
    if seen != EXPECTED_SERIES:
        raise AdmissionError("STM32U3 metadata series coverage drifted")
    return payload


def _read_discovery_rows() -> list[dict[str, str]]:
    with DISCOVERY_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != DISCOVERY_COLUMNS:
            raise AdmissionError("STM32U3 discovery CSV schema drifted")
        return list(reader)


def build_candidate_inputs() -> list[dict[str, Any]]:
    load_security_fence()
    discovery = _read_json(DISCOVERY)
    if (
        discovery.get("transaction") != "stm32u3-manufacturer-identity-discovery"
        or discovery.get("authority") != "research_only"
        or discovery.get("manufacturer") != MANUFACTURER
        or discovery.get("series") != FAMILY
        or discovery.get("base_device_count") != EXPECTED_BASE_COUNT
        or discovery.get("exact_icpn_count") != EXPECTED_EXACT_COUNT
        or discovery.get("base_device_set_sha256") != EXPECTED_BASE_SET_SHA256
        or discovery.get("exact_icpn_set_sha256") != EXPECTED_EXACT_SET_SHA256
        or discovery.get("production_exact_icpn_count") != 1862
    ):
        raise AdmissionError("STM32U3 retained identity boundary drifted")
    if discovery.get("marketing_status_counts") != {"Active": 100, "Evaluation": 6}:
        raise AdmissionError("STM32U3 observed marketing-status distribution drifted")
    result = discovery.get("result")
    if not isinstance(result, dict) or result.get("commercial_identity_clean") is not True or result.get("bounded_discovery_clean") is not True or result.get("synthesized_exact_icpns") != 0:
        raise AdmissionError("STM32U3 manufacturer identity discovery is not clean")
    claims = discovery.get("claims")
    if not isinstance(claims, dict) or not claims or set(claims.values()) != {False}:
        raise AdmissionError("STM32U3 identity claims escaped fail-closed state")

    rows = _read_discovery_rows()
    if len(rows) != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32U3 retained exact ICPN count drifted")
    bases: set[str] = set()
    icpns: set[str] = set()
    status_counts = {"Active": 0, "Evaluation": 0}
    candidates: list[dict[str, Any]] = []
    for row in rows:
        base, icpn = row["base_device"], row["icpn"]
        series = _series_for_base(base)
        status = row["marketing_status"]
        if (
            row["manufacturer"] != MANUFACTURER or row["family"] != FAMILY
            or status not in status_counts or row["observed_at"] != "2026-09-15"
            or row["authority"] != "ST Quality & Reliability" or series is None
            or not icpn.startswith(base) or icpn in icpns
        ):
            raise AdmissionError(f"invalid retained STM32U3 identity row: {icpn}")
        expected_url = f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html"
        if row["source_url"] != expected_url:
            raise AdmissionError(f"{icpn}: manufacturer source URL drifted")
        bases.add(base)
        icpns.add(icpn)
        status_counts[status] += 1
        candidates.append({
            "manufacturer": MANUFACTURER,
            "series": series,
            "base_device": base,
            "icpn": icpn,
            "marketing_status": status,
            "identity_source": row["source_url"],
        })
    if status_counts != {"Active": 100, "Evaluation": 6}:
        raise AdmissionError("STM32U3 identity row status counts drifted")
    if len(bases) != EXPECTED_BASE_COUNT or _set_sha(bases) != EXPECTED_BASE_SET_SHA256:
        raise AdmissionError("STM32U3 retained Base Device set drifted")
    if len(icpns) != EXPECTED_EXACT_COUNT or _set_sha(icpns) != EXPECTED_EXACT_SET_SHA256:
        raise AdmissionError("STM32U3 retained exact ICPN set drifted")
    return sorted(candidates, key=lambda item: (item["base_device"], item["icpn"]))


@lru_cache(maxsize=1)
def retained_exact_icpns() -> frozenset[str]:
    return frozenset(item["icpn"] for item in build_candidate_inputs())


def _authority_by_series(path: Path = DEFAULT_AUTHORITY) -> dict[str, dict[str, Any]]:
    return {record["series"]: record for record in load_authority(path)["records"]}


def _decode_tail(option_suffix: str, authority: dict[str, Any]) -> tuple[str, str]:
    if option_suffix not in authority["retained_allowed_tails"]:
        raise CandidateManualReview(f"suffix tail {option_suffix!r} outside retained STM32U3 authority")
    core = option_suffix
    packing = "tray_or_unspecified"
    if core.endswith("TR"):
        packing = "tape_and_reel"
        core = core[:-2]
    if core == "":
        dedicated = "standard"
    else:
        dedicated = authority["dedicated_pinout_codes"].get(core)
        if dedicated is None:
            raise CandidateManualReview(f"suffix tail {option_suffix!r} has unsupported dedicated-pinout semantics")
    return dedicated, packing


def build_metadata_row(candidate: dict[str, Any], fields: list[str] | None = None, *, authority_path: Path = DEFAULT_AUTHORITY) -> dict[str, str]:
    icpn, base, series = candidate.get("icpn"), candidate.get("base_device"), candidate.get("series")
    status = candidate.get("marketing_status")
    if not all(isinstance(v, str) for v in (icpn, base, series, status)):
        raise CandidateReject("candidate identity is incomplete")
    if icpn not in retained_exact_icpns():
        raise CandidateReject("identity is outside retained STM32U3 exact commercial scope")
    if series not in EXPECTED_SERIES or _series_for_base(base) != series or not icpn.startswith(base):
        raise CandidateReject(f"invalid exact STM32U3 identity: {icpn}")
    if status not in {"Active", "Evaluation"}:
        raise CandidateReject(f"{icpn}: unsupported observed marketing status")

    authority = _authority_by_series(authority_path).get(series)
    if authority is None:
        raise CandidateManualReview(f"{series}: no official Ordering Information authority")
    pin_code, flash_code = base[-2], base[-1]
    suffix = icpn[len(base):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    package = authority["package_codes"].get(package_code)
    temperature = authority["temperature_codes"].get(temperature_code)
    flash_size = authority["flash"].get(flash_code)
    pin_count = authority.get("pin_package_overrides", {}).get(f"{pin_code}:{package_code}", authority["pin_codes"].get(pin_code))
    if pin_count is None:
        raise CandidateManualReview(f"{base}: pin/package code outside official authority")
    if flash_size is None:
        raise CandidateManualReview(f"{base}: Flash code {flash_code} outside official authority")
    if package is None:
        raise CandidateManualReview(f"{icpn}: package code {package_code} outside official authority")
    if temperature is None:
        raise CandidateManualReview(f"{icpn}: temperature code {temperature_code} outside official authority")
    dedicated, packing = _decode_tail(option_suffix, authority)

    row = {
        "manufacturer": MANUFACTURER,
        "icpn": icpn,
        "family": FAMILY,
        "series": series,
        "base_device": base,
        "marketing_status_observed": status,
        "package": package,
        "pin_count": pin_count,
        "flash_size": flash_size,
        "temperature_grade": temperature,
        "dedicated_pinout": dedicated,
        "packing": packing,
        "option_suffix": option_suffix,
        "source_type": "official_st_datasheet_ordering_information_plus_retained_exact_identity",
        "source_reference": f"{authority['document_id']} Rev {authority['revision']} Ordering Information",
        "source_authority": authority["datasheet_url"],
        "verification_status": "manufacturer_ordering_information_verified",
    }
    selected = list(METADATA_FIELDS) if fields is None else fields
    if any(field not in METADATA_FIELDS for field in selected):
        raise CandidateReject("unsupported STM32U3 metadata field request")
    return {field: row[field] for field in selected}
