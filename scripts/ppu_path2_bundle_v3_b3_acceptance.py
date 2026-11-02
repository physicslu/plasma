#!/usr/bin/env python3
"""Path 2 guarded real Z2 Bundle v3 B1/B2/B3 and explicit Python smoke.

Requires the existing trusted Issue #981 exact PR-HEAD operator-cli dispatcher,
an already qualified factory-pinned B3 Bootstrap on Z2 and enrolled SSH.
No Bootstrap upgrade writer, service restart, FPGA load or DUT operation.
When any precondition is absent: stop, emit redacted NOT_RUN/BLOCKED evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
DEVICE = re.compile(r"ppu-device-[0-9a-f]{16,64}\Z")
SMOKE_LINES = ("SMOKE_VERSION=0.1.0", "ICPN=STM32F103C8T6",
               "FLASH_BYTES=65536", "PASS")
TARGET = {"platform": "linux-armv7", "board": "pynq-z2",
          "fpga_part": "xc7z020clg400-1"}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("SOURCE_MODULE_NOT_AVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def report_template(source_sha: str, device_id: str):
    return {
        "schema": "plasma.ppu.path2-b3-smoke.v1",
        "source_sha": source_sha, "device_id_expected": device_id,
        "bundle_schema": "plasma.ppu.bundle.v3",
        "b1_receive": "NOT_RUN", "b2_admission": "NOT_RUN",
        "b3_install": "NOT_RUN", "smoke_execution": "NOT_RUN",
        "factory_bootstrap": "NOT_VERIFIED",
        "fpga": "NOT_RUN", "dut": "NOT_RUN",
        "transport_security": "PRIVATE_COMMISSIONING_HTTP_NOT_PRODUCTION_QUALIFIED",
    }


def run(host: str, device_id: str, source_sha: str, *, interval: float = 1):
    common = load("ppu_b3_path2_common", ROOT / "scripts/ppu_path2_hardware_baseline.py")
    builder = load("ppu_b3_path2_builder", ROOT / "scripts/ppu-bundle-v3-smoke.py")
    report = report_template(source_sha, device_id)
    common._private_ipv4(host)
    initial = common.probe_status(host)
    if initial.get("device_id_observed") != device_id:
        report["reason"] = "Z2_PINNED_DEVICE_ID_MISMATCH"
        return report, 69
    report["device_id_observed"] = device_id
    # Only after pinned device verification may the existing enrolled SSH
    # helper fetch the device-bound Bootstrap token in process memory.
    token = common._existing_bootstrap_token_via_z2_ssh(host)
    client = common.DirectSSHAuthenticatedBootstrap(
        host, module=common._load_client(), token=token,
    )
    status = client.status()
    if (status.get("identity", {}).get("device_id") != device_id
            or status.get("bootstrap", {}).get("state") != "bootstrap_ready"):
        report["reason"] = "B3_AUTHENTICATED_DEVICE_NOT_READY"
        return report, 69
    deployed = status.get("deployment")
    if (status.get("runtime", {}).get("state") == "recovery_required"
            or (type(deployed) is dict and deployed.get("state") in (
                "queued", "running", "recovery_required"
            ))):
        report["reason"] = "B3_ACTIVE_OR_RECOVERY_DEPLOYMENT"
        return report, 69
    if status.get("capabilities", {}).get("bundle_v3_b3_install") is not True:
        report["reason"] = "B3_FACTORY_INSTALLER_NOT_INSTALLED"
        return report, 69
    report["factory_bootstrap"] = "READY_CAPABILITY_REPORTED"

    with tempfile.TemporaryDirectory(prefix="plasma-ppu-b3-") as temp:
        artifact = Path(temp) / "ppu-b3-smoke.zip"
        digest = builder.make_bundle(artifact, source_sha)
        raw = artifact.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            report["reason"] = "LOCAL_ARCHIVE_DIGEST_CHANGED"
            return report, 2
        report["archive_sha256"] = digest
        # B1 includes a negative chunk-SHA test before the positive upload.
        b1 = common.b1_upload(client, common._load_client(), raw)
        report["b1_receive"] = b1
        if b1.get("status") != "PASS":
            report["reason"] = "B1_NOT_PROVEN"
            return report, 2
        # B2 admission is data-only; it cannot by itself grant installation.
        b2 = common.b2_admission(client, b1["upload_id"], source_sha,
                                 TARGET, digest, kind="bundle")
        report["b2_admission"] = b2
        if b2.get("status") != "PASS":
            report["reason"] = "B2_NOT_PROVEN"
            return report, 2
        b3 = client._call("POST", "/v1/deployments", {
            "kind": "bundle", "upload_id": b1["upload_id"], "install_only": True,
        }).get("deployment")
        if type(b3) is not dict or b3.get("state") not in ("queued", "running"):
            report["reason"] = "B3_START_RECEIPT_INVALID"
            return report, 2
        tx_id = b3.get("transaction_id")
        if not isinstance(tx_id, str) or not re.fullmatch(r"[0-9a-f]{32}", tx_id):
            report["reason"] = "B3_TRANSACTION_ID_INVALID"
            return report, 2
        end = time.monotonic() + 120
        while time.monotonic() < end:
            latest = client._call("GET", "/v1/deployment", None).get("deployment")
            if type(latest) is not dict or latest.get("transaction_id") != tx_id:
                report["reason"] = "B3_TRANSACTION_CHANGED"
                return report, 2
            state = latest.get("state")
            if state in ("failed", "recovery_required"):
                report["b3_install"] = "FAIL_RECOVERY_REQUIRED"
                report["reason"] = "B3_INSTALL_FAILED_OR_UNKNOWN"
                return report, 2
            if state == "succeeded":
                evidence = latest.get("result")
                if (type(evidence) is not dict
                        or evidence.get("stage") != "bundle_install_only"
                        or evidence.get("archive_sha256") != digest
                        or evidence.get("source_commit") != source_sha
                        or evidence.get("runtime_activation_executed") is not False
                        or evidence.get("fpga") != "NOT_RUN"
                        or evidence.get("dut") != "NOT_RUN"):
                    report["reason"] = "B3_INSTALL_EVIDENCE_MISMATCH"
                    return report, 2
                correlation = evidence.get("coordinator_receipt")
                if (type(correlation) is not dict
                        or correlation.get("api_transaction_id") != tx_id
                        or correlation.get("coordinator_state") != "bundle_installed"):
                    report["reason"] = "B3_JOURNAL_CORRELATION_MISMATCH"
                    return report, 2
                report["b3_install"] = {
                    "status": "PASS",
                    "api_transaction_id": tx_id,
                    "coordinator_transaction_id": correlation["coordinator_transaction_id"],
                    "archive_sha256": digest,
                    "files_verified": evidence.get("files_verified"),
                    "package_order": evidence.get("package_order"),
                }
                break
            if state not in ("queued", "running"):
                report["reason"] = "B3_UNEXPECTED_API_STATE"
                return report, 2
            time.sleep(interval)
        else:
            report["reason"] = "B3_TIMEOUT_OUTCOME_UNCERTAIN"
            return report, 2

    # Explicitly execute only the reviewed smoke payload, as an unprivileged
    # Z2 user via the existing pinned SSH/sudo transport. Never execute
    # arbitrary scripts from a user-supplied Bundle manifest or as root.
    helper = load("ppu_b3_existing_ssh", ROOT / "scripts/plasma_wordport_program.py")
    credentials, known_hosts = helper.z2_login_credentials(Path.home())
    if credentials["ssh_host"] != host:
        report["reason"] = "Z2_SSH_HOST_PIN_MISMATCH"
        return report, 2
    cmd = [
        "runuser", "-u", "nobody", "--",
        "/usr/bin/python3", "-I", "-B",
        "/opt/plasma/bundles/ppu-b3-smoke/payload/packages/python-smoke/python/smoke.py",
        "--root", "/opt/plasma/bundles/ppu-b3-smoke",
    ]
    code, output = helper.password_ssh_z2(cmd, credentials, known_hosts, timeout=45)
    observed = [line.strip() for line in output.splitlines() if line.strip() in SMOKE_LINES]
    if code != 0 or observed != list(SMOKE_LINES):
        report["smoke_execution"] = "FAIL"
        report["reason"] = "B3_SMOKE_EXECUTION_NOT_PROVEN"
        return report, 2
    report["smoke_execution"] = {
        "status": "PASS", "version": "0.1.0",
        "icpn_fixture": "STM32F103C8T6", "flash_bytes_fixture": 65536,
        "run_as": "nobody",
    }
    return report, 0


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--device-id", required=True)
    p.add_argument("--source-sha", required=True)
    a = p.parse_args(argv)
    report = report_template(a.source_sha, a.device_id)
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT,
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if not HEX40.fullmatch(a.source_sha) or head != a.source_sha:
            raise RuntimeError("EXACT_SOURCE_SHA_MISMATCH")
        if not DEVICE.fullmatch(a.device_id):
            raise RuntimeError("DEVICE_ID_PIN_INVALID")
        report, code = run(a.host, a.device_id, a.source_sha)
    except Exception as exc:
        # Never include raw SSH/API responses or credential bytes in evidence.
        report["reason"] = (
            str(exc) if type(exc) is RuntimeError and str(exc) in (
                "EXACT_SOURCE_SHA_MISMATCH", "DEVICE_ID_PIN_INVALID"
            ) else type(exc).__name__
        )
        # Generic errors may have occurred AFTER a real B1/B2/B3 mutation.
        # Never relabel an attempted physical operation as preflight NOT_RUN.
        code = 69 if report["reason"] in (
            "EXACT_SOURCE_SHA_MISMATCH", "DEVICE_ID_PIN_INVALID"
        ) else 2
    print("PLASMA_PPU_PATH2_B3_JSON=" + json.dumps(
        report, sort_keys=True, separators=(",", ":"),
    ))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
