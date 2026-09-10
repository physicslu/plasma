"""STM32G4 Phase 4.9D canonical admission row policy.

Phase 4.9C owns manufacturer-backed metadata. This adapter adds an independent
OpenOCD ordering-pattern route gate for canonical admission planning.

A positive OpenOCD route is a routing capability observation only. It does not
establish Flash algorithm equivalence, option-byte/security semantics, physical
programming qualification, HIL coverage, or runtime support. CMSIS aliases are
not commercial identities and are not emitted into canonical rows.
"""
from __future__ import annotations

from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview
from stm32g4_metadata_policy import FAMILY, MANUFACTURER, METADATA_FIELDS, build_metadata_row

TARGET_CONFIG = "tcl/target/stm32g4x.cfg"
CANONICAL_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "package",
    "pin_count", "flash_size", "temperature_grade", "option_suffix",
    "cmsis_device_name", "existing_identifier", "existing_identifier_kind",
    "mapping_status", "openocd_target_config", "source_type", "source_reference",
    "source_authority", "verification_status",
)


def build_canonical_row(candidate: dict[str, Any], fields: list[str]) -> dict[str, str]:
    """Combine closed 4.9C metadata with one strict G4 ordering-pattern route."""
    metadata = build_metadata_row(candidate, list(METADATA_FIELDS))
    mapping = candidate.get("base_mapping")
    icpn = metadata["icpn"]
    if not isinstance(mapping, dict):
        raise CandidateManualReview(f"{icpn}: candidate lacks OpenOCD route mapping")
    target_configs = mapping.get("target_configs")
    if (
        mapping.get("status") != "unique"
        or mapping.get("match_count") != 1
        or not isinstance(target_configs, list)
        or target_configs != [TARGET_CONFIG]
    ):
        raise CandidateManualReview(
            f"{icpn}: exact ICPN lacks one unique STM32G4 OpenOCD ordering-pattern mapping"
        )
    if mapping.get("identifier_kind") != "ordering_pattern":
        raise CandidateManualReview(f"{icpn}: unexpected STM32G4 identifier kind")
    existing_identifier = mapping.get("existing_identifier")
    if not isinstance(existing_identifier, str) or not existing_identifier:
        raise CandidateManualReview(f"{icpn}: mapped ordering-pattern identifier missing")

    values = {
        **metadata,
        "cmsis_device_name": "",
        "existing_identifier": existing_identifier,
        "existing_identifier_kind": "ordering_pattern",
        "mapping_status": "deterministic_ordering_pattern",
        "openocd_target_config": TARGET_CONFIG,
    }
    if tuple(fields) != CANONICAL_FIELDS:
        raise AdmissionError("canonical CSV schema is not supported by STM32G4 Phase 4.9D")
    if values["manufacturer"] != MANUFACTURER or values["family"] != FAMILY:
        raise AdmissionError("STM32G4 metadata identity drifted before admission")
    return {field: values[field] for field in fields}
