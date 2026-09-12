"""Bounded STM32L0 Phase L0.3 commercial metadata policy.

Identity/lifecycle authority remains retained L0.2 official-ST evidence.
Metadata authority is official ST datasheet Ordering Information. Candidates
outside explicit ordering-authority coverage fail closed to manual review.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject
from st_product_page_acquisition import AcquisitionError, validate_source_url
from validate_stm32l0_phase_l0_2_retained_evidence import EVIDENCE as L0_2_EVIDENCE, EXPECTED_EVIDENCE_ID, main as validate_retained

HERE = Path(__file__).resolve().parent
DEFAULT_ORDERING_AUTHORITY = HERE / "stm32l0-phase-l0.3-ordering-authority.json"
L0_2_SUMMARY = L0_2_EVIDENCE / "live-summary.json"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32L0"
PHASE = "L0.3"
PARSER_PROFILE = "stm32l0_l0_2_dual_surface_v1"
EXPECTED_ACTIVE_CANDIDATE_COUNT = 360
EXPECTED_TARGET_COUNT = 99
EXPECTED_EXCLUDED_COUNT = 10
EXPECTED_SERIES = {
    "STM32L010", "STM32L011", "STM32L021", "STM32L031", "STM32L041",
    "STM32L051", "STM32L052", "STM32L053", "STM32L062", "STM32L063",
    "STM32L071", "STM32L072", "STM32L073", "STM32L081", "STM32L082", "STM32L083",
}
ICPN_RE = re.compile(r"^STM32L0[0-9A-Z]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
METADATA_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "package",
    "pin_count", "flash_size", "temperature_grade", "option_suffix",
    "source_type", "source_reference", "source_authority", "verification_status",
)
PIN_COUNT = {"D":"14", "F":"20", "E":"25", "G":"28", "K":"32", "T":"36", "C":"48", "R":"64", "V":"100"}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path.name}: root must be object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CandidateReject(f"candidate lacks valid {label}")
    return value


def load_ordering_authority(path: Path = DEFAULT_ORDERING_AUTHORITY) -> dict[str, dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("schema_version") != 1 or payload.get("phase") != PHASE:
        raise AdmissionError("unsupported STM32L0 ordering-authority schema/phase")
    if payload.get("family") != FAMILY or payload.get("manufacturer") != MANUFACTURER:
        raise AdmissionError("STM32L0 ordering-authority identity drifted")
    if payload.get("authority_version") != "stm32l0-l0.3-retained360-v1":
        raise AdmissionError("STM32L0 ordering-authority version drifted")
    governance = payload.get("governance")
    if not isinstance(governance, dict) or not governance or set(governance.values()) != {False}:
        raise AdmissionError("STM32L0 ordering authority escaped fail-closed governance")
    common_temp = payload.get("common_temperature")
    common_pkg = payload.get("common_package")
    if not isinstance(common_temp, dict) or set(common_temp) != {"3","6","7"}:
        raise AdmissionError("STM32L0 common temperature authority drifted")
    if not isinstance(common_pkg, dict):
        raise AdmissionError("STM32L0 common package authority missing")
    records = payload.get("records")
    if not isinstance(records, list) or len(records) != 16:
        raise AdmissionError("STM32L0 ordering authority requires 16 records")
    by_series: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise AdmissionError("ordering-authority record must be object")
        series = record.get("series")
        if series not in EXPECTED_SERIES or series in by_series:
            raise AdmissionError(f"invalid/duplicate ordering series {series}")
        url = record.get("datasheet_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/resource/en/datasheet/") or not url.endswith(".pdf"):
            raise AdmissionError(f"{series}: invalid ST datasheet URL")
        if not isinstance(record.get("revision"), int) or record.get("ordering_section") != 8 or not isinstance(record.get("pdf_page"), int):
            raise AdmissionError(f"{series}: incomplete datasheet binding")
        for key in ("pin_codes", "flash", "package_codes", "temperature_codes", "option_suffixes"):
            if not record.get(key):
                raise AdmissionError(f"{series}: missing {key} authority")
        if set(record["temperature_codes"]) - set(common_temp):
            raise AdmissionError(f"{series}: unknown temperature code")
        if set(record["package_codes"]) - set(common_pkg):
            raise AdmissionError(f"{series}: unknown package code")
        by_series[series] = record
    if set(by_series) != EXPECTED_SERIES:
        raise AdmissionError("STM32L0 ordering-authority series set drifted")
    l010 = by_series["STM32L010"]
    if l010.get("coverage") != "explicit_base_only" or l010.get("covered_base_devices") != ["STM32L010C6"]:
        raise AdmissionError("STM32L010 authority must remain explicit-base-only")
    if "D" in l010["option_suffixes"] or "DTR" in l010["option_suffixes"]:
        raise AdmissionError("STM32L010 must not inherit general D/BOR option")
    if "S" not in by_series["STM32L031"]["option_suffixes"]:
        raise AdmissionError("STM32L031 S option authority missing")
    return by_series


def _base_covered(base: str, record: dict[str, Any]) -> bool:
    covered = record.get("covered_base_devices")
    if isinstance(covered, list):
        return base in covered
    return record.get("coverage") in {
        "series_x3_x4", "series_x4", "series_x4_x6", "series_x6", "series_x6_x8",
        "series_x8", "series_x8_xB_xZ",
    }


def build_candidate_inputs() -> list[dict[str, Any]]:
    if validate_retained() != 0:
        raise AdmissionError("L0.2 retained evidence validator failed")
    summary = _read_json(L0_2_SUMMARY)
    if summary.get("discovery_id") != "stm32l0-l0.2-official-st-commercial-discovery-v1":
        raise AdmissionError("L0.2 discovery identity drifted")
    if summary.get("family") != FAMILY or summary.get("phase") != "L0.2":
        raise AdmissionError("L0.2 summary scope drifted")
    if (
        summary.get("bounded_discovery_clean") is not True
        or summary.get("commercial_identity_clean") is not True
        or summary.get("commercial_identity_verified_targets") != EXPECTED_TARGET_COUNT
        or summary.get("active_exact_icpn_candidates") != EXPECTED_ACTIVE_CANDIDATE_COUNT
        or summary.get("excluded_non_active_part_numbers") != EXPECTED_EXCLUDED_COUNT
        or summary.get("identity_manual_intervention_required") != 0
    ):
        raise AdmissionError("L0.2 clean commercial boundary drifted")
    claims = summary.get("claims")
    if not isinstance(claims, dict) or not claims or set(claims.values()) != {False}:
        raise AdmissionError("L0.2 claims escaped fail-closed state")
    results = summary.get("results")
    if not isinstance(results, list) or len(results) != EXPECTED_TARGET_COUNT:
        raise AdmissionError("L0.2 result count drifted")
    candidates: list[dict[str, Any]] = []
    bases: set[str] = set()
    icpns: set[str] = set()
    excluded: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            raise AdmissionError("invalid L0.2 result")
        base = result.get("base_device")
        source_url = result.get("source_url")
        evidence = result.get("evidence")
        if not isinstance(base, str) or base in bases:
            raise AdmissionError(f"invalid/duplicate L0.2 Base Device {base}")
        bases.add(base)
        if result.get("disposition") != "active_candidates" or result.get("commercial_identity_status") != "verified_active":
            raise AdmissionError(f"{base}: L0.3 accepts only retained Active identity state")
        if result.get("manual_intervention_required") is not False:
            raise AdmissionError(f"{base}: retained manual state drifted")
        if not isinstance(source_url, str):
            raise AdmissionError(f"{base}: retained source URL missing")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base}: retained product URL not approved") from exc
        if not isinstance(evidence, dict) or evidence.get("parser_profile") != PARSER_PROFILE or evidence.get("parser_version") != 2:
            raise AdmissionError(f"{base}: retained evidence profile drifted")
        rendered = _require_sha256(evidence.get("rendered_dom_sha256"), "rendered DOM digest")
        section = _require_sha256(evidence.get("evidence_section_sha256"), "evidence-section digest")
        non_active = evidence.get("excluded_non_active_part_numbers")
        if not isinstance(non_active, list):
            raise AdmissionError(f"{base}: missing excluded list")
        for item in non_active:
            if not isinstance(item, dict) or not isinstance(item.get("icpn"), str):
                raise AdmissionError(f"{base}: malformed excluded item")
            excluded.add(item["icpn"])
        exact = evidence.get("exact_icpns")
        if not isinstance(exact, list) or not exact:
            raise AdmissionError(f"{base}: missing exact ICPNs")
        for icpn in exact:
            if not isinstance(icpn, str) or ICPN_RE.fullmatch(icpn) is None or not icpn.startswith(base) or icpn in icpns:
                raise AdmissionError(f"{base}: invalid/duplicate exact ICPN {icpn}")
            icpns.add(icpn)
            candidates.append({
                "manufacturer": MANUFACTURER,
                "base_device": base,
                "icpn": icpn,
                "authoritative_evidence": {
                    "evidence_id": EXPECTED_EVIDENCE_ID,
                    "source_url": source_url,
                    "rendered_dom_sha256": rendered,
                    "evidence_section_sha256": section,
                    "evidence_profile": PARSER_PROFILE,
                },
            })
    if len(bases) != EXPECTED_TARGET_COUNT or len(icpns) != EXPECTED_ACTIVE_CANDIDATE_COUNT or len(excluded) != EXPECTED_EXCLUDED_COUNT:
        raise AdmissionError("L0.2 retained identity cardinality drifted")
    return candidates


@lru_cache(maxsize=1)
def retained_exact_icpns() -> frozenset[str]:
    return frozenset(item["icpn"] for item in build_candidate_inputs())


def build_metadata_row(candidate: dict[str, Any], fields: list[str] | None = None, *, authority_path: Path = DEFAULT_ORDERING_AUTHORITY) -> dict[str, str]:
    icpn = candidate.get("icpn")
    base = candidate.get("base_device")
    evidence = candidate.get("authoritative_evidence")
    if not isinstance(icpn, str) or not isinstance(base, str) or icpn not in retained_exact_icpns():
        raise CandidateReject("identity is outside retained L0.2 Active scope")
    if not icpn.startswith(base) or icpn == base:
        raise CandidateReject(f"invalid exact STM32L0 ICPN: {icpn}")
    if not isinstance(evidence, dict) or evidence.get("evidence_id") != EXPECTED_EVIDENCE_ID or evidence.get("evidence_profile") != PARSER_PROFILE:
        raise CandidateReject(f"{base}: retained identity evidence missing/drifted")
    _require_sha256(evidence.get("rendered_dom_sha256"), "rendered DOM digest")
    _require_sha256(evidence.get("evidence_section_sha256"), "evidence-section digest")

    series = base[:9]
    authorities = load_ordering_authority(authority_path)
    authority = authorities.get(series)
    if authority is None:
        raise CandidateManualReview(f"{base}: no official Ordering Information authority")
    if not _base_covered(base, authority):
        raise CandidateManualReview(f"{base}: retained Ordering Information authority does not explicitly cover this Base Device")

    pin_code, flash_code = base[-2], base[-1]
    suffix = icpn[len(base):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    if pin_code not in authority["pin_codes"]:
        raise CandidateManualReview(f"{base}: pin code {pin_code} outside bounded authority")
    flash_size = authority["flash"].get(flash_code)
    if flash_size is None:
        raise CandidateManualReview(f"{base}: Flash code {flash_code} outside bounded authority")
    if package_code not in authority["package_codes"]:
        raise CandidateManualReview(f"{icpn}: package code {package_code} outside bounded authority")
    if temperature_code not in authority["temperature_codes"]:
        raise CandidateManualReview(f"{icpn}: temperature code {temperature_code} outside bounded authority")
    if option_suffix not in authority["option_suffixes"]:
        raise CandidateReject(f"{icpn}: option suffix {option_suffix!r} outside bounded authority")

    payload = _read_json(authority_path)
    package = payload["common_package"][package_code]
    temperature = payload["common_temperature"][temperature_code]
    pin_count = PIN_COUNT.get(pin_code)
    if pin_count is None:
        raise CandidateManualReview(f"{base}: unresolved pin-count code {pin_code}")
    if pin_code == "C" and package_code == "Y":
        pin_count = "49"

    values = {
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
        "source_type": "manufacturer_ordering_information",
        "source_reference": authority["datasheet_url"],
        "source_authority": "STMicroelectronics official",
        "verification_status": "verified_st_datasheet_ordering_information_plus_retained_exact_identity",
    }
    requested = list(METADATA_FIELDS) if fields is None else fields
    if tuple(requested) != METADATA_FIELDS:
        raise AdmissionError("metadata schema is not supported by STM32L0 L0.3 policy")
    return {field: values[field] for field in requested}
