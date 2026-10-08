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


def is_final_layer1_tail(row: Mapping[str, str]) -> bool:
    """Return whether a row belongs to the post-Phase-4.2 final Layer-1 tail."""

    # Historical admission membership is an identity/provenance fact.  Do not
    # couple it to mutable backend routing state: v6.16 may legitimately enrich
    # these exact identities after their Layer-1 admission.
    return (
        row.get("source_type")
        == "official_st_exact_product_authority_plus_locked_active_lifecycle"
    )


def without_final_layer1_tail(rows):
    """Return the immutable pre-v6.2 STM32F4 historical view."""

    return [row for row in rows if not is_final_layer1_tail(row)]


def admitted_after_phase42(row: Mapping[str, str], cutoff: str) -> bool:
    """Return whether a canonical row was admitted after the Phase 4.2 cutoff."""

    cutoff_rank = _phase_rank(cutoff)

    # Final v6.2 Layer-1-only identities were admitted long after all Phase 4.2
    # transactions. They intentionally have no retained Phase 4.2 evidence
    # binding. Their backend route may evolve later, but historical replays must
    # still treat them as post-Phase-4.2 additions rather than folding them into
    # old prestates.
    if is_final_layer1_tail(row):
        return True

    match = PHASE42_EVIDENCE.search(row.get("source_reference", ""))
    return match is not None and _phase_rank(match.group(1)) > cutoff_rank
