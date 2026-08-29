#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import AcceptanceError, Client, DEFAULT_BASE_URL
import eight_site_batch
import emode_programming
import job_cancel
import managed_ps_loopback
import pmode_batch

SCENARIOS = {
    managed_ps_loopback.SCENARIO: managed_ps_loopback.run,
    emode_programming.SCENARIO: emode_programming.run,
    job_cancel.SCENARIO: job_cancel.run,
    pmode_batch.SCENARIO: pmode_batch.run,
    eight_site_batch.SCENARIO: eight_site_batch.run,
}
SUITES = {
    "managed-software": [
        "ps-loopback",
        "emode-programming",
        "job-cancel",
        "pmode-batch",
        "eight-site-batch",
    ]
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run deployed Plasma runtime acceptance scenarios."
    )
    result.add_argument("scenario", choices=[*SCENARIOS, *SUITES])
    result.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"managed PPU BFF prefix (default: {DEFAULT_BASE_URL})",
    )
    result.add_argument(
        "--environment",
        default="managed-software",
        help="environment label recorded in evidence",
    )
    result.add_argument(
        "--evidence-root",
        type=Path,
        default=Path("artifacts/runtime-acceptance"),
        help="directory for machine-readable evidence",
    )
    result.add_argument(
        "--allow-real-hardware",
        action="store_true",
        help=(
            "allow write-capable scenarios against a non-Mock provider; use only when "
            "real-hardware execution is explicitly approved"
        ),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    client = Client(
        args.base_url,
        environment=args.environment,
        allow_real_hardware=args.allow_real_hardware,
        evidence_root=args.evidence_root,
    )
    selected = SUITES.get(args.scenario, [args.scenario])
    summary: dict[str, dict] = {}
    for name in selected:
        print(f"\n=== {name} ===")
        try:
            result = SCENARIOS[name](client)
            path = client.write_evidence(name, result)
            summary[name] = result
            print(f"PASS {name}")
            print(f"evidence: {path}")
        except Exception as exc:
            failure = {
                "result": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            path = client.write_evidence(name, failure)
            summary[name] = failure
            print(f"FAIL {name}: {exc}", file=sys.stderr)
            print(f"evidence: {path}", file=sys.stderr)
            return 1

    if len(selected) > 1:
        summary_path = client.write_evidence(
            args.scenario,
            {
                "result": "PASS",
                "scenarios": {name: item["result"] for name, item in summary.items()},
            },
        )
        print(f"\nPASS {args.scenario}")
        print(f"summary evidence: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
