#!/usr/bin/env python3
"""STM32U0 product-page evidence adapter using ST Quality & Reliability authority.

For U0.2 the official Quality & Reliability table is sufficient because it binds
exact Part Number and Marketing Status in the same manufacturer-controlled row.
Sample & Buy remains useful transport/context evidence, but its dynamically rendered
status cells are not an identity/lifecycle gate for this transaction.
"""

from __future__ import annotations

from typing import Any

from st_product_page_acquisition import build_evidence_record as _build

PARSER_PROFILE = "stm32u0_quality_reliability_v1"


def build_browser_evidence_record(**kwargs: Any) -> dict[str, object]:
    record = _build(**kwargs)
    record["parser_profile"] = PARSER_PROFILE
    record["sample_buy_gates_commercial_identity"] = False
    return record


__all__ = ["PARSER_PROFILE", "build_browser_evidence_record"]
