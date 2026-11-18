#!/usr/bin/env python3
"""SWPC engineering-only Manager Batch -> Z2 -> Blue Pill CDC E2E runner.

Hardware writes require explicit --execute and the existing Manager/PPU
authorization. This tool never deploys the Control Station, Runtime, Bundle or
FPGA; it refuses a Manager plan that requires resource activation.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "firmware/blue-pill-usb-cdc/host"))
from plasma_ab_burn_in import IMAGES  # noqa: E402 - reuse locked hashes/sizes/periods
from cdc_probe import run_live  # noqa: E402 - reuse ID + heartbeat verifier

ICPN = "STM32F103C8T6"
OPERATIONS = ["erase", "program", "verify"]
HEX32 = re.compile(r"[0-9a-f]{32}\Z")


class HILFailure(Exception):
    pass


def image_spec(path: Path, version: str) -> dict:
    meta = IMAGES[version]
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != meta["size"] or digest != meta["sha256"]:
        raise HILFailure(f"{version}: image size/SHA256 does not match pinned A/B fixture")
    return {"version": version, "sha256": digest, "size": len(raw),
            "image_base64": base64.b64encode(raw).decode("ascii")}


def sequence(mode: str, cycles: int) -> list[str]:
    if mode == "smoke":
        if cycles != 1:
            raise HILFailure("smoke requires --cycles 1")
        return ["v0.1", "v0.2", "v0.1"]
    if not 1 <= cycles <= 1000:
        raise HILFailure("burn-in requires cycles 1..1000")
    return ["v0.1", "v0.2"] * cycles


def require_loopback(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise HILFailure("Manager API must use the SWPC loopback HTTP root")
    return url.rstrip("/")


class Manager:
    def __init__(self, url: str):
        self.url = require_loopback(url)
        self.last_start_id: str | None = None
        self.last_batch_id: str | None = None
        self.last_preview_plan_id: str | None = None

    def call(self, method: str, route: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self.url + route, data=data, method=method,
                          headers={"Accept": "application/json",
                                   "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=15) as response:
                if response.status not in (200, 202):
                    raise HILFailure(f"{method} {route}: HTTP {response.status}")
                result = json.loads(response.read(2 * 1024 * 1024))
        except HTTPError as exc:
            # A definite server 4xx is a refusal. A 5xx is not evidence
            # that a submitted write did not reach the Manager.
            raise HILFailure(f"{method} {route}: HTTP {exc.code}; do not resubmit") from exc
        except (URLError, OSError, ValueError) as exc:
            raise HILFailure(f"{method} {route}: outcome unobservable; do not resubmit") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise HILFailure(f"{method} {route}: invalid/negative response")
        return result


def issue_and_check_reuse(client: Manager, alias: str, site: int, image: dict) -> str:
    body = {"icpn": ICPN, "site_id": site,
            "operations": OPERATIONS, "image_base64": image["image_base64"]}
    route = f"/api/registry/{alias}/bootstrap/programming/plans"
    response = client.call("POST", route, body)
    plan = response.get("plan")
    if not isinstance(plan, dict) or not HEX32.fullmatch(str(plan.get("plan_id"))):
        raise HILFailure("Manager plan identity not confirmed; do not proceed")
    plan_id = plan["plan_id"]
    # Keep the exact issued identity even if the subsequent VOID request fails.
    # A preview Start must be reconciled rather than silently abandoned.
    client.last_preview_plan_id = plan_id
    # The preview wrote a run Start to the Manager journal. Void it before
    # returning; this tool submits programming only through canonical Batch.
    void = client.call("POST", f"/api/programming/starts/{plan_id}/void",
                       {"void": "VOID_UNSTARTED_START"})
    reconciliation = void.get("reconciliation")
    if not isinstance(reconciliation, dict) or reconciliation.get("state") != "NOT_ACCEPTED":
        raise HILFailure("unused preview Start was not definitely voided")
    if (plan.get("activation_required") is not False
            or (plan.get("resource") or {}).get("reuse") is not True
            or plan.get("fpga_load") is not False):
        raise HILFailure("RESOURCE_REUSE_NOT_PROVEN: HIL must not activate Bundle/FPGA")
    asset = plan.get("image_asset") or {}
    if asset.get("sha256") != image["sha256"] or asset.get("size") != image["size"]:
        raise HILFailure("Manager planned a different image")
    sha = (plan.get("resource") or {}).get("resource_set_sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        raise HILFailure("Manager Resource Set identity is missing")
    return sha


def validate_receipt(batch: dict, alias: str, site: int, image: dict,
                     expected_resource: str) -> dict:
    if (batch.get("outcome") != "PASS" or batch.get("execution_status") != "COMPLETED"
            or batch.get("counts", {}).get("pass") != 1
            or batch.get("counts", {}).get("sites") != 1):
        raise HILFailure("Batch did not finish with exactly one Site PASS")
    units = batch.get("units")
    if not isinstance(units, list) or len(units) != 1:
        raise HILFailure("Batch units not single Site")
    unit = units[0]
    if (unit.get("ppu_alias") != alias or unit.get("site_id") != site
            or unit.get("outcome") != "PASS"):
        raise HILFailure("Batch Site identity/outcome mismatch")
    attempts = unit.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 1:
        raise HILFailure("Batch attempt count != 1")
    attempt = attempts[0]
    if attempt.get("outcome") != "PASS" or attempt.get("safe_off") is not True:
        raise HILFailure("Batch attempt PASS/SAFE_OFF not verified")
    run = batch.get("current_run")
    if not isinstance(run, dict) or run.get("outcome") != "PASS":
        raise HILFailure("Manager Run receipt missing")
    receipt = run.get("receipt")
    if not isinstance(receipt, dict):
        raise HILFailure("PPU Job receipt missing")
    required = {
        "safe_off": True,
        "readback_sha256": image["sha256"],
        "expected_image_sha256": image["sha256"],
        "observed_image_sha256": image["sha256"],
        "bytes_verified": image["size"],
        "expected_image_size": image["size"],
        "observed_image_size": image["size"],
        "expected_resource_set_sha256": expected_resource,
        "observed_resource_set_sha256": expected_resource,
        "resource_reuse": True,
        "observed_operations": OPERATIONS,
        "attempts": 1,
    }
    for field, expected in required.items():
        if receipt.get(field) != expected:
            raise HILFailure(f"Receipt {field}: mismatch")
    binding = receipt.get("expected_job_binding_sha256")
    if (not isinstance(binding, str) or not re.fullmatch(r"[0-9a-f]{64}", binding)
            or binding != receipt.get("observed_job_binding_sha256")
            or not isinstance(receipt.get("expected_steps"), dict)
            or receipt.get("expected_steps") != receipt.get("observed_steps")):
        raise HILFailure("Job Binding or operation evidence mismatch")
    if run.get("job_submission_count") != 1:
        raise HILFailure("Job submission count != 1")
    return {"batch_id": batch.get("batch_id"), "job_id": receipt.get("job_id"),
            "readback_sha256": receipt["readback_sha256"],
            "safe_off": True, "resource_set_sha256": expected_resource,
            "job_binding_sha256": receipt["expected_job_binding_sha256"]}


def one_attempt(client: Manager, alias: str, site: int, image: dict,
                timeout_s: float, poll_s: float) -> tuple[dict, dict]:
    client.last_start_id = None
    client.last_batch_id = None
    client.last_preview_plan_id = None
    resource = issue_and_check_reuse(client, alias, site, image)
    start = client.call("POST", "/api/programming/starts", {"kind": "batch"})
    token = (start.get("start") or {}).get("start_id")
    if not isinstance(token, str) or not HEX32.fullmatch(token):
        raise HILFailure("start_id unavailable; do not submit")
    client.last_start_id = token
    body = {"start_id": token, "icpn": ICPN, "targets": [
        {"ppu_alias": alias, "site_ids": [site]}],
        "operations": OPERATIONS, "image_base64": image["image_base64"],
        "repeat": 1, "retry_limit": 0, "stop_policy": {"kind": "never"}}
    # Exactly one write attempt. A transport failure after POST may mean that
    # the Job ran; never resend. Evidence records the start ID for read-only
    # reconciliation by the operator.
    try:
        response = client.call("POST", "/api/programming/batches", body)
    except HILFailure as exc:
        raise HILFailure(f"start_id={token}; {exc}") from exc
    batch = response.get("batch")
    batch_id = batch.get("batch_id") if isinstance(batch, dict) else None
    if not isinstance(batch_id, str) or not HEX32.fullmatch(batch_id):
        raise HILFailure(f"start_id={token}: batch identity missing; do not resubmit")
    client.last_batch_id = batch_id
    deadline = time.monotonic() + timeout_s
    while batch.get("outcome") is None:
        if time.monotonic() >= deadline:
            raise HILFailure(f"start_id={token}, batch_id={batch_id}: poll deadline; do not resubmit")
        time.sleep(poll_s)
        polled = client.call("GET", f"/api/programming/batches/{batch_id}")
        next_batch = polled.get("batch")
        if (not isinstance(next_batch, dict)
                or next_batch.get("batch_id") != batch_id):
            raise HILFailure(
                f"start_id={token}, batch_id={batch_id}: Batch poll identity "
                "missing/mismatched; do not resubmit")
        batch = next_batch
    evidence = validate_receipt(batch, alias, site, image, resource)
    return evidence, {"start_id": token, "batch_id": batch_id, "batch": batch}


def require_swpc_hostname(name: str) -> None:
    if sys.platform != "linux" or name.split(".", 1)[0].casefold() != "swpc":
        raise HILFailure("live engineering HIL is restricted to the SWPC Linux host")


def validate_tty(value: str) -> None:
    if not (value == "/dev/ttyACM0" or value.startswith("/dev/serial/by-id/")):
        raise HILFailure("CDC port must be /dev/serial/by-id/... or explicit /dev/ttyACM0")


def run(args: argparse.Namespace) -> int:
    order = sequence(args.mode, args.cycles)
    validate_tty(args.port)
    require_loopback(args.manager_url)
    images = {"v0.1": image_spec(args.image_v01, "v0.1"),
              "v0.2": image_spec(args.image_v02, "v0.2")}
    if not args.execute:
        print(json.dumps({"result": "PLAN_ONLY", "mode": args.mode,
                          "attempts": len(order), "order": order,
                          "hardware": "NOT_RUN"}))
        return 0
    require_swpc_hostname(socket.gethostname())
    if not 1 <= args.site <= 8 or not re.fullmatch(r"[A-Za-z0-9._:-]{1,96}", args.ppu_alias):
        raise HILFailure("invalid PPU alias or Site")
    os.umask(0o077)
    root = args.output.expanduser()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        + "-" + str(os.getpid()))
    directory.mkdir(mode=0o700)
    client = Manager(args.manager_url)
    report: dict = {"schema": "plasma.engineering.hil-e2e.v1",
                    "mode": args.mode, "source": "SWPC_MANAGER_API",
                    "ppu_alias": args.ppu_alias, "site_id": args.site,
                    "results": [], "result": "IN_PROGRESS"}
    try:
        for n, version in enumerate(order, 1):
            image = images[version]
            result, raw = one_attempt(client, args.ppu_alias, args.site, image,
                                      args.batch_timeout, args.poll_interval)
            # Do not store input image bytes or any authentication material.
            (directory / f"{n:03d}-batch.json").write_text(
                json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            cdc_path = directory / f"{n:03d}-cdc.log"
            with cdc_path.open("w", encoding="utf-8") as sink:
                with redirect_stdout(sink):
                    run_live(args.port, args.cdc_duration, args.cdc_tolerance,
                             version=IMAGES[version]["version"])
            result.update(version=version, cdc="PASS", firmware_sha256=image["sha256"])
            report["results"].append(result)
            print(f"ATTEMPT {n}/{len(order)} {version}: E/P/V + Readback + CDC PASS",
                  flush=True)
        report["result"] = "PASS"
        return 0
    except (HILFailure, AssertionError, OSError, ImportError, RuntimeError, UnicodeError) as exc:
        report["result"] = "BLOCKED"
        report["reason"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        report["last_preview_plan_id"] = client.last_preview_plan_id
        report["last_start_id"] = client.last_start_id
        report["last_batch_id"] = client.last_batch_id
        print(f"HIL BLOCKED: {report['reason']}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        # A running Manager Batch is not cancelled just because this observer
        # exits; leave the exact Start/Batch IDs for read-only reconciliation.
        report["result"] = "OUTCOME_UNKNOWN"
        report["reason"] = "OPERATOR_INTERRUPTED_OBSERVER_DO_NOT_RESUBMIT"
        report["last_preview_plan_id"] = client.last_preview_plan_id
        report["last_start_id"] = client.last_start_id
        report["last_batch_id"] = client.last_batch_id
        return 130
    finally:
        (directory / "summary.json").write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(f"EVIDENCE: {directory}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", choices=("bluepill-ab",), required=True)
    p.add_argument("--mode", choices=("smoke", "burn-in"), default="smoke")
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--manager-url", default="http://127.0.0.1:18280")
    p.add_argument("--ppu-alias", default="z2")
    p.add_argument("--site", type=int, default=2)
    p.add_argument("--port", required=True)
    p.add_argument("--image-v01", type=Path, required=True)
    p.add_argument("--image-v02", type=Path, required=True)
    p.add_argument("--batch-timeout", type=float, default=900.0)
    p.add_argument("--poll-interval", type=float, default=1.0)
    p.add_argument("--cdc-duration", type=float, default=30.0)
    p.add_argument("--cdc-tolerance", type=float, default=0.2)
    p.add_argument("--output", type=Path, default=Path("~/plasma-engineering-hil"))
    p.add_argument("--execute", action="store_true",
                   help="explicitly use current Manager/PPU owner authorization to program DUT")
    args = p.parse_args(argv)
    if (not all(math.isfinite(value) for value in
                (args.batch_timeout, args.poll_interval,
                 args.cdc_duration, args.cdc_tolerance))
            or args.batch_timeout < 30 or not 0.2 <= args.poll_interval <= 10
            or args.cdc_duration < 10 or not 0.0 < args.cdc_tolerance <= 1.0):
        p.error("invalid bounded time/tolerance values")
    try:
        return run(args)
    except (HILFailure, OSError) as exc:
        print(f"HIL BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
