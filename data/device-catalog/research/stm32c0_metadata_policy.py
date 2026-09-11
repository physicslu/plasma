"""Bounded STM32C0 Phase C0.3 commercial metadata policy.

Commercial identity/lifecycle authority is retained C0.2 official-ST evidence.
Metadata semantics are restricted to official ST datasheet Ordering Information
frozen in stm32c0-phase-c0.3-ordering-authority.json.

OpenOCD routing and CMSIS aliases are not metadata authorities. The adapter
accepts only the 220 retained Active exact ICPNs. STM32C071 N product-version
semantics are preserved in the raw option_suffix (N / NTR) and are never
normalized away.
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
DISCOVERY = HERE / "stm32c0-phase-c0.2-discovery-manifest.json"
EVIDENCE = HERE / "evidence/stm32c0-c0.2-official-st-discovery-live-2026-09-11"
LEAVES = EVIDENCE / "evidence"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32C0"
PARSER_PROFILE = "stm32c0_c0_2_dual_surface_v1"
EXPECTED_ACTIVE_CANDIDATE_COUNT = 220
EXPECTED_TARGET_COUNT = 50
EXPECTED_AUTHORITY_RECORDS = {
    "STM32C011": ("DS13866", 5, 7, 93),
    "STM32C031": ("DS13867", 4, 7, 100),
    "STM32C051": ("DS14721", 2, 7, 107),
    "STM32C071": ("DS14693", 2, 7, 128),
    "STM32C091": ("DS14720", 3, 7, 121),
    "STM32C092": ("DS14720", 3, 7, 121),
}
ICPN_RE = re.compile(r"^STM32C(?:011|031|051|071|091|092)[0-9A-Z]+$")
BASE_RE = re.compile(r"^(STM32C(?:011|031|051|071|091|092))([A-Z])([0-9A-Z])$")
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


def _series(base_device: str) -> str:
    match = BASE_RE.fullmatch(base_device)
    if match is None:
        raise CandidateReject(f"unsupported STM32C0 Base Device: {base_device}")
    return match.group(1)


def load_ordering_authority(path: Path = DEFAULT_ORDERING_AUTHORITY) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AdmissionError("STM32C0 ordering authority must be a JSON object")
    if payload.get("schema_version") != 1 or payload.get("phase") != "C0.3":
        raise AdmissionError("unsupported STM32C0 ordering-authority schema/phase")
    if payload.get("family") != FAMILY or payload.get("manufacturer") != MANUFACTURER:
        raise AdmissionError("STM32C0 ordering-authority family/manufacturer drifted")
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
    if by_series["STM32C091"]["document_id"] != by_series["STM32C092"]["document_id"]:
        raise AdmissionError("STM32C091/092 shared official ordering authority drifted")
    return by_series


@lru_cache(maxsize=1)
def retained_candidate_index() -> tuple[frozenset[str], frozenset[str]]:
    discovery = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    targets = discovery.get("targets") if isinstance(discovery, dict) else None
    if not isinstance(targets, list) or len(targets) != EXPECTED_TARGET_COUNT:
        raise AdmissionError("C0.2 discovery target scope must contain exactly 50 Base Devices")
    bases: set[str] = set()
    icpns: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise AdmissionError("C0.2 discovery target must be an object")
        base = target.get("base_device")
        source_url = target.get("source_url")
        if not isinstance(base, str) or not isinstance(source_url, str) or base in bases:
            raise AdmissionError("C0.2 discovery Base Device/source is invalid or duplicated")
        if BASE_RE.fullmatch(base) is None:
            raise AdmissionError(f"{base}: unsupported C0.3 Base Device")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base}: retained product URL is not approved") from exc
        if not source_url.endswith(f"/{base.lower()}.html"):
            raise AdmissionError(f"{base}: retained product URL slug mismatch")
        evidence_path = LEAVES / f"{base}.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if not isinstance(evidence, dict) or evidence.get("base_device") != base:
            raise AdmissionError(f"{base}: retained evidence identity drifted")
        if evidence.get("parser_profile") != PARSER_PROFILE:
            raise AdmissionError(f"{base}: retained evidence parser profile drifted")
        if evidence.get("source_url") != source_url:
            raise AdmissionError(f"{base}: retained evidence source URL drifted")
        _require_sha256(evidence.get("rendered_dom_sha256"), "rendered DOM digest")
        _require_sha256(evidence.get("evidence_section_sha256"), "evidence-section digest")
        exact = evidence.get("exact_icpns")
        if not isinstance(exact, list) or not exact:
            raise AdmissionError(f"{base}: retained Active exact ICPNs missing")
        bases.add(base)
        for icpn in exact:
            if not isinstance(icpn, str) or ICPN_RE.fullmatch(icpn) is None or not icpn.startswith(base) or icpn in icpns:
                raise AdmissionError(f"{base}: invalid/duplicated retained exact ICPN {icpn}")
            icpns.add(icpn)
    if len(icpns) != EXPECTED_ACTIVE_CANDIDATE_COUNT:
        raise AdmissionError(f"C0.3 requires exactly 220 retained Active ICPNs, got {len(icpns)}")
    return frozenset(bases), frozenset(icpns)


def build_candidate_inputs() -> list[dict[str, Any]]:
    bases, _ = retained_candidate_index()
    discovery = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    candidates: list[dict[str, Any]] = []
    for target in discovery["targets"]:
        base = target["base_device"]
        if base not in bases:
            raise AdmissionError(f"{base}: target outside retained C0.2 scope")
        evidence = json.loads((LEAVES / f"{base}.json").read_text(encoding="utf-8"))
        for icpn in evidence["exact_icpns"]:
            candidates.append({
                "manufacturer": MANUFACTURER,
                "base_device": base,
                "icpn": icpn,
                "authoritative_evidence": {
                    "source_url": evidence["source_url"],
                    "rendered_dom_sha256": evidence["rendered_dom_sha256"],
                    "evidence_section_sha256": evidence["evidence_section_sha256"],
                    "evidence_profile": evidence["parser_profile"],
                },
            })
    if len(candidates) != EXPECTED_ACTIVE_CANDIDATE_COUNT or len({c["icpn"] for c in candidates}) != len(candidates):
        raise AdmissionError("C0.3 retained Active candidate projection drifted")
    return candidates


def _decode(base_device: str, icpn: str, authority_path: Path = DEFAULT_ORDERING_AUTHORITY) -> tuple[str, str, str, str, str]:
    match = BASE_RE.fullmatch(base_device)
    if match is None:
        raise CandidateReject(f"unsupported STM32C0 Base Device: {base_device}")
    series, pin_code, flash_code = match.groups()
    suffix = icpn[len(base_device):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature ordering codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    authority = load_ordering_authority(authority_path)[series]
    semantics = authority["retained_semantics"]
    package = semantics["package"].get(package_code)
    pin_count = semantics["pin_package"].get(f"{pin_code}/{package_code}")
    flash_size = semantics["flash"].get(flash_code)
    temperature = semantics["temperature"].get(temperature_code)
    option = semantics["option"].get(option_suffix)
    if package is None:
        raise CandidateManualReview(f"{icpn}: package code {package_code} is outside bounded Ordering Information authority")
    if pin_count is None:
        raise CandidateManualReview(f"{icpn}: pin/package {pin_code}/{package_code} is outside bounded Ordering Information authority")
    if flash_size is None:
        raise CandidateManualReview(f"{base_device}: Flash code {flash_code} is outside bounded Ordering Information authority")
    if temperature is None:
        raise CandidateManualReview(f"{icpn}: temperature code {temperature_code} is outside bounded Ordering Information authority")
    if option is None:
        raise CandidateReject(f"{icpn}: option suffix {option_suffix!r} is outside bounded Ordering Information authority")
    if "N" in option_suffix and series != "STM32C071":
        raise CandidateReject(f"{icpn}: N product version is only authorized by bounded C071 Ordering Information")
    return package, pin_count, flash_size, temperature, option_suffix


def build_metadata_row(
    candidate: dict[str, Any],
    fields: list[str] | None = None,
    *,
    authority_path: Path = DEFAULT_ORDERING_AUTHORITY,
) -> dict[str, str]:
    icpn = candidate.get("icpn")
    base = candidate.get("base_device")
    evidence = candidate.get("authoritative_evidence")
    bases, retained_icpns = retained_candidate_index()
    if not isinstance(icpn, str) or not isinstance(base, str) or base not in bases:
        raise CandidateReject("invalid/out-of-scope STM32C0 commercial identity")
    if icpn not in retained_icpns:
        raise CandidateReject(f"{icpn}: exact identity is outside retained C0.2 Active scope")
    if ICPN_RE.fullmatch(icpn) is None or not icpn.startswith(base) or icpn == base:
        raise CandidateReject(f"invalid exact STM32C0 ICPN: {icpn}")
    if not isinstance(evidence, dict) or evidence.get("evidence_profile") != PARSER_PROFILE:
        raise CandidateReject(f"{base}: retained identity evidence missing")
    source_url = evidence.get("source_url")
    if not isinstance(source_url, str) or not source_url.endswith(f"/{base.lower()}.html"):
        raise CandidateReject(f"{base}: retained identity source URL mismatch")
    _require_sha256(evidence.get("rendered_dom_sha256"), "rendered DOM digest")
    _require_sha256(evidence.get("evidence_section_sha256"), "evidence-section digest")

    package, pin_count, flash_size, temperature, option_suffix = _decode(base, icpn, authority_path)
    series = _series(base)
    authority = load_ordering_authority(authority_path)[series]
    verification = "verified_st_datasheet_ordering_information_plus_retained_c0_2_exact_identity"
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
        "source_type": "manufacturer_ordering_information",
        "source_reference": authority["datasheet_url"],
        "source_authority": "STMicroelectronics official",
        "verification_status": verification,
    }
    requested = list(METADATA_FIELDS) if fields is None else fields
    if tuple(requested) != METADATA_FIELDS:
        raise AdmissionError("metadata schema is not supported by the STM32C0 C0.3 policy")
    return {field: values[field] for field in requested}
