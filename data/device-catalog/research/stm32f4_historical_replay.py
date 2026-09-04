"""Helpers for reconstructing immutable STM32F4 Phase 4.2 catalog boundaries."""

from __future__ import annotations

import re
from collections.abc import Mapping

PHASE42_EVIDENCE = re.compile(r"(?:^|-)phase4\.2([a-z]+)(?:-|$)", re.IGNORECASE)


def _phase_rank(label: str) -> int:
    """Return the spreadsheet-style rank for A..Z, AA..AZ, and later labels."""

    if re.fullmatch(r"[A-Za-z]+", label) is None:
        raise ValueError("Phase 4.2 label must contain only ASCII letters")
    rank = 0
    for character in label.lower():
        rank = rank * 26 + ord(character) - ord("a") + 1
    return rank


def admitted_after_phase42(row: Mapping[str, str], cutoff: str) -> bool:
    """Return whether a canonical row was admitted after the Phase 4.2 cutoff."""

    cutoff_rank = _phase_rank(cutoff)
    match = PHASE42_EVIDENCE.search(row.get("source_reference", ""))
    return match is not None and _phase_rank(match.group(1)) > cutoff_rank
