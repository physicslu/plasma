"""Bounded STM32G0 Phase 4.8C commercial metadata policy.

Commercial identity/lifecycle authority is the retained Phase 4.8B official-ST
browser evidence. Ordering-code semantics are bound to official ST ordering
information. OpenOCD and CMSIS aliases are not metadata authorities.

The STM32G0B1/STM32G0C1 N product version is preserved as an explicit option
suffix. It is not normalized away: ST ordering information defines N as a
product-version selector, and Phase 4.8B retained two Active N-suffix ICPNs.
"""
from __future__ import annotations

import re
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32g0_dual_surface_evidence import PARSER_PROFILE

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32G0"
EXPECTED_ACTIVE_CANDIDATE_COUNT = 49
SUPPORTED_BASE_DEVICES = frozenset({
    "STM32G030C6", "STM32G031C4", "STM32G041C6", "STM32G050C6",
    "STM32G051C6", "STM32G061C6", "STM32G070CB", "STM32G071C8",
    "STM32G081CB", "STM32G0B0CE", "STM32G0B1CB", "STM32G0C1CC",
})

DATASHEET_AUTHORITIES = {
    "STM32G030": "https://www.st.com/resource/en/datasheet/stm32g030c6.pdf",
    "STM32G031": "https://www.st.com/resource/en/datasheet/stm32g031c4.pdf",
    "STM32G041": "https://www.st.com/resource/en/datasheet/stm32g041c6.pdf",
    "STM32G050": "https://www.st.com/resource/en/datasheet/stm32g050c6.pdf",
    "STM32G051": "https://www.st.com/resource/en/datasheet/stm32g051c6.pdf",
    "STM32G061": "https://www.st.com/resource/en/datasheet/stm32g061c6.pdf",
    "STM32G070": "https://www.st.com/resource/en/datasheet/stm32g070cb.pdf",
    "STM32G071": "https://www.st.com/resource/en/datasheet/stm32g071c8.pdf",
    "STM32G081": "https://www.st.com/resource/en/datasheet/stm32g081cb.pdf",
    "STM32G0B0": "https://www.st.com/resource/en/datasheet/stm32g0b0ce.pdf",
    "STM32G0B1": "https://www.st.com/resource/en/datasheet/stm32g0b1kb.pdf",
    "STM32G0C1": "https://www.st.com/resource/en/datasheet/stm32g0c1cc.pdf",
}

FLASH_BY_CODE = {
    "4": "16 KiB",
    "6": "32 KiB",
    "8": "64 KiB",
    "B": "128 KiB",
    "C": "256 KiB",
    "E": "512 KiB",
}
PIN_COUNT_BY_CODE = {"C": "48"}
PACKAGE_BY_CODE = {"T": "LQFP", "U": "UFQFPN"}
TEMPERATURE_BY_CODE = {
    "6": "-40 to 85 C",
    "7": "-40 to 105 C",
    "3": "-40 to 125 C",
}
OPTION_SUFFIXES = frozenset({"", "TR", "N", "NTR"})
N_VERSION_BASES = frozenset({"STM32G0B1CB", "STM32G0C1CC"})
ICPN_RE = re.compile(r"^STM32G0[0-9A-Z]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BASE_RE = re.compile(r"^(STM32G(?:0\d{2}|0B0|0B1|0C1))([A-Z])([A-Z0-9])$")

METADATA_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "package",
    "pin_count", "flash_size", "temperature_grade", "option_suffix",
    "source_type", "source_reference", "source_authority", "verification_status",
)


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CandidateReject(f"candidate lacks valid {label}")
    return value


def _series(base_device: str) -> str:
    match = BASE_RE.fullmatch(base_device)
    if match is None:
        raise CandidateReject(f"unsupported STM32G0 Base Device: {base_device}")
    return match.group(1)


def build_candidate_inputs(*, discovery_baseline: dict[str, Any], evidence_id: str) -> list[dict[str, Any]]:
    """Project only retained Active exact ICPNs into the Phase 4.8C policy scope."""
    if not isinstance(evidence_id, str) or not evidence_id:
        raise AdmissionError("STM32G0 retained evidence requires evidence_id")
    targets = discovery_baseline.get("targets")
    if not isinstance(targets, list) or len(targets) != 12:
        raise AdmissionError("Phase 4.8B retained target scope must contain exactly 12 targets")

    candidates: list[dict[str, Any]] = []
    active_bases: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise AdmissionError("retained STM32G0 target must be an object")
        base = target.get("base_device")
        disposition = target.get("disposition")
        source_url = target.get("source_url")
        if not isinstance(base, str) or not isinstance(source_url, str):
            raise AdmissionError("retained STM32G0 target identity/source missing")
        if base not in SUPPORTED_BASE_DEVICES:
            raise AdmissionError(f"{base}: target outside bounded Phase 4.8C scope")
        if disposition != "active_candidates" or target.get("commercial_identity_status") != "verified_active":
            raise AdmissionError(f"{base}: Phase 4.8C accepts only retained Active target dispositions")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base}: retained product URL is not approved") from exc
        if not source_url.endswith(f"/{base.lower()}.html"):
            raise AdmissionError(f"{base}: retained product URL slug mismatch")
        exact = target.get("exact_icpns")
        if not isinstance(exact, list) or not exact:
            raise AdmissionError(f"{base}: Active disposition lacks exact ICPNs")
        rendered = _require_sha256(target.get("rendered_dom_sha256"), "rendered DOM digest")
        section = _require_sha256(target.get("evidence_section_sha256"), "evidence-section digest")
        active_bases.add(base)
        for icpn in exact:
            if not isinstance(icpn, str) or not icpn.startswith(base):
                raise AdmissionError(f"{base}: foreign Active exact ICPN")
            candidates.append({
                "manufacturer": MANUFACTURER,
                "base_device": base,
                "icpn": icpn,
                "authoritative_evidence": {
                    "evidence_id": evidence_id,
                    "source_url": source_url,
                    "rendered_dom_sha256": rendered,
                    "evidence_section_sha256": section,
                    "evidence_profile": PARSER_PROFILE,
                },
            })
    if active_bases != set(SUPPORTED_BASE_DEVICES):
        raise AdmissionError(f"Phase 4.8C Active Base Device scope drifted: {sorted(active_bases)}")
    if len(candidates) != EXPECTED_ACTIVE_CANDIDATE_COUNT:
        raise AdmissionError(
            f"Phase 4.8C requires exactly {EXPECTED_ACTIVE_CANDIDATE_COUNT} retained Active candidates, got {len(candidates)}"
        )
    if len({item["icpn"] for item in candidates}) != len(candidates):
        raise AdmissionError("Phase 4.8C retained Active candidate set contains duplicates")
    return candidates


def _decode(base_device: str, icpn: str) -> tuple[str, str, str, str, str]:
    match = BASE_RE.fullmatch(base_device)
    if match is None:
        raise CandidateReject(f"unsupported STM32G0 Base Device: {base_device}")
    _, pin_code, flash_code = match.groups()
    suffix = icpn[len(base_device):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature ordering codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    package = PACKAGE_BY_CODE.get(package_code)
    pin_count = PIN_COUNT_BY_CODE.get(pin_code)
    flash_size = FLASH_BY_CODE.get(flash_code)
    temperature = TEMPERATURE_BY_CODE.get(temperature_code)
    if package is None:
        raise CandidateManualReview(f"{icpn}: unsupported package code {package_code}")
    if pin_count is None:
        raise CandidateManualReview(f"{base_device}: unsupported pin-count code {pin_code}")
    if flash_size is None:
        raise CandidateManualReview(f"{base_device}: unsupported Flash code {flash_code}")
    if temperature is None:
        raise CandidateManualReview(f"{icpn}: unsupported temperature code {temperature_code}")
    if option_suffix not in OPTION_SUFFIXES:
        raise CandidateReject(f"{icpn}: unsupported option suffix {option_suffix!r}")
    if "N" in option_suffix and base_device not in N_VERSION_BASES:
        raise CandidateReject(f"{icpn}: N product version is not authorized for this bounded Base Device")
    return package, pin_count, flash_size, temperature, option_suffix


def build_metadata_row(candidate: dict[str, Any], fields: list[str] | None = None) -> dict[str, str]:
    """Build manufacturer-backed metadata without applying capability routing."""
    icpn = candidate.get("icpn")
    base = candidate.get("base_device")
    evidence = candidate.get("authoritative_evidence")
    if not isinstance(icpn, str) or not isinstance(base, str) or base not in SUPPORTED_BASE_DEVICES:
        raise CandidateReject("invalid/out-of-scope STM32G0 commercial identity")
    if ICPN_RE.fullmatch(icpn) is None or not icpn.startswith(base) or icpn == base:
        raise CandidateReject(f"invalid exact STM32G0 ICPN: {icpn}")
    if not isinstance(evidence, dict) or evidence.get("evidence_profile") != PARSER_PROFILE:
        raise CandidateReject(f"{base}: retained identity evidence missing")
    source_url = evidence.get("source_url")
    evidence_id = evidence.get("evidence_id")
    if not isinstance(source_url, str) or not isinstance(evidence_id, str) or not evidence_id:
        raise CandidateReject(f"{base}: retained evidence identity incomplete")
    try:
        validate_source_url(source_url)
    except AcquisitionError as exc:
        raise CandidateReject(f"{base}: retained source URL not approved") from exc
    if not source_url.endswith(f"/{base.lower()}.html"):
        raise CandidateReject(f"{base}: retained source URL slug mismatch")
    _require_sha256(evidence.get("rendered_dom_sha256"), "rendered DOM digest")
    _require_sha256(evidence.get("evidence_section_sha256"), "evidence-section digest")

    package, pin_count, flash_size, temperature, option_suffix = _decode(base, icpn)
    series = _series(base)
    authority = DATASHEET_AUTHORITIES.get(series)
    if authority is None:
        raise CandidateManualReview(f"{base}: no official ST ordering-information authority bound")

    verification = "verified_st_datasheet_ordering_information_plus_retained_exact_identity"
    if "N" in option_suffix:
        verification += "_with_preserved_n_product_version"

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
        "source_type": "official_st_ordering_information_plus_retained_phase4_8b_identity",
        "source_reference": f"{authority}#identity={evidence_id}",
        "source_authority": "STMicroelectronics official",
        "verification_status": verification,
    }
    requested = list(METADATA_FIELDS) if fields is None else fields
    if tuple(requested) != METADATA_FIELDS:
        raise AdmissionError("metadata schema is not supported by the STM32G0 Phase 4.8C policy")
    return {field: values[field] for field in requested}
