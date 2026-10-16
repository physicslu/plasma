"""SWD-04 offline post-HIL restoration acceptance. Never operates the Z2."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from pl.hil.swd04.contract import (
    REQUIRED_SERVICES, RECOVERY_BIN_SHA256, SafetyError, _require,
)


def _normalize_uio(snapshot):
    records = snapshot.get("uio")
    _require(type(records) is list, "Missing UIO snapshot")
    result = []
    for item in records:
        _require(type(item) is dict, "Malformed UIO record")
        row = (item.get("name"), item.get("address"), item.get("size"))
        _require(all(isinstance(f, str) for f in row), "Incomplete UIO record")
        result.append(row)
    _require(len(set(result)) == len(result), "Duplicate UIO resource")
    return sorted(result)


def verify_restoration(before: dict, after: dict, evidence: dict) -> dict:
    """Compare hardware/OS contract by identity, never by unstable uio index."""
    for field in ("architecture", "pynq_version", "fclk0_hz"):
        _require(before.get(field) == after.get(field),
                 "Pre/post mismatch: " + field)
    _require(after.get("fpga_manager_state") == "operating",
             "FPGA manager not operating after restore")
    _require(after.get("device_model_confirmed") is True,
             "Wrong restored board identity")
    _require(before.get("fclk0_hz") == 100000000,
             "Preload FCLK0 not 100MHz")
    _require(_normalize_uio(before) == _normalize_uio(after),
             "Original UIO name/address/size bindings not restored")
    for service in REQUIRED_SERVICES:
        _require(before.get("services", {}).get(service) == "active",
                 "Preload service baseline abnormal")
        _require(after.get("services", {}).get(service) == "active",
                 "Service not restored: " + service)
    if not re.fullmatch(r"[a-f0-9]{64}",
                        str(before.get("metadata_sha256", ""))):
        raise SafetyError("Original metadata hash not recorded")
    _require(before["metadata_sha256"] == after.get("metadata_sha256"),
             "Original PYNQ metadata bytes not restored")
    _require(evidence.get("recovery_bin_sha256") == RECOVERY_BIN_SHA256,
             "Recovery firmware differs from known-good base.bin")
    required = (
        "base_bin_load_returned_operating",
        "candidate_unloaded",
        "uios_reconciled",
        "public_key_ssh_verified",
        "jupyter_http_verified",
        "gateway_live_verified",
        "gateway_ready_verified",
        "no_new_kernel_axi_or_fpga_errors",
        "no_ps7_init_or_ddr_reinitialization",
    )
    for key in required:
        _require(evidence.get(key) is True,
                 "Missing separately observed restoration evidence: " + key)
    return {
        "qualification": "SWD-04",
        "restoration": "PASS",
        "method": "offline_review_of_operator_observed_restoration_evidence",
        "z2_hil_execution": "MUST_BE_RECORDED_SEPARATELY",
        "physical_swd": "NOT_RUN",
        "real_ic_programming": "NOT_RUN",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", type=Path, required=True)
    p.add_argument("--after", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists():
        print("SWD04_RESTORE_NO_GO: refuse overwrite", file=sys.stderr)
        return 2
    try:
        before = json.loads(args.before.read_text())
        after = json.loads(args.after.read_text())
        observed = json.loads(args.evidence.read_text())
        if any(type(x) is not dict for x in (before, after, observed)):
            raise SafetyError("Evidence must be JSON objects")
        accepted = verify_restoration(before, after, observed)
        with args.output.open("x") as f:
            json.dump(accepted, f, sort_keys=True, indent=2)
            f.write("\n")
    except (ValueError, OSError, SafetyError) as exc:
        print("SWD04_RESTORE_NO_GO: " + str(exc), file=sys.stderr)
        return 2
    print("SWD04_RESTORE_OFFLINE_EVIDENCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
