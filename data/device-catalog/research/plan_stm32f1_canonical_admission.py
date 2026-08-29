#!/usr/bin/env python3
"""Create a deterministic read-only STM32F1 canonical admission plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stm32f1_canonical_admission import AdmissionError, build_admission_plan

HERE = Path(__file__).resolve().parent
DEFAULT_EVIDENCE = HERE / "evidence" / "stm32f1-phase2.6-browser-2026-08-29"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--canonical", type=Path, default=HERE / "stm32f1-commercial-icpn.csv")
    parser.add_argument("--catalog", type=Path, default=HERE / "openocd-parts-canonical.csv")
    parser.add_argument("--baseline", type=Path, default=HERE / "stm32f1-acquisition-pilot-baseline.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        plan = build_admission_plan(
            evidence_dir=args.evidence_dir,
            canonical_path=args.canonical,
            catalog_path=args.catalog,
            baseline_path=args.baseline,
        )
    except (AdmissionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
