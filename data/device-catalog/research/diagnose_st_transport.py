#!/usr/bin/env python3
"""Diagnose the live HTTP transport path used by STM32 ICPN acquisition.

This is a bounded research diagnostic for one fixed STM32F1 product page. It does
not crawl, parse/admit commercial ICPNs, or modify any canonical dataset.

The production acquisition path uses urllib. The diagnostic therefore probes
urllib first after DNS/TCP/TLS checks. Curl comparisons are executed only when
urllib fails, which keeps the normal successful path to one HTTP GET while still
providing enough evidence to distinguish likely urllib-specific behavior from a
broader GitHub-runner/ST HTTP path failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from email.parser import BytesHeaderParser
from pathlib import Path
from typing import Any, Callable

from st_product_page_acquisition import AcquisitionError, fetch_html, validate_source_url

TARGET_BASE_DEVICE = "STM32F100C8"
TARGET_URL = "https://www.st.com/en/microcontrollers-microprocessors/stm32f100c8.html"
PLASMA_USER_AGENT = "Plasma-ICPN-Research/1.0 (+https://github.com/physicslu/plasma)"
PLASMA_ACCEPT = "text/html,application/xhtml+xml"
MIN_REQUEST_DELAY_SECONDS = 1.0
DEFAULT_REQUEST_DELAY_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_DIAGNOSTIC_BODY_BYTES = 5 * 1024 * 1024
SELECTED_RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "etag",
    "last-modified",
    "server",
    "via",
    "x-cache",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _error_record(exc: BaseException) -> dict[str, object]:
    return {
        "status": "failure",
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def probe_dns(host: str) -> dict[str, object]:
    started = time.monotonic()
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = sorted({item[4][0] for item in infos})
        if not addresses:
            raise OSError("DNS returned no stream addresses")
        return {
            "status": "success",
            "addresses": addresses,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }
    except OSError as exc:
        record = _error_record(exc)
        record["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        return record


def probe_tcp(host: str, timeout_seconds: float) -> dict[str, object]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, 443), timeout=timeout_seconds) as sock:
            peer = sock.getpeername()
        return {
            "status": "success",
            "peer": f"{peer[0]}:{peer[1]}",
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }
    except OSError as exc:
        record = _error_record(exc)
        record["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        return record


def probe_tls(host: str, timeout_seconds: float) -> dict[str, object]:
    started = time.monotonic()
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout_seconds) as raw_sock:
            with context.wrap_socket(raw_sock, server_hostname=host) as tls_sock:
                peer = tls_sock.getpeername()
                version = tls_sock.version()
                cipher = tls_sock.cipher()
        return {
            "status": "success",
            "peer": f"{peer[0]}:{peer[1]}",
            "tls_version": version,
            "cipher": cipher[0] if cipher else None,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }
    except (OSError, ssl.SSLError) as exc:
        record = _error_record(exc)
        record["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        return record


def probe_urllib(url: str, timeout_seconds: float) -> dict[str, object]:
    started = time.monotonic()
    try:
        body, final_url, etag, last_modified = fetch_html(url, timeout_seconds)
        return {
            "status": "success",
            "final_url": final_url,
            "body_bytes": len(body),
            "raw_sha256": hashlib.sha256(body).hexdigest(),
            "http_etag": etag,
            "http_last_modified": last_modified,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }
    except (AcquisitionError, OSError) as exc:
        record = _error_record(exc)
        record["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        return record


def _selected_headers_from_dump(path: Path) -> dict[str, str]:
    raw = path.read_bytes() if path.exists() else b""
    # curl -L can emit multiple response header blocks. Keep the final HTTP block.
    normalized = raw.replace(b"\r\n", b"\n")
    blocks = [block for block in normalized.split(b"\n\n") if block.startswith(b"HTTP/")]
    if not blocks:
        return {}
    lines = blocks[-1].split(b"\n")
    header_bytes = b"\n".join(lines[1:]) + b"\n\n"
    parsed = BytesHeaderParser().parsebytes(header_bytes)
    return {
        key.lower(): value
        for key, value in parsed.items()
        if key.lower() in SELECTED_RESPONSE_HEADERS
    }


def probe_curl(
    url: str,
    *,
    timeout_seconds: float,
    plasma_headers: bool,
) -> dict[str, object]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        body_path = tmp / "body.bin"
        headers_path = tmp / "headers.txt"
        command = [
            "curl",
            "--location",
            "--silent",
            "--show-error",
            "--connect-timeout",
            str(min(timeout_seconds, 10.0)),
            "--max-time",
            str(timeout_seconds),
            "--max-filesize",
            str(MAX_DIAGNOSTIC_BODY_BYTES),
            "--dump-header",
            str(headers_path),
            "--output",
            str(body_path),
            "--write-out",
            "%{http_code}\n%{url_effective}\n%{time_namelookup}\n%{time_connect}\n%{time_appconnect}\n%{time_starttransfer}\n%{time_total}\n",
        ]
        if plasma_headers:
            command.extend(["--user-agent", PLASMA_USER_AGENT, "--header", f"Accept: {PLASMA_ACCEPT}"])
        command.append(url)

        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds + 5.0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            record = _error_record(exc)
            record["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
            record["request_profile"] = "plasma_headers" if plasma_headers else "curl_default"
            return record

        fields = completed.stdout.splitlines()
        metrics: dict[str, object] = {}
        if len(fields) >= 7:
            metrics = {
                "http_status": fields[-7],
                "final_url": fields[-6],
                "time_namelookup_seconds": fields[-5],
                "time_connect_seconds": fields[-4],
                "time_appconnect_seconds": fields[-3],
                "time_starttransfer_seconds": fields[-2],
                "time_total_seconds": fields[-1],
            }

        body = body_path.read_bytes() if body_path.exists() else b""
        record = {
            "status": "success" if completed.returncode == 0 else "failure",
            "request_profile": "plasma_headers" if plasma_headers else "curl_default",
            "curl_exit_code": completed.returncode,
            "stderr": completed.stderr.strip()[-1000:],
            "body_bytes": len(body),
            "raw_sha256": hashlib.sha256(body).hexdigest() if body else None,
            "selected_response_headers": _selected_headers_from_dump(headers_path),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            **metrics,
        }
        return record


def classify_transport(probes: dict[str, dict[str, object]]) -> str:
    """Classify the failure conservatively; urllib success is authoritative."""

    if probes.get("urllib", {}).get("status") == "success":
        return "transport_ok"

    curl_plasma = probes.get("curl_plasma_headers", {}).get("status") == "success"
    curl_default = probes.get("curl_default", {}).get("status") == "success"
    if curl_plasma:
        return "urllib_specific_failure"
    if curl_default:
        return "request_header_policy_suspected"
    if probes.get("dns", {}).get("status") == "failure":
        return "dns_failure"
    if probes.get("tcp", {}).get("status") == "failure":
        return "tcp_path_failure_or_address_selection"
    if probes.get("tls", {}).get("status") == "failure":
        return "tls_path_failure_or_address_selection"
    return "upstream_http_response_failure_or_filter"


def run_diagnostic(
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    if timeout_seconds <= 0:
        raise AcquisitionError("timeout must be positive")
    if delay_seconds < MIN_REQUEST_DELAY_SECONDS:
        raise AcquisitionError(
            f"diagnostic request delay must be at least {MIN_REQUEST_DELAY_SECONDS} seconds"
        )
    validate_source_url(TARGET_URL)
    host = "www.st.com"
    started_at = utc_now()

    probes: dict[str, dict[str, object]] = {
        "dns": probe_dns(host),
        "tcp": probe_tcp(host, min(timeout_seconds, 10.0)),
        "tls": probe_tls(host, min(timeout_seconds, 10.0)),
    }

    probes["urllib"] = probe_urllib(TARGET_URL, timeout_seconds)
    if probes["urllib"]["status"] != "success":
        sleeper(delay_seconds)
        probes["curl_plasma_headers"] = probe_curl(
            TARGET_URL,
            timeout_seconds=timeout_seconds,
            plasma_headers=True,
        )
        if probes["curl_plasma_headers"]["status"] != "success":
            sleeper(delay_seconds)
            probes["curl_default"] = probe_curl(
                TARGET_URL,
                timeout_seconds=timeout_seconds,
                plasma_headers=False,
            )

    classification = classify_transport(probes)
    return {
        "schema_version": 1,
        "diagnostic": "stm32f1_phase2.6.1_st_transport",
        "target_base_device": TARGET_BASE_DEVICE,
        "target_url": TARGET_URL,
        "started_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "timeout_seconds": timeout_seconds,
        "request_delay_seconds": delay_seconds,
        "classification": classification,
        "production_urllib_transport_ok": classification == "transport_ok",
        "probes": probes,
        "execution": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "github_repository": os.getenv("GITHUB_REPOSITORY"),
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
            "github_sha": os.getenv("GITHUB_SHA"),
        },
        "canonical_dataset_admission": False,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write diagnostic JSON; stdout if omitted")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--delay", type=float, default=DEFAULT_REQUEST_DELAY_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = run_diagnostic(timeout_seconds=args.timeout, delay_seconds=args.delay)
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if report["production_urllib_transport_ok"] else 1
    except (AcquisitionError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
