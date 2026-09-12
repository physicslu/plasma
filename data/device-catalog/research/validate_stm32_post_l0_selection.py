#!/usr/bin/env python3
"""Hard-lock STM32 post-L0 next-family research selection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stm32_post_l0_selection import (
    DEFAULT_EVIDENCE,
    DEFAULT_ORDERING_REVIEW,
    FROZEN_PRODUCTION,
    build_selection,
    selection_is_clean,
)

HERE = Path(__file__).resolve().parent
SELECTION = HERE / "stm32-post-l0-next-family-selection.json"
PRIOR_SELECTION = HERE / "stm32-post-c0-next-family-selection.json"

EXPECTED_PRODUCTION_SHA256 = "c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec"
EXPECTED_RETAINED_EVIDENCE_SHA256 = "45c3020462601e6cb36e726cc1acc4203abc36a96063a5223ab5c7511bcff02c"
EXPECTED_ORDERING_REVIEW_SHA256 = "d16e71cb322c7da754ed12cc1bd0e984015888cbf8bdb07685e1d87966ad8612"
EXPECTED_PRIOR_SELECTION_SHA256 = "a46cef39516bf94901b979ccfc446b5720b2c6855b46ede1765232f6082df134"
EXPECTED_SELECTION_SHA256 = "70dd86816606e94380fe6a0b0474a88771542607fc7db2aaa3a8be65e1e2e7b8"


class ValidationError(RuntimeError):
    pass


def req(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"{path.name}: expected JSON object")
    return value


def main() -> int:
    req(sha256(FROZEN_PRODUCTION) == EXPECTED_PRODUCTION_SHA256, "post-L0 Production prestate drift")
    req(sha256(DEFAULT_EVIDENCE) == EXPECTED_RETAINED_EVIDENCE_SHA256, "retained official-ST evidence drift")
    req(sha256(DEFAULT_ORDERING_REVIEW) == EXPECTED_ORDERING_REVIEW_SHA256, "retained Ordering Information review drift")
    req(sha256(PRIOR_SELECTION) == EXPECTED_PRIOR_SELECTION_SHA256, "prior post-C0 selection drift")
    req(sha256(SELECTION) == EXPECTED_SELECTION_SHA256, "post-L0 selection bytes drift")

    frozen = read_json(SELECTION)
    generated = build_selection()
    req(generated == frozen, "post-L0 deterministic selection replay drift")
    req(selection_is_clean(generated), "post-L0 selection is not clean")

    req(generated.get("selected_next_research_family") == "STM32L4", "STM32L4 selection drift")
    req(generated.get("current_shortlist") == ["STM32L1", "STM32L4"], "post-L0 shortlist drift")
    req(generated.get("ordering_review_candidates") == ["STM32L4"], "Ordering review candidate drift")
    req(generated.get("production_prestate") == {
        "exact_icpns": 1272,
        "base_devices": 392,
        "stm32_families": 11,
        "stm32l0_exact_icpns": 360,
    }, "post-L0 Production prestate semantics drift")

    l1 = generated["candidate_evidence"]["STM32L1"]
    l4 = generated["candidate_evidence"]["STM32L4"]
    req(l1["active_candidate_targets"] == 1 and l1["lifecycle_excluded_targets"] == 3, "STM32L1 lifecycle disposition drift")
    req(l1["rejected_for_future_support"] is False, "STM32L1 was incorrectly rejected for future support")
    req(l4["active_candidate_targets"] == 24 and l4["lifecycle_excluded_targets"] == 0, "STM32L4 lifecycle disposition drift")
    req(set(generated["authority_boundaries"].values()) == {False}, "post-L0 authority boundary escaped")

    print("STM32 post-L0 next-family selection: VALID")
    print("Production prestate: 1272 exact ICPNs / 392 Base Devices / 11 families")
    print("Current shortlist: STM32L1, STM32L4")
    print("STM32L1: lifecycle-deprioritized (1/4 Active representatives)")
    print("STM32L4: selected (24/24 Active representatives; Ordering Information complete)")
    print("Production writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
