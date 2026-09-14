"""Fail-closed STM32L5 manufacturer-authoritative metadata policy.

Commercial identity/lifecycle authority remains the retained 49 exact ICPNs from the
STM32L5 manufacturer-identity discovery transaction. Metadata decoding is bounded by
official ST Ordering Information for STM32L552xx (DS12737) and STM32L562xx (DS12736).
A syntactically valid ordering code is never sufficient to expand the retained identity set.
Security/runtime capability remains independently fail-closed.
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
DEFAULT_AUTHORITY = HERE / "stm32l5-metadata-authority.json"
DISCOVERY = HERE / "stm32l5-manufacturer-identity-discovery.json"
DISCOVERY_CSV = HERE / "stm32l5-commercial-identity-discovery.csv"
SECURITY = HERE / "stm32l5-security-scope-foundation.json"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32L5"
TRANSACTION = "stm32l5-metadata-policy"
EXPECTED_BASE_COUNT = 17
EXPECTED_EXACT_COUNT = 49
EXPECTED_BASE_SET_SHA256 = "a49212731437f33674abc0c5c6a90697bbc3e377f997c618a66fb96b51632435"
EXPECTED_EXACT_SET_SHA256 = "f9a74a7badfb39f8fc52753fc3904cd63a8b3e0a2e4dcc37dee759809aaa68b1"
EXPECTED_SERIES = {"STM32L552", "STM32L562"}
DISCOVERY_COLUMNS = [
    "manufacturer", "family", "base_device", "icpn", "marketing_status",
    "source_url", "observed_at", "authority",
]
METADATA_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "package", "pin_count",
    "flash_size", "temperature_grade", "option_suffix", "source_type", "source_reference",
    "source_authority", "verification_status",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path.name}: root must be object")
    return value


def _set_sha(values: set[str] | frozenset[str]) -> str:
    payload = "\n".join(sorted(values)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_security_fence(path: Path = SECURITY) -> dict[str, Any]:
    payload = _read_json(path)
    if payload.get("transaction") != "stm32l5-security-scope-foundation" or payload.get("authority") != "research_only":
        raise AdmissionError("STM32L5 security foundation identity drifted")
    partition = payload.get("research_partition")
    if not isinstance(partition, dict):
        raise AdmissionError("STM32L5 security research partition missing")
    if partition.get("manufacturer_identity_discovery_allowed") is not True or partition.get("commercial_icpn_discovery_allowed") is not True:
        raise AdmissionError("STM32L5 security foundation no longer permits bounded identity research")
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
        if partition.get(key) is not False:
            raise AdmissionError(f"STM32L5 security fence unexpectedly open: {key}")
    return payload


def load_authority(path: Path = DEFAULT_AUTHORITY) -> dict[str, Any]:
    payload = _read_json(path)
    if (
        payload.get("schema_version") != 1
        or payload.get("transaction") != TRANSACTION
        or payload.get("authority") != "research_only"
        or payload.get("authority_version") != "stm32l5-metadata-retained49-v1"
        or payload.get("manufacturer") != MANUFACTURER
        or payload.get("family") != FAMILY
    ):
        raise AdmissionError("STM32L5 metadata authority identity/schema drifted")
    if payload.get("expected_base_devices") != EXPECTED_BASE_COUNT or payload.get("expected_exact_icpns") != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32L5 metadata authority cardinality drifted")
    if payload.get("expected_exact_icpn_set_sha256") != EXPECTED_EXACT_SET_SHA256:
        raise AdmissionError("STM32L5 metadata authority exact-set digest drifted")

    governance = payload.get("governance")
    if not isinstance(governance, dict) or not governance or set(governance.values()) != {False}:
        raise AdmissionError("STM32L5 metadata authority escaped fail-closed governance")

    grammar = payload.get("suffix_grammar")
    if not isinstance(grammar, dict):
        raise AdmissionError("STM32L5 suffix grammar missing")
    tails = grammar.get("retained_allowed_tails")
    if tails != ["", "P", "Q", "TR", "PTR", "QTR"]:
        raise AdmissionError("STM32L5 retained suffix-tail grammar drifted")
    if grammar.get("programmed_parts_wildcard_admission_authorized") is not False:
        raise AdmissionError("STM32L5 programmed-parts wildcard unexpectedly authorized")
    if grammar.get("dedicated_pinout_codes") != {"P": "external_smps", "Q": "smps_step_down"}:
        raise AdmissionError("STM32L5 dedicated-pinout authority drifted")
    if grammar.get("packing_codes") != {"TR": "tape_and_reel"}:
        raise AdmissionError("STM32L5 packing authority drifted")

    records = payload.get("records")
    if not isinstance(records, list) or len(records) != 2:
        raise AdmissionError("STM32L5 metadata authority requires exactly two series records")
    by_series: dict[str, dict[str, Any]] = {}
    expected_docs = {"STM32L552": ("DS12737", 6), "STM32L562": ("DS12736", 5)}
    for record in records:
        if not isinstance(record, dict):
            raise AdmissionError("STM32L5 metadata authority record must be object")
        series = record.get("series")
        if series not in EXPECTED_SERIES or series in by_series:
            raise AdmissionError(f"invalid/duplicate STM32L5 series authority: {series}")
        if (record.get("document_id"), record.get("revision")) != expected_docs[series] or record.get("ordering_pdf_page") != 334:
            raise AdmissionError(f"{series}: Ordering Information document binding drifted")
        url = record.get("datasheet_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/resource/en/datasheet/") or not url.endswith(".pdf"):
            raise AdmissionError(f"{series}: invalid official ST datasheet URL")
        for field in ("pin_codes", "flash", "package_codes", "temperature_codes"):
            value = record.get(field)
            if not isinstance(value, dict) or not value or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
                raise AdmissionError(f"{series}: incomplete {field} authority")
        by_series[series] = record
    if set(by_series) != EXPECTED_SERIES:
        raise AdmissionError("STM32L5 series authority coverage drifted")
    return payload


def _read_discovery_rows() -> list[dict[str, str]]:
    with DISCOVERY_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != DISCOVERY_COLUMNS:
            raise AdmissionError("STM32L5 discovery CSV schema drifted")
        return list(reader)


def build_candidate_inputs() -> list[dict[str, Any]]:
    load_security_fence()
    discovery = _read_json(DISCOVERY)
    if (
        discovery.get("transaction") != "stm32l5-manufacturer-identity-discovery"
        or discovery.get("authority") != "research_only"
        or discovery.get("manufacturer") != MANUFACTURER
        or discovery.get("series") != FAMILY
        or discovery.get("base_device_count") != EXPECTED_BASE_COUNT
        or discovery.get("exact_icpn_count") != EXPECTED_EXACT_COUNT
        or discovery.get("base_device_set_sha256") != EXPECTED_BASE_SET_SHA256
        or discovery.get("exact_icpn_set_sha256") != EXPECTED_EXACT_SET_SHA256
    ):
        raise AdmissionError("STM32L5 retained identity-discovery boundary drifted")
    result = discovery.get("result")
    if not isinstance(result, dict) or result.get("commercial_identity_clean") is not True or result.get("bounded_discovery_clean") is not True:
        raise AdmissionError("STM32L5 retained identity discovery is not clean")
    claims = discovery.get("claims")
    if not isinstance(claims, dict) or not claims or set(claims.values()) != {False}:
        raise AdmissionError("STM32L5 discovery claims escaped fail-closed state")

    rows = _read_discovery_rows()
    if len(rows) != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32L5 retained exact ICPN count drifted")

    bases: set[str] = set()
    icpns: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        base = row["base_device"]
        icpn = row["icpn"]
        series = base[:9]
        if (
            row["manufacturer"] != MANUFACTURER
            or row["family"] != FAMILY
            or row["marketing_status"] != "Active"
            or row["observed_at"] != "2026-09-14"
            or row["authority"] != "ST Quality & Reliability"
            or series not in EXPECTED_SERIES
            or len(base) != 11
            or not icpn.startswith(base)
            or icpn in icpns
        ):
            raise AdmissionError(f"invalid retained STM32L5 identity row: {icpn}")
        expected_url = f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html"
        if row["source_url"] != expected_url:
            raise AdmissionError(f"{icpn}: manufacturer source URL drifted")
        bases.add(base)
        icpns.add(icpn)
        candidates.append({
            "manufacturer": MANUFACTURER,
            "series": series,
            "base_device": base,
            "icpn": icpn,
            "identity_source": row["source_url"],
        })

    if len(bases) != EXPECTED_BASE_COUNT or len(icpns) != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32L5 retained identity cardinality drifted")
    if _set_sha(bases) != EXPECTED_BASE_SET_SHA256 or _set_sha(icpns) != EXPECTED_EXACT_SET_SHA256:
        raise AdmissionError("STM32L5 retained identity set digest drifted")
    candidates.sort(key=lambda item: (item["base_device"], item["icpn"]))
    return candidates


@lru_cache(maxsize=1)
def retained_exact_icpns() -> frozenset[str]:
    return frozenset(item["icpn"] for item in build_candidate_inputs())


def _authority_by_series(path: Path = DEFAULT_AUTHORITY) -> dict[str, dict[str, Any]]:
    payload = load_authority(path)
    return {record["series"]: record for record in payload["records"]}


def _validate_option_tail(option_suffix: str, authority_path: Path = DEFAULT_AUTHORITY) -> None:
    grammar = load_authority(authority_path)["suffix_grammar"]
    if option_suffix not in grammar["retained_allowed_tails"]:
        raise CandidateManualReview(f"suffix tail {option_suffix!r} outside retained STM32L5 authority")
    core = option_suffix
    if core.endswith("TR"):
        core = core[:-2]
    if core not in {"", *grammar["dedicated_pinout_codes"].keys()}:
        raise CandidateManualReview(f"suffix tail {option_suffix!r} has unsupported dedicated-pinout semantics")


def build_metadata_row(
    candidate: dict[str, Any],
    fields: list[str] | None = None,
    *,
    authority_path: Path = DEFAULT_AUTHORITY,
) -> dict[str, str]:
    icpn = candidate.get("icpn")
    base = candidate.get("base_device")
    series = candidate.get("series")
    if not isinstance(icpn, str) or not isinstance(base, str) or not isinstance(series, str):
        raise CandidateReject("candidate identity is incomplete")
    if icpn not in retained_exact_icpns():
        raise CandidateReject("identity is outside retained STM32L5 exact commercial scope")
    if series not in EXPECTED_SERIES or base[:9] != series or len(base) != 11 or not icpn.startswith(base):
        raise CandidateReject(f"invalid exact STM32L5 identity: {icpn}")

    authority = _authority_by_series(authority_path).get(series)
    if authority is None:
        raise CandidateManualReview(f"{series}: no official Ordering Information authority")

    pin_code, flash_code = base[-2], base[-1]
    suffix = icpn[len(base):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]

    pin_count = authority["pin_codes"].get(pin_code)
    flash_size = authority["flash"].get(flash_code)
    package = authority["package_codes"].get(package_code)
    temperature = authority["temperature_codes"].get(temperature_code)
    if pin_count is None:
        raise CandidateManualReview(f"{base}: pin code {pin_code} outside official authority")
    if flash_size is None:
        raise CandidateManualReview(f"{base}: Flash code {flash_code} outside official authority")
    if package is None:
        raise CandidateManualReview(f"{icpn}: package code {package_code} outside official authority")
    if temperature is None:
        raise CandidateManualReview(f"{icpn}: temperature code {temperature_code} outside official authority")
    _validate_option_tail(option_suffix, authority_path)

    row = {
        "manufacturer": MANUFACTURER,
        "icpn": icpn,
        "family": FAMILY,
        "series": series,
        "base_device": base,
        "package": package,
        "pin_count": pin_count,
        "flash_size": flash_size,
        "temperature_grade": temperature,
        "option_suffix": option_suffix,
        "source_type": "official_st_datasheet_ordering_information_plus_retained_exact_identity",
        "source_reference": f"{authority['document_id']} Rev {authority['revision']} p{authority['ordering_pdf_page']}",
        "source_authority": authority["datasheet_url"],
        "verification_status": "manufacturer_ordering_information_verified",
    }
    selected = list(METADATA_FIELDS) if fields is None else fields
    if any(field not in METADATA_FIELDS for field in selected):
        raise CandidateReject("unsupported STM32L5 metadata field request")
    return {field: row[field] for field in selected}
