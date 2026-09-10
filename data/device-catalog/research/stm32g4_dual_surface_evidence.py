#!/usr/bin/env python3
"""STM32G4 retained-evidence adapter for ST dual-surface product pages."""

from __future__ import annotations

from typing import Any

from st_dual_surface_evidence import (
    EVIDENCE_SURFACE,
    dual_surface_ready,
    extract_dual_surface_part_number_records,
)
from st_dual_surface_evidence import build_dual_surface_browser_evidence_record as _build

PARSER_PROFILE = "stm32g4_dual_surface_v1"


def build_dual_surface_browser_evidence_record(**kwargs: Any) -> dict[str, object]:
    return _build(parser_profile=PARSER_PROFILE, **kwargs)


__all__ = [
    "EVIDENCE_SURFACE",
    "PARSER_PROFILE",
    "build_dual_surface_browser_evidence_record",
    "dual_surface_ready",
    "extract_dual_surface_part_number_records",
]
