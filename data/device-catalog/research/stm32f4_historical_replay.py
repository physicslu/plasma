"""Helpers for reconstructing immutable STM32F4 Phase 4.2 catalog boundaries."""

from __future__ import annotations

import re
from collections.abc import Mapping

PHASE42_EVIDENCE = re.compile(r"(?:^|-)phase4\.2([a-z])(?:-|$)", re.IGNORECASE)


def admitted_after_phase42(row: Mapping[str, str], cutoff: str) -> bool:
    """Return whether a canonical row was admitted after the Phase 4.2 cutoff."""

    if len(cutoff) != 1 or not cutoff.isalpha():
        raise ValueError("Phase 4.2 cutoff must be one letter")
    match = PHASE42_EVIDENCE.search(row.get("source_reference", ""))
    return match is not None and match.group(1).lower() > cutoff.lower()
