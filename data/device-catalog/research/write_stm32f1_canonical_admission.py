#!/usr/bin/env python3
"""Apply a clean deterministic STM32F1 admission plan to the canonical CSV."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stm32f1_canonical_admission import AdmissionError, read_json, write_canonical_dataset

HERE = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=HERE / "stm32f1-phase2.7-admission-plan.json")
    parser.add_argument("--canonical", type=Path, default=HERE / "stm32f1-commercial-icpn.csv")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = write_canonical_dataset(plan=read_json(args.plan), canonical_path=args.canonical)
    except (AdmissionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
