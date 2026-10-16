"""LT02-05 P0 CLI: OFFLINE ONLY. No hardware access, no load authorization."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from pl.hil.lt02.contract import Candidate, SafetyError, json_object, plan


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "bit", "hwh", "manifest", "candidate-bin", "recovery-bin",
        "recovery-hwh", "approved-hashes", "inventory", "operator", "output",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists():
        print("LT02_P0_NO_GO: Refuse to overwrite evidence", file=sys.stderr)
        return 2
    try:
        candidate = Candidate(args.bit, args.hwh, args.manifest,
                              args.candidate_bin, args.recovery_bin,
                              args.recovery_hwh)
        result = plan(candidate, json_object(args.approved_hashes),
                      json_object(args.inventory), json_object(args.operator))
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except (OSError, ValueError, SafetyError) as exc:
        print("LT02_P0_NO_GO: " + str(exc), file=sys.stderr)
        return 2
    print("LT02_P0_OFFLINE_PASS_NO_LIVE_HARDWARE_AUTHORIZATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
