from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUALIFICATION_STATES = (
    "UNPROVISIONED",
    "HOST_READY",
    "RUNNER_ENROLLED",
    "L4_PASS",
    "STALE",
    "REVOKED",
)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unable to read JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON evidence must be an object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"required GitHub Actions environment variable is missing: {name}")
    return value


def _validate_preflight(report: dict[str, Any], event_sha: str) -> None:
    if report.get("status") != "PASS":
        raise RuntimeError("persistent preflight did not PASS")
    if report.get("qualification_state") != "RUNNER_ENROLLED":
        raise RuntimeError("persistent preflight did not prove RUNNER_ENROLLED state")
    identity = report.get("identity")
    if not isinstance(identity, dict):
        raise RuntimeError("persistent preflight identity evidence is missing")
    if identity.get("event_sha") != event_sha or identity.get("checked_out_sha") != event_sha:
        raise RuntimeError("persistent preflight SHA identity does not match GITHUB_SHA")
    if identity.get("ref") != "refs/heads/main" or not identity.get("main_only"):
        raise RuntimeError("persistent preflight is not main-only evidence")
    if report.get("z2_hardware_claim") != "NONE":
        raise RuntimeError("persistent preflight must not claim Z2 hardware evidence")


def _validate_fingerprint(report: dict[str, Any], event_sha: str) -> None:
    if report.get("git_sha") != event_sha:
        raise RuntimeError("persistent environment fingerprint SHA does not match GITHUB_SHA")
    if report.get("z2_network_backend_claim") != "NONE":
        raise RuntimeError("persistent environment fingerprint must not claim a Z2 backend")


def _validate_repeatability(report: dict[str, Any], event_sha: str) -> None:
    if report.get("overall_result") != "PASS":
        raise RuntimeError("persistent repeatability evidence did not PASS")
    if report.get("run_count") != 2:
        raise RuntimeError("persistent repeatability evidence must contain exactly two runs")
    runs = report.get("runs")
    if not isinstance(runs, list) or len(runs) != 2:
        raise RuntimeError("persistent repeatability run evidence is incomplete")
    for run in runs:
        if not isinstance(run, dict) or run.get("git_sha") != event_sha:
            raise RuntimeError("persistent repeatability run SHA does not match GITHUB_SHA")
    if report.get("manual_cleanup") is not False or report.get("sudo") is not False:
        raise RuntimeError("persistent repeatability evidence violates no-cleanup/no-sudo contract")


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create the canonical exact-run Plasma persistent L4 qualification summary."
    )
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--fingerprint", type=Path, required=True)
    parser.add_argument("--repeatability", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "FAIL",
        "qualification_state": "RUNNER_ENROLLED",
        "qualification_state_model": list(QUALIFICATION_STATES),
        "evidence_level": "L4_persistent_integration_host",
        "z2_hardware_claim": "NONE",
    }
    try:
        event_sha = _require_env("GITHUB_SHA")
        repository = _require_env("GITHUB_REPOSITORY")
        run_id = _require_env("GITHUB_RUN_ID")
        run_attempt = _require_env("GITHUB_RUN_ATTEMPT")
        workflow = _require_env("GITHUB_WORKFLOW")
        runner_name = _require_env("RUNNER_NAME")
        runner_os = _require_env("RUNNER_OS")
        runner_arch = _require_env("RUNNER_ARCH")

        preflight = _load(args.preflight)
        fingerprint = _load(args.fingerprint)
        repeatability = _load(args.repeatability)
        _validate_preflight(preflight, event_sha)
        _validate_fingerprint(fingerprint, event_sha)
        _validate_repeatability(repeatability, event_sha)

        host = preflight.get("host") if isinstance(preflight.get("host"), dict) else {}
        persistent_root = (
            preflight.get("persistent_root")
            if isinstance(preflight.get("persistent_root"), dict)
            else {}
        )
        docker = preflight.get("docker") if isinstance(preflight.get("docker"), dict) else {}
        armv7 = preflight.get("armv7") if isinstance(preflight.get("armv7"), dict) else {}
        network = preflight.get("network") if isinstance(preflight.get("network"), dict) else {}

        report.update(
            {
                "status": "PASS",
                "qualification_state": "L4_PASS",
                "qualified_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "repository": repository,
                "qualified_sha": event_sha,
                "github_run": {
                    "run_id": run_id,
                    "run_attempt": run_attempt,
                    "workflow": workflow,
                },
                "runner": {
                    "name": runner_name,
                    "os": runner_os,
                    "arch": runner_arch,
                    "version_evidence_source": (
                        "GitHub Actions job-start log bound to github_run.run_id"
                    ),
                },
                "host_binding": {
                    "hostname": host.get("hostname") or host.get("machine"),
                    "uid": host.get("uid"),
                    "gid": host.get("gid"),
                    "kernel_release": host.get("kernel_release"),
                    "machine": host.get("machine"),
                    "os_release": host.get("os_release"),
                    "docker_server_version": docker.get("server_version"),
                    "docker_root_dir": docker.get("root_dir"),
                    "docker_rootless": docker.get("rootless"),
                    "armv7_image": armv7.get("image"),
                    "armv7_machine": armv7.get("machine"),
                    "persistent_root": persistent_root.get("path"),
                    "persistent_root_filesystem": persistent_root.get("filesystem"),
                    "persistent_root_mode": persistent_root.get("mode"),
                    "default_route_signature_sha256": network.get(
                        "default_route_signature_sha256"
                    ),
                },
                "evidence": {
                    "preflight": {
                        "path": str(args.preflight),
                        "sha256": _sha256(args.preflight),
                    },
                    "environment_fingerprint": {
                        "path": str(args.fingerprint),
                        "sha256": _sha256(args.fingerprint),
                    },
                    "repeatability": {
                        "path": str(args.repeatability),
                        "sha256": _sha256(args.repeatability),
                    },
                },
                "staleness_contract": {
                    "exact_sha_bound": True,
                    "becomes_stale_when_main_sha_changes": True,
                    "becomes_stale_when_bound_host_fingerprint_changes": True,
                    "administrative_revocation_overrides_pass": True,
                    "fixed_time_to_live": "NONE",
                },
                "not_claimed": [
                    "required PR status-check enforcement",
                    "PYNQ-Z2 hardware",
                    "PYNQ-Z2 native network backend",
                    "physical Ethernet MAC/PHY/cable/switch behavior",
                    "PS-to-PL",
                    "FPGA Site I/O",
                    "target power control",
                    "real IC programming",
                    "eight-Site concurrent programming",
                ],
            }
        )
        _write_report(args.report, report)
        print(
            "PLASMA_PERSISTENT_INTEGRATION_QUALIFICATION="
            + json.dumps(report, sort_keys=True, separators=(",", ":")),
            flush=True,
        )
        return 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        _write_report(args.report, report)
        print(f"[FAIL] persistent integration qualification summary: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
