"""Host-only SWD-04 Gate P0. No hardware access is implemented here."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pl.hil.swd04.contract import Candidate, SafetyError, plan


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bit", type=Path, required=True)
    p.add_argument("--hwh", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--recovery-bin", type=Path, required=True)
    p.add_argument("--recovery-hwh", type=Path, required=True)
    p.add_argument("--inventory", type=Path, required=True,
                   help="Read-only operator-collected JSON evidence")
    p.add_argument("--attestation", type=Path, required=True,
                   help="Manually acknowledged UART/power/isolation readiness")
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    candidate = Candidate(args.bit, args.hwh, args.manifest,
                          args.recovery_bin, args.recovery_hwh)
    try:
        inventory = json.loads(args.inventory.read_text())
        attestation = json.loads(args.attestation.read_text())
        if type(inventory) is not dict or type(attestation) is not dict:
            raise SafetyError("Inventory/attestation must be JSON objects")
        report = plan(candidate, inventory, attestation)
    except (ValueError, OSError, SafetyError) as exc:
        print("SWD04_P0_NO_GO: " + str(exc), file=sys.stderr)
        return 2
    content = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            print("SWD04_P0_NO_GO: output already exists", file=sys.stderr)
            return 2
        with args.output.open("x") as f:
            f.write(content)
    else:
        print(content, end="")
    print("SWD04_P0_OFFLINE_PASS_NO_HARDWARE_ACTION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
