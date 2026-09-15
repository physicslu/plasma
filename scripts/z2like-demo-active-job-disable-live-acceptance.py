#!/usr/bin/env python3
"""Live-negative acceptance for active-Site-Job disable rejection.

This gate proves that the public Manager refuses ``commissioned -> disabled``
while a real configured-Mock Site Job is active on the canonical SWPC/QEMU
z2like-demo target.

The configured-Mock provider is the deployed QEMU Programming provider. It is
not the legacy mutable Mock Runtime, so this gate never reads or writes
``/api/mock/runtime``. The QEMU simulation installer owns the deterministic
bounded erase delay used to make one Job observable across Manager poll cycles.

The gate never reports the Bootstrap pairing token or browser maintenance
capability. It cancels the live test Job on exit and never forces a lifecycle
transition.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Mapping, Sequence


BASE_SCRIPT = Path(__file__).with_name("z2like-demo-browser-live-acceptance.py")
_SPEC = importlib.util.spec_from_file_location("_z2like_demo_browser_live", BASE_SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load shared live-acceptance helpers from {BASE_SCRIPT}")
_live = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_live)

AcceptanceError = _live.AcceptanceError
BrowserSession = _live.BrowserSession

TERMINAL_JOB_STATES = frozenset(
    {"success", "failed", "cancelled", "timeout", "aborted"}
)
TEST_SITE_ID = 1


def _safe_segment(value: str, label: str) -> str:
    if not value or urllib.parse.quote(value, safe="") != value:
        raise AcceptanceError(f"{label} is not a safe canonical path segment")
    return value


def _engineering_root(facility_id: str, ppu_id: str) -> str:
    facility = _safe_segment(facility_id, "facility_id")
    ppu = _safe_segment(ppu_id, "ppu_id")
    return f"/api/manager/ppu/api/engineering/targets/{facility}/{ppu}"


def _require_configured_mock_catalog(session: BrowserSession) -> dict[str, Any]:
    status, payload, _ = session.request("/api/manager/ppu/api/engineering/targets")
    _live._expect(status, 200, payload, "configured-Mock Programming catalog")
    if not (
        payload.get("ok") is True
        and payload.get("provider") == "configured_mock"
        and payload.get("ppu_count") == 1
        and payload.get("site_count") == _live.EXPECTED_SITE_COUNT
    ):
        raise AcceptanceError(
            f"active-Job gate requires the canonical configured_mock 8-Site provider: {payload!r}"
        )
    return payload


def _start_erase_job(
    session: BrowserSession,
    *,
    facility_id: str,
    ppu_id: str,
) -> str:
    root = _engineering_root(facility_id, ppu_id)
    status, payload, _ = session.request(
        f"{root}/api/jobs",
        method="POST",
        body={"site_id": TEST_SITE_ID, "operation": "erase"},
    )
    _live._expect(status, 202, payload, "configured-Mock live erase Job start")
    job = payload.get("job")
    job_id = job.get("job_id") if isinstance(job, dict) else payload.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise AcceptanceError("configured-Mock live erase Job omitted job_id")
    return job_id


def _job_snapshot(
    session: BrowserSession,
    *,
    facility_id: str,
    ppu_id: str,
    job_id: str,
) -> dict[str, Any]:
    root = _engineering_root(facility_id, ppu_id)
    query = urllib.parse.urlencode({"site": TEST_SITE_ID, "job": job_id})
    status, payload, _ = session.request(f"{root}/api/status?{query}")
    _live._expect(status, 200, payload, "configured-Mock live Job status")
    job = payload.get("job")
    if not isinstance(job, dict):
        raise AcceptanceError("configured-Mock live Job status omitted job")
    return job


def _cancel_job(
    session: BrowserSession,
    *,
    facility_id: str,
    ppu_id: str,
    job_id: str,
) -> None:
    current = _job_snapshot(
        session,
        facility_id=facility_id,
        ppu_id=ppu_id,
        job_id=job_id,
    )
    if str(current.get("state") or "").lower() in TERMINAL_JOB_STATES:
        return
    root = _engineering_root(facility_id, ppu_id)
    status, payload, _ = session.request(
        f"{root}/api/jobs/{urllib.parse.quote(job_id, safe='')}/cancel",
        method="POST",
        body={},
    )
    _live._expect(status, 200, payload, "configured-Mock live Job cancel")


def _wait_job_terminal(
    session: BrowserSession,
    *,
    facility_id: str,
    ppu_id: str,
    job_id: str,
    timeout_s: float = 45.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = _job_snapshot(
            session,
            facility_id=facility_id,
            ppu_id=ppu_id,
            job_id=job_id,
        )
        if str(last.get("state") or "").lower() in TERMINAL_JOB_STATES:
            return last
        time.sleep(0.5)
    raise AcceptanceError(f"configured-Mock live Job did not become terminal: {last!r}")


def _wait_manager_observes_job(
    session: BrowserSession,
    alias: str,
    job_id: str,
    *,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last = "no fleet response"
    while time.monotonic() < deadline:
        payload, ppu = _live._fleet_ppu(session, alias)
        observation = ppu.get("observation")
        topology = ppu.get("topology")
        sites = topology.get("sites") if isinstance(topology, dict) else None
        if isinstance(observation, dict) and observation.get("state") == "current" and isinstance(sites, list):
            for site in sites:
                if not isinstance(site, dict) or site.get("site_id") != TEST_SITE_ID:
                    continue
                if site.get("current_job_id") == job_id:
                    return payload
        last = json.dumps(
            {
                "observed_at": payload.get("observed_at"),
                "observation": observation,
                "topology": topology,
            },
            sort_keys=True,
        )
        time.sleep(1.0)
    raise AcceptanceError(
        f"Manager did not publish the active configured-Mock Site Job before timeout: {last}"
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[1]
    session = BrowserSession(args.origin)
    deployed_commit = _live._wait_public_deployment(
        session,
        expected_commit=args.expected_commit,
        repo=repo,
        timeout_s=args.render_timeout,
    )

    _live._local_ingress_acceptance(args.local_managed_origin)
    entry = _live._registry_entry(session, args.alias)
    if entry.get("endpoint") != args.expected_ppu_endpoint.rstrip("/"):
        raise AcceptanceError(
            f"canonical registry endpoint mismatch: {entry.get('endpoint')!r} != "
            f"{args.expected_ppu_endpoint!r}"
        )
    if entry.get("lifecycle") != "commissioned":
        raise AcceptanceError(
            f"active-Job live-negative gate requires commissioned lifecycle, "
            f"found {entry.get('lifecycle')!r}"
        )

    _, ppu = _live._wait_current_idle(session, args.alias, timeout_s=120.0)
    _require_configured_mock_catalog(session)
    identity = ppu.get("identity")
    if not isinstance(identity, dict):
        raise AcceptanceError("public fleet omitted PPU identity")
    facility_id = identity.get("facility_id")
    ppu_id = identity.get("ppu_id")
    if not all(isinstance(value, str) and value for value in (facility_id, ppu_id)):
        raise AcceptanceError(f"public fleet identity is incomplete: {identity!r}")

    token = _live._read_pairing_token(args.container)
    try:
        status, paired, _ = session.request(
            f"/api/manager/registry/{args.alias}/bootstrap/pair",
            method="POST",
            body={"token": token},
        )
    finally:
        token = ""
    _live._expect(status, 200, paired, "verified pairing for active-Job live-negative gate")
    if not session.capability_value():
        raise AcceptanceError("verified pairing did not issue maintenance capability")

    job_id: str | None = None
    unexpected_disabled = False
    active_observed_at: str | None = None
    terminal_state: str | None = None
    cleanup_errors: list[str] = []

    try:
        job_id = _start_erase_job(
            session,
            facility_id=str(facility_id),
            ppu_id=str(ppu_id),
        )
        active_snapshot = _wait_manager_observes_job(session, args.alias, job_id)
        observed_at = active_snapshot.get("observed_at")
        active_observed_at = observed_at if isinstance(observed_at, str) else None

        status, blocked, _ = session.request(
            f"/api/manager/registry/{args.alias}",
            method="PATCH",
            body={"lifecycle": "disabled"},
        )
        if status == 200:
            unexpected_disabled = True
            raise AcceptanceError(
                "Manager unexpectedly allowed commissioned -> disabled while an active Site Job was observed"
            )
        _live._expect(
            status,
            409,
            blocked,
            "disable while active Site Job",
            code="ppu_busy",
        )
    finally:
        if job_id is not None:
            try:
                _cancel_job(
                    session,
                    facility_id=str(facility_id),
                    ppu_id=str(ppu_id),
                    job_id=job_id,
                )
                terminal = _wait_job_terminal(
                    session,
                    facility_id=str(facility_id),
                    ppu_id=str(ppu_id),
                    job_id=job_id,
                )
                terminal_state = str(terminal.get("state") or "")
                _live._wait_current_idle(session, args.alias, timeout_s=60.0)
            except AcceptanceError as exc:
                cleanup_errors.append(f"job cleanup: {exc}")

        if unexpected_disabled:
            try:
                _live._wait_current_idle(session, args.alias, timeout_s=60.0)
                _live._set_lifecycle(session, args.alias, "commissioned", timeout_s=90.0)
            except AcceptanceError as exc:
                cleanup_errors.append(f"lifecycle cleanup: {exc}")

        if cleanup_errors and sys.exc_info()[0] is None:
            raise AcceptanceError("; ".join(cleanup_errors))
        if cleanup_errors and sys.exc_info()[0] is not None:
            print(
                "z2like-demo-active-job-disable-live-acceptance: cleanup warning: "
                + "; ".join(cleanup_errors),
                file=sys.stderr,
            )

    return {
        "result": "PASS",
        "evidence_level": "live-swpc-render-qemu-active-site-job-negative",
        "public_origin": args.origin,
        "render_deployed_commit": deployed_commit,
        "accepted_source_commit": args.expected_commit,
        "upstream_browser_workflow_run_id": args.upstream_browser_run_id,
        "ppu_alias": args.alias,
        "ppu_endpoint": args.expected_ppu_endpoint,
        "programming_provider": "configured_mock",
        "configured_mock_runtime_mutated": False,
        "test_site_id": TEST_SITE_ID,
        "active_site_job_observed": "PASS",
        "active_site_job_observed_at": active_observed_at,
        "disable_while_active_site_job": "BLOCKED_PPU_BUSY",
        "test_job_terminal_state": terminal_state,
        "pairing_secret_exposed": False,
        "maintenance_capability_exposed": False,
        "not_live_qualified_by_this_gate": [
            "forced stale/non-idle maintenance proof rejection",
            "15-minute capability expiry wall-clock rejection",
            "real PYNQ-Z2 deployment/reboot/rollback",
            "PL/FPGA behavior",
            "target power/electrical behavior",
            "real IC programming",
            "physical multi-Site concurrency",
        ],
    }


def _write_report(path: Path | None, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prove z2like-demo rejects disable while an active configured-Mock Site Job exists"
    )
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--upstream-browser-run-id", required=True)
    parser.add_argument("--origin", default="https://z2like-demo.open4th.com")
    parser.add_argument("--expected-ppu-endpoint", default="https://ppu-managed-lab.open4th.com")
    parser.add_argument("--alias", default="z2like-qemu")
    parser.add_argument("--container", default="plasma-z2like-demo-qemu")
    parser.add_argument("--local-managed-origin", default="http://127.0.0.1:18082")
    parser.add_argument("--render-timeout", type=float, default=600.0)
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not _live.HEX40.fullmatch(args.expected_commit):
        print(
            "z2like-demo-active-job-disable-live-acceptance: expected commit must be a full 40-hex SHA",
            file=sys.stderr,
        )
        return 2
    if not args.upstream_browser_run_id.isdigit():
        print(
            "z2like-demo-active-job-disable-live-acceptance: upstream browser run id must be numeric",
            file=sys.stderr,
        )
        return 2
    try:
        report = run(args)
    except (AcceptanceError, OSError) as exc:
        report = {
            "result": "FAIL",
            "evidence_level": "live-swpc-render-qemu-active-site-job-negative",
            "accepted_source_commit": args.expected_commit,
            "upstream_browser_workflow_run_id": args.upstream_browser_run_id,
            "error": str(exc),
            "safety": (
                "No force lifecycle transition is permitted; configured-Mock runtime settings are not mutated; "
                "Job cancellation and normal lifecycle cleanup are attempted on every post-pairing exit."
            ),
        }
        _write_report(args.report, report)
        return 2
    _write_report(args.report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())