"""STM32F4-specific commercial identity, ordering-pattern mapping, and canonical-row policy."""

from __future__ import annotations

import re
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    CandidateManualReview,
    CandidateReject,
)
from st_product_page_acquisition import AcquisitionError, validate_source_url

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32F4"
TARGET_CONFIG = "tcl/target/stm32f4x.cfg"
BASE_RE = re.compile(r"^STM32F4\d{2}([A-Z])([A-Z0-9])$")
ICPN_RE = re.compile(r"^STM32F4[0-9A-Z]+$")
FLASH_BY_CODE = {
    "B": "128 KiB",
    "C": "256 KiB",
    "D": "384 KiB",
    "E": "512 KiB",
    "G": "1024 KiB",
    "I": "2048 KiB",
}
TEMPERATURE_BY_CODE = {
    "3": "-40 to 125 C",
    "6": "-40 to 85 C",
    "7": "-40 to 105 C",
}
PACKAGE_BY_CODE = {
    "F": "WLCSP",
    "H": "UFBGA",
    "T": "LQFP",
    "U": "UFQFPN",
    "Y": "WLCSP",
}


def commercial_core(icpn: str) -> str:
    """Remove packing-only suffixes before matching OpenOCD ordering patterns."""

    for suffix in ("TR", "TT"):
        if icpn.endswith(suffix):
            return icpn[: -len(suffix)]
    return icpn


def _pattern_matches(pattern: str, value: str) -> bool:
    regex = "".join("[A-Z0-9]" if char.lower() == "x" else re.escape(char) for char in pattern)
    return re.fullmatch(regex, value) is not None


def resolve_ordering_pattern_mapping(
    icpn: str,
    catalog_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Resolve one exact ICPN against STM32F4 OpenOCD ordering-pattern rows."""

    core = commercial_core(icpn)
    matches = [
        row
        for row in catalog_rows
        if row.get("vendor") == MANUFACTURER
        and row.get("plasma_series") == FAMILY
        and row.get("identifier_kind") == "ordering_pattern"
        and isinstance(row.get("part_number"), str)
        and _pattern_matches(row["part_number"], core)
    ]
    if not matches:
        return {
            "status": "unmapped",
            "match_count": 0,
            "target_configs": [],
        }

    target_configs = sorted({row.get("target_config", "") for row in matches if row.get("target_config")})
    identifiers = sorted({row.get("part_number", "") for row in matches if row.get("part_number")})
    if len(matches) == 1 and len(target_configs) == 1:
        return {
            "status": "unique",
            "match_count": 1,
            "identifier_kind": "ordering_pattern",
            "existing_identifier": identifiers[0],
            "target_configs": target_configs,
        }
    return {
        "status": "ambiguous",
        "match_count": len(matches),
        "identifier_kinds": sorted({row.get("identifier_kind", "") for row in matches}),
        "existing_identifiers": identifiers,
        "target_configs": target_configs,
    }


def build_candidate_inputs(
    *,
    summary: dict[str, Any],
    evidence_id: str,
    catalog_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    evidence_results = summary.get("results")
    if not isinstance(evidence_results, list):
        raise AdmissionError("retained STM32F4 pilot results must be a list")

    candidates: list[dict[str, Any]] = []
    for result in evidence_results:
        if not isinstance(result, dict):
            raise AdmissionError("retained STM32F4 pilot result must be an object")
        base_device = result.get("base_device")
        evidence = result.get("evidence")
        if not isinstance(base_device, str) or not isinstance(evidence, dict):
            raise AdmissionError("retained STM32F4 pilot result lacks base/evidence")
        source_url = evidence.get("source_url")
        if not isinstance(source_url, str):
            raise AdmissionError(f"{base_device}: missing source URL")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base_device}: source URL is not approved") from exc

        raw_icpns = evidence.get("exact_icpns")
        if not isinstance(raw_icpns, list):
            raise AdmissionError(f"{base_device}: exact_icpns must be a list")
        for icpn in raw_icpns:
            if not isinstance(icpn, str):
                raise AdmissionError(f"{base_device}: exact ICPN must be a string")
            candidates.append(
                {
                    "manufacturer": MANUFACTURER,
                    "base_device": base_device,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": evidence_id,
                        "source_url": source_url,
                        "rendered_dom_sha256": evidence.get("rendered_dom_sha256"),
                        "evidence_section_sha256": evidence.get("evidence_section_sha256"),
                    },
                    "base_mapping": resolve_ordering_pattern_mapping(icpn, catalog_rows),
                }
            )
    return candidates


def _package_and_pins(pin_code: str, package_code: str) -> tuple[str, str]:
    package = PACKAGE_BY_CODE.get(package_code)
    if package is None:
        raise CandidateReject(f"unsupported STM32F4 package code: {package_code}")

    direct = {
        ("C", "U"): "48",
        ("C", "F"): "49",
        ("C", "Y"): "49",
        ("V", "T"): "100",
        ("Z", "T"): "144",
        ("Z", "Y"): "143",
    }
    pins = direct.get((pin_code, package_code))
    if pins is None:
        raise CandidateManualReview(
            f"unsupported STM32F4 pin/package combination: {pin_code}/{package_code}"
        )
    return package, pins


def build_canonical_row(candidate: dict[str, Any], fields: list[str]) -> dict[str, str]:
    icpn = candidate.get("icpn")
    base_device = candidate.get("base_device")
    evidence = candidate.get("authoritative_evidence")
    mapping = candidate.get("base_mapping")
    if not isinstance(icpn, str) or not isinstance(base_device, str):
        raise CandidateReject("invalid STM32F4 commercial identity")
    if not isinstance(evidence, dict):
        raise CandidateReject("candidate lacks authoritative evidence")
    if not isinstance(mapping, dict):
        raise CandidateManualReview("candidate lacks programming mapping")

    base_match = BASE_RE.fullmatch(base_device)
    if base_match is None:
        raise CandidateReject(f"unsupported STM32F4 base-device identity: {base_device}")
    if not ICPN_RE.fullmatch(icpn) or not icpn.startswith(base_device) or icpn == base_device:
        raise CandidateReject(f"invalid exact commercial ICPN: {icpn}")

    suffix = icpn[len(base_device) :]
    if len(suffix) < 2:
        raise CandidateReject(f"ICPN lacks package/temperature codes: {icpn}")
    package_code, temperature_code = suffix[0], suffix[1]
    if temperature_code not in TEMPERATURE_BY_CODE:
        raise CandidateReject(f"unsupported STM32F4 temperature code: {icpn}")

    target_configs = mapping.get("target_configs")
    if mapping.get("status") != "unique" or not isinstance(target_configs, list) or len(target_configs) != 1:
        raise CandidateManualReview(f"ICPN lacks one unique OpenOCD ordering-pattern mapping: {icpn}")
    if target_configs[0] != TARGET_CONFIG:
        raise CandidateManualReview(f"unexpected STM32F4 OpenOCD target mapping: {icpn}")
    existing_identifier = mapping.get("existing_identifier")
    if not isinstance(existing_identifier, str) or not existing_identifier:
        raise CandidateManualReview(f"ICPN lacks mapped ordering-pattern identifier: {icpn}")

    source_url = evidence.get("source_url")
    evidence_id = evidence.get("evidence_id")
    if not isinstance(source_url, str) or not source_url:
        raise CandidateReject(f"{base_device}: missing authoritative source URL")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise CandidateReject(f"{base_device}: missing evidence_id")

    pin_code, flash_code = base_match.groups()
    flash_size = FLASH_BY_CODE.get(flash_code)
    if flash_size is None:
        raise CandidateManualReview(f"unsupported STM32F4 flash-size code: {base_device}")
    package, pin_count = _package_and_pins(pin_code, package_code)

    values = {
        "manufacturer": MANUFACTURER,
        "icpn": icpn,
        "family": FAMILY,
        "series": base_device[:9],
        "base_device": base_device,
        "package": package,
        "pin_count": pin_count,
        "flash_size": flash_size,
        "temperature_grade": TEMPERATURE_BY_CODE[temperature_code],
        "option_suffix": suffix[2:],
        "cmsis_device_name": "",
        "existing_identifier": existing_identifier,
        "existing_identifier_kind": "ordering_pattern",
        "mapping_status": "deterministic_ordering_pattern",
        "openocd_target_config": target_configs[0],
        "source_type": "official_st_product_page_retained_browser_evidence",
        "source_reference": f"{source_url}#plasma-evidence={evidence_id}",
        "source_authority": "STMicroelectronics official",
        "verification_status": "verified_direct_st_retained_browser_exact_icpn",
    }
    if set(values) != set(fields):
        raise AdmissionError("canonical CSV schema is not supported by the STM32F4 policy")
    return {field: values[field] for field in fields}
