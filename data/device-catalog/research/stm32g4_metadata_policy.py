"""Bounded STM32G4 Phase 4.9C commercial metadata policy.

Commercial identity/lifecycle authority is the retained Phase 4.9B official-ST
browser evidence. Metadata semantics are restricted to the official ST ordering
information bound in stm32g4-phase4.9c-ordering-authority.json.

OpenOCD routing and CMSIS aliases are not metadata authorities. The adapter is
intentionally narrow: it accepts only the 25 retained Active exact ICPNs and
fails closed on unbound ordering-code combinations.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32g4_dual_surface_evidence import PARSER_PROFILE

HERE = Path(__file__).resolve().parent
DEFAULT_ORDERING_AUTHORITY = HERE / "stm32g4-phase4.9c-ordering-authority.json"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32G4"
EXPECTED_TARGET_COUNT = 11
EXPECTED_ACTIVE_CANDIDATE_COUNT = 25

SUPPORTED_BASE_DEVICES = frozenset({
    "STM32G431C6",
    "STM32G441CB",
    "STM32G473CB",
    "STM32G474CB",
    "STM32G483CE",
    "STM32G484CE",
    "STM32G491CC",
    "STM32G4A1CE",
})
SOURCE_UNAVAILABLE_BASES = frozenset({
    "STM32G411C6",
    "STM32G414CB",
    "STM32G471CC",
})
EXPECTED_PROPOSAL_EXCLUSIONS = frozenset({
    "STM32G441CBT3",
    "STM32G441CBU3",
    "STM32G484CET3",
})
SERIES_BY_BASE = {
    "STM32G431C6": "STM32G431",
    "STM32G441CB": "STM32G441",
    "STM32G473CB": "STM32G473",
    "STM32G474CB": "STM32G474",
    "STM32G483CE": "STM32G483",
    "STM32G484CE": "STM32G484",
    "STM32G491CC": "STM32G491",
    "STM32G4A1CE": "STM32G4A1",
}
EXPECTED_AUTHORITY_RECORDS = {
    "STM32G431": ("DS12589", 6, 101, 194),
    "STM32G441": ("DS12960", 5, 101, 194),
    "STM32G473": ("DS12712", 5, 119, 225),
    "STM32G474": ("DS12288", 6, 124, 232),
    "STM32G483": ("DS12997", 4, 119, 227),
    "STM32G484": ("DS12983", 5, 123, 231),
    "STM32G491": ("DS13122", 4, 101, 193),
    "STM32G4A1": ("DS13268", 4, 103, 198),
}

ICPN_RE = re.compile(r"^STM32G4[0-9A-Z]+$")
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
        raise AdmissionError("STM32G4 ordering authority must be a JSON object")
    if payload.get("schema_version") != 1 or payload.get("phase") != "4.9C":
        raise AdmissionError("unsupported STM32G4 ordering-authority schema/phase")
    if payload.get("family") != FAMILY or payload.get("manufacturer") != MANUFACTURER:
        raise AdmissionError("STM32G4 ordering-authority family/manufacturer drifted")
    governance = payload.get("governance")
    if not isinstance(governance, dict):
        raise AdmissionError("STM32G4 ordering-authority governance is missing")
    if governance.get("openocd_is_metadata_authority") is not False:
        raise AdmissionError("OpenOCD must not be an STM32G4 metadata authority")
    if governance.get("cmsis_alias_is_metadata_authority") is not False:
        raise AdmissionError("CMSIS aliases must not be an STM32G4 metadata authority")
    if governance.get("scope_expansion_authorized") is not False:
        raise AdmissionError("Phase 4.9C ordering authority cannot expand scope")
    if governance.get("production_write_authorized") is not False:
        raise AdmissionError("Phase 4.9C ordering authority cannot authorize Production")

    records = payload.get("records")
    if not isinstance(records, list) or len(records) != len(EXPECTED_AUTHORITY_RECORDS):
        raise AdmissionError("STM32G4 ordering-authority record count drifted")
    by_series: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise AdmissionError("STM32G4 ordering-authority record must be an object")
        series = record.get("series")
        if not isinstance(series, str) or series in by_series:
            raise AdmissionError("STM32G4 ordering-authority series is invalid/duplicated")
        expected = EXPECTED_AUTHORITY_RECORDS.get(series)
        if expected is None:
            raise AdmissionError(f"unexpected STM32G4 ordering authority series: {series}")
        document_id, revision, table, page = expected
        if (
            record.get("document_id") != document_id
            or record.get("revision") != revision
            or record.get("ordering_table") != table
            or record.get("pdf_page") != page
        ):
            raise AdmissionError(f"{series}: official ordering-document binding drifted")
        url = record.get("datasheet_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/resource/en/datasheet/") or not url.endswith(".pdf"):
            raise AdmissionError(f"{series}: official ST datasheet URL is invalid")
        review = record.get("review")
        if not isinstance(review, dict) or review.get("text_extraction") is not True:
            raise AdmissionError(f"{series}: official ordering text was not reviewed")
        if series == "STM32G483":
            if review.get("visual_ordering_table") is not False:
                raise AdmissionError("STM32G483 visual-review limitation must remain explicit")
        elif review.get("visual_ordering_table") is not True:
            raise AdmissionError(f"{series}: ordering table visual review is missing")
        semantics = record.get("retained_semantics")
        if not isinstance(semantics, dict):
            raise AdmissionError(f"{series}: retained ordering semantics missing")
        for key in ("pin_package", "flash", "package", "temperature", "option"):
            if not isinstance(semantics.get(key), dict) or not semantics[key]:
                raise AdmissionError(f"{series}: retained {key} semantics missing")
        by_series[series] = record
    if set(by_series) != set(EXPECTED_AUTHORITY_RECORDS):
        raise AdmissionError("STM32G4 ordering-authority series set drifted")
    return by_series


def build_candidate_inputs(*, discovery_baseline: dict[str, Any], evidence_id: str) -> list[dict[str, Any]]:
    """Project only retained Phase 4.9B Active exact identities into Phase 4.9C."""
    if not isinstance(evidence_id, str) or not evidence_id:
        raise AdmissionError("STM32G4 retained evidence requires evidence_id")
    targets = discovery_baseline.get("targets")
    if not isinstance(targets, list) or len(targets) != EXPECTED_TARGET_COUNT:
        raise AdmissionError("Phase 4.9B retained target scope must contain exactly 11 targets")

    candidates: list[dict[str, Any]] = []
    active_bases: set[str] = set()
    unavailable_bases: set[str] = set()
    proposal_exclusions: set[str] = set()
    observed_bases: set[str] = set()

    for target in targets:
        if not isinstance(target, dict):
            raise AdmissionError("retained STM32G4 target must be an object")
        base = target.get("base_device")
        disposition = target.get("disposition")
        source_url = target.get("source_url")
        if not isinstance(base, str) or not isinstance(source_url, str):
            raise AdmissionError("retained STM32G4 target identity/source missing")
        if base in observed_bases:
            raise AdmissionError(f"{base}: duplicated retained target")
        observed_bases.add(base)

        if base in SOURCE_UNAVAILABLE_BASES:
            if (
                disposition != "source_unavailable_excluded"
                or target.get("commercial_identity_status") != "unverified"
                or target.get("source_unavailable_status") != "http_404"
                or "exact_icpns" in target
            ):
                raise AdmissionError(f"{base}: source-unavailable disposition drifted")
            unavailable_bases.add(base)
            continue

        if base not in SUPPORTED_BASE_DEVICES:
            raise AdmissionError(f"{base}: target outside bounded STM32G4 Phase 4.9C scope")
        if disposition != "active_candidates" or target.get("commercial_identity_status") != "verified_active":
            raise AdmissionError(f"{base}: Phase 4.9C accepts only retained Active target dispositions")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base}: retained product URL is not approved") from exc
        if not source_url.endswith(f"/{base.lower()}.html"):
            raise AdmissionError(f"{base}: retained product URL slug mismatch")

        exact = target.get("exact_icpns")
        excluded = target.get("excluded_non_active_part_numbers")
        if not isinstance(exact, list) or not exact:
            raise AdmissionError(f"{base}: Active disposition lacks exact ICPNs")
        if not isinstance(excluded, list):
            raise AdmissionError(f"{base}: lifecycle exclusion projection missing")
        rendered = _require_sha256(target.get("rendered_dom_sha256"), "rendered DOM digest")
        section = _require_sha256(target.get("evidence_section_sha256"), "evidence-section digest")
        active_bases.add(base)

        for item in excluded:
            if not isinstance(item, dict):
                raise AdmissionError(f"{base}: lifecycle exclusion must be an object")
            icpn = item.get("icpn")
            status = item.get("marketing_status")
            if not isinstance(icpn, str) or not icpn.startswith(base):
                raise AdmissionError(f"{base}: invalid lifecycle-excluded exact identity")
            if not isinstance(status, str) or not status.startswith("Proposal"):
                raise AdmissionError(f"{base}: unexpected lifecycle exclusion state")
            proposal_exclusions.add(icpn)

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

    expected_all_bases = set(SUPPORTED_BASE_DEVICES) | set(SOURCE_UNAVAILABLE_BASES)
    if observed_bases != expected_all_bases:
        raise AdmissionError(f"Phase 4.9C retained target set drifted: {sorted(observed_bases)}")
    if active_bases != set(SUPPORTED_BASE_DEVICES):
        raise AdmissionError(f"Phase 4.9C Active Base Device scope drifted: {sorted(active_bases)}")
    if unavailable_bases != set(SOURCE_UNAVAILABLE_BASES):
        raise AdmissionError(f"Phase 4.9C source-unavailable scope drifted: {sorted(unavailable_bases)}")
    if proposal_exclusions != set(EXPECTED_PROPOSAL_EXCLUSIONS):
        raise AdmissionError(f"Phase 4.9C Proposal exclusion set drifted: {sorted(proposal_exclusions)}")
    if len(candidates) != EXPECTED_ACTIVE_CANDIDATE_COUNT:
        raise AdmissionError(
            f"Phase 4.9C requires exactly {EXPECTED_ACTIVE_CANDIDATE_COUNT} retained Active candidates, got {len(candidates)}"
        )
    if len({item["icpn"] for item in candidates}) != len(candidates):
        raise AdmissionError("Phase 4.9C retained Active candidate set contains duplicates")
    return candidates


def build_metadata_row(
    candidate: dict[str, Any],
    fields: list[str] | None = None,
    *,
    authority_path: Path = DEFAULT_ORDERING_AUTHORITY,
) -> dict[str, str]:
    """Decode one retained Active exact ICPN using only bounded official-ST semantics."""
    icpn = candidate.get("icpn")
    base = candidate.get("base_device")
    evidence = candidate.get("authoritative_evidence")
    if not isinstance(icpn, str) or not isinstance(base, str) or base not in SUPPORTED_BASE_DEVICES:
        raise CandidateReject("invalid/out-of-scope STM32G4 commercial identity")
    if ICPN_RE.fullmatch(icpn) is None or not icpn.startswith(base) or icpn == base:
        raise CandidateReject(f"invalid exact STM32G4 ICPN: {icpn}")
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
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature ordering codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    pin_code, flash_code = base[-2], base[-1]
    series = SERIES_BY_BASE[base]

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
        raise CandidateManualReview(f"{icpn}: pin/package combination {pin_code}/{package_code} is outside bounded ordering authority")
    if flash_size is None:
        raise CandidateManualReview(f"{base}: Flash code {flash_code} is outside bounded ordering authority")
    if temperature is None:
        raise CandidateManualReview(f"{icpn}: temperature code {temperature_code} is outside bounded ordering authority")
    if option is None:
        raise CandidateReject(f"{icpn}: option suffix {option_suffix!r} is outside bounded ordering authority")

    datasheet_url = authority["datasheet_url"]
    document_id = authority["document_id"]
    revision = authority["revision"]
    ordering_table = authority["ordering_table"]
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
        "source_type": "official_st_ordering_information_plus_retained_phase4_9b_identity",
        "source_reference": (
            f"{datasheet_url}#document={document_id};revision={revision};table={ordering_table};"
            f"identity={evidence_id}"
        ),
        "source_authority": "STMicroelectronics official",
        "verification_status": "verified_st_datasheet_ordering_information_plus_retained_exact_identity",
    }
    requested = list(METADATA_FIELDS) if fields is None else fields
    if tuple(requested) != METADATA_FIELDS:
        raise AdmissionError("metadata schema is not supported by the STM32G4 Phase 4.9C policy")
    return {field: values[field] for field in requested}
