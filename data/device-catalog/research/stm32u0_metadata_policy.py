"""Bounded STM32U0 Phase U0.3 commercial metadata policy.

Commercial identity/lifecycle authority is the retained U0.2 official-ST
Quality & Reliability evidence. Metadata semantics are restricted to the
official ST Ordering Information sections frozen in
stm32u0-phase-u0.3-ordering-authority.json.

OpenOCD routing and CMSIS aliases are not metadata authorities. The adapter
accepts only the 68 retained Active exact ICPNs and fails closed on any
identity or ordering-code combination outside that retained boundary.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject
from st_product_page_acquisition import AcquisitionError, validate_source_url
from validate_stm32u0_phase_u0_2_retained_evidence import EXPECTED_EVIDENCE_ID, TARGETS

HERE = Path(__file__).resolve().parent
DEFAULT_ORDERING_AUTHORITY = HERE / "stm32u0-phase-u0.3-ordering-authority.json"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32U0"
PARSER_PROFILE = "stm32u0_quality_reliability_v1"
EXPECTED_ACTIVE_CANDIDATE_COUNT = 68
EXPECTED_TARGET_COUNT = 26
SUPPORTED_BASE_DEVICES = frozenset({
    "STM32U031C6",
    "STM32U031C8",
    "STM32U031F4",
    "STM32U031F6",
    "STM32U031F8",
    "STM32U031K4",
    "STM32U031K6",
    "STM32U031K8",
    "STM32U031R6",
    "STM32U031R8",
    "STM32U073C8",
    "STM32U073CB",
    "STM32U073CC",
    "STM32U073K8",
    "STM32U073KB",
    "STM32U073KC",
    "STM32U073M8",
    "STM32U073MB",
    "STM32U073MC",
    "STM32U073R8",
    "STM32U073RB",
    "STM32U073RC",
    "STM32U083CC",
    "STM32U083KC",
    "STM32U083MC",
    "STM32U083RC",
})
EXPECTED_AUTHORITY_RECORDS = {
    "STM32U031": ("DS14581", 2, 8, 124),
    "STM32U073": ("DS14548", 2, 8, 135),
    "STM32U083": ("DS14463", 2, 8, 135),
}
ICPN_RE = re.compile(r"^STM32U(?:031|073|083)[0-9A-Z]+$")
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


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CandidateReject(f"candidate lacks valid {label}")
    return value


def load_ordering_authority(path: Path = DEFAULT_ORDERING_AUTHORITY) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AdmissionError("STM32U0 ordering authority must be a JSON object")
    if payload.get("schema_version") != 1 or payload.get("phase") != "U0.3":
        raise AdmissionError("unsupported STM32U0 ordering-authority schema/phase")
    if payload.get("family") != FAMILY or payload.get("manufacturer") != MANUFACTURER:
        raise AdmissionError("STM32U0 ordering-authority family/manufacturer drifted")
    governance = payload.get("governance")
    if not isinstance(governance, dict):
        raise AdmissionError("STM32U0 ordering-authority governance is missing")
    false_controls = (
        "openocd_is_metadata_authority",
        "cmsis_alias_is_metadata_authority",
        "scope_expansion_authorized",
        "canonical_admission_authorized",
        "production_write_authorized",
        "programming_policy_defined",
        "flash_geometry_qualified",
        "option_security_semantics_qualified",
        "physical_hil_qualified",
        "runtime_programming_support_claimed",
    )
    if any(governance.get(key) is not False for key in false_controls):
        raise AdmissionError("STM32U0 ordering authority widened a fail-closed governance boundary")

    records = payload.get("records")
    if not isinstance(records, list) or len(records) != len(EXPECTED_AUTHORITY_RECORDS):
        raise AdmissionError("STM32U0 ordering-authority record count drifted")
    by_series: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise AdmissionError("STM32U0 ordering-authority record must be an object")
        series = record.get("series")
        if not isinstance(series, str) or series in by_series:
            raise AdmissionError("STM32U0 ordering-authority series is invalid/duplicated")
        expected = EXPECTED_AUTHORITY_RECORDS.get(series)
        if expected is None:
            raise AdmissionError(f"unexpected STM32U0 ordering authority series: {series}")
        document_id, revision, section, page = expected
        if (
            record.get("document_id") != document_id
            or record.get("revision") != revision
            or record.get("ordering_section") != section
            or record.get("pdf_page") != page
        ):
            raise AdmissionError(f"{series}: official Ordering Information binding drifted")
        url = record.get("datasheet_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/resource/en/datasheet/") or not url.endswith(".pdf"):
            raise AdmissionError(f"{series}: official ST datasheet URL is invalid")
        review = record.get("review")
        if not isinstance(review, dict) or review.get("structured_text") is not True:
            raise AdmissionError(f"{series}: official Ordering Information text was not reviewed")
        current = record.get("current_revision_check")
        if (
            not isinstance(current, dict)
            or current.get("observed_revision") != revision
            or current.get("revision_drift") is not False
            or current.get("source") != "official_st_datasheet_surface"
        ):
            raise AdmissionError(f"{series}: current-revision check drifted")
        semantics = record.get("retained_semantics")
        if not isinstance(semantics, dict):
            raise AdmissionError(f"{series}: retained ordering semantics missing")
        for key in ("pin_package", "flash", "package", "temperature", "option"):
            if not isinstance(semantics.get(key), dict) or not semantics[key]:
                raise AdmissionError(f"{series}: retained {key} semantics missing")
        by_series[series] = record
    if set(by_series) != set(EXPECTED_AUTHORITY_RECORDS):
        raise AdmissionError("STM32U0 ordering-authority series set drifted")
    return by_series


def build_candidate_inputs(*, evidence_id: str = EXPECTED_EVIDENCE_ID, targets_path: Path = TARGETS) -> list[dict[str, Any]]:
    if evidence_id != EXPECTED_EVIDENCE_ID:
        raise AdmissionError("STM32U0 U0.3 evidence identity drifted")
    with targets_path.open(newline="", encoding="utf-8") as handle:
        targets = list(csv.DictReader(handle))
    if len(targets) != EXPECTED_TARGET_COUNT:
        raise AdmissionError("U0.2 retained target scope must contain exactly 26 targets")

    candidates: list[dict[str, Any]] = []
    observed_bases: set[str] = set()
    observed_icpns: set[str] = set()
    for target in targets:
        base = target.get("base_device")
        source_url = target.get("source_url")
        if not isinstance(base, str) or base not in SUPPORTED_BASE_DEVICES or base in observed_bases:
            raise AdmissionError(f"invalid/duplicated retained STM32U0 Base Device: {base}")
        observed_bases.add(base)
        if (
            target.get("disposition") != "active_candidates"
            or target.get("commercial_identity_status") != "verified_active"
            or target.get("excluded_non_active_part_numbers") not in ("", None)
        ):
            raise AdmissionError(f"{base}: U0.3 accepts only retained Active U0.2 identity state")
        if (
            target.get("parser_profile") != PARSER_PROFILE
            or target.get("sample_buy_gates_commercial_identity") != "false"
            or target.get("historical_openocd_routing_status") != "unique"
            or target.get("routing_gates_commercial_identity") != "false"
        ):
            raise AdmissionError(f"{base}: retained identity/routing boundary drifted")
        if not isinstance(source_url, str):
            raise AdmissionError(f"{base}: retained official ST product URL missing")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base}: retained product URL is not approved") from exc
        if not source_url.endswith(f"/{base.lower()}.html"):
            raise AdmissionError(f"{base}: retained product URL slug mismatch")
        raw_sha = _require_sha256(target.get("raw_sha256"), "raw evidence digest")
        section_sha = _require_sha256(target.get("evidence_section_sha256"), "evidence-section digest")
        exact_field = target.get("exact_icpns")
        if not isinstance(exact_field, str) or not exact_field:
            raise AdmissionError(f"{base}: Active target lacks exact ICPNs")
        for icpn in exact_field.split(";"):
            if ICPN_RE.fullmatch(icpn) is None or not icpn.startswith(base) or icpn in observed_icpns:
                raise AdmissionError(f"{base}: invalid/duplicated retained exact ICPN {icpn}")
            observed_icpns.add(icpn)
            candidates.append({
                "manufacturer": MANUFACTURER,
                "base_device": base,
                "icpn": icpn,
                "authoritative_evidence": {
                    "evidence_id": evidence_id,
                    "source_url": source_url,
                    "raw_sha256": raw_sha,
                    "evidence_section_sha256": section_sha,
                    "evidence_profile": PARSER_PROFILE,
                },
            })

    if observed_bases != set(SUPPORTED_BASE_DEVICES):
        raise AdmissionError("U0.3 retained Base Device set drifted")
    if len(candidates) != EXPECTED_ACTIVE_CANDIDATE_COUNT:
        raise AdmissionError(f"U0.3 requires exactly 68 retained Active candidates, got {len(candidates)}")
    return candidates


def retained_exact_icpns() -> frozenset[str]:
    return frozenset(item["icpn"] for item in build_candidate_inputs())


def build_metadata_row(
    candidate: dict[str, Any],
    fields: list[str] | None = None,
    *,
    authority_path: Path = DEFAULT_ORDERING_AUTHORITY,
) -> dict[str, str]:
    icpn = candidate.get("icpn")
    base = candidate.get("base_device")
    evidence = candidate.get("authoritative_evidence")
    if not isinstance(icpn, str) or not isinstance(base, str) or base not in SUPPORTED_BASE_DEVICES:
        raise CandidateReject("invalid/out-of-scope STM32U0 commercial identity")
    if icpn not in retained_exact_icpns():
        raise CandidateReject(f"{icpn}: exact identity is outside retained U0.2 Active scope")
    if not icpn.startswith(base) or icpn == base:
        raise CandidateReject(f"invalid exact STM32U0 ICPN: {icpn}")
    if not isinstance(evidence, dict) or evidence.get("evidence_id") != EXPECTED_EVIDENCE_ID:
        raise CandidateReject(f"{base}: retained identity evidence missing")
    if evidence.get("evidence_profile") != PARSER_PROFILE:
        raise CandidateReject(f"{base}: retained identity evidence profile drifted")
    source_url = evidence.get("source_url")
    if not isinstance(source_url, str) or not source_url.endswith(f"/{base.lower()}.html"):
        raise CandidateReject(f"{base}: retained identity source URL mismatch")
    _require_sha256(evidence.get("raw_sha256"), "raw evidence digest")
    _require_sha256(evidence.get("evidence_section_sha256"), "evidence-section digest")

    suffix = icpn[len(base):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature ordering codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    pin_code, flash_code = base[-2], base[-1]
    series = base[:9]

    authorities = load_ordering_authority(authority_path)
    authority = authorities[series]
    semantics = authority["retained_semantics"]
    package = semantics["package"].get(package_code)
    pin_count = semantics["pin_package"].get(f"{pin_code}/{package_code}")
    flash_size = semantics["flash"].get(flash_code)
    temperature = semantics["temperature"].get(temperature_code)
    option = semantics["option"].get(option_suffix)
    if package is None:
        raise CandidateManualReview(f"{icpn}: package code {package_code} is outside bounded ordering authority")
    if pin_count is None:
        raise CandidateManualReview(f"{icpn}: pin/package {pin_code}/{package_code} is outside bounded ordering authority")
    if flash_size is None:
        raise CandidateManualReview(f"{base}: Flash code {flash_code} is outside bounded ordering authority")
    if temperature is None:
        raise CandidateManualReview(f"{icpn}: temperature code {temperature_code} is outside bounded ordering authority")
    if option is None:
        raise CandidateReject(f"{icpn}: option suffix {option_suffix!r} is outside bounded ordering authority")

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
        raise AdmissionError("metadata schema is not supported by the STM32U0 U0.3 policy")
    return {field: values[field] for field in requested}
