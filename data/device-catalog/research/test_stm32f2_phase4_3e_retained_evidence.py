#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from validate_stm32f2_phase4_3e_retained_evidence import (
    DEFAULT_BASELINE,
    DEFAULT_EVIDENCE_DIR,
    STM32F2EvidenceError,
    validate,
)


def main() -> int:
    report = validate(evidence_dir=DEFAULT_EVIDENCE_DIR, baseline_path=DEFAULT_BASELINE)
    assert report["status"] == "valid"
    assert report["targets"] == 4
    assert report["active_exact_icpn_candidates"] == 13
    assert report["excluded_non_active_part_numbers"] == 0
    assert report["unique_openocd_mappings"] == 13
    assert report["production_admission_ready"] is False

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        evidence = root / "evidence"
        shutil.copytree(DEFAULT_EVIDENCE_DIR, evidence)
        summary_path = evidence / "pilot-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["results"][0]["evidence"]["exact_icpns"].append("STM32F205RCT8")
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            validate(evidence_dir=evidence, baseline_path=DEFAULT_BASELINE)
        except (STM32F2EvidenceError, RuntimeError):
            pass
        else:
            raise AssertionError("mutated retained evidence must fail closed")

    print("Phase 4.3E STM32F2 retained evidence PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
