"""Bounded STM32F3 commercial identity and canonical-row policy.

This family adapter owns STM32F3 ordering-code semantics for evidence-backed
candidates.  It does not authorize canonical or Production writes.
"""

from __future__ import annotations

import re
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    CandidateManualReview,
    CandidateReject,
)
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32f3_dual_surface_evidence import EVIDENCE_SURFACE
from stm32f3_phase4_4b_discovery import resolve_mapping

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32F3"
TARGET_CONFIG = "tcl/target/stm32f3x.cfg"
EVIDENCE_PROFILE = "stm32f3_dual_surface_v1"
SUPPORTED_BASE_DEVICES = frozenset(
    {
        "STM32F301C6",
        "STM32F302C6",
        "STM32F303C6",
        "STM32F373C8",
        "STM32F334C4",
        "STM32F318C8",
    }
)
BASE_RE = re.compile(r"^STM32F3\d{2}([A-Z])([A-Z0-9])$")
ICPN_RE = re.compile(r"^STM32F3[0-9A-Z]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FLASH_BY_CODE = {
    "4": "16 KiB",
    "6": "32 KiB",
    "8": "64 KiB",
}
TEMPERATURE_BY_CODE = {
    "6": "-40 to 85 C",
    "7": "-40 to 105 C",
}
PACKAGE_BY_CODE = {
    "T": "LQFP",
    "Y": "WLCSP",
}
PINS_BY_COMBINATION = {
    ("C", "T"): "48",
    ("C", "Y"): "49",
}
OPTION_SUFFIXES = frozenset({"", "TR"})
CANONICAL_FIELDS = (
    "manufacturer",
    "icpn",
    "family",
    "series",
    "base_device",
    "package",
    "pin_count",
    "flash_size",
    "temperature_grade",
    "option_suffix",
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
    "source_type",
    "source_reference",
    "source_authority",
    "verification_status",
)


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CandidateReject(f"candidate lacks valid {label}")
    return value


def _package_and_pins(pin_code: str, package_code: str) -> tuple[str, str]:
    package = PACKAGE_BY_CODE.get(package_code)
    if package is None:
        raise CandidateReject(f"unsupported STM32F3 package code: {package_code}")
    pins = PINS_BY_COMBINATION.get((pin_code, package_code))
    if pins is None:
        raise CandidateManualReview(
            f"unsupported STM32F3 pin/package combination: {pin_code}/{package_code}"
        )
    return package, pins


def build_candidate_inputs(
    *,
    summary: dict[str, Any],
    evidence_id: str,
    catalog_rows: list[dict[str, str]],
    supported_base_devices: frozenset[str] = SUPPORTED_BASE_DEVICES,
    expected_candidate_count: int = 10,
) -> list[dict[str, Any]]:
    """Normalize retained Phase 4.4B evidence into deterministic policy inputs."""

    if not evidence_id:
        raise AdmissionError("STM32F3 retained evidence requires evidence_id")
    results = summary.get("results")
    if not isinstance(results, list):
        raise AdmissionError("retained STM32F3 results must be a list")

    candidates: list[dict[str, Any]] = []
    observed_bases: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            raise AdmissionError("retained STM32F3 result must be an object")
        base_device = result.get("base_device")
        evidence = result.get("evidence")
        if not isinstance(base_device, str) or not isinstance(evidence, dict):
            raise AdmissionError("retained STM32F3 result lacks base/evidence")
        if base_device not in supported_base_devices:
            raise AdmissionError(f"{base_device}: outside bounded STM32F3 policy")
        if result.get("acquisition_status") != "success":
            raise AdmissionError(f"{base_device}: retained acquisition was not successful")
        if evidence.get("parser_profile") != EVIDENCE_PROFILE:
            raise AdmissionError(f"{base_device}: retained evidence profile drifted")
        if evidence.get("evidence_surface") != EVIDENCE_SURFACE:
            raise AdmissionError(f"{base_device}: retained evidence surface drifted")
        excluded = evidence.get("excluded_non_active_part_numbers")
        if excluded != []:
            raise AdmissionError(f"{base_device}: bounded policy requires zero lifecycle exclusions")
        observed_bases.append(base_device)

        source_url = evidence.get("source_url")
        if not isinstance(source_url, str):
            raise AdmissionError(f"{base_device}: missing source URL")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base_device}: source URL is not approved") from exc
        if source_url != result.get("source_url") or not source_url.endswith(
            f"/{base_device.lower()}.html"
        ):
            raise AdmissionError(f"{base_device}: source URL binding drifted")

        raw_icpns = evidence.get("exact_icpns")
        records = evidence.get("part_number_records")
        if not isinstance(raw_icpns, list) or not raw_icpns:
            raise AdmissionError(f"{base_device}: exact_icpns must be a non-empty list")
        if not isinstance(records, list) or len(records) != len(raw_icpns):
            raise AdmissionError(f"{base_device}: lifecycle record count drifted")
        if [item.get("icpn") for item in records if isinstance(item, dict)] != raw_icpns:
            raise AdmissionError(f"{base_device}: identity/lifecycle join drifted")
        if any(
            not isinstance(item, dict)
            or item.get("active") is not True
            or not isinstance(item.get("marketing_status"), str)
            or not item["marketing_status"].startswith("Active")
            for item in records
        ):
            raise AdmissionError(f"{base_device}: non-Active lifecycle leaked into policy")

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
                        "evidence_profile": EVIDENCE_PROFILE,
                    },
                    "base_mapping": resolve_mapping(icpn, catalog_rows),
                }
            )

    if set(observed_bases) != set(supported_base_devices) or len(observed_bases) != len(
        supported_base_devices
    ):
        raise AdmissionError("retained STM32F3 Base Device scope drifted")
    if len(candidates) != expected_candidate_count:
        raise AdmissionError(
            f"bounded STM32F3 policy requires exactly {expected_candidate_count} "
            f"retained candidates, got {len(candidates)}"
        )
    return candidates


def build_canonical_row(candidate: dict[str, Any], fields: list[str]) -> dict[str, str]:
    """Apply bounded STM32F3 metadata and mapping policy to one candidate."""

    icpn = candidate.get("icpn")
    base_device = candidate.get("base_device")
    evidence = candidate.get("authoritative_evidence")
    mapping = candidate.get("base_mapping")
    if not isinstance(icpn, str) or not isinstance(base_device, str):
        raise CandidateReject("invalid STM32F3 commercial identity")
    if not isinstance(evidence, dict):
        raise CandidateReject("candidate lacks authoritative evidence")
    if not isinstance(mapping, dict):
        raise CandidateManualReview("candidate lacks programming mapping")

    base_match = BASE_RE.fullmatch(base_device)
    if base_match is None:
        raise CandidateReject(f"unsupported STM32F3 base-device identity: {base_device}")
    if base_device not in SUPPORTED_BASE_DEVICES:
        raise CandidateReject(f"{base_device}: outside bounded STM32F3 policy")
    if not ICPN_RE.fullmatch(icpn) or not icpn.startswith(base_device) or icpn == base_device:
        raise CandidateReject(f"invalid exact commercial ICPN: {icpn}")

    suffix = icpn[len(base_device) :]
    if len(suffix) < 2:
        raise CandidateReject(f"ICPN lacks package/temperature codes: {icpn}")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    if temperature_code not in TEMPERATURE_BY_CODE:
        raise CandidateReject(f"unsupported STM32F3 temperature code: {temperature_code}")
    if option_suffix not in OPTION_SUFFIXES:
        raise CandidateReject(f"unsupported STM32F3 option suffix: {option_suffix}")

    pin_code, flash_code = base_match.groups()
    flash_size = FLASH_BY_CODE.get(flash_code)
    if flash_size is None:
        raise CandidateManualReview(f"unsupported STM32F3 flash-size code: {flash_code}")
    package, pin_count = _package_and_pins(pin_code, package_code)

    target_configs = mapping.get("target_configs")
    if mapping.get("status") != "unique" or not isinstance(target_configs, list) or len(
        target_configs
    ) != 1:
        raise CandidateManualReview(
            f"ICPN lacks one unique OpenOCD ordering-pattern mapping: {icpn}"
        )
    if target_configs[0] != TARGET_CONFIG:
        raise CandidateManualReview(f"unexpected STM32F3 OpenOCD target mapping: {icpn}")
    if mapping.get("identifier_kind") != "ordering_pattern":
        raise CandidateManualReview(f"unexpected STM32F3 identifier kind: {icpn}")
    existing_identifier = mapping.get("existing_identifier")
    if not isinstance(existing_identifier, str) or not existing_identifier:
        raise CandidateManualReview(f"ICPN lacks mapped ordering-pattern identifier: {icpn}")

    source_url = evidence.get("source_url")
    evidence_id = evidence.get("evidence_id")
    if (
        not isinstance(source_url, str)
        or not isinstance(evidence_id, str)
        or not evidence_id
        or evidence.get("evidence_profile") != EVIDENCE_PROFILE
    ):
        raise CandidateReject(f"{base_device}: missing authoritative evidence identity")
    try:
        validate_source_url(source_url)
    except AcquisitionError as exc:
        raise CandidateReject(f"{base_device}: source URL is not approved") from exc
    if not source_url.endswith(f"/{base_device.lower()}.html"):
        raise CandidateReject(f"{base_device}: source URL slug mismatch")
    _require_sha256(evidence.get("rendered_dom_sha256"), "rendered DOM digest")
    _require_sha256(evidence.get("evidence_section_sha256"), "evidence-section digest")

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
        "option_suffix": option_suffix,
        "cmsis_device_name": "",
        "existing_identifier": existing_identifier,
        "existing_identifier_kind": "ordering_pattern",
        "mapping_status": "deterministic_ordering_pattern",
        "openocd_target_config": target_configs[0],
        "source_type": "official_st_product_page_retained_browser_dual_surface_evidence",
        "source_reference": f"{source_url}#plasma-evidence={evidence_id}",
        "source_authority": "STMicroelectronics official",
        "verification_status": "verified_direct_st_retained_browser_exact_icpn",
    }
    if tuple(fields) != CANONICAL_FIELDS:
        raise AdmissionError("canonical CSV schema is not supported by the STM32F3 policy")
    return {field: values[field] for field in fields}
