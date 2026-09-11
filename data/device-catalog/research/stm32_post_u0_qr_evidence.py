#!/usr/bin/env python3
"""Authoritative Q&R evidence adapter for the post-U0 STM32 selection probe.

Commercial identity/lifecycle authority is the official ST Quality and Reliability
row that co-locates exact Part Number and Marketing Status. Sample & Buy is not an
identity gate. This deliberately matches the authority boundary established by
STM32U0 U0.2.
"""
from __future__ import annotations

from typing import Any

from st_browser_acquisition import build_browser_evidence_record

PARSER_PROFILE = "stm32_post_u0_qr_identity_v1"
EVIDENCE_AUTHORITY = "official_st_quality_and_reliability_exact_part_number_marketing_status"
SAMPLE_BUY_IS_IDENTITY_GATE = False


def build_qr_evidence_record(**kwargs: Any) -> dict[str, object]:
    record = build_browser_evidence_record(**kwargs)
    record["parser_profile"] = PARSER_PROFILE
    record["commercial_identity_authority"] = EVIDENCE_AUTHORITY
    record["sample_buy_is_identity_gate"] = SAMPLE_BUY_IS_IDENTITY_GATE
    return record


__all__ = [
    "PARSER_PROFILE",
    "EVIDENCE_AUTHORITY",
    "SAMPLE_BUY_IS_IDENTITY_GATE",
    "build_qr_evidence_record",
]
