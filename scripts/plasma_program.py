#!/usr/bin/env python3
"""Bundle-driven PLASMA programming CLI, independent of the execution path.

Uses existing Bootstrap B1/B2/B3 and Gateway flash_cycle APIs. The Runtime and
Site Worker own all physical admission, FPGA/SWD and SAFE_OFF operations.
One invocation selects exactly one Bundle and one Site. Never retry a write.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import http.client
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from urllib.parse import quote
import zipfile

import ppu_deploy_api
import ppu_unified_deployment

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
PACKAGE_ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
DEVICE_ID = re.compile(r"ppu-device-[0-9a-f]{16,64}\Z")
JOB_ID = re.compile(r"job-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}\Z")
TERMINAL = frozenset(("success", "failed", "error", "cancelled", "timeout", "aborted"))
MAX_BUNDLE = 64 * 1024 * 1024
SCHEMA = "plasma.program.bundle-flash.v1"


class ProgramDenied(RuntimeError):
    pass


class OutcomeUnknown(ProgramDenied):
    def __init__(self, reason: str, job_id: str | None = None):
        super().__init__(reason)
        self.job_id = job_id


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ProgramDenied(code)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class Selection:
    archive: bytes
    bundle_sha: str
    firmware_package: str
    firmware_sha: str
    firmware_size: int
    profile: str
    provider: str
    target: str
    site: int


def read_bundle(path: Path, *, site: int, package: str | None,
                image: Path | None = None) -> Selection:
    """Validate the canonical Bundle with the existing verifier, no extraction."""
    require(type(site) is int and site >= 1, "SITE_INVALID")
    require(not path.is_symlink() and path.is_file()
            and 0 < path.stat().st_size <= MAX_BUNDLE, "BUNDLE_FILE_DENIED")
    archive = path.read_bytes()
    digest = sha256(archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        info = z.getinfo("manifest.json")
        require(info.file_size <= 65536, "BUNDLE_MANIFEST_TOO_LARGE")
        manifest = json.loads(z.read(info))
    require(type(manifest) is dict and manifest.get("schema") == "plasma.ppu.bundle.v3",
            "BUNDLE_SCHEMA_DENIED")
    # Same verifier as the existing B2/B3 contract, not a new ZIP parser.
    ppu_unified_deployment.verify_host_only_bundle(
        path, expected_sha256=digest, target_profile=manifest.get("target"))
    packages = manifest["packages"]
    require(not any(p["kind"] == "fpga-image" for p in packages),
            "FPGA_IMAGE_REQUIRES_SEPARATE_AUTHORIZATION")
    by_id = {p["id"]: p for p in packages}
    candidates = [p for p in packages if p["kind"] == "firmware-asset"]
    if package is None:
        require(len(candidates) == 1, "FIRMWARE_PACKAGE_SELECTION_REQUIRED")
        firmware = candidates[0]
    else:
        require(PACKAGE_ID.fullmatch(package) is not None,
                "FIRMWARE_PACKAGE_ID_INVALID")
        firmware = by_id.get(package)
        require(firmware is not None and firmware["kind"] == "firmware-asset",
                "FIRMWARE_PACKAGE_NOT_FOUND")
    require(len(firmware["requires"]) == 1, "FIRMWARE_PROFILE_AMBIGUOUS")
    profile = by_id.get(firmware["requires"][0])
    require(profile is not None and profile["kind"] == "programming-profile"
            and len(profile["requires"]) == 1, "PROGRAMMING_PROFILE_INVALID")
    provider = by_id.get(profile["requires"][0])
    require(provider is not None and provider["kind"] == "platform-provider",
            "PROGRAMMING_PROVIDER_INVALID")
    descriptor_path = (
        "payload/packages/" + profile["id"] + "/data/plasma-provider.json")
    require(any(f["path"] == descriptor_path for f in profile["files"]),
            "PROGRAMMING_PROFILE_DESCRIPTOR_MISSING")
    firmware_files = firmware["files"]
    require(len(firmware_files) == 1, "FIRMWARE_FILE_AMBIGUOUS")
    entry = firmware_files[0]
    require(entry["path"].startswith(
        "payload/packages/" + firmware["id"] + "/data/")
        and entry["path"].endswith(".bin")
        and entry["executable"] is False, "FIRMWARE_BIN_INVALID")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        descriptor = json.loads(z.read(descriptor_path))
        raw_firmware = z.read(entry["path"])
    require(sha256(raw_firmware) == entry["sha256"]
            and len(raw_firmware) == entry["size"] and len(raw_firmware) > 0,
            "FIRMWARE_SHA_OR_SIZE_MISMATCH")
    require(descriptor.get("schema") == "plasma.ppu.provider-capabilities.v1"
            and descriptor.get("provider_package") == provider["id"]
            and descriptor.get("target")
            and "flash_cycle" in descriptor.get("operations", []),
            "SITE_OR_TARGET_NOT_QUALIFIED")
    if image is not None:
        require(not image.is_symlink() and image.is_file()
                and image.stat().st_size == len(raw_firmware)
                and sha256(image.read_bytes()) == entry["sha256"],
                "EXTERNAL_IMAGE_NOT_IN_BUNDLE")
    # Firmware bytes are NEVER sent to the Gateway: only the selected Set IDs.
    return Selection(archive, digest, firmware["id"], entry["sha256"],
                     entry["size"], profile["id"], provider["id"],
                     descriptor["target"], site)


def validate_host(host: str, device_id: str) -> None:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        raise ProgramDenied("HOST_PRIVATE_IPV4_REQUIRED") from None
    require(addr.version == 4 and addr.is_private and not addr.is_loopback
            and not addr.is_link_local, "HOST_PRIVATE_IPV4_REQUIRED")
    require(DEVICE_ID.fullmatch(device_id) is not None,
            "DEVICE_ID_PIN_INVALID")


def validate_source_pin(sha: str | None) -> None:
    """Optional for direct CLI; Path 2/3 dispatchers still pin their own source."""
    if sha is None:
        return
    require(SHA40.fullmatch(sha) is not None, "SOURCE_SHA_INVALID")
    result = subprocess.run(["git", "rev-parse", "HEAD"],
                            cwd=Path(__file__).resolve().parents[1],
                            text=True, capture_output=True, check=True,
                            timeout=8)
    require(result.stdout.strip() == sha, "SOURCE_SHA_MISMATCH")


def owner_token(host: str, path: Path | None) -> str:
    if path is None:
        # Reuse the existing enrolled SWPC credential path (works in Path 2
        # and any locally authorized equivalent worker environment).
        import ppu_path2_hardware_baseline as enrolled
        return enrolled._existing_bootstrap_token_via_z2_ssh(host)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600
            and 32 <= info.st_size <= 512, "OWNER_TOKEN_FILE_DENIED")
    token = path.read_text(encoding="ascii").strip()
    require(32 <= len(token) <= 256 and token.isascii()
            and all(33 <= ord(ch) <= 126 for ch in token),
            "OWNER_TOKEN_INVALID")
    return token


def open_bootstrap(host: str, token: str):
    """Reuse the qualified private commissioning client; never fake TLS."""
    import ppu_path2_hardware_baseline as enrolled

    class ExistingBootstrap(enrolled.DirectSSHAuthenticatedBootstrap):
        def _install_body(self, admitted, mode, fpga_load):
            return self.module.BootstrapAPIClient._install_body(
                self, admitted, mode, fpga_load)

        def install_bundle(self, admitted, *, mode, fpga_load):
            return self.module.BootstrapAPIClient.install_bundle(
                self, admitted, mode=mode, fpga_load=fpga_load)

        def assets_status(self):
            return self.module.BootstrapAPIClient.assets_status(self)

        def reconcile_bundle_assets(self, archive, *, fpga_load):
            return self.module.BootstrapAPIClient.reconcile_bundle_assets(
                self, archive, fpga_load=fpga_load)

    return ExistingBootstrap(host, module=ppu_deploy_api, token=token)


def get_gateway(host: str, endpoint: str) -> dict:
    connection = http.client.HTTPConnection(host, 18080, timeout=12)
    try:
        connection.request("GET", endpoint, headers={"Accept": "application/json"})
        response = connection.getresponse()
        raw = response.read(65537)
        require(response.status == 200 and len(raw) <= 65536,
                "GATEWAY_READ_DENIED")
        value = json.loads(raw)
        require(type(value) is dict, "GATEWAY_RESPONSE_INVALID")
        return value
    finally:
        connection.close()


def readiness(host: str, chosen: Selection) -> dict:
    health = get_gateway(host, "/api/health/ready")
    node = get_gateway(host, "/api/node")
    status = get_gateway(host, "/api/status?site=" + str(chosen.site))
    ppu = status.get("ppu")
    ident = node.get("ppu")
    require(type(ppu) is dict and type(ident) is dict
            and ident.get("ppu_id") and ident.get("ppu_id") == ppu.get("ppu_id"),
            "PPU_IDENTITY_MISMATCH")
    lease = ppu.get("execution")
    activation = ppu.get("runtime_activation")
    sites = status.get("sites")
    require(type(lease) is dict and type(activation) is dict
            and type(sites) is list and len(sites) == 1
            and type(sites[0]) is dict, "PPU_STATUS_UNTRUSTED")
    site = sites[0]
    require(health.get("ok") is True and health.get("execution") == "ready"
            and lease.get("busy") is False and lease.get("active_job_count") == 0
            and activation.get("active") is False
            and site.get("site_id") == chosen.site
            and site.get("enabled") is True and site.get("state") == "idle"
            and site.get("current_job_id") is None and site.get("queued_jobs") == 0
            and site.get("interface") == "openocd"
            and site.get("target") == chosen.target,
            "SITE_NOT_READY_OR_BUSY")
    return {"ppu_id": ident["ppu_id"], "site": chosen.site, "site_idle": True}


def require_device(client: ppu_deploy_api.BootstrapAPIClient, device_id: str,
                   runtime_sha: str | None = None) -> None:
    status = client.status()
    require(status.get("identity", {}).get("device_id") == device_id
            and status.get("bootstrap", {}).get("state") == "bootstrap_ready"
            and status.get("runtime", {}).get("state") == "runtime_active",
            "BOOTSTRAP_DEVICE_OR_RUNTIME_INVALID")
    deployment = status.get("deployment")
    require(not (type(deployment) is dict and
                 deployment.get("state") in ("queued", "running", "recovery_required")),
            "BOOTSTRAP_DEPLOYMENT_BUSY")
    if runtime_sha is not None:
        require(SHA40.fullmatch(runtime_sha) is not None
                and status["runtime"].get("git_sha") == runtime_sha,
                "RUNTIME_RELEASE_NOT_UPDATED")


def activate(client: ppu_deploy_api.BootstrapAPIClient,
             selection: Selection) -> dict:
    """Reuse existing B1/B2/B3 and observe its exact single transaction."""
    current = client.assets_status()
    if current["state"] == "ACTIVE" and current["asset_set_sha256"] == selection.bundle_sha:
        return {"result": "ALREADY_ACTIVE", "asset_set_sha256": selection.bundle_sha,
                "transaction_id": None}
    submission = client.reconcile_bundle_assets(selection.archive, fpga_load=False)
    require(submission.get("result") == "B3_INSTALL_QUEUED"
            and submission.get("asset_set_sha256") == selection.bundle_sha,
            "B3_SUBMISSION_OUTCOME_UNKNOWN")
    transaction = submission["b3"]["transaction_id"]
    deadline = time.monotonic() + 300
    while True:
        state = client.deployment_state(transaction)
        if state["state"] == "succeeded":
            break
        require(state["state"] in ("queued", "running"),
                "B3_FAILED_OR_RECOVERY_REQUIRED")
        require(time.monotonic() < deadline, "B3_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT")
        time.sleep(1)
    verified = client.assets_status()
    require(verified["state"] == "ACTIVE"
            and verified["asset_set_sha256"] == selection.bundle_sha,
            "B3_ACTIVE_SET_MISMATCH")
    return {"result": "ACTIVATED", "asset_set_sha256": selection.bundle_sha,
            "transaction_id": transaction}


def _gateway_challenge(host: str, device_id: str, auth) -> str:
    """Read-only P2A-1 challenge from the PPU Gateway (LOM-P2A-2 G13)."""
    connection = http.client.HTTPConnection(host, 18080, timeout=12)
    try:
        connection.request("GET", "/api/auth/challenge", headers={"Accept": "application/json"})
        response = connection.getresponse()
        raw = response.read(65537)
    finally:
        connection.close()
    value = json.loads(raw) if response.status == 200 and len(raw) <= 65536 else None
    require(type(value) is dict and value.get("ok") is True and value.get("schema") == auth.SCHEMA
            and value.get("device_id") == device_id and type(value.get("nonce")) is str,
            "GATEWAY_CHALLENGE_DENIED")
    return value["nonce"]


def post_once(host: str, selection: Selection, *, credential: str, device_id: str) -> str:
    """Submit ONE flash_cycle Job, signed under the enrolled PPU controller (G13)."""
    payload = {
        "site_id": selection.site, "operation": "flash_cycle", "timeout_s": 180.0,
        "target": selection.target, "provider": selection.provider,
        "profile": selection.profile,
        "asset_set_sha256": selection.bundle_sha,
        "asset_package_id": selection.firmware_package,
        "bundle_asset_sha256": selection.firmware_sha,
    }
    auth = ppu_deploy_api._request_auth_module()
    body = json.dumps(payload, sort_keys=True).encode()
    nonce = _gateway_challenge(host, device_id, auth)
    header, context = auth.sign_request(credential=credential, method="POST", path="/api/jobs",
                                        body=body, device_id=device_id, nonce=nonce)
    connection = http.client.HTTPConnection(host, 18080, timeout=18)
    try:
        # No retry, including any network error after the bytes were sent.
        connection.request("POST", "/api/jobs",
                           body=body,
                           headers={"Content-Type": "application/json",
                                    "Accept": "application/json",
                                    "Authorization": header})
        response = connection.getresponse()
        raw = response.read(65537)
        if len(raw) > 65536:
            raise OutcomeUnknown("JOB_SUBMISSION_RESPONSE_TOO_LARGE")
        if response.status != 202:
            raise ProgramDenied("JOB_SUBMISSION_REJECTED_HTTP_" + str(response.status))
        try:
            auth.verify_response(credential=credential, context=context, status=202, body=raw,
                                 header=response.getheader(auth.RESPONSE_HEADER))
        except auth.RequestAuthError:
            raise OutcomeUnknown("JOB_SUBMISSION_RESPONSE_UNAUTHENTICATED_DO_NOT_RESUBMIT") from None
        reply = json.loads(raw)
        job = reply.get("job") if type(reply) is dict else None
        if type(job) is not dict or type(job.get("job_id")) is not str:
            raise OutcomeUnknown("JOB_ID_UNKNOWN_DO_NOT_RESUBMIT")
        job_id = job["job_id"]
        if JOB_ID.fullmatch(job_id) is None:
            raise OutcomeUnknown("JOB_ID_INVALID_DO_NOT_RESUBMIT")
        return job_id
    except (OSError, TimeoutError, http.client.HTTPException, ValueError):
        raise OutcomeUnknown("JOB_SUBMISSION_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT") from None
    finally:
        connection.close()


def poll_job(host: str, job_id: str) -> dict:
    deadline = time.monotonic() + 240
    while True:
        job = get_gateway(host, "/api/status?job=" +
                          quote(job_id, safe="")).get("job")
        if type(job) is not dict or job.get("job_id") != job_id:
            raise OutcomeUnknown("JOB_STATUS_IDENTITY_UNKNOWN", job_id)
        if job.get("state") in TERMINAL:
            return job
        if job.get("state") not in ("queued", "running") or time.monotonic() >= deadline:
            raise OutcomeUnknown("JOB_RESULT_UNKNOWN_DO_NOT_RESUBMIT", job_id)
        time.sleep(1)


def verify_job(job: dict, selection: Selection) -> dict:
    result = job.get("result")
    details = result.get("details") if type(result) is dict else None
    flash = details.get("flash_cycle") if type(details) is dict else None
    good = (job.get("state") == "success" and job.get("site_id") == selection.site
            and job.get("operation") == "flash_cycle"
            and type(result) is dict and result.get("state") == "success"
            and result.get("image_sha256") == selection.firmware_sha
            and result.get("image_size") == selection.firmware_size
            and result.get("attempts") == 1
            and type(flash) is dict and flash.get("result") == "PASS"
            and flash.get("readback_sha256") == selection.firmware_sha
            and flash.get("bytes_verified") == selection.firmware_size
            and flash.get("safe_off") is True)
    return {"status": "PASS" if good else "FAIL_OR_INCOMPLETE",
            "job_id": job.get("job_id"), "job_state": job.get("state"),
            "firmware_sha256": selection.firmware_sha,
            "readback_sha256": flash.get("readback_sha256") if type(flash) is dict else None,
            "bytes_verified": flash.get("bytes_verified") if type(flash) is dict else None,
            "safe_off": flash.get("safe_off") if type(flash) is dict else None,
            "submission_count": 1}


def execute(command: str, selection: Selection, *, host: str, device_id: str,
            client: ppu_deploy_api.BootstrapAPIClient,
            runtime_sha: str | None = None, approved_once: bool = False) -> dict:
    require(command in {"diagnose", "deploy", "flash", "run"}, "COMMAND_DENIED")
    require(command == "diagnose" or approved_once, "OWNER_APPROVAL_REQUIRED")
    validate_host(host, device_id)
    require_device(client, device_id,
                   runtime_sha if command in ("flash", "run") else None)
    before = readiness(host, selection)
    active = client.assets_status()
    if command == "diagnose":
        return {"status": "PASS", "before": before,
                "active_asset_set_sha256": active.get("asset_set_sha256"),
                "expected_asset_set_sha256": selection.bundle_sha,
                "mutations": "NOT_RUN"}
    deployed = None
    if command in ("deploy", "run"):
        # Do not allow an FPGA-bearing Bundle to silently load or replace PL.
        deployed = activate(client, selection)
    else:
        require(active["state"] == "ACTIVE" and
                active["asset_set_sha256"] == selection.bundle_sha,
                "BUNDLE_NOT_CURRENTLY_ACTIVE")
    if command == "deploy":
        return {"status": "PASS", "deployment": deployed,
                "flash": "NOT_RUN"}
    # A deployment receipt alone does not authorize a programming Job.
    require_device(client, device_id, runtime_sha)
    require(client.assets_status()["asset_set_sha256"] == selection.bundle_sha,
            "ACTIVE_SET_CHANGED")
    readiness(host, selection)
    try:
        job_id = post_once(host, selection, credential=client._token, device_id=device_id)
    except OutcomeUnknown as exc:
        return {"status": "OUTCOME_UNKNOWN", "reason": str(exc),
                "submission_count": "UNKNOWN", "auto_retry": "DISABLED"}
    try:
        job = poll_job(host, job_id)
    except (OutcomeUnknown, ProgramDenied, OSError, TimeoutError) as exc:
        return {"status": "OUTCOME_UNKNOWN",
                "reason": str(exc) if isinstance(exc, ProgramDenied)
                else type(exc).__name__, "job_id": job_id,
                "submission_count": 1, "auto_retry": "DISABLED"}
    verified = verify_job(job, selection)
    if verified["status"] == "PASS":
        try:
            readiness(host, selection)
        except Exception:
            verified["status"] = "FAIL_OR_INCOMPLETE"
            verified["post_site_state"] = "UNKNOWN"
    return {"status": verified["status"], "deployment": deployed,
            "job": verified, "auto_retry": "DISABLED"}



def deploy_runtime_kit(client, selection: Selection, *, host: str,
                       device_id: str, runtime_sha: str, kit_sha256: str,
                       ppu_id: str, facility_id: str,
                       display_name: str) -> dict:
    """Use ONLY the installed Bootstrap Coordinator for a single Runtime upgrade."""
    require(type(runtime_sha) is str and SHA40.fullmatch(runtime_sha) is not None
            and type(kit_sha256) is str and SHA64.fullmatch(kit_sha256) is not None,
            "RUNTIME_KIT_IDENTITY_REQUIRED")
    require(type(ppu_id) is str and type(facility_id) is str
            and type(display_name) is str and 1 <= len(display_name) <= 128
            and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", ppu_id) is not None
            and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", facility_id) is not None
            and all(ord(c) >= 32 for c in display_name),
            "RUNTIME_PLATFORM_IDENTITY_REQUIRED")
    # Trusted GitHub Actions step must already have verified CI run provenance,
    # ZIP digest, kit sidecar, target, and the full nested release source SHA.
    kit_name = os.environ.get("PLASMA_Z2_KIT_ARTIFACT_PATH", "")
    require(kit_name and os.path.isabs(kit_name)
            and os.environ.get("PLASMA_Z2_KIT_SOURCE_SHA") == runtime_sha,
            "TRUSTED_RUNTIME_KIT_NOT_DELIVERED")
    kit = Path(kit_name)
    require(not kit.is_symlink() and kit.is_file()
            and 0 < kit.stat().st_size <= 512 * 1024 * 1024,
            "RUNTIME_KIT_PATH_DENIED")
    digest = hashlib.sha256()
    with kit.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    require(digest.hexdigest() == kit_sha256, "RUNTIME_KIT_SHA256_MISMATCH")
    require_device(client, device_id)
    before = readiness(host, selection)
    require(before["ppu_id"] == ppu_id, "PPU_IDENTITY_MISMATCH")
    current = client.status()
    require(current.get("capabilities", {}).get("runtime_deployment") is True,
            "BOOTSTRAP_RUNTIME_DEPLOYMENT_UNAVAILABLE")
    old_sha = current["runtime"].get("git_sha")
    active = client.assets_status()
    require(active.get("state") == "ACTIVE"
            and active.get("asset_set_sha256") == selection.bundle_sha,
            "ACTIVE_SET_CHANGED")
    if old_sha == runtime_sha:
        return {"status": "PASS", "deployment": "ALREADY_INSTALLED",
                "runtime_git_sha": runtime_sha, "flash": "NOT_RUN"}
    archive = kit.read_bytes()
    require(hashlib.sha256(archive).hexdigest() == kit_sha256,
            "RUNTIME_KIT_CHANGED")
    # No direct /opt/plasma writes, service kills or FPGA operations here.
    # The existing Coordinator owns quiescence, transaction and rollback.
    uploaded = client.upload(archive)
    try:
        accepted = client.submit(
            kind="ppu-runtime", upload_id=uploaded, gateway_host=host,
            ppu_id=ppu_id, facility_id=facility_id, display_name=display_name)
    except Exception:
        return {"status": "OUTCOME_UNKNOWN", "phase": "RUNTIME_SUBMIT",
                "upload_id": uploaded, "auto_retry": "DISABLED",
                "flash": "NOT_RUN"}
    tx = accepted.transaction_id
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        try:
            record = client.deployment_state(tx)
        except Exception:
            return {"status": "OUTCOME_UNKNOWN", "transaction_id": tx,
                    "phase": "DEPLOYMENT_POLL", "auto_retry": "DISABLED",
                    "flash": "NOT_RUN"}
        if record["state"] == "succeeded":
            break
        if record["state"] in ("failed", "recovery_required"):
            return {"status": "FAIL_OR_RECOVERY_REQUIRED",
                    "transaction_id": tx, "deployment_state": record["state"],
                    "auto_retry": "DISABLED", "flash": "NOT_RUN"}
        time.sleep(2)
    else:
        return {"status": "OUTCOME_UNKNOWN", "transaction_id": tx,
                "phase": "DEPLOYMENT_TIMEOUT", "auto_retry": "DISABLED",
                "flash": "NOT_RUN"}
    # Only GETs after activation. A missing readiness is never a new install.
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            require_device(client, device_id, runtime_sha)
            readiness(host, selection)
            verified = client.assets_status()
            require(verified.get("asset_set_sha256") == selection.bundle_sha,
                    "RUNTIME_UPGRADE_CHANGED_ACTIVE_SET")
            return {"status": "PASS", "transaction_id": tx,
                    "before_runtime_git_sha": old_sha,
                    "runtime_git_sha": runtime_sha,
                    "active_asset_set_sha256": selection.bundle_sha,
                    "auto_retry": "DISABLED", "flash": "NOT_RUN"}
        except (OSError, ProgramDenied, TimeoutError):
            time.sleep(2)
    return {"status": "POST_INSTALL_VERIFICATION_INCOMPLETE",
            "transaction_id": tx, "auto_retry": "DISABLED",
            "flash": "NOT_RUN"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("diagnose", "deploy", "flash", "run", "runtime-deploy"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--firmware-package")
    parser.add_argument("--image", type=Path,
                        help="optional BIN equality check; never transmitted")
    parser.add_argument("--site", type=int, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--runtime-sha",
                        help="required for flash/run/runtime-deploy; full Runtime Git SHA")
    parser.add_argument("--kit-sha256", help="source-bound CI Runtime Kit digest")
    parser.add_argument("--ppu-id", help="existing Z2 PPU ID, for runtime-deploy")
    parser.add_argument("--facility-id", help="existing facility ID, for runtime-deploy")
    parser.add_argument("--display-name", help="existing display name, for runtime-deploy")
    parser.add_argument("--owner-token-file", type=Path,
                        help="existing owner-only 0600 credential; otherwise use enrolled SWPC SSH")
    parser.add_argument("--source-sha", help="optional exact Git HEAD pin for dispatched runs")
    parser.add_argument("--approved-once", action="store_true")
    args = parser.parse_args(argv)
    receipt = {"schema": SCHEMA, "command": args.command,
               "status": "NOT_RUN", "auto_retry": "DISABLED"}
    try:
        require(args.command not in ("flash", "run", "runtime-deploy")
                or args.runtime_sha is not None, "RUNTIME_SHA_REQUIRED")
        require(args.command == "diagnose" or args.approved_once,
                "OWNER_APPROVAL_REQUIRED")
        validate_host(args.host, args.device_id)
        validate_source_pin(args.source_sha)
        selection = read_bundle(args.bundle, site=args.site,
                                package=args.firmware_package, image=args.image)
        receipt.update(bundle_sha256=selection.bundle_sha,
                       firmware_sha256=selection.firmware_sha,
                       firmware_package=selection.firmware_package,
                       site_id=selection.site)
        token = owner_token(args.host, args.owner_token_file)
        client = open_bootstrap(args.host, token)
        if args.command == "runtime-deploy":
            result = deploy_runtime_kit(
                client, selection, host=args.host, device_id=args.device_id,
                runtime_sha=args.runtime_sha, kit_sha256=args.kit_sha256,
                ppu_id=args.ppu_id, facility_id=args.facility_id,
                display_name=args.display_name)
        else:
            result = execute(args.command, selection, host=args.host,
                             device_id=args.device_id, client=client,
                             runtime_sha=args.runtime_sha,
                             approved_once=args.approved_once)
        receipt.update(result)
        code = 0 if receipt["status"] == "PASS" else 1
    except ProgramDenied as exc:
        receipt.update(status="BLOCKED_OR_OUTCOME_UNKNOWN", reason=str(exc))
        code = 69
    except Exception as exc:
        # Never expose authorization tokens, SSH output or raw HTTP responses.
        receipt.update(status="BLOCKED_OR_OUTCOME_UNKNOWN",
                       reason=type(exc).__name__)
        code = 69
    print("PLASMA_PROGRAM=" +
          json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
