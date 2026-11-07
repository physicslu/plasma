#!/usr/bin/env python3
"""Path 2 Site2 deploy/diagnose/flash single entry; existing owner dispatcher only."""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "plasma.site2.path2-operations.v1"
ACCEPTED_ACTIVE_SHA = "b82ce5fd0725dacdd02a3805168e847b190841c95887ba2c567761a48024e393"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")

class OperationDenied(RuntimeError):
    pass

def require(ok: bool, reason: str) -> None:
    if not ok:
        raise OperationDenied(reason)

def source_guard(source_sha: str) -> None:
    require(type(source_sha) is str and SHA40.fullmatch(source_sha) is not None,
            "SOURCE_SHA_INVALID")
    current = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, check=True, text=True,
                             timeout=8).stdout.strip()
    require(current == source_sha, "SOURCE_SHA_MISMATCH")

def run(operation: str, source_sha: str, *, approved_once: bool = False) -> dict:
    require(operation in ("deploy", "diagnose", "flash"), "OPERATION_DENIED")
    # This flag is accidental-click protection, NOT an owner authorization.
    # The existing Issue #981 source-pinned Work Order supplies that authority.
    require(operation == "diagnose" or approved_once is True,
            "MUTATION_REQUIRES_APPROVED_ONCE")
    source_guard(source_sha)

    if operation == "diagnose":
        import plasma_site2_active_readonly_path2 as doctor
        observation = doctor.run(source_sha)
        require(observation.get("readiness") == "PASS" and
                observation.get("opf_static") == "PASS", "DIAGNOSE_NOT_READY")
        return {"schema": SCHEMA, "operation": operation, "status": "PASS",
                "observation": observation, "flash": "NOT_RUN",
                "bundle_deploy": "NOT_RUN", "fpga_reload": "NOT_RUN"}

    if operation == "deploy":
        # Existing Bootstrap B1/B2/B3 and its idempotent already-active branch;
        # never reimplement installer/SSH, reload FPGA or select Engine.
        import opf_site2_joint_acceptance as opf
        import plasma_site2_active_readonly_path2 as doctor
        receipt = opf.execute()
        require(receipt.get("result") == "PASS" and receipt.get("action") in
                ("ALREADY_ACTIVE_NO_REDEPLOY", "B3_DEPLOYED_AND_VERIFIED"),
                "DEPLOY_RECEIPT_NOT_PASS")
        active_sha = (receipt.get("asset_set_sha256") if
                      receipt["action"] == "ALREADY_ACTIVE_NO_REDEPLOY"
                      else receipt.get("new_asset_set_sha256"))
        require(type(active_sha) is str and
                re.fullmatch(r"[0-9a-f]{64}", active_sha) is not None,
                "DEPLOY_ACTIVE_SHA_INVALID")
        post = doctor.run(source_sha)
        require(post.get("readiness") == "PASS" and
                post.get("asset_set_sha256") == active_sha, "DEPLOY_POST_CHECK_DENIED")
        return {"schema": SCHEMA, "operation": operation, "status": "PASS",
                "action": receipt["action"], "asset_set_sha256": active_sha,
                "deployment_receipt": receipt, "post_diagnostic": post,
                "flash": "NOT_RUN", "fpga_reload": "NOT_RUN"}

    # Existing single POST / status poll / Readback / SAFE_OFF entry. Fixed
    # Site2, ICPN, image SHA, Provider/Profile and previously qualified Set.
    import plasma_site2_single_flash_path2 as flash
    receipt = flash.execute(source_sha, ACCEPTED_ACTIVE_SHA)
    return {"schema": SCHEMA, "operation": operation,
            "status": ("PASS" if receipt.get("flash_result") == "PASS"
                       else "FAILED_OR_OUTCOME_UNKNOWN"),
            "job": receipt,
            "submission_count": receipt.get("submission_count", "UNKNOWN"),
            "auto_retry": "DISABLED", "bundle_deploy": "NOT_RUN",
            "fpga_reload": "NOT_RUN"}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("deploy", "diagnose", "flash"))
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--approved-once", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = run(args.operation, args.source_sha,
                      approved_once=args.approved_once)
        rc = 0 if receipt["status"] == "PASS" else 1
    except Exception as exc:
        reason = (str(exc) if isinstance(exc, OperationDenied)
                  else type(exc).__name__)
        receipt = {"schema": SCHEMA, "operation": args.operation,
                   "status": ("BLOCKED_READ_ONLY" if args.operation == "diagnose"
                              else "BLOCKED_OR_OUTCOME_UNKNOWN"),
                   "reason": reason, "auto_retry": "DISABLED",
                   "submission_count": ("NOT_APPLICABLE" if
                                        args.operation == "diagnose" else "UNKNOWN")}
        rc = 69
    print("PLASMA_SITE2_PATH2_OPS=" +
          json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return rc

if __name__ == "__main__":
    raise SystemExit(main())
