#!/usr/bin/env python3
"""PLASMA Path 2 physical PPU Package B1/B2 acceptance.

Owner-approved operator-cli / guarded-hardware ONLY. This script has exactly
one private-LAN Bootstrap ingress. It NEVER installs, activates, invokes SSH,
runs shell, loads FPGA, changes Site state or programs DUT. No token in argv,
stdout, Github Work Order or evidence. A commissioning HTTP bearer is only
acceptable over a physically controlled isolated network.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile
from io import BytesIO
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,80}\Z")
SCHEMA = "plasma.ppu.hardware-package-baseline.v1"
TOKEN_ENV = "PLASMA_PPU_BOOTSTRAP_TOKEN_FILE"
HOST_ENV = "PLASMA_PPU_COMMISSIONING_ALLOWED_IP"
CLIENT_PATH = ROOT / "scripts/ppu_deploy_api.py"


class BaselineError(RuntimeError):
    pass


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_client():
    spec = importlib.util.spec_from_file_location("ppu_hardware_baseline_api", CLIENT_PATH)
    if spec is None or spec.loader is None:
        raise BaselineError("BASELINE_API_CLIENT_MISSING")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _token_from_private_file(path: Path) -> str:
    # No token in a Work Order, CLI argument, a stdout receipt or GitHub log.
    if not path.is_absolute() or path.is_symlink():
        raise BaselineError("PRIVATE_TOKEN_FILE_DENIED")
    s = path.stat()
    if (not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode) != 0o600
            or s.st_uid != os.geteuid() or s.st_size < 32 or s.st_size > 512):
        raise BaselineError("PRIVATE_TOKEN_FILE_UNSAFE")
    token = path.read_text(encoding="ascii").strip()
    if len(token) < 32 or len(token) > 512 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise BaselineError("PRIVATE_TOKEN_INVALID")
    return token


def _private_ipv4(host: str) -> str:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as exc:
        raise BaselineError("PPU_IP_LITERAL_REQUIRED") from exc
    if (addr.version != 4 or not addr.is_private or addr.is_loopback
            or addr.is_link_local or addr.is_multicast or addr.is_unspecified):
        raise BaselineError("PPU_PRIVATE_LAN_ONLY")
    if host != os.environ.get(HOST_ENV):
        raise BaselineError("PPU_ALLOWED_IP_PIN_MISSING_OR_MISMATCH")
    return host


def _commissioning_transport(host: str):
    """Direct, pinned, no proxy, no redirect. NOT production TLS."""
    _private_ipv4(host)

    def request(method: str, path: str, payload: bytes | None,
                headers: Mapping[str, str]) -> tuple[int, bytes]:
        if (method not in ("GET", "POST") or not path.startswith("/v1/")
                or ".." in path or "?" in path or "#" in path or "\\" in path
                or any(ord(c) < 33 or ord(c) > 126 for c in path)):
            raise BaselineError("TRANSPORT_PATH_DENIED")
        connection = http.client.HTTPConnection(host, 18081, timeout=10)
        try:
            connection.request(method, path, body=payload, headers=dict(headers))
            result = connection.getresponse()
            data = result.read(2 * 1024 * 1024 + 1)
            return result.status, data
        finally:
            connection.close()
    return request


def _git_head() -> str:
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True, timeout=5, check=True)
    return res.stdout.strip()


def _zipped(manifest: Mapping[str, Any], entries: Mapping[str, bytes]) -> bytes:
    result = BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as out:
        for path, data in [("manifest.json", json.dumps(
                manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")),
                *sorted(entries.items())]:
            info = zipfile.ZipInfo(path, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            out.writestr(info, data)
    return result.getvalue()


def _file(path: str, data: bytes) -> dict[str, Any]:
    return {"path": path, "size": len(data), "sha256": _sha(data), "executable": False}


def sample_v1(source_sha: str, target: Mapping[str, str], *, corrupt_file_sha: bool = False,
              mismatch_target: bool = False) -> bytes:
    content = b"# PLASMA hardware baseline - data only, never executed\n"
    path = "payload/python/baseline.py"
    meta = _file(path, content)
    if corrupt_file_sha:
        meta["sha256"] = "0" * 64
    manifest = {
        "schema": "plasma.ppu.package.v1",
        "name": "hardware-baseline-b1",
        "kind": "python",
        "version": "1.0.0",
        "source_commit": source_sha,
        "target": dict(target),
        "files": [meta],
    }
    if mismatch_target:
        manifest["target"]["board"] = "mismatch-board"
    return _zipped(manifest, {path: content})


def sample_v2(source_sha: str, target: Mapping[str, str]) -> bytes:
    first_path = "payload/components/catalog/data/ic.json"
    second_path = "payload/components/profile/data/geometry.json"
    first = b'{"ic":"safe-host-only-fixture"}'
    second = b'{"flash_size":65536}'
    manifest = {
        "schema": "plasma.ppu.bundle.v2",
        "name": "hardware-baseline-bundle",
        "version": "1.0.0",
        "purpose": "diagnostics",
        "source_commit": source_sha,
        "target": dict(target),
        "components": [
            {"id": "catalog", "kind": "ic-catalog", "version": "1.0.0",
             "requires": [], "files": [_file(first_path, first)]},
            {"id": "profile", "kind": "programming-profile", "version": "1.0.0",
             "requires": ["catalog"], "files": [_file(second_path, second)]},
        ],
    }
    return _zipped(manifest, {first_path: first, second_path: second})


def _expect_http_rejection(api, method: str, path: str, body: dict, error: str) -> None:
    try:
        api._call(method, path, body)
    except Exception as exc:
        if not isinstance(exc, error):
            raise BaselineError("NEGATIVE_WRONG_ERROR_CLASS") from exc
        if "API_HTTP_REJECTED:409" not in str(exc):
            raise BaselineError("NEGATIVE_NOT_REJECTED_AS_409") from None
    else:
        raise BaselineError("NEGATIVE_UNEXPECTEDLY_ACCEPTED")


def b1_upload(api, client_module, data: bytes) -> dict[str, Any]:
    """Real upload, tampered-chunk denial and exact committed SHA256."""
    digest = _sha(data)
    created = api._call("POST", "/v1/uploads", {"size": len(data), "sha256": digest})
    upload = created.get("upload")
    uid = upload.get("upload_id") if isinstance(upload, dict) else None
    if type(uid) is not str or not HEX32.fullmatch(uid):
        raise BaselineError("B1_UPLOAD_ID_INVALID")
    first = data[:min(4096, len(data))]
    _expect_http_rejection(api, "POST", f"/v1/uploads/{uid}/chunks", {
        "offset": 0, "data_base64": base64.b64encode(first).decode(),
        "sha256": "0" * 64,
    }, client_module.DeploymentAPIError)
    offset = 0
    for start in range(0, len(data), 1024 * 1024):
        part = data[start:start + 1024 * 1024]
        reply = api._call("POST", f"/v1/uploads/{uid}/chunks", {
            "offset": offset, "data_base64": base64.b64encode(part).decode(),
            "sha256": _sha(part),
        })
        meta = reply.get("upload")
        offset += len(part)
        if not isinstance(meta, dict) or meta.get("received_bytes") != offset:
            raise BaselineError("B1_CHUNK_PROGRESS_INVALID")
    committed = api._call("POST", f"/v1/uploads/{uid}/commit", {}).get("upload")
    if (not isinstance(committed, dict)
            or committed.get("state") != "committed"
            or committed.get("upload_id") != uid
            or committed.get("sha256") != digest):
        raise BaselineError("B1_COMMIT_RECEIPT_INVALID")
    return {"status": "PASS", "upload_id": uid, "archive_sha256": digest,
            "bytes_received": len(data), "negative_chunk_sha256": "REJECTED"}


def b2_admission(api, uid: str, source_sha: str, target: Mapping[str, str],
                 digest: str, *, kind: str) -> dict[str, Any]:
    submission = api.submit(kind=kind, upload_id=uid)
    if submission.state != "admitted":
        raise BaselineError("B2_NOT_ADMITTED")
    r = api.deployment_state(submission.transaction_id)
    result = r["result"]
    plan = result["plan"]
    if (result["stage"] != "package_admission_only"
            or result["install_qualified"] is not False
            or plan["execution_permitted"] is not False
            or plan["source_commit"] != source_sha
            or plan["target"] != dict(target)
            or plan["archive_sha256"] != digest
            or plan["kind"] != kind):
        raise BaselineError("B2_INCORRECT_RECEIPT")
    return {"status": "PASS", "transaction_id": submission.transaction_id,
            "archive_sha256": digest, "stage": result["stage"],
            "execution_permitted": False, "install_qualified": False,
            "kind": kind}


def b2_negative(api, client_module, source_sha: str, target: Mapping[str, str]) -> dict[str, str]:
    failed = sample_v1(source_sha, target, corrupt_file_sha=True)
    uid = api.upload(failed)
    _expect_http_rejection(api, "POST", "/v1/deployments",
                           {"kind": "python", "upload_id": uid},
                           client_module.DeploymentAPIError)
    mismatched = sample_v1(source_sha, target, mismatch_target=True)
    uid2 = api.upload(mismatched)
    _expect_http_rejection(api, "POST", "/v1/deployments",
                           {"kind": "python", "upload_id": uid2},
                           client_module.DeploymentAPIError)
    return {"wrong_file_sha256": "REJECTED", "wrong_target": "REJECTED"}


def run(api, client_module, *, source_sha: str, target: Mapping[str, str],
        expected_device_id: str) -> dict[str, Any]:
    """Distinct B1, B2-v1, B2-v2 verdicts; no installation ever."""
    report: dict[str, Any] = {
        "schema": SCHEMA, "source_sha": source_sha, "target": dict(target),
        "device_id": None, "b1": {"status": "NOT_RUN"},
        "b2_v1": {"status": "NOT_RUN"}, "b2_v2": {"status": "NOT_RUN"},
        "b3_install": "NOT_RUN", "b4_activation_rollback": "NOT_RUN",
        "fpga": "NOT_RUN", "dut": "NOT_RUN",
        "transport_security": "PRIVATE_COMMISSIONING_HTTP_NOT_PRODUCTION_QUALIFIED",
        "baseline_qualification": "NOT_QUALIFIED",
    }
    status = api.status()
    info = status.get("identity")
    actual = info.get("device_id") if isinstance(info, dict) else None
    if (type(actual) is not str or actual != expected_device_id
            or status.get("bootstrap", {}).get("state") != "bootstrap_ready"):
        report["b1"] = {"status": "BLOCKED", "code": "PINNED_DEVICE_IDENTITY_MISMATCH"}
        return report
    report["device_id"] = actual
    if status.get("runtime", {}).get("state") == "recovery_required" or (
            isinstance(status.get("deployment"), dict) and
            status["deployment"].get("state") in ("queued", "running", "recovery_required")):
        report["b1"] = {"status": "BLOCKED", "code": "PPU_RECOVERY_OR_ACTIVE_DEPLOYMENT"}
        return report
    raw_v1 = sample_v1(source_sha, target)
    try:
        b1 = b1_upload(api, client_module, raw_v1)
        report["b1"] = b1
    except Exception as exc:
        report["b1"] = {"status": "FAIL", "code": type(exc).__name__}
        return report
    try:
        result = b2_admission(api, b1["upload_id"], source_sha, target,
                              b1["archive_sha256"], kind="python")
        result["negatives"] = b2_negative(api, client_module, source_sha, target)
        report["b2_v1"] = result
    except Exception as exc:
        report["b2_v1"] = {"status": "BLOCKED", "code": type(exc).__name__}
    # A missing v2 verifier on Z2 is an independent qualification gap,
    # not a failure of B1 or a reason to upgrade the installed Bootstrap.
    try:
        raw_v2 = sample_v2(source_sha, target)
        v2_uid = api.upload(raw_v2)
        report["b2_v2"] = b2_admission(
            api, v2_uid, source_sha, target, _sha(raw_v2), kind="bundle",
        )
    except Exception as exc:
        report["b2_v2"] = {"status": "NOT_QUALIFIED", "code": type(exc).__name__}
    if (report["b1"]["status"] == "PASS"
            and report["b2_v1"]["status"] == "PASS"
            and report["b2_v2"]["status"] == "PASS"):
        report["baseline_qualification"] = "B1_B2_V1_V2_PASS"
    elif report["b1"]["status"] == "PASS":
        report["baseline_qualification"] = "B1_PASS_PARTIAL"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Z2 hardware Package receive/admission ONLY")
    parser.add_argument("--host", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--board", required=True)
    parser.add_argument("--fpga-part", required=True)
    args = parser.parse_args(argv)
    try:
        if not SHA40.fullmatch(args.source_sha) or _git_head() != args.source_sha:
            raise BaselineError("SOURCE_SHA_PIN_MISMATCH")
        target = {"platform": args.platform, "board": args.board, "fpga_part": args.fpga_part}
        if any(not SAFE.fullmatch(v) for v in target.values()):
            raise BaselineError("TARGET_PROFILE_INPUT_DENIED")
        if not re.fullmatch(r"ppu-device-[0-9a-f]{16,64}", args.device_id):
            raise BaselineError("DEVICE_ID_PIN_INVALID")
        host = _private_ipv4(args.host)
        credential = os.environ.get(TOKEN_ENV)
        if not credential:
            raise BaselineError("PRIVATE_TOKEN_FILE_NOT_PROVISIONED")
        token = _token_from_private_file(Path(credential))
        module = _load_client()
        api = module.BootstrapAPIClient(
            f"https://{host}:18081", token,
            transport=_commissioning_transport(host),
        )
        report = run(api, module, source_sha=args.source_sha, target=target,
                     expected_device_id=args.device_id)
        print("PLASMA_PPU_HARDWARE_BASELINE_JSON=" + json.dumps(
            report, sort_keys=True, separators=(",", ":"),
        ))
        return 0 if report["b1"]["status"] == "PASS" else 1
    except (BaselineError, OSError, ValueError, subprocess.SubprocessError) as exc:
        # NEVER print exception details containing token, URL, or untrusted body.
        print("PLASMA_PPU_HARDWARE_BASELINE_JSON=" + json.dumps({
            "schema": SCHEMA, "b1": "NOT_RUN",
            "b2_v1": "NOT_RUN", "b2_v2": "NOT_RUN",
            "code": type(exc).__name__, "result": "NOT_RUN",
        }, sort_keys=True, separators=(",", ":")))
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
