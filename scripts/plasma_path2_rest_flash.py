#!/usr/bin/env python3
"""Bounded PLASMA Path 2 REST Flash acceptance; standard library only.

DEFAULT = strictly read-only HTTP GET preflight. --execute-flash is a separate
owner-authorized hardware work order: it WILL erase/program the selected DUT.
Nothing here opens SSH, resets an IC directly, loads FPGA, or changes Z2 config.

No FPGA Image ID, OpenOCD install, firmware filename or exact ICPN is hardcoded.
The selected PPU/Site/ICPN and source SHA are explicit work-order inputs.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import stat
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TERMINAL = frozenset({"success", "failed", "error", "timeout", "cancelled", "aborted"})
MAX_ASSET_BYTES = 8 * 1024 * 1024  # Transport budget, NOT a target Flash geometry.
MAX_RESPONSE_BYTES = 512 * 1024


class PreflightError(Exception):
    """The read-only observation did not prove readiness; no Flash submitted."""


class FlashExecutionError(Exception):
    """A POST may have reached the PPU: NEVER classify as NOT_RUN or auto-retry."""


class RestClient:
    def __init__(self, url: str, timeout: float = 10.0):
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
                or parsed.port is None):
            raise PreflightError("INVALID_PPU_ENDPOINT")
        self.scheme, self.host, self.port = parsed.scheme, parsed.hostname, parsed.port
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        if method not in {"GET", "POST"} or not path.startswith("/api/"):
            raise PreflightError("UNSUPPORTED_REST_REQUEST")
        if method == "POST" and (path != "/api/jobs" or body is None):
            raise PreflightError("POST_NOT_AUTHORIZED_BY_SCRIPT")
        if method == "GET" and body is not None:
            raise PreflightError("GET_CANNOT_HAVE_BODY")
        conn_class = (http.client.HTTPSConnection if self.scheme == "https"
                      else http.client.HTTPConnection)
        conn = conn_class(self.host, self.port, timeout=self.timeout)
        try:
            wire = json.dumps(body, separators=(",", ":")).encode() if body is not None else None
            headers = {"Content-Type": "application/json"} if body is not None else {}
            conn.request(method, path, wire, headers)
            response = conn.getresponse()
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise PreflightError("RESPONSE_TOO_LARGE")
            if response.status != (202 if method == "POST" else 200):
                raise PreflightError("HTTP_" + str(response.status))
            try:
                payload = json.loads(data)
            except (ValueError, UnicodeDecodeError) as exc:
                raise PreflightError("INVALID_REST_JSON") from exc
            if not isinstance(payload, dict) or payload.get("ok") is False:
                raise PreflightError("REST_RESPONSE_NOT_OK")
            return payload
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            raise PreflightError("PPU_CONNECTION_FAILED") from exc
        finally:
            conn.close()


def _dict(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise PreflightError(name + "_INVALID")
    return value


def _only_site(payload: dict, site: int) -> dict:
    sites = payload.get("sites")
    if not isinstance(sites, list) or len(sites) != 1:
        raise PreflightError("SITE_STATUS_INCOMPLETE")
    record = _dict(sites[0], "SITE")
    if record.get("site_id") != site:
        raise PreflightError("SITE_ID_MISMATCH")
    return record


def preflight(client: RestClient, *, site: int, ppu_id: str | None, target: str) -> dict:
    """Read-only. Does not claim C3, USB CDC, electrical or physical readiness."""
    health = client.request("GET", "/api/health/ready")
    if health.get("ok") is not True or health.get("execution") != "ready":
        raise PreflightError("PPU_GATEWAY_NOT_READY")
    node = client.request("GET", "/api/node")
    node_ppu = _dict(node.get("ppu"), "NODE_PPU")
    discovered_ppu_id = node_ppu.get("ppu_id")
    if not isinstance(discovered_ppu_id, str) or not discovered_ppu_id:
        raise PreflightError("PPU_ID_UNAVAILABLE")
    if ppu_id is not None and discovered_ppu_id != ppu_id:
        raise PreflightError("WRONG_PPU")
    status = client.request("GET", "/api/status?site=" + str(site))
    ppu = _dict(status.get("ppu"), "STATUS_PPU")
    if ppu.get("ppu_id") != discovered_ppu_id:
        raise PreflightError("STATUS_PPU_MISMATCH")
    lease = _dict(ppu.get("execution"), "EXECUTION_LEASE")
    if lease.get("busy") is not False or lease.get("active_job_count") != 0:
        raise PreflightError("PPU_EXECUTION_BUSY")
    activation = _dict(ppu.get("runtime_activation"), "ACTIVATION")
    if activation.get("active") is not False:
        raise PreflightError("PPU_RUNTIME_QUIESCED")
    selected = _only_site(status, site)
    if selected.get("enabled") is not True or selected.get("interface") != "openocd":
        raise PreflightError("SITE_NOT_OPENOCD_ENABLED")
    if selected.get("target") != target:
        raise PreflightError("SITE_TARGET_MISMATCH")
    if (selected.get("state") != "idle"
            or selected.get("current_job_id") is not None
            or selected.get("queued_jobs") != 0):
        raise PreflightError("SITE_NOT_IDLE")
    # capabilities.operations is currently missing flash_cycle despite a valid
    # REST/C3 route. It is advisory only, not a sufficient/required readiness proof.
    return {
        "result": "READ_ONLY_PREFLIGHT_PASS",
        "ppu_id": discovered_ppu_id, "ppu_id_source": "live_node_and_status",
        "ppu_id_expected_checked": ppu_id is not None,
        "site_id": site, "target": target,
        "http_methods": ["GET"], "flash_submitted": False,
        "c3_engine_verified": False, "external_ssh_owner_verified": False,
        "usb_cdc_verified": False, "physical_hardware_verified": False,
    }


def reconcile_latest_job(client: RestClient, *, site: int, ppu_id: str | None,
                         target: str, expected_sha256: str) -> dict:
    """GET-only observation after an ambiguous POST. Never authorizes a retry.

    A matching latest Job is evidence, not proof that this exact client POST
    created it: the failed HTTP response did not provide a Job ID.
    """
    if SHA256.fullmatch(expected_sha256) is None:
        raise PreflightError("EXPECTED_SHA256_INVALID")
    node = client.request("GET", "/api/node")
    observed_id = _dict(node.get("ppu"), "NODE_PPU").get("ppu_id")
    if not isinstance(observed_id, str) or not observed_id:
        raise PreflightError("PPU_ID_UNAVAILABLE")
    if ppu_id is not None and ppu_id != observed_id:
        raise PreflightError("WRONG_PPU")
    status = client.request("GET", "/api/status?site=" + str(site))
    ppu = _dict(status.get("ppu"), "STATUS_PPU")
    if ppu.get("ppu_id") != observed_id:
        raise PreflightError("STATUS_PPU_MISMATCH")
    selected = _only_site(status, site)
    if selected.get("target") != target:
        raise PreflightError("SITE_TARGET_MISMATCH")
    lease = _dict(ppu.get("execution"), "EXECUTION_LEASE")
    out = {
        "result": "READ_ONLY_RECONCILIATION",
        "ppu_id": observed_id, "site_id": site, "target": target,
        "site_state": selected.get("state"),
        "current_job_id": selected.get("current_job_id"),
        "active_job_count": lease.get("active_job_count"),
        "execution_busy": lease.get("busy"),
        "expected_image_sha256": expected_sha256,
        "flash_submitted": False, "http_methods": ["GET"],
        "original_post_outcome_still_unknown": True,
        "safe_to_retry": False, "correlated_to_original_post": False,
    }
    latest = selected.get("latest_job")
    if latest is None:
        out["latest_job_observed"] = False
        return out
    latest = _dict(latest, "LATEST_JOB")
    job_id = latest.get("job_id")
    if not isinstance(job_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", job_id) is None:
        raise PreflightError("LATEST_JOB_ID_INVALID")
    observed = client.request("GET", "/api/status?job=" + quote(job_id, safe=""))
    job = _dict(observed.get("job"), "JOB_STATUS")
    if job.get("job_id") != job_id:
        raise PreflightError("LATEST_JOB_ID_MISMATCH")
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    cycle = details.get("flash_cycle") if isinstance(details.get("flash_cycle"), dict) else {}
    out.update({
        "latest_job_observed": True,
        "latest_job_id": job_id,
        "latest_job_operation": job.get("operation", latest.get("operation")),
        "latest_job_state": job.get("state"),
        "latest_job_created_at": job.get("created_at", latest.get("created_at")),
        "latest_job_updated_at": job.get("updated_at", latest.get("updated_at")),
        "latest_result_image_sha256": result.get("image_sha256"),
        "latest_flash_result": cycle.get("result"),
        "latest_flash_readback_sha256": cycle.get("readback_sha256"),
        "latest_flash_bytes_verified": cycle.get("bytes_verified"),
        "latest_flash_safe_off": cycle.get("safe_off"),
        "latest_job_matches_expected_sha": (
            result.get("image_sha256") == expected_sha256
            and cycle.get("readback_sha256") == expected_sha256
            and job.get("state") == "success"
            and cycle.get("result") == "PASS"
            and cycle.get("safe_off") is True
        ),
    })
    return out


def _read_image(path: Path, sha256: str) -> bytes:
    if SHA256.fullmatch(sha256) is None:
        raise PreflightError("FIRMWARE_SHA256_INVALID")
    try:
        # Don't follow arbitrary symlinks into a private SWPC file.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_ASSET_BYTES:
                raise PreflightError("FIRMWARE_SIZE_INVALID")
            payload = f.read(MAX_ASSET_BYTES + 1)
    except OSError as exc:
        raise PreflightError("FIRMWARE_UNAVAILABLE") from exc
    if hashlib.sha256(payload).hexdigest() != sha256:
        raise PreflightError("FIRMWARE_SHA256_MISMATCH")
    return payload


def execute_flash(client: RestClient, *, site: int, ppu_id: str, target: str,
                  image_file: Path, image_sha256: str, deadline_s: float,
                  poll_s: float = 0.5, sleep=time.sleep, clock=time.monotonic) -> dict:
    """DESTRUCTIVE. Only invoke from an owner-approved guarded-hardware work order."""
    if not isinstance(ppu_id, str) or not ppu_id:
        raise PreflightError("EXPLICIT_PPU_ID_REQUIRED_FOR_FLASH")
    payload = _read_image(image_file, image_sha256)
    # Observe readiness again immediately before the only mutation (POST).
    preflight(client, site=site, ppu_id=ppu_id, target=target)
    try:
        response = client.request("POST", "/api/jobs", {
        "site_id": site, "operation": "flash_cycle", "target": target,
        "timeout_s": deadline_s, "asset_name": image_file.name,
        "asset_type": "image", "asset_format": "binary",
        "asset_size": len(payload), "asset_sha256": image_sha256,
        "asset_base64": base64.b64encode(payload).decode("ascii"),
        })
    except PreflightError as exc:
        raise FlashExecutionError("FLASH_SUBMISSION_OUTCOME_UNKNOWN:" + str(exc)) from exc
    try:
        job = _dict(response.get("job"), "JOB_SUBMISSION")
        job_id = job.get("job_id")
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", job_id):
            raise FlashExecutionError("JOB_ID_INVALID_AFTER_POST")
    except PreflightError as exc:
        raise FlashExecutionError("FLASH_JOB_RECEIPT_UNKNOWN") from exc
    stop_at = clock() + deadline_s + 10
    while clock() < stop_at:
        try:
            obs = client.request("GET", "/api/status?job=" + quote(job_id, safe=""))
            job = _dict(obs.get("job"), "JOB_STATUS")
        except PreflightError as exc:
            raise FlashExecutionError("JOB_OBSERVATION_UNKNOWN:" + job_id) from exc
        if job.get("job_id") != job_id:
            raise FlashExecutionError("JOB_ID_MISMATCH_AFTER_POST")
        if job.get("state") in TERMINAL:
            try:
                result = (_dict(job.get("result"), "JOB_RESULT")
                          if job.get("state") == "success" else {})
                details = _dict(result.get("details"), "JOB_DETAILS") if result else {}
                cycle = _dict(details.get("flash_cycle"), "FLASH_CYCLE") if details else {}
            except PreflightError as exc:
                raise FlashExecutionError("JOB_RECEIPT_MALFORMED:" + job_id) from exc
            verified = (
                job.get("state") == "success"
                and cycle.get("result") == "PASS"
                and cycle.get("readback_sha256") == image_sha256
                and cycle.get("bytes_verified") == len(payload)
                and cycle.get("safe_off") is True
                and cycle.get("icpn") == target
            )
            return {
                "result": "FLASH_READBACK_PASS" if verified else "FLASH_UNPROVEN_OR_FAILED",
                "job_id": job_id, "job_state": job.get("state"),
                "ppu_id": ppu_id, "site_id": site, "target": target,
                "image_sha256": image_sha256, "image_size": len(payload),
                "readback_sha256": cycle.get("readback_sha256"),
                "safe_off": cycle.get("safe_off") is True,
                "cdc_heartbeat_verified": False,
                "external_ssh_owner_verified": False,
            }
        sleep(poll_s)
    raise FlashExecutionError("FLASH_RESULT_UNKNOWN_TIMEOUT_CHECK_JOB_BEFORE_RETRY:" + job_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="PPU Gateway base URL with explicit port")
    parser.add_argument("--ppu-id",
                        help="Optional for GET-only discovery; REQUIRED for destructive Flash")
    parser.add_argument("--site-id", type=int, required=True)
    parser.add_argument("--target", required=True, help="Exact ICPN selected for this job")
    parser.add_argument("--reconcile", action="store_true",
                        help="GET-only latest Site/Job observation after unknown POST; no retries")
    parser.add_argument("--execute-flash", action="store_true",
                        help="DESTRUCTIVE; requires separate owner-approved Path 2 Work Order")
    parser.add_argument("--confirm-site", type=int, default=None,
                        help="Must equal --site-id before destructive POST")
    parser.add_argument("--image-file", type=Path)
    parser.add_argument("--image-sha256")
    parser.add_argument("--job-timeout", type=float, default=120.0)
    args = parser.parse_args(argv)
    try:
        if args.site_id < 1 or not args.target or args.ppu_id == "":
            raise PreflightError("INVALID_SELECTED_PPU_SITE_OR_TARGET")
        if not 5 <= args.job_timeout <= 3600:
            raise PreflightError("INVALID_JOB_TIMEOUT")
        client = RestClient(args.url)
        if args.reconcile:
            if (args.execute_flash or args.image_file is not None
                    or args.confirm_site is not None or args.image_sha256 is None):
                raise PreflightError("RECONCILE_READ_ONLY_ARGS_REQUIRED")
            receipt = reconcile_latest_job(
                client, site=args.site_id, ppu_id=args.ppu_id,
                target=args.target, expected_sha256=args.image_sha256)
            print(json.dumps(receipt, sort_keys=True))
            return 0
        if args.execute_flash:
            if (not args.ppu_id or args.confirm_site != args.site_id
                    or args.image_file is None or args.image_sha256 is None):
                raise PreflightError("EXPLICIT_FLASH_CONFIRMATION_REQUIRED")
            receipt = execute_flash(client, site=args.site_id, ppu_id=args.ppu_id,
                                    target=args.target, image_file=args.image_file,
                                    image_sha256=args.image_sha256,
                                    deadline_s=args.job_timeout)
            print(json.dumps(receipt, sort_keys=True))
            return 0 if receipt["result"] == "FLASH_READBACK_PASS" else 2
        if (args.confirm_site is not None or args.image_file is not None
                or args.image_sha256 is not None):
            raise PreflightError("FLASH_ARGUMENTS_REQUIRE_EXECUTE_FLAG")
        receipt = preflight(client, site=args.site_id, ppu_id=args.ppu_id, target=args.target)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except FlashExecutionError as exc:
        print(json.dumps({"result": "FLASH_OUTCOME_UNKNOWN", "reason": str(exc),
                          "must_reconcile_job_before_retry": True}), file=sys.stderr)
        return 2
    except PreflightError as exc:
        print(json.dumps({"result": "NOT_READY_OR_FAILED", "reason": str(exc),
                          "flash_success": False}), file=sys.stderr)
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
