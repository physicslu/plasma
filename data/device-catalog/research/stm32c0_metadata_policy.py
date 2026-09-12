"""Bounded STM32C0 Phase C0.3 commercial metadata policy.

Commercial identity/lifecycle authority remains the retained C0.2 official-ST
Quality & Reliability + Sample & Buy exact-set evidence. Metadata semantics are
restricted to the official ST Ordering Information records frozen in
stm32c0-phase-c0.3-ordering-authority.json.

OpenOCD routing and CMSIS aliases are not metadata authorities. This adapter
accepts only the 220 retained Active exact ICPNs and fails closed on any
identity or ordering-code combination outside that boundary.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject
from st_product_page_acquisition import AcquisitionError, validate_source_url

HERE = Path(__file__).resolve().parent
DEFAULT_ORDERING_AUTHORITY = HERE / "stm32c0-phase-c0.3-ordering-authority.json"
C0_2_SUMMARY = HERE / "evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11/pilot-summary.json"
C0_2_DISCOVERY = HERE / "stm32c0-phase-c0.2-discovery-manifest.json"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32C0"
PARSER_PROFILE = "stm32c0_c0_2_dual_surface_v1"
EXPECTED_EVIDENCE_ID = "stm32c0-c0.2-official-st-commercial-discovery-v1"
EXPECTED_ACTIVE_CANDIDATE_COUNT = 220
EXPECTED_TARGET_COUNT = 50
EXPECTED_EXCLUDED_NON_ACTIVE = {"STM32C091KBT3"}
EXPECTED_AUTHORITY_RECORDS = {
    "STM32C011": ("DS13866", 5, 7, 93),
    "STM32C031": ("DS13867", 4, 7, 100),
    "STM32C051": ("DS14721", 2, 7, 107),
    "STM32C071": ("DS14693", 2, 7, 128),
    "STM32C091": ("DS14720", 3, 7, 121),
    "STM32C092": ("DS14720", 3, 7, 121),
}
ICPN_RE = re.compile(r"^STM32C(?:011|031|051|071|091|092)[0-9A-Z]+$")
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


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path.name}: root must be a JSON object")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CandidateReject(f"candidate lacks valid {label}")
    return value


def load_ordering_authority(path: Path = DEFAULT_ORDERING_AUTHORITY) -> dict[str, dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("schema_version") != 1 or payload.get("phase") != "C0.3":
        raise AdmissionError("unsupported STM32C0 ordering-authority schema/phase")
    if payload.get("family") != FAMILY or payload.get("manufacturer") != MANUFACTURER:
        raise AdmissionError("STM32C0 ordering-authority family/manufacturer drifted")
    if payload.get("authority_version") != "stm32c0-c0.3-retained220-v1":
        raise AdmissionError("STM32C0 ordering-authority version drifted")

    governance = payload.get("governance")
    if not isinstance(governance, dict):
        raise AdmissionError("STM32C0 ordering-authority governance is missing")
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
        raise AdmissionError("STM32C0 ordering authority widened a fail-closed governance boundary")

    records = payload.get("records")
    if not isinstance(records, list) or len(records) != len(EXPECTED_AUTHORITY_RECORDS):
        raise AdmissionError("STM32C0 ordering-authority record count drifted")

    by_series: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise AdmissionError("STM32C0 ordering-authority record must be an object")
        series = record.get("series")
        if not isinstance(series, str) or series in by_series:
            raise AdmissionError("STM32C0 ordering-authority series is invalid/duplicated")
        expected = EXPECTED_AUTHORITY_RECORDS.get(series)
        if expected is None:
            raise AdmissionError(f"unexpected STM32C0 ordering authority series: {series}")
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
        raise AdmissionError("STM32C0 ordering-authority series set drifted")
    c071_options = by_series["STM32C071"]["retained_semantics"]["option"]
    if set(c071_options) != {"", "TR", "N", "NTR"}:
        raise AdmissionError("STM32C071 N/TR product-version and packing semantics drifted")
    if by_series["STM32C091"]["document_id"] != by_series["STM32C092"]["document_id"]:
        raise AdmissionError("STM32C091/STM32C092 shared DS14720 authority drifted")
    return by_series


def build_candidate_inputs() -> list[dict[str, Any]]:
    summary = _read_json(C0_2_SUMMARY)
    discovery = _read_json(C0_2_DISCOVERY)
    if summary.get("discovery_id") != EXPECTED_EVIDENCE_ID:
        raise AdmissionError("STM32C0 C0.2 retained evidence identity drifted")
    if summary.get("family") != FAMILY or summary.get("phase") != "C0.2":
        raise AdmissionError("STM32C0 C0.2 summary identity drifted")
    if (
        summary.get("bounded_discovery_clean") is not True
        or summary.get("commercial_identity_clean") is not True
        or summary.get("commercial_identity_verified_targets") != EXPECTED_TARGET_COUNT
        or summary.get("active_exact_icpn_candidates") != EXPECTED_ACTIVE_CANDIDATE_COUNT
        or summary.get("source_unavailable_exclusions") != 0
        or summary.get("identity_manual_intervention_required") != 0
    ):
        raise AdmissionError("STM32C0 C0.2 clean commercial boundary drifted")
    route = summary.get("openocd_routing")
    if not isinstance(route, dict) or route.get("gates_commercial_identity") is not False:
        raise AdmissionError("OpenOCD routing cannot gate STM32C0 commercial identity")

    targets = discovery.get("targets")
    results = summary.get("results")
    if not isinstance(targets, list) or len(targets) != EXPECTED_TARGET_COUNT:
        raise AdmissionError("C0.2 retained discovery must contain exactly 50 targets")
    if not isinstance(results, list) or len(results) != EXPECTED_TARGET_COUNT:
        raise AdmissionError("C0.2 retained summary must contain exactly 50 results")
    target_by_base = {
        item.get("base_device"): item
        for item in targets
        if isinstance(item, dict) and isinstance(item.get("base_device"), str)
    }
    if len(target_by_base) != EXPECTED_TARGET_COUNT:
        raise AdmissionError("C0.2 retained Base Device target set drifted")

    candidates: list[dict[str, Any]] = []
    observed_bases: set[str] = set()
    observed_icpns: set[str] = set()
    excluded: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            raise AdmissionError("C0.2 retained result must be an object")
        base = result.get("base_device")
        source_url = result.get("source_url")
        if not isinstance(base, str) or base not in target_by_base or base in observed_bases:
            raise AdmissionError(f"invalid/duplicated retained STM32C0 Base Device: {base}")
        observed_bases.add(base)
        if (
            result.get("disposition") != "active_candidates"
            or result.get("commercial_identity_status") != "verified_active"
            or result.get("manual_intervention_required") is not False
        ):
            raise AdmissionError(f"{base}: C0.3 accepts only retained Active C0.2 identity state")
        route = result.get("openocd_routing")
        if not isinstance(route, dict) or route.get("gates_commercial_identity") is not False:
            raise AdmissionError(f"{base}: routing authority boundary drifted")
        if not isinstance(source_url, str):
            raise AdmissionError(f"{base}: retained official ST product URL missing")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base}: retained product URL is not approved") from exc
        if not source_url.endswith(f"/{base.lower()}.html"):
            raise AdmissionError(f"{base}: retained product URL slug mismatch")

        evidence = result.get("evidence")
        if not isinstance(evidence, dict) or evidence.get("base_device") != base:
            raise AdmissionError(f"{base}: retained evidence missing")
        if evidence.get("parser_profile") != PARSER_PROFILE or evidence.get("parser_version") != 2:
            raise AdmissionError(f"{base}: retained evidence parser profile drifted")
        if evidence.get("source_url") != source_url:
            raise AdmissionError(f"{base}: retained evidence source URL mismatch")
        rendered_sha = _require_sha256(evidence.get("rendered_dom_sha256"), "rendered DOM digest")
        section_sha = _require_sha256(evidence.get("evidence_section_sha256"), "evidence-section digest")

        non_active = evidence.get("excluded_non_active_part_numbers")
        if not isinstance(non_active, list):
            raise AdmissionError(f"{base}: retained non-Active list missing")
        for item in non_active:
            if not isinstance(item, dict) or not isinstance(item.get("icpn"), str):
                raise AdmissionError(f"{base}: invalid retained non-Active record")
            excluded.add(item["icpn"])

        exact = evidence.get("exact_icpns")
        if not isinstance(exact, list) or not exact:
            raise AdmissionError(f"{base}: Active target lacks exact ICPNs")
        for icpn in exact:
            if (
                not isinstance(icpn, str)
                or ICPN_RE.fullmatch(icpn) is None
                or not icpn.startswith(base)
                or icpn in observed_icpns
            ):
                raise AdmissionError(f"{base}: invalid/duplicated retained exact ICPN {icpn}")
            if icpn in excluded:
                raise AdmissionError(f"{base}: exact ICPN cannot be both Active and excluded")
            observed_icpns.add(icpn)
            candidates.append({
                "manufacturer": MANUFACTURER,
                "base_device": base,
                "icpn": icpn,
                "authoritative_evidence": {
                    "evidence_id": EXPECTED_EVIDENCE_ID,
                    "source_url": source_url,
                    "rendered_dom_sha256": rendered_sha,
                    "evidence_section_sha256": section_sha,
                    "evidence_profile": PARSER_PROFILE,
                },
            })

    if observed_bases != set(target_by_base):
        raise AdmissionError("C0.3 retained Base Device set drifted")
    if len(candidates) != EXPECTED_ACTIVE_CANDIDATE_COUNT or len(observed_icpns) != EXPECTED_ACTIVE_CANDIDATE_COUNT:
        raise AdmissionError(f"C0.3 requires exactly 220 retained Active candidates, got {len(candidates)}")
    if excluded != EXPECTED_EXCLUDED_NON_ACTIVE:
        raise AdmissionError(f"C0.3 non-Active continuity set drifted: {sorted(excluded)}")
    return candidates


@lru_cache(maxsize=1)
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
    if not isinstance(icpn, str) or not isinstance(base, str):
        raise CandidateReject("invalid STM32C0 commercial identity")
    if icpn not in retained_exact_icpns():
        raise CandidateReject(f"{icpn}: exact identity is outside retained C0.2 Active scope")
    if ICPN_RE.fullmatch(icpn) is None or not icpn.startswith(base) or icpn == base:
        raise CandidateReject(f"invalid exact STM32C0 ICPN: {icpn}")
    if not isinstance(evidence, dict) or evidence.get("evidence_id") != EXPECTED_EVIDENCE_ID:
        raise CandidateReject(f"{base}: retained identity evidence missing")
    if evidence.get("evidence_profile") != PARSER_PROFILE:
        raise CandidateReject(f"{base}: retained identity evidence profile drifted")
    source_url = evidence.get("source_url")
    if not isinstance(source_url, str) or not source_url.endswith(f"/{base.lower()}.html"):
        raise CandidateReject(f"{base}: retained identity source URL mismatch")
    _require_sha256(evidence.get("rendered_dom_sha256"), "rendered DOM digest")
    _require_sha256(evidence.get("evidence_section_sha256"), "evidence-section digest")

    suffix = icpn[len(base):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature ordering codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    pin_code, flash_code = base[-2], base[-1]
    series = base[:9]

    authorities = load_ordering_authority(authority_path)
    authority = authorities.get(series)
    if authority is None:
        raise CandidateReject(f"{base}: subfamily is outside C0.3 ordering authority")
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
        raise AdmissionError("metadata schema is not supported by the STM32C0 C0.3 policy")
    return {field: values[field] for field in requested}
