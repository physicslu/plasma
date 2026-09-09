"""STM32F0 Phase 4.5D canonical admission row policy.

Phase 4.5C owns manufacturer-backed metadata. This adapter adds the independent
programmer/OpenOCD capability gate required for canonical admission. It does not
authorize a Production write.
"""

from __future__ import annotations

from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    CandidateManualReview,
)
from stm32f0_metadata_policy import (
    FAMILY,
    MANUFACTURER,
    METADATA_FIELDS,
    build_metadata_row,
)

TARGET_CONFIG = "tcl/target/stm32f0x.cfg"
CANONICAL_FIELDS = (
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
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
    "source_type",
    "source_reference",
    "source_authority",
    "verification_status",
)


def build_canonical_row(candidate: dict[str, Any], fields: list[str]) -> dict[str, str]:
    """Combine closed 4.5C metadata semantics with a strict 4.5D mapping gate."""

    metadata = build_metadata_row(candidate, list(METADATA_FIELDS))
    mapping = candidate.get("base_mapping")
    icpn = metadata["icpn"]
    if not isinstance(mapping, dict):
        raise CandidateManualReview(f"{icpn}: candidate lacks programming mapping")

    target_configs = mapping.get("target_configs")
    if (
        mapping.get("status") != "unique"
        or mapping.get("match_count") != 1
        or not isinstance(target_configs, list)
        or len(target_configs) != 1
    ):
        raise CandidateManualReview(
            f"{icpn}: ICPN lacks one unique OpenOCD ordering-pattern mapping"
        )
    if target_configs[0] != TARGET_CONFIG:
        raise CandidateManualReview(f"{icpn}: unexpected STM32F0 OpenOCD target mapping")
    if mapping.get("identifier_kind") != "ordering_pattern":
        raise CandidateManualReview(f"{icpn}: unexpected STM32F0 identifier kind")
    existing_identifier = mapping.get("existing_identifier")
    if not isinstance(existing_identifier, str) or not existing_identifier:
        raise CandidateManualReview(f"{icpn}: mapped ordering-pattern identifier missing")

    values = {
        **metadata,
        "cmsis_device_name": "",
        "existing_identifier": existing_identifier,
        "existing_identifier_kind": "ordering_pattern",
        "mapping_status": "deterministic_ordering_pattern",
        "openocd_target_config": target_configs[0],
    }
    if tuple(fields) != CANONICAL_FIELDS:
        raise AdmissionError("canonical CSV schema is not supported by the STM32F0 admission policy")
    if values["manufacturer"] != MANUFACTURER or values["family"] != FAMILY:
        raise AdmissionError("STM32F0 metadata identity drifted before admission")
    return {field: values[field] for field in fields}
