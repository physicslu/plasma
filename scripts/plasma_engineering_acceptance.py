#!/usr/bin/env python3
"""SWPC engineering-only controlled composition: deploy -> verify -> HIL.

This is a coordinator, not another Deployment Engine or Programming Engine.
The individual tools remain independently callable. No action by default.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PLASMACTL = ROOT / "scripts" / "plasmactl"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
INSTALLED_SHA = re.compile(r"(?m)^Git SHA:[ \t]*([0-9a-f]{40})[ \t]*$")


class AcceptanceBlocked(Exception):
    pass


def source_identity(run_cmd) -> str:
    result = run_cmd(["git", "-C", str(ROOT), "rev-parse", "HEAD"], 15)
    sha = result.strip()
    if not SHA40.fullmatch(sha):
        raise AcceptanceBlocked("SOURCE_SHA_UNAVAILABLE")
    changes = run_cmd(["git", "-C", str(ROOT), "status", "--porcelain"], 15)
    if changes.strip():
        raise AcceptanceBlocked("SOURCE_WORKTREE_NOT_CLEAN")
    return sha


def subprocess_run(argv: list[str], timeout_s: float) -> str:
    try:
        proc = subprocess.run(
            argv, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AcceptanceBlocked(
            "COMMAND_TIMEOUT: execution outcome may be unknown; do not retry automatically"
        ) from exc
    except OSError as exc:
        raise AcceptanceBlocked(f"COMMAND_UNAVAILABLE:{type(exc).__name__}") from exc
    if proc.returncode != 0:
        # Avoid copying an untrusted program's raw logs into higher-level evidence.
        raise AcceptanceBlocked(f"COMMAND_FAILED:{Path(argv[0]).name}:exit={proc.returncode}")
    return proc.stdout


def hil_arguments(args: argparse.Namespace) -> list[str]:
    return [
        str(PLASMACTL), "hil", "programming",
        "--profile", "bluepill-ab", "--mode", "smoke",
        "--site", str(args.site), "--ppu-alias", args.ppu_alias,
        "--image-v01", str(args.image_v01), "--image-v02", str(args.image_v02),
        "--port", args.port,
    ]


def validate_hil_evidence(root: Path, *, ppu_alias: str, site: int) -> Path:
    """Require the child's own durable three-attempt HIL summary to claim PASS."""
    if not root.is_dir() or root.is_symlink():
        raise AcceptanceBlocked("HIL_EVIDENCE_ROOT_MISSING")
    results = list(root.glob("*/summary.json"))
    if len(results) != 1 or results[0].is_symlink():
        raise AcceptanceBlocked("HIL_EVIDENCE_AMBIGUOUS_OR_MISSING")
    path = results[0]
    if path.parent.is_symlink():
        raise AcceptanceBlocked("HIL_EVIDENCE_SYMLINK_DENIED")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AcceptanceBlocked("HIL_EVIDENCE_UNREADABLE") from exc
    if (not isinstance(payload, dict)
            or payload.get("schema") != "plasma.engineering.hil-e2e.v1"
            or payload.get("result") != "PASS"
            or payload.get("mode") != "smoke"
            or payload.get("ppu_alias") != ppu_alias
            or payload.get("site_id") != site):
        raise AcceptanceBlocked("HIL_EVIDENCE_IDENTITY_OR_RESULT_MISMATCH")
    attempts = payload.get("results")
    if not isinstance(attempts, list) or len(attempts) != 3:
        raise AcceptanceBlocked("HIL_ATTEMPT_COUNT_MISMATCH")
    for attempt, expected_version in zip(attempts, ("v0.1", "v0.2", "v0.1")):
        if (not isinstance(attempt, dict)
                or attempt.get("version") != expected_version
                or attempt.get("cdc") != "PASS"
                or attempt.get("safe_off") is not True
                or not isinstance(attempt.get("firmware_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", attempt["firmware_sha256"])
                or attempt.get("readback_sha256") != attempt["firmware_sha256"]
                or not isinstance(attempt.get("batch_id"), str)
                or not attempt["batch_id"]):
            raise AcceptanceBlocked("HIL_ATTEMPT_EVIDENCE_MISMATCH")
    return path.parent


def steps(run_cmd, args: argparse.Namespace, *, sha: str, report: dict) -> None:
    hil = hil_arguments(args)
    # Validate locked fixture bytes and the CLI contract BEFORE changing the
    # currently installed software. With no --execute, HIL makes no API call.
    print("ACCEPTANCE: HIL fixture preflight", flush=True)
    run_cmd(hil, 60)
    report["stages"].append({"name": "HIL_FIXTURE_PREFLIGHT", "result": "PASS"})

    print("ACCEPTANCE: Control Station deployment", flush=True)
    run_cmd([str(PLASMACTL), "deploy", "local-control-station"], args.deploy_timeout)
    report["stages"].append({"name": "DEPLOY", "result": "PASS"})

    status = run_cmd([str(PLASMACTL), "status", "local-control-station"], 30)
    match = INSTALLED_SHA.search(status)
    if match is None or match.group(1) != sha:
        raise AcceptanceBlocked("DEPLOYED_RELEASE_SHA_MISMATCH")
    report["stages"].append({"name": "RELEASE_IDENTITY", "result": "PASS"})

    print("ACCEPTANCE: release identity and postflight", flush=True)
    run_cmd([str(PLASMACTL), "verify", "local-control-station"], 45)
    report["stages"].append({"name": "POSTFLIGHT", "result": "PASS"})

    # Last stage: performs real Erase/Program/Verify on the selected Site.
    # Never send it a retry flag. If the POST outcome is unobservable, the
    # HIL runner preserves the start_id and refuses to re-submit.
    report["hil_evidence_root"] = str(Path(report["evidence_dir"]) / "hil")
    print("ACCEPTANCE: Manager Batch → DUT → CDC HIL", flush=True)
    run_cmd([*hil, "--output", report["hil_evidence_root"], "--execute"],
            args.hil_timeout)
    actual = validate_hil_evidence(
        Path(report["hil_evidence_root"]), ppu_alias=args.ppu_alias, site=args.site
    )
    report["hil_evidence_dir"] = str(actual)
    report["stages"].append({"name": "MANAGER_BATCH_CDC_HIL", "result": "PASS"})


def run(args: argparse.Namespace, run_cmd=subprocess_run) -> int:
    sha = source_identity(run_cmd)
    if args.expected_source_sha and sha != args.expected_source_sha:
        raise AcceptanceBlocked("SOURCE_SHA_NOT_APPROVED")
    if not args.execute:
        # Preview is host-only and does not test API, Z2 or DUT.
        run_cmd(hil_arguments(args), 60)
        print(json.dumps({
            "result": "PLAN_ONLY", "source_sha": sha, "hardware": "NOT_RUN",
            "deployment": "NOT_RUN", "order": [
                "HIL_FIXTURE_PREFLIGHT", "DEPLOY", "RELEASE_IDENTITY",
                "POSTFLIGHT", "MANAGER_BATCH_CDC_HIL",
            ],
        }, sort_keys=True))
        return 0
    if not args.expected_source_sha or not SHA40.fullmatch(args.expected_source_sha):
        raise AcceptanceBlocked("EXECUTE_REQUIRES_EXACT_SOURCE_SHA")
    if sys.platform != "linux" or socket.gethostname().split(".", 1)[0].casefold() != "swpc":
        raise AcceptanceBlocked("SWPC_LINUX_REQUIRED")
    if args.site not in range(1, 9):
        raise AcceptanceBlocked("INVALID_SITE")
    os.umask(0o077)
    evidence_root = args.output.expanduser()
    evidence_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = evidence_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                                 + f"-{os.getpid()}")
    directory.mkdir(mode=0o700)
    report = {
        "schema": "plasma.engineering.acceptance-full.v1",
        "source_sha": sha, "profile": "local-control-station",
        "ppu_alias": args.ppu_alias, "site": args.site,
        "result": "IN_PROGRESS", "stages": [],
        "hil_automatic_retry": False, "evidence_dir": str(directory),
    }
    try:
        steps(run_cmd, args, sha=sha, report=report)
        report["result"] = "PASS"
        return 0
    except AcceptanceBlocked as exc:
        report["result"] = "BLOCKED"
        report["reason"] = str(exc)
        report["operator_action"] = "RECONCILE_BEFORE_ANY_RETRY"
        print(f"ACCEPTANCE BLOCKED: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        report["result"] = "OUTCOME_UNKNOWN"
        report["reason"] = "INTERRUPTED; no automatic deployment or HIL retry"
        return 130
    finally:
        (directory / "summary.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"ACCEPTANCE EVIDENCE: {directory}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", required=True, choices=("bluepill-ab",))
    p.add_argument("--site", type=int, default=2)
    p.add_argument("--ppu-alias", default="z2")
    p.add_argument("--image-v01", type=Path, required=True)
    p.add_argument("--image-v02", type=Path, required=True)
    p.add_argument("--port", required=True)
    p.add_argument("--expected-source-sha", default="")
    p.add_argument("--deploy-timeout", type=int, default=1200)
    p.add_argument("--hil-timeout", type=int, default=3600)
    p.add_argument("--output", type=Path, default=Path("~/plasma-engineering-acceptance"))
    p.add_argument("--execute", action="store_true")
    args = p.parse_args(argv)
    if not 120 <= args.deploy_timeout <= 7200 or not 120 <= args.hil_timeout <= 14400:
        p.error("invalid bounded timeout")
    try:
        return run(args)
    except AcceptanceBlocked as exc:
        print(f"ACCEPTANCE BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
