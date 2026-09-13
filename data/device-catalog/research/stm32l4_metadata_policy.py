"""Fail-closed STM32L4 Phase L4.3 manufacturer-authoritative metadata policy.

Commercial identity/lifecycle authority remains the immutable L4.2 official-ST
exact-set evidence. Metadata authority is official ST datasheet Ordering
Information. The policy decodes only the 446 retained Active exact ICPNs and
never expands identity scope.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject
from validate_stm32l4_phase_l4_2_retained_evidence import EVIDENCE as L4_2_EVIDENCE, main as validate_retained

HERE = Path(__file__).resolve().parent
DEFAULT_ORDERING_AUTHORITY = HERE / "stm32l4-phase-l4.3-ordering-authority.json"
L4_2_SUMMARY = L4_2_EVIDENCE / "live-summary.json"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32L4"
PHASE = "L4.3"
EXPECTED_ACTIVE_CANDIDATE_COUNT = 446
EXPECTED_BASE_DEVICE_COUNT = 138
EXPECTED_EXCLUDED_COUNT = 5
EXPECTED_UNIQUE_DATASHEETS = 20
EXPECTED_SERIES = {
    "STM32L412", "STM32L422", "STM32L431", "STM32L432", "STM32L433", "STM32L442",
    "STM32L443", "STM32L451", "STM32L452", "STM32L462", "STM32L471", "STM32L475",
    "STM32L476", "STM32L486", "STM32L496", "STM32L4A6", "STM32L4P5", "STM32L4Q5",
    "STM32L4R5", "STM32L4R7", "STM32L4R9", "STM32L4S5", "STM32L4S7", "STM32L4S9",
}
ICPN_RE = re.compile(r"^STM32L4[0-9A-Z]+$")
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


def load_ordering_authority(path: Path = DEFAULT_ORDERING_AUTHORITY) -> dict[str, dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("schema_version") != 1 or payload.get("phase") != PHASE:
        raise AdmissionError("unsupported STM32L4 L4.3 ordering-authority schema/phase")
    if payload.get("family") != FAMILY or payload.get("manufacturer") != MANUFACTURER:
        raise AdmissionError("STM32L4 ordering-authority identity drifted")
    if payload.get("authority_version") != "stm32l4-l4.3-retained446-v1":
        raise AdmissionError("STM32L4 ordering-authority version drifted")
    governance = payload.get("governance")
    if not isinstance(governance, dict) or not governance or set(governance.values()) != {False}:
        raise AdmissionError("STM32L4 ordering authority escaped fail-closed governance")
    grammars = payload.get("grammars")
    if not isinstance(grammars, dict) or not grammars:
        raise AdmissionError("STM32L4 suffix grammar authority missing")
    for grammar_id, grammar in grammars.items():
        if not isinstance(grammar, dict):
            raise AdmissionError(f"{grammar_id}: malformed suffix grammar")
        tails = grammar.get("allowed_tails")
        if not isinstance(tails, list) or not tails or len(tails) != len(set(tails)) or any(not isinstance(x, str) for x in tails):
            raise AdmissionError(f"{grammar_id}: invalid allowed suffix tails")
    records = payload.get("records")
    if not isinstance(records, list) or len(records) != 24:
        raise AdmissionError("STM32L4 ordering authority requires 24 series records")
    by_series: dict[str, dict[str, Any]] = {}
    docs: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise AdmissionError("ordering-authority record must be object")
        series = record.get("series")
        if series not in EXPECTED_SERIES or series in by_series:
            raise AdmissionError(f"invalid/duplicate STM32L4 series {series}")
        url = record.get("datasheet_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/resource/en/datasheet/") or not url.endswith(".pdf"):
            raise AdmissionError(f"{series}: invalid official ST datasheet URL")
        if not isinstance(record.get("document_id"), str) or not isinstance(record.get("revision"), int) or not isinstance(record.get("ordering_pdf_page"), int):
            raise AdmissionError(f"{series}: incomplete document binding")
        docs.add(record["document_id"])
        for field in ("pin_codes", "flash", "package_codes", "temperature_codes"):
            value = record.get(field)
            if not isinstance(value, dict) or not value or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
                raise AdmissionError(f"{series}: missing {field} authority")
        grammar_id = record.get("suffix_grammar")
        if grammar_id not in grammars:
            raise AdmissionError(f"{series}: unknown suffix grammar {grammar_id}")
        by_series[series] = record
    if set(by_series) != EXPECTED_SERIES or len(docs) != EXPECTED_UNIQUE_DATASHEETS:
        raise AdmissionError("STM32L4 Ordering Information coverage drifted")
    return by_series


def _retained_summary() -> dict[str, Any]:
    if validate_retained() != 0:
        raise AdmissionError("L4.2 retained evidence validator failed")
    summary = _read_json(L4_2_SUMMARY)
    expected = {
        "phase": "L4.2", "family": FAMILY, "base_device_count": EXPECTED_BASE_DEVICE_COUNT,
        "active_exact_icpn_candidates": EXPECTED_ACTIVE_CANDIDATE_COUNT,
        "excluded_non_active_part_numbers": EXPECTED_EXCLUDED_COUNT,
        "commercial_identity_verified_targets": EXPECTED_BASE_DEVICE_COUNT,
        "identity_manual_intervention_required": 0, "acquisition_failure": 0,
        "bounded_discovery_clean": True, "commercial_identity_clean": True,
    }
    if any(summary.get(k) != v for k, v in expected.items()):
        raise AdmissionError("L4.2 retained commercial boundary drifted")
    claims = summary.get("claims")
    if not isinstance(claims, dict) or not claims or set(claims.values()) != {False}:
        raise AdmissionError("L4.2 claims escaped fail-closed state")
    return summary


def build_candidate_inputs() -> list[dict[str, Any]]:
    summary = _retained_summary()
    results = summary.get("results")
    if not isinstance(results, list) or len(results) != EXPECTED_BASE_DEVICE_COUNT:
        raise AdmissionError("L4.2 retained result count drifted")
    candidates: list[dict[str, Any]] = []
    bases: set[str] = set()
    icpns: set[str] = set()
    excluded: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            raise AdmissionError("malformed L4.2 result")
        base = result.get("base_device")
        series = result.get("subfamily")
        evidence = result.get("evidence")
        source_url = result.get("source_url")
        if not isinstance(base, str) or base in bases or not isinstance(series, str) or series not in EXPECTED_SERIES:
            raise AdmissionError(f"invalid/duplicate L4.2 Base Device {base}")
        bases.add(base)
        if not base.startswith(series) or result.get("disposition") != "active_candidates" or result.get("commercial_identity_status") != "verified_active":
            raise AdmissionError(f"{base}: L4.3 accepts only retained Active identity state")
        if result.get("manual_intervention_required") is not False:
            raise AdmissionError(f"{base}: retained manual state drifted")
        if not isinstance(source_url, str) or not source_url.startswith("https://www.st.com/en/microcontrollers-microprocessors/"):
            raise AdmissionError(f"{base}: official ST product URL missing")
        if not isinstance(evidence, dict) or evidence.get("parser_profile") != "stm32l4_l4_2_dual_surface_v1" or evidence.get("parser_version") != 2:
            raise AdmissionError(f"{base}: retained evidence profile drifted")
        exact = evidence.get("exact_icpns")
        non_active = evidence.get("excluded_non_active_part_numbers")
        if not isinstance(exact, list) or not exact or not isinstance(non_active, list):
            raise AdmissionError(f"{base}: exact lifecycle disposition missing")
        for item in non_active:
            if not isinstance(item, dict) or not isinstance(item.get("icpn"), str):
                raise AdmissionError(f"{base}: malformed excluded exact Part Number")
            excluded.add(item["icpn"])
        for icpn in exact:
            if not isinstance(icpn, str) or ICPN_RE.fullmatch(icpn) is None or not icpn.startswith(base) or icpn in icpns:
                raise AdmissionError(f"{base}: invalid/duplicate exact ICPN {icpn}")
            icpns.add(icpn)
            candidates.append({"manufacturer": MANUFACTURER, "series": series, "base_device": base, "icpn": icpn, "identity_source": source_url})
    if len(bases) != EXPECTED_BASE_DEVICE_COUNT or len(icpns) != EXPECTED_ACTIVE_CANDIDATE_COUNT or len(excluded) != EXPECTED_EXCLUDED_COUNT:
        raise AdmissionError("L4.2 retained identity cardinality drifted")
    if icpns & excluded:
        raise AdmissionError("Active and excluded exact sets collide")
    return candidates


@lru_cache(maxsize=1)
def retained_exact_icpns() -> frozenset[str]:
    return frozenset(item["icpn"] for item in build_candidate_inputs())


def _resolve_pin_count(series: str, pin_value: str, package_code: str) -> str:
    if series == "STM32L476" and pin_value == "100/99":
        return "99" if package_code == "Y" else "100"
    return pin_value


def build_metadata_row(candidate: dict[str, Any], fields: list[str] | None = None, *, authority_path: Path = DEFAULT_ORDERING_AUTHORITY) -> dict[str, str]:
    icpn = candidate.get("icpn")
    base = candidate.get("base_device")
    series = candidate.get("series")
    if not isinstance(icpn, str) or not isinstance(base, str) or not isinstance(series, str):
        raise CandidateReject("candidate identity is incomplete")
    if icpn not in retained_exact_icpns():
        raise CandidateReject("identity is outside retained L4.2 Active scope")
    if not icpn.startswith(base) or base[:9] != series or len(base) < 11:
        raise CandidateReject(f"invalid exact STM32L4 identity: {icpn}")
    authorities = load_ordering_authority(authority_path)
    authority = authorities.get(series)
    if authority is None:
        raise CandidateManualReview(f"{series}: no official Ordering Information authority")
    pin_code, flash_code = base[-2], base[-1]
    suffix = icpn[len(base):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    pin_value = authority["pin_codes"].get(pin_code)
    flash_size = authority["flash"].get(flash_code)
    package = authority["package_codes"].get(package_code)
    temperature = authority["temperature_codes"].get(temperature_code)
    if pin_value is None:
        raise CandidateManualReview(f"{base}: pin code {pin_code} outside official authority")
    if flash_size is None:
        raise CandidateManualReview(f"{base}: Flash code {flash_code} outside official authority")
    if package is None:
        raise CandidateManualReview(f"{icpn}: package code {package_code} outside official authority")
    if temperature is None:
        raise CandidateManualReview(f"{icpn}: temperature code {temperature_code} outside official authority")
    payload = _read_json(authority_path)
    grammar = payload["grammars"][authority["suffix_grammar"]]
    if option_suffix not in grammar["allowed_tails"]:
        raise CandidateManualReview(f"{icpn}: suffix tail {option_suffix!r} outside official {authority['suffix_grammar']} grammar")
    row = {
        "manufacturer": MANUFACTURER,
        "icpn": icpn,
        "family": FAMILY,
        "series": series,
        "base_device": base,
        "package": package,
        "pin_count": _resolve_pin_count(series, pin_value, package_code),
        "flash_size": flash_size,
        "temperature_grade": temperature,
        "option_suffix": option_suffix,
        "source_type": "official_st_datasheet_ordering_information",
        "source_reference": f"{authority['document_id']} Rev {authority['revision']} p{authority['ordering_pdf_page']}",
        "source_authority": authority["datasheet_url"],
        "verification_status": "manufacturer_ordering_information_verified",
    }
    selected = list(METADATA_FIELDS) if fields is None else fields
    if any(field not in METADATA_FIELDS for field in selected):
        raise CandidateReject("unsupported metadata field request")
    return {field: row[field] for field in selected}
