#!/usr/bin/env python3
"""Compatibility import for the U0.2 product-page evidence adapter.

U0.2 intentionally does not gate commercial identity on the dynamically rendered
Sample & Buy lifecycle cell. The official Quality & Reliability row is authoritative
because it co-locates exact Part Number and Marketing Status. This module keeps the
initial transaction import stable while delegating to that explicit U0 policy.
"""

from __future__ import annotations

from typing import Any

from stm32u0_product_page_evidence import PARSER_PROFILE, build_browser_evidence_record


def build_dual_surface_browser_evidence_record(**kwargs: Any) -> dict[str, object]:
    """Return U0 Q&R evidence; the legacy function name carries no dual-surface gate."""
    return build_browser_evidence_record(**kwargs)


__all__ = ["PARSER_PROFILE", "build_dual_surface_browser_evidence_record"]
