#!/usr/bin/env python3
"""Validate one STM32U0 U0.2 live summary against frozen U0.1 controls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32u0_phase_u0_1_foundation import EXPECTED_EXACT_ICPNS
from stm32u0_phase_u0_2_discovery import MAX_TARGETS, discovery_is_clean


def validate_summary(payload: dict[str, object]) -> dict[str, object]:
    if payload.get("schema_version") != 1 or payload.get("phase") != "U0.2" or payload.get("family") != "STM32U0":
        raise AcquisitionError("unexpected STM32U0 U0.2 live summary identity")
    if not discovery_is_clean(payload):
        raise AcquisitionError("STM32U0 U0.2 live summary is not a clean bounded discovery")
    if payload.get("attempted") != MAX_TARGETS:
        raise AcquisitionError("STM32U0 U0.2 target count drifted")
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != MAX_TARGETS:
        raise AcquisitionError("STM32U0 U0.2 live results must cover all deterministic targets")

    by_base: dict[str, dict[str, object]] = {}
    active_icpns: set[str] = set()
    for raw in results:
        if not isinstance(raw, dict):
            raise AcquisitionError("STM32U0 U0.2 result must be an object")
        base = raw.get("base_device")
        if not isinstance(base, str) or base in by_base:
            raise AcquisitionError(f"duplicate/invalid STM32U0 U0.2 Base Device: {base!r}")
        by_base[base] = raw
        if raw.get("acquisition_status") != "success":
            continue
        evidence = raw.get("evidence")
        if not isinstance(evidence, dict):
            raise AcquisitionError(f"{base}: successful live result lacks evidence")
        exact = evidence.get("exact_icpns")
        if not isinstance(exact, list) or not all(isinstance(value, str) for value in exact):
            raise AcquisitionError(f"{base}: invalid exact ICPN list")
        for icpn in exact:
            if icpn in active_icpns:
                raise AcquisitionError(f"duplicate Active exact ICPN across Base Devices: {icpn}")
            active_icpns.add(icpn)

    representative_drift: dict[str, dict[str, list[str]]] = {}
    for base, expected in EXPECTED_EXACT_ICPNS.items():
        result = by_base.get(base)
        if result is None or result.get("acquisition_status") != "success":
            raise AcquisitionError(f"U0.1 representative unavailable in U0.2 live evidence: {base}")
        evidence = result.get("evidence")
        assert isinstance(evidence, dict)
        observed = sorted(str(value) for value in evidence.get("exact_icpns", []))
        frozen = sorted(expected)
        if observed != frozen:
            representative_drift[base] = {"u0_1_retained": frozen, "u0_2_observed": observed}
    if representative_drift:
        raise AcquisitionError(
            "U0.1 representative exact-ICPN drift requires manual review: "
            + json.dumps(representative_drift, sort_keys=True)
        )

    return {
        "target_count": MAX_TARGETS,
        "active_exact_icpn_count": len(active_icpns),
        "u0_1_representative_controls": len(EXPECTED_EXACT_ICPNS),
        "representative_drift": False,
        "canonical_admission_authorized": False,
        "production_write_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.summary.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AcquisitionError("live summary must be a JSON object")
    print(json.dumps(validate_summary(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
