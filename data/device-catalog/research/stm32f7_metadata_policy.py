"""Bounded STM32F7 Phase 4.6C commercial metadata policy.

Identity/lifecycle authority is the retained Phase 4.6B official-ST evidence.
Ordering-code semantics come from explicit official ST ordering-information contracts.
OpenOCD is not a metadata authority and is not consulted by this module.

STM32F750N8 is intentionally handled by an exact-product override because the
currently machine-extracted DS12535 ordering table is internally inconsistent
with ST's exact commercial product metadata. The override is narrow and
fail-closed: only the retained Active ICPN STM32F750N8H6 is accepted.
"""

from __future__ import annotations

import re
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32f7_dual_surface_evidence import PARSER_PROFILE

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32F7"
EXPECTED_ACTIVE_CANDIDATE_COUNT = 19
SUPPORTED_BASE_DEVICES = frozenset({
    "STM32F722IC",
    "STM32F723IC",
    "STM32F730I8",
    "STM32F732IE",
    "STM32F733IE",
    "STM32F745IE",
    "STM32F750N8",
    "STM32F778AI",
    "STM32F779AI",
})
SOURCE_UNAVAILABLE_BASES = frozenset({"STM32F768AI", "STM32F769AG"})
LIFECYCLE_EXCLUDED_BASES = frozenset({
    "STM32F746BE", "STM32F756BG", "STM32F765BG", "STM32F767BG", "STM32F777BI"
})

DATASHEET_AUTHORITIES = {
    "STM32F722": "https://www.st.com/resource/en/datasheet/stm32f722ic.pdf",
    "STM32F723": "https://www.st.com/resource/en/datasheet/stm32f722ic.pdf",
    "STM32F730": "https://www.st.com/resource/en/datasheet/stm32f730i8.pdf",
    "STM32F732": "https://www.st.com/resource/en/datasheet/stm32f732ie.pdf",
    "STM32F733": "https://www.st.com/resource/en/datasheet/stm32f732ie.pdf",
    "STM32F745": "https://www.st.com/resource/en/datasheet/stm32f745ie.pdf",
    "STM32F778": "https://www.st.com/resource/en/datasheet/stm32f777bi.pdf",
    "STM32F779": "https://www.st.com/resource/en/datasheet/stm32f777bi.pdf",
}
F750_EXACT_PRODUCT_AUTHORITY = "https://www.st.com/en/microcontrollers-microprocessors/stm32f750n8.html"

# Only codes required by the retained 19 Active candidates are admitted here.
# This is deliberately narrower than the theoretical STM32F7 ordering space.
FLASH_BY_CODE = {
    "C": "256 KiB",
    "E": "512 KiB",
    "8": "64 KiB",
    "I": "2048 KiB",
}
TEMPERATURE_BY_CODE = {
    "6": "-40 to 85 C",
    "7": "-40 to 105 C",
}
PACKAGE_BY_CODE = {
    "T": "LQFP",
    "K": "UFBGA",
    "H": "TFBGA",
    "Y": "WLCSP",
}
PINS_BY_PIN_CODE = {
    "I": "176",
    "N": "216",
    "A": "180",
}
OPTION_SUFFIXES = frozenset({"", "TR"})
ICPN_RE = re.compile(r"^STM32F7[0-9A-Z]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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

# Base Device structure: STM32F7 + 3-digit subfamily + pin-code + flash-code.
BASE_RE = re.compile(r"^(STM32F7\d{2})([A-Z])([A-Z0-9])$")


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CandidateReject(f"candidate lacks valid {label}")
    return value


def _series(base_device: str) -> str:
    # e.g. STM32F722IC -> STM32F722
    return base_device[:9]


def build_candidate_inputs(*, discovery_baseline: dict[str, Any], evidence_id: str) -> list[dict[str, Any]]:
    """Project only retained Active dispositions into Phase 4.6C inputs."""

    if not isinstance(evidence_id, str) or not evidence_id:
        raise AdmissionError("STM32F7 retained evidence requires evidence_id")
    targets = discovery_baseline.get("targets")
    if not isinstance(targets, list) or len(targets) != 16:
        raise AdmissionError("Phase 4.6B retained target scope must contain exactly 16 targets")

    candidates: list[dict[str, Any]] = []
    active_bases: set[str] = set()
    lifecycle_bases: set[str] = set()
    unavailable_bases: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise AdmissionError("retained STM32F7 target must be an object")
        base = target.get("base_device")
        disposition = target.get("disposition")
        source_url = target.get("source_url")
        if not isinstance(base, str) or not isinstance(source_url, str):
            raise AdmissionError("retained STM32F7 target identity/source missing")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base}: retained product URL is not approved") from exc
        if not source_url.endswith(f"/{base.lower()}.html"):
            raise AdmissionError(f"{base}: retained product URL slug mismatch")

        if disposition == "active_candidates":
            if base not in SUPPORTED_BASE_DEVICES:
                raise AdmissionError(f"{base}: Active target outside bounded Phase 4.6C scope")
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
        elif disposition == "lifecycle_excluded":
            lifecycle_bases.add(base)
            if base not in LIFECYCLE_EXCLUDED_BASES:
                raise AdmissionError(f"{base}: unexpected lifecycle exclusion")
            if target.get("exact_icpns") != [] or not target.get("excluded_non_active_part_numbers"):
                raise AdmissionError(f"{base}: lifecycle exclusion semantics drifted")
        elif disposition == "source_unavailable_excluded":
            unavailable_bases.add(base)
            if base not in SOURCE_UNAVAILABLE_BASES or target.get("source_unavailable_status") != "http_404":
                raise AdmissionError(f"{base}: source-unavailable exclusion semantics drifted")
            if "exact_icpns" in target:
                raise AdmissionError(f"{base}: unavailable source must not supply exact ICPNs")
        else:
            raise AdmissionError(f"{base}: unsupported retained disposition {disposition!r}")

    if active_bases != set(SUPPORTED_BASE_DEVICES):
        raise AdmissionError(f"Phase 4.6C Active Base Device scope drifted: {sorted(active_bases)}")
    if lifecycle_bases != set(LIFECYCLE_EXCLUDED_BASES):
        raise AdmissionError("Phase 4.6C lifecycle-excluded Base Device scope drifted")
    if unavailable_bases != set(SOURCE_UNAVAILABLE_BASES):
        raise AdmissionError("Phase 4.6C source-unavailable Base Device scope drifted")
    if len(candidates) != EXPECTED_ACTIVE_CANDIDATE_COUNT:
        raise AdmissionError(
            f"Phase 4.6C requires exactly {EXPECTED_ACTIVE_CANDIDATE_COUNT} retained Active candidates, got {len(candidates)}"
        )
    if len({item["icpn"] for item in candidates}) != len(candidates):
        raise AdmissionError("Phase 4.6C retained Active candidate set contains duplicates")
    return candidates


def _decode_standard(base_device: str, icpn: str) -> tuple[str, str, str, str]:
    base_match = BASE_RE.fullmatch(base_device)
    if base_match is None:
        raise CandidateReject(f"unsupported STM32F7 Base Device: {base_device}")
    _, pin_code, flash_code = base_match.groups()
    suffix = icpn[len(base_device):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature ordering codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    flash_size = FLASH_BY_CODE.get(flash_code)
    package = PACKAGE_BY_CODE.get(package_code)
    pin_count = PINS_BY_PIN_CODE.get(pin_code)
    temperature = TEMPERATURE_BY_CODE.get(temperature_code)
    if flash_size is None:
        raise CandidateManualReview(f"{base_device}: unsupported flash code {flash_code}")
    if package is None:
        raise CandidateManualReview(f"{icpn}: unsupported package code {package_code}")
    if pin_count is None:
        raise CandidateManualReview(f"{base_device}: unsupported pin code {pin_code}")
    if temperature is None:
        raise CandidateManualReview(f"{icpn}: unsupported temperature code {temperature_code}")
    if option_suffix not in OPTION_SUFFIXES:
        raise CandidateReject(f"{icpn}: unsupported option suffix {option_suffix!r}")
    return package, pin_count, flash_size, temperature


def build_metadata_row(candidate: dict[str, Any], fields: list[str] | None = None) -> dict[str, str]:
    """Build metadata for one retained Active exact ICPN without capability routing."""

    icpn = candidate.get("icpn")
    base = candidate.get("base_device")
    evidence = candidate.get("authoritative_evidence")
    if not isinstance(icpn, str) or not isinstance(base, str) or base not in SUPPORTED_BASE_DEVICES:
        raise CandidateReject("invalid/out-of-scope STM32F7 commercial identity")
    if not ICPN_RE.fullmatch(icpn) or not icpn.startswith(base) or icpn == base:
        raise CandidateReject(f"invalid exact STM32F7 ICPN: {icpn}")
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

    suffix = icpn[len(base):]
    option_suffix = suffix[2:] if len(suffix) >= 2 else ""
    if base == "STM32F750N8":
        if icpn != "STM32F750N8H6":
            raise CandidateReject(f"{icpn}: F750 exact-product override is intentionally narrow")
        package, pin_count, flash_size, temperature = "TFBGA", "216", "64 KiB", "-40 to 85 C"
        metadata_authority = F750_EXACT_PRODUCT_AUTHORITY
        verification = "verified_direct_st_exact_product_metadata_override"
    else:
        package, pin_count, flash_size, temperature = _decode_standard(base, icpn)
        authority = DATASHEET_AUTHORITIES.get(_series(base))
        if authority is None:
            raise CandidateManualReview(f"{base}: no official ST ordering-information authority bound")
        metadata_authority = authority
        verification = "verified_st_datasheet_ordering_information_plus_retained_exact_identity"

    values = {
        "manufacturer": MANUFACTURER,
        "icpn": icpn,
        "family": FAMILY,
        "series": _series(base),
        "base_device": base,
        "package": package,
        "pin_count": pin_count,
        "flash_size": flash_size,
        "temperature_grade": temperature,
        "option_suffix": option_suffix,
        "source_type": "official_st_ordering_information_plus_retained_phase4_6b_identity",
        "source_reference": f"{metadata_authority}#identity={evidence_id}",
        "source_authority": "STMicroelectronics official",
        "verification_status": verification,
    }
    requested = list(METADATA_FIELDS) if fields is None else fields
    if tuple(requested) != METADATA_FIELDS:
        raise AdmissionError("metadata schema is not supported by the STM32F7 Phase 4.6C policy")
    return {field: values[field] for field in requested}
