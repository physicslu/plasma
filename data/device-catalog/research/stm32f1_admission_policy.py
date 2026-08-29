"""STM32F1-specific commercial identity and canonical-row policy."""

from __future__ import annotations

import re
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    CandidateManualReview,
    CandidateReject,
)
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32f1_acquisition_pilot import catalog_mapping

MANUFACTURER = "STMicroelectronics"
TRANSPORT = "chromium_rendered_dom"
BASE_RE = re.compile(r"^STM32F1\d{2}([CRVZ])([8BCE])$")
ICPN_RE = re.compile(r"^STM32F1[0-9A-Z]+$")
PACKAGE_BY_CODE = {"T": "LQFP", "U": "UFQFPN", "Y": "WLCSP64"}
PINS_BY_CODE = {"C": "48", "R": "64", "V": "100", "Z": "144"}
FLASH_BY_CODE = {"8": "64 KiB", "B": "128 KiB", "C": "256 KiB", "E": "512 KiB"}
TEMPERATURE_BY_CODE = {"6": "-40 to 85 C", "7": "-40 to 105 C"}


def build_candidate_inputs(
    *,
    summary: dict[str, Any],
    evidence_id: str,
    catalog_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Normalize retained STM32F1 evidence into transport-agnostic admission inputs."""

    evidence_results = summary.get("results")
    if not isinstance(evidence_results, list):
        raise AdmissionError("retained pilot results must be a list")

    candidates: list[dict[str, Any]] = []
    for result in evidence_results:
        if not isinstance(result, dict):
            raise AdmissionError("retained pilot result must be an object")
        base_device = result.get("base_device")
        evidence = result.get("evidence")
        if not isinstance(base_device, str) or not isinstance(evidence, dict):
            raise AdmissionError("retained pilot result lacks base/evidence")
        source_url = evidence.get("source_url")
        if not isinstance(source_url, str):
            raise AdmissionError(f"{base_device}: missing source URL")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base_device}: source URL is not approved") from exc

        mapping = catalog_mapping(base_device, catalog_rows)
        raw_icpns = evidence.get("exact_icpns")
        if not isinstance(raw_icpns, list):
            raise AdmissionError(f"{base_device}: exact_icpns must be a list")
        for icpn in raw_icpns:
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
                    "base_mapping": mapping,
                }
            )
    return candidates


def build_canonical_row(candidate: dict[str, Any], fields: list[str]) -> dict[str, str]:
    """Apply STM32F1 commercial-code semantics to one normalized candidate."""

    icpn = candidate.get("icpn")
    base_device = candidate.get("base_device")
    evidence = candidate.get("authoritative_evidence")
    mapping = candidate.get("base_mapping")
    if not isinstance(icpn, str) or not isinstance(base_device, str):
        raise CandidateReject("invalid STM32F1 commercial identity")
    if not isinstance(evidence, dict):
        raise CandidateReject("candidate lacks authoritative evidence")
    if not isinstance(mapping, dict):
        raise CandidateManualReview("base device lacks programming mapping")

    base_match = BASE_RE.fullmatch(base_device)
    if base_match is None:
        raise CandidateReject(f"unsupported STM32F1 base-device identity: {base_device}")
    if not ICPN_RE.fullmatch(icpn) or not icpn.startswith(base_device) or icpn == base_device:
        raise CandidateReject(f"invalid exact commercial ICPN: {icpn}")
    suffix = icpn[len(base_device) :]
    if len(suffix) < 2:
        raise CandidateReject(f"ICPN lacks package/temperature codes: {icpn}")
    package_code, temperature_code = suffix[0], suffix[1]
    if package_code not in (set(PACKAGE_BY_CODE) | {"H"}) or temperature_code not in TEMPERATURE_BY_CODE:
        raise CandidateReject(f"unsupported package/temperature code: {icpn}")

    target_configs = mapping.get("target_configs")
    if mapping.get("status") != "unique" or not isinstance(target_configs, list) or len(target_configs) != 1:
        raise CandidateManualReview(f"base device lacks one unique OpenOCD mapping: {base_device}")
    identifier_kind = mapping.get("identifier_kind")
    if not isinstance(identifier_kind, str) or not identifier_kind:
        raise CandidateManualReview(f"base device lacks mapping identifier kind: {base_device}")

    source_url = evidence.get("source_url")
    evidence_id = evidence.get("evidence_id")
    if not isinstance(source_url, str) or not source_url:
        raise CandidateReject(f"{base_device}: missing authoritative source URL")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise CandidateReject(f"{base_device}: missing evidence_id")

    pin_code, flash_code = base_match.groups()
    package = "TFBGA" if package_code == "H" and pin_code == "R" else (
        "LFBGA" if package_code == "H" else PACKAGE_BY_CODE[package_code]
    )
    values = {
        "manufacturer": MANUFACTURER,
        "icpn": icpn,
        "family": "STM32F1",
        "series": base_device[:9],
        "base_device": base_device,
        "package": package,
        "pin_count": PINS_BY_CODE[pin_code],
        "flash_size": FLASH_BY_CODE[flash_code],
        "temperature_grade": TEMPERATURE_BY_CODE[temperature_code],
        "option_suffix": suffix[2:],
        "cmsis_device_name": base_device,
        "existing_identifier": base_device,
        "existing_identifier_kind": identifier_kind,
        "mapping_status": "deterministic_pattern",
        "openocd_target_config": target_configs[0],
        "source_type": "official_st_product_page_retained_browser_evidence",
        "source_reference": f"{source_url}#plasma-evidence={evidence_id}",
        "source_authority": "STMicroelectronics official",
        "verification_status": "verified_direct_st_retained_browser_exact_icpn",
    }
    if set(values) != set(fields):
        raise AdmissionError("canonical CSV schema is not supported by the STM32F1 policy")
    return {field: values[field] for field in fields}
