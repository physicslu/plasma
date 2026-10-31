#!/usr/bin/env python3
"""Real PYNQ Z2 guarded B1/B2 acceptance for canonical Bundle v3 ONLY.

Run via owner-authenticated Issue #981 Path 2 operator-cli, exact PR HEAD.
Uses the already enrolled SWPC->Z2 SSH privilege to read the existing
device credential only in process memory, with pinned SSH host identity.
Never invokes Package v1/Bundle v2 admission, installs/activates/restarts
anything, loads FPGA, or interacts with DUT. B3/B4 remain NOT_RUN.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}\Z")
SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,80}\Z")


def _load_baseline():
    path = ROOT / "scripts/ppu_path2_hardware_baseline.py"
    spec = importlib.util.spec_from_file_location("ppu_v3_hardware_common", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("V3_HARDWARE_DRIVER_MISSING")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(*, host: str, device_id: str, source_sha: str, target: dict[str, str]):
    common = _load_baseline()
    report = {
        "schema": "plasma.ppu.hardware-bundle-v3-acceptance.v1",
        "bundle_schema": "plasma.ppu.bundle.v3",
        "source_sha": source_sha,
        "target": target,
        "device_id_expected": device_id,
        "b1_receive": {"status": "NOT_RUN"},
        "b2_v3_admission": {"status": "NOT_RUN"},
        "b3_stage": "NOT_RUN",
        "b4_activate_rollback": "NOT_RUN",
        "fpga": "NOT_RUN",
        "dut": "NOT_RUN",
        "installer": "NOT_RUN",
        "installed_verifier_source_sha": "NOT_ATTESTED",
        "transport_security": "PRIVATE_COMMISSIONING_HTTP_NOT_PRODUCTION_QUALIFIED",
        "qualification": "NOT_QUALIFIED",
    }
    common._private_ipv4(host)
    observed = common.probe_status(host)
    if observed.get("device_id_observed") != device_id:
        report["b1_receive"] = {"status": "BLOCKED", "code": "DEVICE_IDENTITY_MISMATCH"}
        return report
    report["device_id_observed"] = device_id
    report["bootstrap_version_observed"] = observed.get("bootstrap_version_observed")
    report["runtime_state_observed"] = observed.get("runtime_state_observed")

    # Only use existing enrolled SSH/sudo and existing device-bound credential.
    # Never persist or print the token, not even during error handling.
    token = common._existing_bootstrap_token_via_z2_ssh(host)
    module = common._load_client()
    api = common.DirectSSHAuthenticatedBootstrap(host, module=module, token=token)
    status = api.status()
    if (status.get("identity", {}).get("device_id") != device_id
            or status.get("bootstrap", {}).get("state") != "bootstrap_ready"):
        report["b1_receive"] = {"status": "BLOCKED", "code": "AUTHENTICATED_DEVICE_MISMATCH"}
        return report
    deployment = status.get("deployment")
    if (status.get("runtime", {}).get("state") == "recovery_required"
            or (isinstance(deployment, dict) and
                deployment.get("state") in ("queued", "running", "recovery_required"))):
        report["b1_receive"] = {"status": "BLOCKED", "code": "ACTIVE_OR_RECOVERY_DEPLOYMENT"}
        return report

    # Single canonical fixture; never invoke sample_v1() or v1 admission.
    raw = common.sample_v3(source_sha, target)
    try:
        b1 = common.b1_upload(api, module, raw)
    except Exception as exc:
        report["b1_receive"] = {"status": "FAIL", "code": type(exc).__name__}
        return report
    report["b1_receive"] = b1
    try:
        receipt = common.b2_admission(
            api, b1["upload_id"], source_sha, target,
            b1["archive_sha256"], kind="bundle",
        )
        report["b2_v3_admission"] = receipt
        report["qualification"] = "B1_B2_V3_PASS_B3_B4_NOT_RUN"
    except Exception as exc:
        report["b2_v3_admission"] = {
            "status": "NOT_QUALIFIED", "code": type(exc).__name__,
        }
        report["qualification"] = "B1_PASS_B2_V3_NOT_QUALIFIED"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Guarded real Z2 Bundle v3 B1/B2 only")
    parser.add_argument("--host", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--board", required=True)
    parser.add_argument("--fpga-part", required=True)
    args = parser.parse_args(argv)
    report = {
        "schema": "plasma.ppu.hardware-bundle-v3-acceptance.v1",
        "b1_receive": "NOT_RUN", "b2_v3_admission": "NOT_RUN",
        "b3_stage": "NOT_RUN", "b4_activate_rollback": "NOT_RUN",
        "qualification": "NOT_QUALIFIED",
    }
    try:
        actual_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, check=True, timeout=5,
        ).stdout.strip()
        target = {
            "platform": args.platform, "board": args.board,
            "fpga_part": args.fpga_part,
        }
        if not SHA.fullmatch(args.source_sha) or actual_sha != args.source_sha:
            raise RuntimeError("EXACT_SOURCE_SHA_MISMATCH")
        if not re.fullmatch(r"ppu-device-[0-9a-f]{16,64}", args.device_id):
            raise RuntimeError("DEVICE_PIN_INVALID")
        if any(not SAFE.fullmatch(x) for x in target.values()):
            raise RuntimeError("TARGET_PIN_INVALID")
        report = run(host=args.host, device_id=args.device_id,
                     source_sha=args.source_sha, target=target)
        result = 0 if report["b1_receive"].get("status") == "PASS" else 1
    except Exception as exc:
        # Sanitized result only; never print network responses, SSH output or token.
        code = str(exc) if isinstance(exc, RuntimeError) and str(exc) in {
            "EXACT_SOURCE_SHA_MISMATCH", "DEVICE_PIN_INVALID", "TARGET_PIN_INVALID",
            "V3_HARDWARE_DRIVER_MISSING",
        } else type(exc).__name__
        report["error_code"] = code
        result = 69
    print("PLASMA_PPU_V3_HARDWARE_ACCEPTANCE_JSON=" +
          json.dumps(report, sort_keys=True, separators=(",", ":")))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
