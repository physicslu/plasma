#!/usr/bin/env python3
"""Historical 4.3H retained-evidence entry point backed by the generic validator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_bounded_evidence import BoundedEvidenceError
from device_catalog_evidence_framework import EvidenceFrameworkError
from stm32f2_bounded_discovery import load_spec
from stm32f2_bounded_evidence import validate as _validate

SPEC = load_spec("4.3H")
DEFAULT_BASELINE = SPEC.baseline_path
DEFAULT_EVIDENCE_DIR = SPEC.evidence_dir
STM32F2EvidenceError = BoundedEvidenceError


def validate(*, evidence_dir: Path, baseline_path: Path) -> dict[str, Any]:
    return _validate(
        phase="4.3H",
        evidence_dir=evidence_dir,
        baseline_path=baseline_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = validate(evidence_dir=args.evidence_dir, baseline_path=args.baseline)
    except (EvidenceFrameworkError, BoundedEvidenceError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
