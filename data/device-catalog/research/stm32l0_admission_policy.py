"""STM32L0 L0.4 canonical admission row policy.

L0.3 owns manufacturer-backed commercial metadata. L0.4 adds one independent
OpenOCD ordering-pattern routing gate for read-only canonical admission planning.
A positive route is not a physical-programming or HIL qualification claim.
"""
from __future__ import annotations

from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview
from stm32l0_metadata_policy import FAMILY, MANUFACTURER, METADATA_FIELDS, build_metadata_row
from stm32l0_phase_l0_2_discovery import commercial_core

TARGET_CONFIG = "tcl/target/stm32l0.cfg"
CANONICAL_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "package",
    "pin_count", "flash_size", "temperature_grade", "option_suffix",
    "cmsis_device_name", "existing_identifier", "existing_identifier_kind",
    "mapping_status", "openocd_target_config", "source_type", "source_reference",
    "source_authority", "verification_status",
)


def build_canonical_row(candidate: dict[str, Any], fields: list[str]) -> dict[str, str]:
    """Combine frozen L0.3 metadata with one strict L0 OpenOCD route."""
    metadata = build_metadata_row(candidate, list(METADATA_FIELDS))
    mapping = candidate.get("base_mapping")
    icpn = metadata["icpn"]
    if not isinstance(mapping, dict):
        raise CandidateManualReview(f"{icpn}: candidate lacks OpenOCD route mapping")
    ordering_pattern = mapping.get("ordering_pattern")
    if (
        mapping.get("status") != "unique"
        or mapping.get("target_config") != TARGET_CONFIG
        or not isinstance(ordering_pattern, str)
        or not ordering_pattern.endswith("x")
        or not commercial_core(icpn).startswith(ordering_pattern[:-1])
    ):
        raise CandidateManualReview(
            f"{icpn}: exact ICPN lacks one unique STM32L0 OpenOCD ordering-pattern mapping"
        )

    values = {
        **metadata,
        "cmsis_device_name": "",
        "existing_identifier": ordering_pattern,
        "existing_identifier_kind": "ordering_pattern",
        "mapping_status": "deterministic_ordering_pattern",
        "openocd_target_config": TARGET_CONFIG,
    }
    if tuple(fields) != CANONICAL_FIELDS:
        raise AdmissionError("canonical CSV schema is not supported by STM32L0 L0.4")
    if values["manufacturer"] != MANUFACTURER or values["family"] != FAMILY:
        raise AdmissionError("STM32L0 metadata identity drifted before admission")
    return {field: values[field] for field in fields}
