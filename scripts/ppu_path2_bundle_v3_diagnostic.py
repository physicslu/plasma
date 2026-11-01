#!/usr/bin/env python3
"""Read-only, sanitized diagnosis of installed Z2 Bootstrap Bundle v3 admission.

Never reads a token, logs, arbitrary filesystem data, or mutates Z2. Uses
existing /v1/status and /v1/deployment read endpoints only. No credential
exposure, install, service restart, FPGA or DUT access.
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
DEVICE = re.compile(r"ppu-device-[0-9a-f]{16,64}\Z")


def _baseline():
    spec = importlib.util.spec_from_file_location(
        "ppu_path2_v3_diagnostic_common", ROOT / "scripts/ppu_path2_hardware_baseline.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("DIAGNOSTIC_DEPENDENCY_MISSING")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(host, device_id):
    common = _baseline()
    common._private_ipv4(host)
    probe = common.probe_status(host)
    report = {
        "schema": "plasma.ppu.bundle-v3-diagnostic.v1",
        "operation": "READ_ONLY",
        "device_id_expected": device_id,
        "device_id_observed": probe.get("device_id_observed"),
        "bootstrap_version": probe.get("bootstrap_version_observed"),
        "bootstrap_api_version": probe.get("bootstrap_api_version_observed"),
        "runtime_state": probe.get("runtime_state_observed"),
        "installed_v3_verifier": "NOT_ATTESTED",
        "b2_v3": "NOT_QUALIFIED",
        "b3": "NOT_RUN",
        "b4": "NOT_RUN",
    }
    if report["device_id_observed"] != device_id:
        report["diagnostic_status"] = "DEVICE_ID_MISMATCH"
        return report
    # Authenticated read of last deployment state; no token in output.
    token = common._existing_bootstrap_token_via_z2_ssh(host)
    client = common.DirectSSHAuthenticatedBootstrap(
        host, module=common._load_client(), token=token)
    status = client.status()
    if status.get("identity", {}).get("device_id") != device_id:
        report["diagnostic_status"] = "AUTHENTICATED_IDENTITY_MISMATCH"
        return report
    try:
        deployment = client._call("GET", "/v1/deployment", None).get("deployment")
        if isinstance(deployment, dict):
            report["last_deployment_state"] = deployment.get("state") if deployment.get("state") in {
                "queued", "running", "admitted", "failed", "succeeded", "recovery_required"
            } else "UNKNOWN"
            result = deployment.get("result")
            if isinstance(result, dict):
                report["last_deployment_stage"] = result.get("stage") if result.get("stage") in {
                    "package_admission_only", "install", "activation", "rollback"
                } else "UNKNOWN"
                plan = result.get("plan")
                if isinstance(plan, dict):
                    report["last_deployment_kind"] = plan.get("kind") if plan.get("kind") in {
                        "bundle", "python", "native-c", "fpga-image", "ppu-runtime"
                    } else "UNKNOWN"
                    report["last_bundle_schema"] = (
                        "plasma.ppu.bundle.v3" if plan.get("bundle_schema") == "plasma.ppu.bundle.v3"
                        else "NOT_V3_ATTESTED"
                    )
    except Exception:
        report["last_deployment_state"] = "NOT_AVAILABLE"
    report["diagnostic_status"] = "READ_ONLY_COMPLETE"
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--device-id", required=True)
    p.add_argument("--source-sha", required=True)
    a = p.parse_args()
    report = {"schema": "plasma.ppu.bundle-v3-diagnostic.v1",
              "operation": "READ_ONLY", "diagnostic_status": "NOT_RUN",
              "b2_v3": "NOT_QUALIFIED", "b3": "NOT_RUN", "b4": "NOT_RUN"}
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        if not SHA.fullmatch(a.source_sha) or head != a.source_sha:
            raise RuntimeError("EXACT_SOURCE_SHA_MISMATCH")
        if not DEVICE.fullmatch(a.device_id):
            raise RuntimeError("DEVICE_PIN_INVALID")
        report = run(a.host, a.device_id)
        code = 0 if report.get("diagnostic_status") == "READ_ONLY_COMPLETE" else 2
    except Exception as exc:
        report["diagnostic_status"] = "BLOCKED"
        report["error_type"] = type(exc).__name__
        code = 2
    print("PLASMA_PPU_V3_DIAGNOSTIC_JSON=" + json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
