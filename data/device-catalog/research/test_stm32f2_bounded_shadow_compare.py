#!/usr/bin/env python3
from __future__ import annotations

import copy
import json

from stm32f2_bounded_discovery import load_spec
from stm32f2_bounded_shadow import compare_shadow_summaries

PHASE = "4.3H"


def main() -> int:
    spec = load_spec(PHASE)
    retained = json.loads(
        (spec.evidence_dir / "pilot-summary.json").read_text(encoding="utf-8")
    )

    clean = compare_shadow_summaries(
        phase=PHASE,
        live=copy.deepcopy(retained),
        retained=retained,
    )
    assert clean["status"] == "clean"
    assert clean["structural_errors"] == []
    assert clean["source_drift"] == []

    source_drift = copy.deepcopy(retained)
    result = source_drift["results"][0]
    removed_icpn = result["evidence"]["exact_icpns"].pop()
    result["candidate_mappings"] = [
        item for item in result["candidate_mappings"] if item["icpn"] != removed_icpn
    ]
    result["canonical_mapping"]["candidate_count"] -= 1
    source_drift["active_exact_icpn_candidates"] -= 1

    drift_report = compare_shadow_summaries(
        phase=PHASE,
        live=source_drift,
        retained=retained,
    )
    assert drift_report["status"] == "source_drift"
    assert drift_report["structural_errors"] == []
    assert drift_report["source_drift"][0]["active_exact_icpns_removed"] == [removed_icpn]

    regression = copy.deepcopy(retained)
    regression["results"][0]["candidate_mappings"][0]["status"] = "ambiguous"
    regression_report = compare_shadow_summaries(
        phase=PHASE,
        live=regression,
        retained=retained,
    )
    assert regression_report["status"] == "software_regression"
    assert regression_report["structural_errors"]

    target_drift = copy.deepcopy(retained)
    target_drift["results"][0]["base_device"] = "STM32F205RF"
    target_report = compare_shadow_summaries(
        phase=PHASE,
        live=target_drift,
        retained=retained,
    )
    assert target_report["status"] == "software_regression"
    assert target_report["structural_errors"]

    print("STM32F2 bounded shadow comparator PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
