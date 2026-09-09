"""Bounded STM32F0 commercial metadata policy.

This family adapter owns ordering-code metadata semantics for the retained
Phase 4.5B exact commercial identities. It intentionally does not evaluate or
gate on OpenOCD routing; capability mapping belongs to the later admission gate.
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
from stm32f0_dual_surface_evidence import PARSER_PROFILE

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32F0"
SUPPORTED_BASE_DEVICES = frozenset(
    {
        "STM32F030C6",
        "STM32F031C4",
        "STM32F038C6",
        "STM32F042C4",
        "STM32F048C6",
        "STM32F051C4",
        "STM32F058C8",
        "STM32F070C6",
        "STM32F071C8",
        "STM32F072C8",
        "STM32F078CB",
        "STM32F091CB",
        "STM32F098CC",
    }
)
BASE_RE = re.compile(r"^STM32F0\d{2}([A-Z])([A-Z0-9])$")
ICPN_RE = re.compile(r"^STM32F0[0-9A-Z]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FLASH_BY_CODE = {
    "4": "16 KiB",
    "6": "32 KiB",
    "8": "64 KiB",
    "B": "128 KiB",
    "C": "256 KiB",
}
TEMPERATURE_BY_CODE = {
    "6": "-40 to 85 C",
    "7": "-40 to 105 C",
}
PACKAGE_BY_CODE = {
    "T": "LQFP",
    "U": "UFQFPN",
    "Y": "WLCSP",
}
PINS_BY_COMBINATION = {
    ("C", "T"): "48",
    ("C", "U"): "48",
    ("C", "Y"): "49",
}
OPTION_SUFFIXES = frozenset({"", "TR"})
METADATA_FIELDS = (
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
        raise CandidateReject(f"unsupported STM32F0 package code: {package_code}")
    pins = PINS_BY_COMBINATION.get((pin_code, package_code))
    if pins is None:
        raise CandidateManualReview(
            f"unsupported STM32F0 pin/package combination: {pin_code}/{package_code}"
        )
    return package, pins


def build_candidate_inputs(
    *,
    discovery_baseline: dict[str, Any],
    evidence_id: str,
    expected_candidate_count: int = 42,
) -> list[dict[str, Any]]:
    """Normalize retained Phase 4.5B evidence into metadata-policy inputs."""

    if not evidence_id:
        raise AdmissionError("STM32F0 retained evidence requires evidence_id")
    targets = discovery_baseline.get("targets")
    if not isinstance(targets, list):
        raise AdmissionError("retained STM32F0 baseline targets must be a list")

    candidates: list[dict[str, Any]] = []
    observed_bases: list[str] = []
    for target in targets:
        if not isinstance(target, dict):
            raise AdmissionError("retained STM32F0 target must be an object")
        base_device = target.get("base_device")
        source_url = target.get("source_url")
        exact_icpns = target.get("exact_icpns")
        if not isinstance(base_device, str) or base_device not in SUPPORTED_BASE_DEVICES:
            raise AdmissionError(f"{base_device}: outside bounded STM32F0 metadata policy")
        if not isinstance(source_url, str):
            raise AdmissionError(f"{base_device}: source URL missing")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base_device}: source URL is not approved") from exc
        if not source_url.endswith(f"/{base_device.lower()}.html"):
            raise AdmissionError(f"{base_device}: source URL slug mismatch")
        if not isinstance(exact_icpns, list) or not exact_icpns:
            raise AdmissionError(f"{base_device}: exact ICPNs missing")
        rendered = target.get("rendered_dom_sha256")
        section = target.get("evidence_section_sha256")
        _require_sha256(rendered, "rendered DOM digest")
        _require_sha256(section, "evidence-section digest")
        observed_bases.append(base_device)

        for icpn in exact_icpns:
            if not isinstance(icpn, str) or not icpn.startswith(base_device):
                raise AdmissionError(f"{base_device}: foreign exact ICPN")
            candidates.append(
                {
                    "manufacturer": MANUFACTURER,
                    "base_device": base_device,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": evidence_id,
                        "source_url": source_url,
                        "rendered_dom_sha256": rendered,
                        "evidence_section_sha256": section,
                        "evidence_profile": PARSER_PROFILE,
                    },
                }
            )

    if set(observed_bases) != set(SUPPORTED_BASE_DEVICES) or len(observed_bases) != len(
        SUPPORTED_BASE_DEVICES
    ):
        raise AdmissionError("retained STM32F0 Base Device scope drifted")
    if len(candidates) != expected_candidate_count:
        raise AdmissionError(
            f"bounded STM32F0 metadata policy requires exactly {expected_candidate_count} "
            f"retained candidates, got {len(candidates)}"
        )
    return candidates


def build_metadata_row(candidate: dict[str, Any], fields: list[str] | None = None) -> dict[str, str]:
    """Decode one exact STM32F0 ordering code without applying capability routing."""

    icpn = candidate.get("icpn")
    base_device = candidate.get("base_device")
    evidence = candidate.get("authoritative_evidence")
    if not isinstance(icpn, str) or not isinstance(base_device, str):
        raise CandidateReject("invalid STM32F0 commercial identity")
    if base_device not in SUPPORTED_BASE_DEVICES:
        raise CandidateReject(f"{base_device}: outside bounded STM32F0 metadata policy")
    if not isinstance(evidence, dict):
        raise CandidateReject("candidate lacks authoritative evidence")

    base_match = BASE_RE.fullmatch(base_device)
    if base_match is None:
        raise CandidateReject(f"unsupported STM32F0 base-device identity: {base_device}")
    if not ICPN_RE.fullmatch(icpn) or not icpn.startswith(base_device) or icpn == base_device:
        raise CandidateReject(f"invalid exact commercial ICPN: {icpn}")

    suffix = icpn[len(base_device) :]
    if len(suffix) < 2:
        raise CandidateReject(f"ICPN lacks package/temperature codes: {icpn}")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    if temperature_code not in TEMPERATURE_BY_CODE:
        raise CandidateReject(f"unsupported STM32F0 temperature code: {temperature_code}")
    if option_suffix not in OPTION_SUFFIXES:
        raise CandidateReject(f"unsupported STM32F0 option suffix: {option_suffix}")

    pin_code, flash_code = base_match.groups()
    flash_size = FLASH_BY_CODE.get(flash_code)
    if flash_size is None:
        raise CandidateManualReview(f"unsupported STM32F0 flash-size code: {flash_code}")
    package, pin_count = _package_and_pins(pin_code, package_code)

    source_url = evidence.get("source_url")
    evidence_id = evidence.get("evidence_id")
    if (
        not isinstance(source_url, str)
        or not isinstance(evidence_id, str)
        or not evidence_id
        or evidence.get("evidence_profile") != PARSER_PROFILE
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
        "source_type": "official_st_product_page_retained_browser_dual_surface_evidence",
        "source_reference": f"{source_url}#plasma-evidence={evidence_id}",
        "source_authority": "STMicroelectronics official",
        "verification_status": "verified_direct_st_retained_browser_exact_icpn",
    }
    requested = list(METADATA_FIELDS) if fields is None else fields
    if tuple(requested) != METADATA_FIELDS:
        raise AdmissionError("metadata schema is not supported by the STM32F0 policy")
    return {field: values[field] for field in requested}
