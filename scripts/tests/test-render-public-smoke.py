#!/usr/bin/env python3
"""Cold-start-aware smoke acceptance for the public Render Plasma demo."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_ORIGIN = "https://plasma-6zz7.onrender.com"
USER_AGENT = "plasma-render-public-smoke/1"


@dataclass
class SmokeReport:
    origin: str
    expected_commit: str | None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    observed_commit: str | None = None
    cold_start_seconds: float | None = None
    checks: dict[str, str] = field(default_factory=dict)

    def to_dict(self, *, result: str, error: str | None = None) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "result": result,
            "origin": self.origin,
            "expected_commit": self.expected_commit,
            "observed_commit": self.observed_commit,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "cold_start_seconds": self.cold_start_seconds,
            "checks": self.checks,
            "error": error,
        }


def request(origin: str, path: str, *, timeout: float) -> tuple[int, str, bytes]:
    req = Request(
        origin.rstrip("/") + path,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    with urlopen(req, timeout=timeout) as response:
        return response.status, response.headers.get_content_type(), response.read()


def request_json(origin: str, path: str, *, timeout: float) -> dict[str, Any]:
    status, content_type, body = request(origin, path, timeout=timeout)
    if status != 200:
        raise RuntimeError(f"{path} returned HTTP {status}")
    if content_type != "application/json":
        raise RuntimeError(f"{path} returned {content_type}, expected application/json")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} JSON payload is not an object")
    return payload


def deployment_commit(origin: str, *, timeout: float) -> str | None:
    try:
        payload = request_json(origin, "/deployment.json", timeout=timeout)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, RuntimeError):
        return None
    value = payload.get("git_commit")
    return value if isinstance(value, str) and value else None


def wait_until_ready(
    origin: str,
    *,
    expected_commit: str | None,
    wake_timeout: float,
    poll_interval: float,
    request_timeout: float,
    report: SmokeReport,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + wake_timeout
    last_issue = "service has not responded yet"

    # The first request intentionally wakes a sleeping Render Free instance.
    try:
        request(origin, "/", timeout=request_timeout)
    except (HTTPError, URLError, TimeoutError):
        pass

    while time.monotonic() < deadline:
        if expected_commit:
            observed = deployment_commit(origin, timeout=request_timeout)
            if not observed:
                last_issue = (
                    "deployment identity is not available yet; waiting for a deployment "
                    f"that reports expected commit {expected_commit}"
                )
                time.sleep(poll_interval)
                continue
            report.observed_commit = observed
            if observed != expected_commit:
                last_issue = (
                    f"Render is serving commit {observed}, waiting for expected {expected_commit}"
                )
                time.sleep(poll_interval)
                continue

        try:
            payload = request_json(origin, "/api/health/ready", timeout=request_timeout)
            if (
                payload.get("ok") is True
                and payload.get("gateway") == "alive"
                and payload.get("execution") == "ready"
            ):
                report.cold_start_seconds = round(time.monotonic() - started, 3)
                report.checks["readiness"] = "PASS"
                return payload
            last_issue = f"readiness payload not ready: {payload!r}"
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_issue = f"{type(exc).__name__}: {exc}"
        time.sleep(poll_interval)

    raise RuntimeError(
        f"Render did not reach the requested deployment/readiness state within "
        f"{wake_timeout:.0f}s; last observation: {last_issue}"
    )


def assert_ui_routes(origin: str, *, timeout: float, report: SmokeReport) -> None:
    for path in ("/", "/demo", "/fleet", "/fleet/programming", "/engineering", "/devices", "/ppu"):
        status, content_type, body = request(origin, path, timeout=timeout)
        if status != 200 or content_type != "text/html":
            raise RuntimeError(f"{path} returned HTTP {status} {content_type}")
        if report.expected_commit is not None:
            if b"Plasma Control Station" not in body:
                raise RuntimeError(f"{path} does not contain the Plasma Control Station shell")
            if b"Plasma PPU Console" in body or b"SITE MATRIX" in body or b"PPU CONTROL" in body:
                raise RuntimeError(f"{path} exposes the retired Single PPU Programming shell")
        elif b"Plasma Control Station" not in body and b"Plasma PPU Console" not in body:
            # Pull-request smoke observes whatever main revision is already deployed.
            # Accept the previous shell until this PR itself is deployed; pinned
            # post-deployment smoke enforces the new Control Station ownership.
            raise RuntimeError(f"{path} does not contain a recognized Plasma product shell")
        report.checks[f"ui:{path}"] = "PASS"


def assert_contracts(origin: str, *, timeout: float, report: SmokeReport) -> None:
    status = request_json(origin, "/api/status", timeout=timeout)
    ppu = status.get("ppu")
    sites = status.get("sites")
    if not isinstance(ppu, dict) or ppu.get("ppu_id") != "render-demo-ppu":
        raise RuntimeError("/api/status does not expose render-demo-ppu")
    if not isinstance(sites, list) or len(sites) != 8:
        raise RuntimeError("/api/status does not expose the expected 8 local Mock Sites")
    report.checks["api:status"] = "PASS"

    catalog = request_json(origin, "/api/engineering/targets", timeout=timeout)
    expected_counts = {(8, 32, 160)}
    # Pull-request smoke observes the currently deployed main commit without
    # pinning it to the PR. Accept the previous topology until this change is
    # deployed; pinned post-deployment smoke remains strict for 8/32/160.
    if report.expected_commit is None:
        expected_counts.add((3, 12, 60))
    actual_counts = (
        catalog.get("facility_count"),
        catalog.get("ppu_count"),
        catalog.get("site_count"),
    )
    if catalog.get("ok") is not True or catalog.get("rest_contract_version") != "3":
        raise RuntimeError("Engineering target catalog is not Web REST v3 ready")
    if catalog.get("provider") != "mock" or actual_counts not in expected_counts:
        raise RuntimeError(
            f"Engineering target catalog mismatch: provider={catalog.get('provider')!r}, "
            f"counts={actual_counts!r}"
        )
    report.checks["api:engineering-targets"] = "PASS"

    # Pull-request runs intentionally observe the currently deployed main revision,
    # not the PR head. New deployment contracts are therefore enforced only when
    # the smoke test is pinned to the exact revision expected to be live.
    if report.expected_commit is not None:
        device_search = request_json(origin, "/api/devices/search?q=stm32&limit=1", timeout=timeout)
        results = device_search.get("results")
        catalog_size = device_search.get("catalog_size")
        if device_search.get("ok") is not True or device_search.get("rest_contract_version") != "3":
            raise RuntimeError("Device Catalog search is not Web REST v3 ready")
        if isinstance(catalog_size, bool) or not isinstance(catalog_size, int) or catalog_size < 7000:
            raise RuntimeError(f"Device Catalog size is invalid: {catalog_size!r}")
        if not isinstance(results, list) or not results:
            raise RuntimeError("Device Catalog search returned no STM32 result")
        identifier = results[0].get("identifier") if isinstance(results[0], dict) else None
        if not isinstance(identifier, str) or "stm32" not in identifier.casefold():
            raise RuntimeError(f"Device Catalog search returned an unexpected identifier: {identifier!r}")
        report.checks["api:device-catalog-search"] = "PASS"
    else:
        report.checks["api:device-catalog-search"] = "SKIP_UNPINNED"

    mock_runtime = request_json(origin, "/api/mock/runtime", timeout=timeout)
    settings = mock_runtime.get("mock_runtime")
    if mock_runtime.get("ok") is not True or mock_runtime.get("rest_contract_version") != "3":
        raise RuntimeError("Mock runtime settings are not Web REST v3 ready")
    if not isinstance(settings, dict):
        raise RuntimeError("Mock runtime settings payload is missing")
    operations = settings.get("operations")
    if not isinstance(operations, dict) or set(operations) != {"erase", "program", "verify", "read"}:
        raise RuntimeError("Mock runtime settings do not expose canonical E/P/V/R operations")
    image_size = settings.get("default_image_size_bytes")
    if isinstance(image_size, bool) or not isinstance(image_size, int) or image_size <= 0:
        raise RuntimeError("Mock runtime default Image size is invalid")
    report.checks["api:mock-runtime"] = "PASS"


def write_report(path: Path | None, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default=DEFAULT_ORIGIN)
    parser.add_argument("--expected-commit", default="")
    parser.add_argument("--wake-timeout", type=float, default=150.0)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--request-timeout", type=float, default=15.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.wake_timeout <= 0 or args.poll_interval <= 0 or args.request_timeout <= 0:
        parser.error("timeouts and poll interval must be positive")
    return args


def main() -> None:
    args = parse_args()
    expected_commit = args.expected_commit.strip() or None
    report = SmokeReport(origin=args.origin.rstrip("/"), expected_commit=expected_commit)
    try:
        ready = wait_until_ready(
            report.origin,
            expected_commit=expected_commit,
            wake_timeout=args.wake_timeout,
            poll_interval=args.poll_interval,
            request_timeout=args.request_timeout,
            report=report,
        )
        if ready.get("service") != "plasma-web-rest-gateway":
            raise RuntimeError("readiness service identity is not plasma-web-rest-gateway")
        if ready.get("ppu_id") != "render-demo-ppu":
            raise RuntimeError("readiness PPU identity is not render-demo-ppu")
        if report.observed_commit is None:
            report.observed_commit = deployment_commit(report.origin, timeout=args.request_timeout)
        assert_contracts(report.origin, timeout=args.request_timeout, report=report)
        assert_ui_routes(report.origin, timeout=args.request_timeout, report=report)
    except BaseException as exc:
        write_report(args.report, report.to_dict(result="FAIL", error=f"{type(exc).__name__}: {exc}"))
        raise
    else:
        write_report(args.report, report.to_dict(result="PASS"))


if __name__ == "__main__":
    main()
