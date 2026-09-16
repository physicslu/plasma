"""Fail-closed STM32U5 manufacturer-authoritative metadata policy.

The retained identity boundary is the 266 exact ICPNs frozen by
stm32u5-exact-orderable-identity-enumeration.json. Official ST Ordering
Information decodes metadata only; syntax never expands identity scope and
does not authorize Production admission, security mutation, debug, runtime,
or HIL support.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject

HERE = Path(__file__).resolve().parent
DEFAULT_AUTHORITY = HERE / "stm32u5-metadata-authority.json"
BASELINE = HERE / "stm32u5-metadata-policy-baseline.json"
EXACT_IDENTITY = HERE / "stm32u5-exact-orderable-identity-enumeration.json"
MANUFACTURER_DISCOVERY = HERE / "stm32u5-manufacturer-identity-discovery.json"
SECURITY = HERE / "stm32u5-security-scope-foundation.json"

MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32U5"
TRANSACTION = "stm32u5-metadata-policy"
AUTHORITY_VERSION = "stm32u5-metadata-retained266-v1"
EXPECTED_BASE_COUNT = 74
EXPECTED_EXACT_COUNT = 266
EXPECTED_BASE_SET_SHA256 = "ab83ea88d30d173e3809b3c1245691a0fb6be4a78f6fa35bd47f6caa8533bcdf"
EXPECTED_EXACT_SET_SHA256 = "ea5e3edc302a022281618ecfa73af8ac6109ad287dcf36e6f1175d20f567caf3"
PRODUCTION_EXACT_COUNT = 2017
ACTIVE_STATUS = "Active Product is in volume production."
PREVIEW_STATUS = "Preview Product is in design stage. EN"
EXPECTED_STATUS_COUNTS = {ACTIVE_STATUS: 265, PREVIEW_STATUS: 1}
EXPECTED_SUBFAMILIES = {
    "STM32U535", "STM32U545", "STM32U575", "STM32U585",
    "STM32U595", "STM32U599", "STM32U5A5", "STM32U5A9",
    "STM32U5F7", "STM32U5F9", "STM32U5G7", "STM32U5G9",
}
AUTHORITY_GROUP_BY_SUBFAMILY = {
    "STM32U535": "STM32U535", "STM32U545": "STM32U545",
    "STM32U575": "STM32U575", "STM32U585": "STM32U585",
    "STM32U595": "STM32U59xxx", "STM32U599": "STM32U59xxx",
    "STM32U5A5": "STM32U5Axxx", "STM32U5A9": "STM32U5Axxx",
    "STM32U5F7": "STM32U5Fxxx", "STM32U5F9": "STM32U5Fxxx",
    "STM32U5G7": "STM32U5Gxxx", "STM32U5G9": "STM32U5Gxxx",
}
METADATA_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device",
    "marketing_status_observed", "package", "pin_count", "flash_size",
    "temperature_grade", "dedicated_pinout", "packing", "option_suffix",
    "source_type", "source_reference", "source_authority", "verification_status",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path.name}: root must be object")
    return value


def _set_sha(values: set[str] | frozenset[str]) -> str:
    payload = "\n".join(sorted(values)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _subfamily_for_base(base: str) -> str | None:
    return next((item for item in sorted(EXPECTED_SUBFAMILIES, key=len, reverse=True) if base.startswith(item)), None)


def load_security_fence(path: Path = SECURITY) -> dict[str, Any]:
    payload = _read_json(path)
    if payload.get("transaction") != "stm32u5-security-scope-foundation" or payload.get("authority") != "research_only":
        raise AdmissionError("STM32U5 security foundation identity drifted")
    if payload.get("exact_icpn_count") != PRODUCTION_EXACT_COUNT or payload.get("series") != FAMILY:
        raise AdmissionError("STM32U5 security foundation Production/family boundary drifted")
    if set(payload.get("subfamily_scope") or []) != EXPECTED_SUBFAMILIES:
        raise AdmissionError("STM32U5 security foundation subfamily scope drifted")
    partition = payload.get("research_partition")
    if not isinstance(partition, dict):
        raise AdmissionError("STM32U5 security research partition missing")
    for key in ("manufacturer_identity_discovery_allowed", "commercial_icpn_discovery_allowed"):
        if partition.get(key) is not True:
            raise AdmissionError(f"STM32U5 security foundation no longer permits {key}")
    for key in (
        "security_semantics_supported", "option_byte_writes_allowed",
        "oem_key_provisioning_allowed", "oem_unlock_execution_allowed",
        "rdp_regression_allowed", "mass_erase_allowed", "flash_geometry_validated",
        "programming_algorithm_equivalence", "runtime_programming_supported",
        "debug_attach_supported", "hil_validated",
    ):
        if partition.get(key) is not False:
            raise AdmissionError(f"STM32U5 security fence unexpectedly open: {key}")
    return payload


def load_authority(path: Path = DEFAULT_AUTHORITY) -> dict[str, Any]:
    payload = _read_json(path)
    if (payload.get("schema_version") != 1 or payload.get("transaction") != TRANSACTION
        or payload.get("authority") != "research_only" or payload.get("authority_version") != AUTHORITY_VERSION
        or payload.get("manufacturer") != MANUFACTURER or payload.get("family") != FAMILY):
        raise AdmissionError("STM32U5 metadata authority identity/schema drifted")
    if payload.get("identity_source") != EXACT_IDENTITY.name or payload.get("parent_identity_source") != MANUFACTURER_DISCOVERY.name:
        raise AdmissionError("STM32U5 metadata authority upstream identity binding drifted")
    if payload.get("expected_base_devices") != EXPECTED_BASE_COUNT or payload.get("expected_exact_icpns") != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32U5 metadata authority cardinality drifted")
    if payload.get("expected_base_device_set_sha256") != EXPECTED_BASE_SET_SHA256 or payload.get("expected_exact_icpn_set_sha256") != EXPECTED_EXACT_SET_SHA256:
        raise AdmissionError("STM32U5 metadata authority retained-set digest drifted")
    governance = payload.get("governance")
    if not isinstance(governance, dict) or not governance or set(governance.values()) != {False}:
        raise AdmissionError("STM32U5 metadata authority escaped fail-closed governance")
    grammar = payload.get("suffix_grammar")
    if not isinstance(grammar, dict) or grammar.get("package_position") != 0 or grammar.get("temperature_position") != 1:
        raise AdmissionError("STM32U5 suffix grammar positions drifted")
    if grammar.get("packing_codes") != {"TR": "tape_and_reel"} or grammar.get("programmed_parts_wildcard_admission_authorized") is not False:
        raise AdmissionError("STM32U5 packing/wildcard grammar drifted")
    expected_docs = {
        "STM32U535": ("DS14217", 5, {"STM32U535"}), "STM32U545": ("DS14216", 5, {"STM32U545"}),
        "STM32U575": ("DS13737", 10, {"STM32U575"}), "STM32U585": ("DS13086", 10, {"STM32U585"}),
        "STM32U59xxx": ("DS13633", 3, {"STM32U595", "STM32U599"}),
        "STM32U5Axxx": ("DS13543", 3, {"STM32U5A5", "STM32U5A9"}),
        "STM32U5Fxxx": ("DS14395", 4, {"STM32U5F7", "STM32U5F9"}),
        "STM32U5Gxxx": ("DS14102", 5, {"STM32U5G7", "STM32U5G9"}),
    }
    records = payload.get("records")
    if not isinstance(records, list) or len(records) != len(expected_docs):
        raise AdmissionError("STM32U5 metadata authority requires eight ordering-authority records")
    seen, covered = set(), set()
    for record in records:
        if not isinstance(record, dict):
            raise AdmissionError("STM32U5 authority record must be object")
        series = record.get("series")
        if series not in expected_docs or series in seen:
            raise AdmissionError(f"invalid/duplicate STM32U5 authority series: {series}")
        seen.add(series)
        doc, rev, subfamilies = expected_docs[series]
        if (record.get("document_id"), record.get("revision")) != (doc, rev) or set(record.get("subfamilies") or []) != subfamilies:
            raise AdmissionError(f"{series}: datasheet/subfamily authority drifted")
        covered.update(subfamilies)
        url = record.get("datasheet_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/resource/en/datasheet/") or not url.endswith(".pdf"):
            raise AdmissionError(f"{series}: invalid official ST datasheet URL")
        for field in ("pin_codes", "pin_package_overrides", "flash", "package_codes", "temperature_codes", "dedicated_pinout_codes"):
            if not isinstance(record.get(field), dict):
                raise AdmissionError(f"{series}: invalid {field} authority")
        if record.get("dedicated_pinout_codes") != {"Q": "smps_step_down"} or record.get("retained_allowed_tails") != ["", "Q", "TR", "QTR"]:
            raise AdmissionError(f"{series}: retained suffix authority drifted")
    if seen != set(expected_docs) or covered != EXPECTED_SUBFAMILIES:
        raise AdmissionError("STM32U5 metadata authority coverage drifted")
    gaps = next(r for r in records if r["series"] == "STM32U5Gxxx").get("known_authority_gaps")
    expected_gap = [{"icpn": "STM32U5G9ZJJ3Q", "field": "temperature_grade", "code": "3", "reason": "DS14102 Rev 5 does not define temperature code 3 for STM32U5Gxxx; exact Preview identity remains retained from ST Quality & Reliability and metadata inference is blocked."}]
    if gaps != expected_gap:
        raise AdmissionError("STM32U5G exact Preview metadata authority gap drifted")
    return payload


def build_candidate_inputs() -> list[dict[str, Any]]:
    load_security_fence()
    discovery = _read_json(MANUFACTURER_DISCOVERY)
    if (discovery.get("transaction") != "stm32u5-manufacturer-identity-discovery" or discovery.get("authority") != "research_only"
        or discovery.get("manufacturer") != MANUFACTURER or discovery.get("series") != FAMILY
        or discovery.get("base_device_count") != EXPECTED_BASE_COUNT or discovery.get("base_device_set_sha256") != EXPECTED_BASE_SET_SHA256
        or discovery.get("production_exact_icpn_count") != PRODUCTION_EXACT_COUNT):
        raise AdmissionError("STM32U5 manufacturer Base Device boundary drifted")
    exact = _read_json(EXACT_IDENTITY)
    if (exact.get("schema_version") != 1 or exact.get("transaction") != "stm32u5-exact-orderable-identity-enumeration"
        or exact.get("authority") != "research_only" or exact.get("manufacturer") != MANUFACTURER or exact.get("series") != FAMILY
        or exact.get("parent_identity_discovery") != MANUFACTURER_DISCOVERY.name or exact.get("base_device_count") != EXPECTED_BASE_COUNT
        or exact.get("exact_icpn_count") != EXPECTED_EXACT_COUNT or exact.get("exact_icpn_set_sha256") != EXPECTED_EXACT_SET_SHA256
        or exact.get("production_exact_icpn_count") != PRODUCTION_EXACT_COUNT or exact.get("marketing_status_counts") != EXPECTED_STATUS_COUNTS):
        raise AdmissionError("STM32U5 retained exact identity boundary drifted")
    result = exact.get("result")
    if (not isinstance(result, dict) or result.get("complete_exact_identity_observation") is not True
        or result.get("bounded_identity_enumeration_clean") is not True or result.get("acquisition_failures") != 0
        or result.get("duplicate_exact_icpns") != 0 or result.get("synthesized_exact_icpns") != 0):
        raise AdmissionError("STM32U5 exact identity enumeration is not clean")
    claims = exact.get("claims")
    if not isinstance(claims, dict) or not claims or set(claims.values()) != {False}:
        raise AdmissionError("STM32U5 exact identity claims escaped fail-closed state")
    raw_records = exact.get("base_device_records")
    if not isinstance(raw_records, list) or len(raw_records) != EXPECTED_BASE_COUNT:
        raise AdmissionError("STM32U5 exact identity Base Device records drifted")
    bases, icpns = set(), set()
    counts = {ACTIVE_STATUS: 0, PREVIEW_STATUS: 0}
    candidates = []
    for entry in raw_records:
        if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str) or not isinstance(entry[1], list):
            raise AdmissionError("invalid STM32U5 retained Base Device record")
        base, identities = entry
        subfamily = _subfamily_for_base(base)
        if subfamily is None or base in bases:
            raise AdmissionError(f"invalid/duplicate STM32U5 Base Device: {base}")
        bases.add(base)
        for identity in identities:
            if not isinstance(identity, list) or len(identity) != 2:
                raise AdmissionError(f"{base}: invalid exact identity row")
            icpn, status = identity
            if not isinstance(icpn, str) or not isinstance(status, str) or not icpn.startswith(base) or icpn in icpns or status not in counts:
                raise AdmissionError(f"invalid retained STM32U5 identity: {icpn}")
            icpns.add(icpn); counts[status] += 1
            candidates.append({"manufacturer": MANUFACTURER, "family": FAMILY, "series": subfamily,
                "authority_group": AUTHORITY_GROUP_BY_SUBFAMILY[subfamily], "base_device": base, "icpn": icpn, "marketing_status": status})
    if counts != EXPECTED_STATUS_COUNTS:
        raise AdmissionError("STM32U5 retained marketing-status counts drifted")
    if len(bases) != EXPECTED_BASE_COUNT or _set_sha(bases) != EXPECTED_BASE_SET_SHA256:
        raise AdmissionError("STM32U5 retained Base Device set drifted")
    if len(icpns) != EXPECTED_EXACT_COUNT or _set_sha(icpns) != EXPECTED_EXACT_SET_SHA256:
        raise AdmissionError("STM32U5 retained exact ICPN set drifted")
    return sorted(candidates, key=lambda item: (item["base_device"], item["icpn"]))


@lru_cache(maxsize=1)
def retained_exact_icpns() -> frozenset[str]:
    return frozenset(item["icpn"] for item in build_candidate_inputs())


def _authority_by_group(path: Path = DEFAULT_AUTHORITY) -> dict[str, dict[str, Any]]:
    return {record["series"]: record for record in load_authority(path)["records"]}


def _decode_tail(option_suffix: str, authority: dict[str, Any]) -> tuple[str, str]:
    if option_suffix not in authority["retained_allowed_tails"]:
        raise CandidateManualReview(f"suffix tail {option_suffix!r} outside retained STM32U5 authority")
    core, packing = option_suffix, "tray_or_unspecified"
    if core.endswith("TR"):
        packing, core = "tape_and_reel", core[:-2]
    if core == "":
        dedicated = "standard"
    else:
        dedicated = authority["dedicated_pinout_codes"].get(core)
        if dedicated is None:
            raise CandidateManualReview(f"suffix tail {option_suffix!r} has unsupported dedicated-pinout semantics")
    return dedicated, packing


def build_metadata_row(candidate: dict[str, Any], fields: list[str] | None = None, *, authority_path: Path = DEFAULT_AUTHORITY) -> dict[str, str]:
    icpn, base, series = candidate.get("icpn"), candidate.get("base_device"), candidate.get("series")
    authority_group, status = candidate.get("authority_group"), candidate.get("marketing_status")
    if not all(isinstance(v, str) for v in (icpn, base, series, authority_group, status)):
        raise CandidateReject("candidate identity is incomplete")
    if icpn not in retained_exact_icpns():
        raise CandidateReject("identity is outside retained STM32U5 exact commercial scope")
    if (series not in EXPECTED_SUBFAMILIES or _subfamily_for_base(base) != series
        or AUTHORITY_GROUP_BY_SUBFAMILY.get(series) != authority_group or not icpn.startswith(base)):
        raise CandidateReject(f"invalid exact STM32U5 identity: {icpn}")
    if status not in EXPECTED_STATUS_COUNTS:
        raise CandidateReject(f"{icpn}: unsupported observed marketing status")
    authority = _authority_by_group(authority_path).get(authority_group)
    if authority is None:
        raise CandidateManualReview(f"{authority_group}: no official Ordering Information authority")
    pin_code, flash_code = base[-2], base[-1]
    suffix = icpn[len(base):]
    if len(suffix) < 2:
        raise CandidateReject(f"{icpn}: lacks package/temperature codes")
    package_code, temperature_code, option_suffix = suffix[0], suffix[1], suffix[2:]
    package = authority["package_codes"].get(package_code)
    temperature = authority["temperature_codes"].get(temperature_code)
    flash_size = authority["flash"].get(flash_code)
    pin_count = authority["pin_package_overrides"].get(f"{pin_code}:{package_code}", authority["pin_codes"].get(pin_code))
    if pin_count is None: raise CandidateManualReview(f"{base}: pin/package code outside official authority")
    if flash_size is None: raise CandidateManualReview(f"{base}: Flash code {flash_code} outside official authority")
    if package is None: raise CandidateManualReview(f"{icpn}: package code {package_code} outside official authority")
    if temperature is None: raise CandidateManualReview(f"{icpn}: temperature code {temperature_code} outside {authority['document_id']} Rev {authority['revision']} Ordering Information")
    dedicated, packing = _decode_tail(option_suffix, authority)
    row = {"manufacturer": MANUFACTURER, "icpn": icpn, "family": FAMILY, "series": series, "base_device": base,
        "marketing_status_observed": status, "package": package, "pin_count": pin_count, "flash_size": flash_size,
        "temperature_grade": temperature, "dedicated_pinout": dedicated, "packing": packing, "option_suffix": option_suffix,
        "source_type": "official_st_datasheet_ordering_information_plus_retained_exact_identity",
        "source_reference": f"{authority['document_id']} Rev {authority['revision']} Ordering Information",
        "source_authority": authority["datasheet_url"], "verification_status": "manufacturer_ordering_information_verified"}
    selected = list(METADATA_FIELDS) if fields is None else fields
    if any(field not in METADATA_FIELDS for field in selected):
        raise CandidateReject("unsupported STM32U5 metadata field request")
    return {field: row[field] for field in selected}
