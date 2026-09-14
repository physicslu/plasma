"""Fail-closed STM32L1 Phase L1.3 manufacturer-authoritative metadata policy.

Commercial identity/lifecycle authority remains immutable L1.2 retained official-ST
exact-set evidence. Metadata authority is official ST datasheet Ordering Information
across ten deterministic authority records. Generation-A and legacy identity semantics
remain distinct; no grammar relaxation may expand the retained 144-ICPN Active scope.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject
from validate_stm32l1_phase_l1_2_retained_evidence import (
    COMMERCIAL as L1_2_COMMERCIAL,
    EXPECTED_ACTIVE_EXACT_COUNT,
    EXPECTED_ACTIVE_SET_SHA256,
    EXPECTED_BASE_COUNT,
    EXPECTED_EXCLUDED_EXACT_COUNT,
    main as validate_retained,
)

HERE = Path(__file__).resolve().parent
DEFAULT_ORDERING_AUTHORITY = HERE / "stm32l1-phase-l1.3-ordering-authority.json"
DEFAULT_EXCEPTIONS = HERE / "stm32l1-phase-l1.3-exact-variant-exceptions.json"
MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32L1"
PHASE = "L1.3"
EXPECTED_AUTHORITY_RECORDS = 10
EXPECTED_UNIQUE_DATASHEETS = 10
EXPECTED_SUBFAMILIES = {"STM32L100", "STM32L151", "STM32L152", "STM32L162"}
METADATA_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "package", "pin_count",
    "flash_size", "temperature_grade", "option_suffix", "source_type", "source_reference",
    "source_authority", "verification_status",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path.name}: root must be object")
    return value


def _set_sha(values: set[str] | frozenset[str]) -> str:
    body = "".join(value + "\n" for value in sorted(values)).encode()
    return hashlib.sha256(body).hexdigest()


def load_ordering_authority(path: Path = DEFAULT_ORDERING_AUTHORITY) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if (
        payload.get("schema_version") != 1
        or payload.get("phase") != PHASE
        or payload.get("family") != FAMILY
        or payload.get("manufacturer") != MANUFACTURER
        or payload.get("authority_version") != "stm32l1-l1.3-retained144-v1"
    ):
        raise AdmissionError("STM32L1 ordering-authority identity/schema drifted")
    governance = payload.get("governance")
    if not isinstance(governance, dict) or not governance or set(governance.values()) != {False}:
        raise AdmissionError("STM32L1 ordering authority escaped fail-closed governance")
    migration = payload.get("migration_authority")
    if not isinstance(migration, dict) or migration.get("document") != "TN1176":
        raise AdmissionError("STM32L1 migration authority drifted")

    grammars = payload.get("grammars")
    if not isinstance(grammars, dict) or not grammars:
        raise AdmissionError("STM32L1 suffix grammar authority missing")
    for grammar_id, grammar in grammars.items():
        tails = grammar.get("allowed_tails") if isinstance(grammar, dict) else None
        if (
            not isinstance(tails, list)
            or not tails
            or len(tails) != len(set(tails))
            or any(not isinstance(x, str) for x in tails)
        ):
            raise AdmissionError(f"{grammar_id}: invalid allowed suffix tails")

    records = payload.get("records")
    if not isinstance(records, list) or len(records) != EXPECTED_AUTHORITY_RECORDS:
        raise AdmissionError("STM32L1 ordering authority requires ten deterministic records")
    seen_ids: set[str] = set()
    docs: set[str] = set()
    coverage_subfamilies: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise AdmissionError("ordering-authority record must be object")
        authority_id = record.get("authority_id")
        if not isinstance(authority_id, str) or authority_id in seen_ids:
            raise AdmissionError("invalid/duplicate STM32L1 authority_id")
        seen_ids.add(authority_id)
        subfamilies = record.get("subfamilies")
        if (
            not isinstance(subfamilies, list)
            or not subfamilies
            or any(x not in EXPECTED_SUBFAMILIES for x in subfamilies)
        ):
            raise AdmissionError(f"{authority_id}: invalid subfamily coverage")
        coverage_subfamilies.update(subfamilies)
        url = record.get("datasheet_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/") or not url.endswith(".pdf"):
            raise AdmissionError(f"{authority_id}: invalid official ST datasheet URL")
        if (
            not isinstance(record.get("document_id"), str)
            or not isinstance(record.get("revision"), int)
            or not isinstance(record.get("ordering_pdf_page"), int)
        ):
            raise AdmissionError(f"{authority_id}: incomplete document binding")
        docs.add(record["document_id"])
        for field in ("pin_codes", "flash", "package_codes", "temperature_codes"):
            value = record.get(field)
            if (
                not isinstance(value, dict)
                or not value
                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items())
            ):
                raise AdmissionError(f"{authority_id}: missing {field} authority")
        if record.get("suffix_grammar") not in grammars:
            raise AdmissionError(f"{authority_id}: unknown suffix grammar")
    if coverage_subfamilies != EXPECTED_SUBFAMILIES or len(docs) != EXPECTED_UNIQUE_DATASHEETS:
        raise AdmissionError("STM32L1 Ordering Information coverage drifted")
    return records


def load_exact_variant_exceptions(path: Path = DEFAULT_EXCEPTIONS) -> dict[str, dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("schema_version") != 1 or payload.get("phase") != PHASE or payload.get("family") != FAMILY:
        raise AdmissionError("STM32L1 exact-variant exception identity/schema drifted")
    if payload.get("scope_expansion_authorized") is not False:
        raise AdmissionError("STM32L1 exception file authorized scope expansion")
    exceptions = payload.get("exceptions")
    if exceptions != {}:
        raise AdmissionError("STM32L1 L1.3 frozen exception whitelist must remain empty")
    return {}


def _retained_commercial() -> dict[str, Any]:
    if validate_retained() != 0:
        raise AdmissionError("L1.2 retained evidence validator failed")
    payload = _read_json(L1_2_COMMERCIAL)
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        raise AdmissionError("L1.2 retained counts missing")
    expected = {
        "base_devices": EXPECTED_BASE_COUNT,
        "active_exact_icpns": EXPECTED_ACTIVE_EXACT_COUNT,
        "excluded_non_active_exact_icpns": EXPECTED_EXCLUDED_EXACT_COUNT,
        "manual_intervention": 0,
        "acquisition_failure": 0,
        "source_unavailable": 0,
    }
    if any(counts.get(k) != v for k, v in expected.items()):
        raise AdmissionError("L1.2 retained commercial boundary drifted")
    if payload.get("clean") != {
        "bounded_discovery": True,
        "commercial_identity": True,
        "representative_continuity": True,
    }:
        raise AdmissionError("L1.2 retained clean-state drifted")
    claims = payload.get("claims")
    if not isinstance(claims, dict) or not claims or set(claims.values()) != {False}:
        raise AdmissionError("L1.2 claims escaped fail-closed state")
    return payload


def build_candidate_inputs() -> list[dict[str, Any]]:
    payload = _retained_commercial()
    records = payload.get("records")
    if not isinstance(records, list) or len(records) != EXPECTED_BASE_COUNT:
        raise AdmissionError("L1.2 retained record count drifted")
    candidates: list[dict[str, Any]] = []
    bases: set[str] = set()
    active: set[str] = set()
    excluded: set[str] = set()
    for record in records:
        if not isinstance(record, list) or len(record) != 5:
            raise AdmissionError("malformed L1.2 retained commercial record")
        subfamily, base, exact, non_active, route = record
        if (
            subfamily not in EXPECTED_SUBFAMILIES
            or not isinstance(base, str)
            or base in bases
            or not base.startswith(subfamily)
            or route != "unique"
        ):
            raise AdmissionError(f"invalid/duplicate retained STM32L1 Base Device {base}")
        if not isinstance(exact, list) or not exact or not isinstance(non_active, list):
            raise AdmissionError(f"{base}: retained exact lifecycle sets malformed")
        bases.add(base)
        for icpn in exact:
            if not isinstance(icpn, str) or not icpn.startswith(base) or icpn in active:
                raise AdmissionError(f"{base}: invalid/duplicate retained Active ICPN {icpn}")
            active.add(icpn)
            candidates.append({
                "manufacturer": MANUFACTURER,
                "series": subfamily,
                "base_device": base,
                "icpn": icpn,
                "identity_source": "L1.2 retained official-ST commercial identity evidence",
            })
        for icpn in non_active:
            if not isinstance(icpn, str) or not icpn.startswith(base) or icpn in excluded:
                raise AdmissionError(f"{base}: invalid/duplicate retained excluded ICPN {icpn}")
            excluded.add(icpn)
    if (
        len(bases) != EXPECTED_BASE_COUNT
        or len(active) != EXPECTED_ACTIVE_EXACT_COUNT
        or len(excluded) != EXPECTED_EXCLUDED_EXACT_COUNT
        or active & excluded
        or _set_sha(active) != EXPECTED_ACTIVE_SET_SHA256
    ):
        raise AdmissionError("L1.2 retained identity boundary/cardinality drifted")
    candidates.sort(key=lambda x: (x["base_device"], x["icpn"]))
    return candidates


@lru_cache(maxsize=1)
def retained_exact_icpns() -> frozenset[str]:
    return frozenset(item["icpn"] for item in build_candidate_inputs())


def _authority_for(
    subfamily: str,
    pin_code: str,
    flash_code: str,
    authority_path: Path = DEFAULT_ORDERING_AUTHORITY,
) -> dict[str, Any]:
    matches = [
        row
        for row in load_ordering_authority(authority_path)
        if subfamily in row["subfamilies"]
        and pin_code in row["pin_codes"]
        and flash_code in row["flash"]
    ]
    if len(matches) != 1:
        raise CandidateManualReview(
            f"{subfamily}{pin_code}{flash_code}: expected one official Ordering Information authority, got {len(matches)}"
        )
    return matches[0]


def _resolve_pin_count(pin_value: str, package_code: str) -> str:
    if pin_value == "100/104":
        return "104" if package_code == "Y" else "100"
    return pin_value


def build_metadata_row(
    candidate: dict[str, Any],
    fields: list[str] | None = None,
    *,
    authority_path: Path = DEFAULT_ORDERING_AUTHORITY,
    exceptions_path: Path = DEFAULT_EXCEPTIONS,
) -> dict[str, str]:
    icpn = candidate.get("icpn")
    base = candidate.get("base_device")
    subfamily = candidate.get("series")
    if not isinstance(icpn, str) or not isinstance(base, str) or not isinstance(subfamily, str):
        raise CandidateReject("candidate identity is incomplete")
    if icpn not in retained_exact_icpns():
        raise CandidateReject("identity is outside retained L1.2 Active scope")
    if subfamily not in EXPECTED_SUBFAMILIES or not base.startswith(subfamily) or not icpn.startswith(base):
        raise CandidateReject(f"invalid exact STM32L1 identity: {icpn}")
    if len(base) != len(subfamily) + 2:
        raise CandidateReject(f"{base}: unexpected STM32L1 Base Device shape")

    load_exact_variant_exceptions(exceptions_path)
    pin_code, flash_code = base[-2], base[-1]
    suffix = icpn[len(base):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]

    authority = _authority_for(subfamily, pin_code, flash_code, authority_path)
    pin_value = authority["pin_codes"].get(pin_code)
    flash_size = authority["flash"].get(flash_code)
    package = authority["package_codes"].get(package_code)
    temperature = authority["temperature_codes"].get(temperature_code)
    if pin_value is None:
        raise CandidateManualReview(f"{base}: pin code {pin_code} outside official authority")
    if flash_size is None:
        raise CandidateManualReview(f"{base}: Flash code {flash_code} outside official authority")
    if package is None:
        raise CandidateManualReview(
            f"{icpn}: package code {package_code} outside official {authority['authority_id']} authority"
        )
    if temperature is None:
        raise CandidateManualReview(
            f"{icpn}: temperature code {temperature_code} outside official {authority['authority_id']} authority"
        )

    payload = _read_json(authority_path)
    grammar = payload["grammars"][authority["suffix_grammar"]]
    if option_suffix not in grammar["allowed_tails"]:
        raise CandidateManualReview(
            f"{icpn}: suffix tail {option_suffix!r} outside official {authority['suffix_grammar']} grammar"
        )

    row = {
        "manufacturer": MANUFACTURER,
        "icpn": icpn,
        "family": FAMILY,
        "series": subfamily,
        "base_device": base,
        "package": package,
        "pin_count": _resolve_pin_count(pin_value, package_code),
        "flash_size": flash_size,
        "temperature_grade": temperature,
        "option_suffix": option_suffix,
        "source_type": "official_st_datasheet_ordering_information",
        "source_reference": (
            f"{authority['document_id']} Rev {authority['revision']} p{authority['ordering_pdf_page']}"
        ),
        "source_authority": authority["datasheet_url"],
        "verification_status": "manufacturer_ordering_information_verified",
    }
    selected = list(METADATA_FIELDS) if fields is None else fields
    if any(field not in METADATA_FIELDS for field in selected):
        raise CandidateReject("unsupported metadata field request")
    return {field: row[field] for field in selected}
