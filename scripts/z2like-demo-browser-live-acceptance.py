#!/usr/bin/env python3
"""Live acceptance for the public z2like-demo Browser Runtime deployment path.

This gate is intentionally post-merge infrastructure. It drives the public
Render Console/BFF surface while running on the trusted SWPC integration host,
where the local QEMU Bootstrap pairing token can be read without publishing it.

The gate may change only the canonical z2like-demo lifecycle and Runtime. It
never prints the device token or browser maintenance capability. On failure it
attempts to return a disabled target to commissioned state only through the
normal Manager safety gate; it never forces commissioning.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

CHUNK_BYTES = 768 * 1024
CAPABILITY_COOKIE = "plasma-manager-maintenance"
EXPECTED_SITE_COUNT = 8
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class AcceptanceError(RuntimeError):
    pass


class BrowserSession:
    def __init__(self, origin: str) -> None:
        self.origin = origin.rstrip("/")
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: Mapping[str, Any] | None = None,
        origin: str | None = None,
        cookie: str | None = None,
        timeout_s: float = 30.0,
    ) -> tuple[int, dict[str, Any], list[str]]:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if method != "GET":
            headers["Origin"] = origin if origin is not None else self.origin
        if cookie is not None:
            headers["Cookie"] = cookie
        request = urllib.request.Request(
            f"{self.origin}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            response = self.opener.open(request, timeout=timeout_s)
            status = int(response.status)
            raw = response.read()
            set_cookies = response.headers.get_all("Set-Cookie") or []
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
            set_cookies = exc.headers.get_all("Set-Cookie") or []
        except (OSError, urllib.error.URLError) as exc:
            raise AcceptanceError(f"request failed for {path}: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcceptanceError(f"non-JSON response for {path}: HTTP {status}") from exc
        if not isinstance(payload, dict):
            raise AcceptanceError(f"non-object JSON response for {path}: HTTP {status}")
        return status, payload, set_cookies

    def capability_value(self) -> str | None:
        for cookie in self.cookies:
            if cookie.name == CAPABILITY_COOKIE:
                return cookie.value
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _error_code(payload: Mapping[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return str(error["code"])
    return None


def _expect(
    status: int,
    expected: int | set[int],
    payload: Mapping[str, Any],
    operation: str,
    *,
    code: str | None = None,
) -> None:
    allowed = {expected} if isinstance(expected, int) else expected
    if status not in allowed:
        raise AcceptanceError(
            f"{operation} returned HTTP {status}, expected {sorted(allowed)}: {payload!r}"
        )
    if code is not None and _error_code(payload) != code:
        raise AcceptanceError(
            f"{operation} returned error code {_error_code(payload)!r}, expected {code!r}"
        )


def _read_pairing_token(container: str) -> str:
    completed = subprocess.run(
        ["docker", "exec", container, "cat", "/var/lib/plasma-bootstrap/control-token"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    token = completed.stdout.strip()
    if completed.returncode != 0 or not 32 <= len(token) <= 256 or any(ch.isspace() for ch in token):
        raise AcceptanceError("cannot read a valid local QEMU Bootstrap pairing token")
    return token


def _commit_is_acceptable(expected: str, actual: str, repo: Path) -> bool:
    if actual == expected:
        return True
    if not HEX40.fullmatch(expected) or not HEX40.fullmatch(actual):
        return False
    present = subprocess.run(
        ["git", "cat-file", "-e", f"{actual}^{{commit}}"],
        cwd=repo,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if present.returncode != 0:
        subprocess.run(
            ["git", "fetch", "--no-tags", "origin", actual],
            cwd=repo,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", expected, actual],
        cwd=repo,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return ancestor.returncode == 0


def _wait_public_deployment(
    session: BrowserSession,
    *,
    expected_commit: str,
    repo: Path,
    timeout_s: float,
) -> str:
    deadline = time.monotonic() + timeout_s
    last = "no deployment identity response"
    while time.monotonic() < deadline:
        try:
            status, payload, _ = session.request("/deployment.json", timeout_s=15.0)
            if status == 200:
                actual = payload.get("git_commit")
                if isinstance(actual, str) and _commit_is_acceptable(expected_commit, actual, repo):
                    return actual
                last = f"deployed_commit={actual!r}"
            else:
                last = f"HTTP {status}: {payload!r}"
        except AcceptanceError as exc:
            last = str(exc)
        time.sleep(5.0)
    raise AcceptanceError(
        f"public Render deployment did not reach expected main ancestry {expected_commit}: {last}"
    )


def _registry_entry(session: BrowserSession, alias: str) -> dict[str, Any]:
    status, payload, _ = session.request("/api/manager/registry")
    _expect(status, 200, payload, "public Manager registry read")
    ppus = payload.get("ppus")
    if not isinstance(ppus, list):
        raise AcceptanceError("public Manager registry omitted ppus")
    matches = [item for item in ppus if isinstance(item, dict) and item.get("alias") == alias]
    if len(matches) != 1:
        raise AcceptanceError(f"public Manager registry does not contain exactly one {alias!r}")
    return matches[0]


def _bootstrap_status(session: BrowserSession, alias: str) -> dict[str, Any]:
    status, payload, _ = session.request(f"/api/manager/registry/{alias}/bootstrap")
    _expect(status, 200, payload, "Browser Bootstrap status")
    bootstrap = payload.get("bootstrap")
    if not isinstance(bootstrap, dict):
        raise AcceptanceError("Browser Bootstrap status omitted bootstrap document")
    return payload


def _fleet_ppu(session: BrowserSession, alias: str) -> tuple[dict[str, Any], dict[str, Any]]:
    status, payload, _ = session.request("/api/fleet")
    _expect(status, 200, payload, "public fleet read")
    ppus = payload.get("ppus")
    if not isinstance(ppus, list):
        raise AcceptanceError("public fleet omitted ppus")
    matches = [item for item in ppus if isinstance(item, dict) and item.get("alias") == alias]
    if len(matches) != 1:
        raise AcceptanceError(f"public fleet does not contain exactly one {alias!r}")
    return payload, matches[0]


def _ppu_is_current_idle(ppu: Mapping[str, Any]) -> bool:
    observation = ppu.get("observation")
    topology = ppu.get("topology")
    sites = topology.get("sites") if isinstance(topology, dict) else None
    if not (
        isinstance(observation, dict)
        and observation.get("state") == "current"
        and ppu.get("transport_state") == "reachable"
        and ppu.get("execution_state") == "ready"
        and ppu.get("identity_conflict") is False
        and isinstance(topology, dict)
        and topology.get("site_count") == EXPECTED_SITE_COUNT
        and isinstance(sites, list)
        and len(sites) == EXPECTED_SITE_COUNT
    ):
        return False
    return all(
        isinstance(site, dict)
        and not site.get("current_job_id")
        and str(site.get("state") or "").lower() not in {
            "queued", "submitting", "running", "stopping", "erase", "program", "verify", "read"
        }
        for site in sites
    )


def _wait_current_idle(
    session: BrowserSession,
    alias: str,
    *,
    timeout_s: float = 120.0,
    newer_than: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_s
    last = "no fleet response"
    while time.monotonic() < deadline:
        try:
            payload, ppu = _fleet_ppu(session, alias)
            observed_at = payload.get("observed_at")
            if _ppu_is_current_idle(ppu) and (
                newer_than is None or (isinstance(observed_at, str) and observed_at > newer_than)
            ):
                return payload, ppu
            last = json.dumps(
                {
                    "observed_at": observed_at,
                    "observation": ppu.get("observation"),
                    "transport_state": ppu.get("transport_state"),
                    "execution_state": ppu.get("execution_state"),
                    "topology": ppu.get("topology"),
                },
                sort_keys=True,
            )
        except AcceptanceError as exc:
            last = str(exc)
        time.sleep(2.0)
    raise AcceptanceError(f"Manager did not publish a current trusted-idle 8-Site observation: {last}")


def _set_lifecycle(
    session: BrowserSession,
    alias: str,
    lifecycle: str,
    *,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while time.monotonic() < deadline:
        status, payload, _ = session.request(
            f"/api/manager/registry/{alias}",
            method="PATCH",
            body={"lifecycle": lifecycle},
        )
        if status == 200:
            entry = payload.get("entry")
            if not isinstance(entry, dict) or entry.get("lifecycle") != lifecycle:
                raise AcceptanceError(f"lifecycle {lifecycle!r} response omitted matching entry")
            return entry
        last = f"HTTP {status}: {payload!r}"
        if status not in {409, 503}:
            break
        time.sleep(2.0)
    raise AcceptanceError(f"cannot set lifecycle to {lifecycle!r}: {last}")


def _programming_regression(session: BrowserSession) -> dict[str, Any]:
    status, payload, _ = session.request("/api/manager/ppu/api/engineering/targets")
    _expect(status, 200, payload, "8-Site Programming catalog regression")
    if not (
        payload.get("ok") is True
        and payload.get("provider") == "configured_mock"
        and payload.get("ppu_count") == 1
        and payload.get("site_count") == EXPECTED_SITE_COUNT
    ):
        raise AcceptanceError(f"8-Site Programming catalog regression failed: {payload!r}")
    return payload


def _local_status(url: str, *, method: str = "GET", body: bytes | None = None) -> int:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        response = opener.open(request, timeout=5.0)
        response.read()
        return int(response.status)
    except urllib.error.HTTPError as exc:
        exc.read()
        return int(exc.code)
    except (OSError, urllib.error.URLError) as exc:
        raise AcceptanceError(f"local managed-ingress probe failed for {url}: {exc}") from exc


def _local_ingress_acceptance(local_origin: str) -> None:
    root = local_origin.rstrip("/")
    if _local_status(f"{root}/__plasma/bootstrap/v1/status") != 200:
        raise AcceptanceError("local managed ingress Bootstrap status is unavailable")
    if _local_status(f"{root}/__plasma/bootstrap/v1/not-allowlisted") != 404:
        raise AcceptanceError("local managed ingress exposed an unknown Bootstrap route")
    if _local_status(
        f"{root}/__plasma/bootstrap/v1/status",
        method="POST",
        body=b"{}",
    ) != 403:
        raise AcceptanceError("local managed ingress did not block wrong Bootstrap method")


def _verify_sidecar(kit: Path, sidecar: Path) -> str:
    if not kit.is_file() or not sidecar.is_file():
        raise AcceptanceError("kit artifact and detached SHA-256 sidecar are required")
    fields = sidecar.read_text(encoding="utf-8").strip().split()
    digest = _sha256(kit)
    if len(fields) != 2 or fields[0].lower() != digest or fields[1].lstrip("*") != kit.name:
        raise AcceptanceError("kit detached SHA-256 sidecar is invalid")
    return digest


def _upload_and_deploy(
    session: BrowserSession,
    alias: str,
    kit: Path,
    kit_sha: str,
    *,
    ppu_id: str,
    facility_id: str,
    display_name: str,
) -> dict[str, Any]:
    root = f"/api/manager/registry/{alias}/bootstrap"
    size = kit.stat().st_size
    status, created, _ = session.request(
        f"{root}/uploads",
        method="POST",
        body={"size": size, "sha256": kit_sha},
    )
    _expect(status, 201, created, "Browser bounded upload create")
    upload = created.get("upload")
    upload_id = upload.get("upload_id") if isinstance(upload, dict) else None
    if not isinstance(upload_id, str) or not re.fullmatch(r"[0-9a-f]{32}", upload_id):
        raise AcceptanceError("Browser upload create did not return a valid upload_id")

    offset = 0
    with kit.open("rb") as stream:
        while True:
            chunk = stream.read(CHUNK_BYTES)
            if not chunk:
                break
            status, chunk_payload, _ = session.request(
                f"{root}/uploads/{upload_id}/chunks",
                method="POST",
                body={
                    "offset": offset,
                    "data_base64": base64.b64encode(chunk).decode("ascii"),
                    "sha256": _sha256_bytes(chunk),
                },
                timeout_s=60.0,
            )
            _expect(status, 200, chunk_payload, "Browser bounded upload chunk")
            offset += len(chunk)
    if offset != size:
        raise AcceptanceError("Browser upload byte count does not match kit size")

    status, committed, _ = session.request(
        f"{root}/uploads/{upload_id}/commit",
        method="POST",
        body={"action": "commit"},
        timeout_s=60.0,
    )
    _expect(status, 200, committed, "Browser upload commit")

    status, deployment, _ = session.request(
        f"{root}/deployments",
        method="POST",
        body={
            "upload_id": upload_id,
            "ppu_id": ppu_id,
            "facility_id": facility_id,
            "display_name": display_name,
        },
        timeout_s=30.0,
    )
    _expect(status, 202, deployment, "Browser Runtime deployment start")

    deadline = time.monotonic() + 240.0
    last: Mapping[str, Any] | None = None
    while time.monotonic() < deadline:
        status, payload, _ = session.request(root, timeout_s=20.0)
        if status == 200:
            target = payload.get("bootstrap")
            record = target.get("deployment") if isinstance(target, dict) else None
            runtime = target.get("runtime") if isinstance(target, dict) else None
            last = record if isinstance(record, dict) else None
            state = record.get("state") if isinstance(record, dict) else None
            if state in {"failed", "recovery_required"}:
                raise AcceptanceError(f"Browser Runtime deployment failed: {record!r}")
            if (
                state == "succeeded"
                and isinstance(runtime, dict)
                and runtime.get("state") == "runtime_active"
            ):
                return payload
        time.sleep(2.0)
    raise AcceptanceError(f"Browser Runtime deployment did not reach runtime_active: {last!r}")


def _tampered_cookie(value: str) -> str:
    if not value:
        raise AcceptanceError("maintenance capability cookie is empty")
    replacement = "A" if value[-1] != "A" else "B"
    return f"{CAPABILITY_COOKIE}={value[:-1]}{replacement}"


def run(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[1]
    kit = args.kit.expanduser().resolve()
    sidecar = args.sidecar.expanduser().resolve()
    kit_sha = _verify_sidecar(kit, sidecar)
    session = BrowserSession(args.origin)
    anonymous = BrowserSession(args.origin)
    lifecycle_disabled = False
    capability_acquired = False
    deployed_commit = _wait_public_deployment(
        session,
        expected_commit=args.expected_commit,
        repo=repo,
        timeout_s=args.render_timeout,
    )

    _local_ingress_acceptance(args.local_managed_origin)
    entry = _registry_entry(session, args.alias)
    if entry.get("endpoint") != args.expected_ppu_endpoint.rstrip("/"):
        raise AcceptanceError(
            f"canonical registry endpoint mismatch: {entry.get('endpoint')!r} != {args.expected_ppu_endpoint!r}"
        )
    if entry.get("lifecycle") != "commissioned":
        raise AcceptanceError(
            f"live acceptance requires a commissioned starting state, found {entry.get('lifecycle')!r}"
        )

    fleet_before, ppu_before = _wait_current_idle(session, args.alias, timeout_s=120.0)
    programming_before = _programming_regression(session)
    identity = ppu_before.get("identity")
    if not isinstance(identity, dict):
        raise AcceptanceError("public fleet omitted PPU identity")
    ppu_id = identity.get("ppu_id")
    facility_id = identity.get("facility_id")
    display_name = identity.get("display_name")
    if not all(isinstance(value, str) and value for value in (ppu_id, facility_id)):
        raise AcceptanceError(f"public fleet identity is incomplete: {identity!r}")
    if not isinstance(display_name, str) or not display_name:
        display_name = "SWPC QEMU ARMv7 Z2 Simulation"

    before = _bootstrap_status(session, args.alias)
    pairing_before = before.get("pairing")
    if not isinstance(pairing_before, dict):
        raise AcceptanceError("Bootstrap status omitted pairing state")

    wrong_token = "invalid-z2like-demo-pairing-token-" + ("0" * 40)
    status, wrong_pair, wrong_cookies = session.request(
        f"/api/manager/registry/{args.alias}/bootstrap/pair",
        method="POST",
        body={"token": wrong_token},
    )
    _expect(status, 409, wrong_pair, "wrong Bootstrap pairing token", code="bootstrap_pairing_required")
    if wrong_cookies or session.capability_value() is not None:
        raise AcceptanceError("wrong Bootstrap pairing token unexpectedly issued maintenance capability")
    after_wrong = _bootstrap_status(session, args.alias)
    if after_wrong.get("pairing") != pairing_before:
        raise AcceptanceError("wrong Bootstrap pairing token changed persisted pairing state")

    token = _read_pairing_token(args.container)
    try:
        status, paired, set_cookies = session.request(
            f"/api/manager/registry/{args.alias}/bootstrap/pair",
            method="POST",
            body={"token": token},
        )
    finally:
        token = ""
    _expect(status, 200, paired, "correct Bootstrap pairing while commissioned")
    capability = session.capability_value()
    if not capability:
        raise AcceptanceError("verified pairing did not install the browser maintenance capability")
    capability_acquired = True
    cookie_contract = "\n".join(set_cookies)
    for marker in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/api/manager", "Max-Age=900"):
        if marker not in cookie_contract:
            raise AcceptanceError(f"maintenance capability cookie omitted {marker}")
    paired_status = _bootstrap_status(session, args.alias)
    paired_state = paired_status.get("pairing")
    if not (
        isinstance(paired_state, dict)
        and paired_state.get("paired") is True
        and paired_state.get("device_match") is True
    ):
        raise AcceptanceError(f"verified pairing state is not device-bound: {paired_state!r}")

    # Capability and origin negative gates are exercised while commissioned so
    # any unexpected admission remains bounded by Manager's maintenance gate.
    status, blocked, _ = anonymous.request(
        f"/api/manager/registry/{args.alias}",
        method="PATCH",
        body={"lifecycle": "disabled"},
    )
    _expect(status, 403, blocked, "lifecycle PATCH without capability", code="maintenance_authorization_required")

    status, blocked, _ = session.request(
        f"/api/manager/registry/{args.alias}",
        method="PATCH",
        body={"lifecycle": "disabled"},
        origin="https://cross-origin.invalid",
    )
    _expect(status, 403, blocked, "cross-origin lifecycle mutation", code="maintenance_authorization_required")

    tampered = BrowserSession(args.origin)
    status, blocked, _ = tampered.request(
        f"/api/manager/registry/{args.alias}",
        method="PATCH",
        body={"lifecycle": "disabled"},
        cookie=_tampered_cookie(capability),
    )
    _expect(status, 403, blocked, "tampered maintenance capability", code="maintenance_authorization_required")

    bootstrap_root = f"/api/manager/registry/{args.alias}/bootstrap"
    status, blocked, _ = session.request(
        f"{bootstrap_root}/uploads",
        method="POST",
        body={"size": 1, "sha256": "0" * 64},
        origin="https://cross-origin.invalid",
    )
    _expect(status, 403, blocked, "cross-origin Bootstrap mutation", code="maintenance_authorization_required")

    status, blocked, _ = session.request(
        f"{bootstrap_root}/uploads",
        method="POST",
        body={"size": 1, "sha256": "0" * 64},
    )
    _expect(status, 409, blocked, "commissioned Bootstrap upload", code="ppu_maintenance_required")

    status, blocked, _ = session.request(
        f"{bootstrap_root}/deployments",
        method="POST",
        body={
            "upload_id": "0" * 32,
            "ppu_id": str(ppu_id),
            "facility_id": str(facility_id),
            "display_name": str(display_name),
        },
    )
    _expect(status, 409, blocked, "commissioned Bootstrap deployment", code="ppu_maintenance_required")

    status, blocked, _ = session.request(f"{bootstrap_root}/not-allowlisted")
    _expect(status, 404, blocked, "unknown Browser Bootstrap route", code="bootstrap_route_not_allowed")
    status, blocked, _ = session.request(bootstrap_root, method="POST", body={})
    _expect(status, 404, blocked, "wrong Browser Bootstrap method", code="bootstrap_route_not_allowed")

    cleanup_error: str | None = None
    try:
        _set_lifecycle(session, args.alias, "disabled", timeout_s=30.0)
        lifecycle_disabled = True
        disabled_fleet, _ = _wait_current_idle(session, args.alias, timeout_s=120.0)
        disabled_observed_at = disabled_fleet.get("observed_at")
        if not isinstance(disabled_observed_at, str):
            raise AcceptanceError("disabled fleet snapshot omitted observed_at")

        deployment = _upload_and_deploy(
            session,
            args.alias,
            kit,
            kit_sha,
            ppu_id=str(ppu_id),
            facility_id=str(facility_id),
            display_name=str(display_name),
        )

        _wait_current_idle(
            session,
            args.alias,
            timeout_s=180.0,
            newer_than=disabled_observed_at,
        )
        _set_lifecycle(session, args.alias, "commissioned", timeout_s=90.0)
        lifecycle_disabled = False
        fleet_after, _ = _wait_current_idle(session, args.alias, timeout_s=120.0)
        programming_after = _programming_regression(session)

        return {
            "result": "PASS",
            "evidence_level": "live-swpc-render-qemu-browser-runtime",
            "public_origin": args.origin,
            "render_deployed_commit": deployed_commit,
            "accepted_source_commit": args.expected_commit,
            "ppu_alias": args.alias,
            "ppu_endpoint": args.expected_ppu_endpoint,
            "starting_lifecycle": "commissioned",
            "wrong_pairing_token": "BLOCKED_NO_CREDENTIAL_CHANGE",
            "verified_pairing_while_commissioned": "PASS",
            "maintenance_capability_cookie_contract": "PASS",
            "lifecycle_without_capability": "BLOCKED",
            "cross_origin_lifecycle": "BLOCKED",
            "cross_origin_bootstrap": "BLOCKED",
            "tampered_capability": "BLOCKED",
            "commissioned_upload": "BLOCKED",
            "commissioned_deployment": "BLOCKED",
            "idle_disable": "PASS",
            "bounded_upload": "PASS",
            "runtime_deployment": "PASS",
            "runtime_state": deployment.get("bootstrap", {}).get("runtime", {}).get("state"),
            "return_to_commissioned": "PASS",
            "programming_before": {
                "provider": programming_before.get("provider"),
                "ppu_count": programming_before.get("ppu_count"),
                "site_count": programming_before.get("site_count"),
            },
            "programming_after": {
                "provider": programming_after.get("provider"),
                "ppu_count": programming_after.get("ppu_count"),
                "site_count": programming_after.get("site_count"),
            },
            "fleet_observed_at_before": fleet_before.get("observed_at"),
            "fleet_observed_at_after": fleet_after.get("observed_at"),
            "unknown_bootstrap_route": "BLOCKED",
            "wrong_bootstrap_method": "BLOCKED",
            "local_managed_ingress_allowlist": "PASS",
            "kit_sha256": kit_sha,
            "not_live_qualified_by_this_gate": [
                "active-Site-Job disable rejection",
                "forced stale/non-idle maintenance proof rejection",
                "15-minute capability expiry wall-clock rejection",
                "real PYNQ-Z2 deployment/reboot/rollback",
                "PL/FPGA behavior",
                "target power/electrical behavior",
                "real IC programming",
                "physical multi-Site concurrency",
            ],
        }
    finally:
        if lifecycle_disabled and capability_acquired:
            try:
                _set_lifecycle(session, args.alias, "commissioned", timeout_s=120.0)
                lifecycle_disabled = False
            except AcceptanceError as exc:
                cleanup_error = str(exc)
        if cleanup_error is not None and sys.exc_info()[0] is None:
            raise AcceptanceError(f"live acceptance cleanup could not restore commissioned lifecycle: {cleanup_error}")
        if cleanup_error is not None and sys.exc_info()[0] is not None:
            print(
                f"z2like-demo-browser-live-acceptance: cleanup could not restore commissioned lifecycle: {cleanup_error}",
                file=sys.stderr,
            )


def _write_report(path: Path | None, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Accept live Browser -> Render -> SWPC/QEMU Runtime deployment")
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
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
    if not HEX40.fullmatch(args.expected_commit):
        print("z2like-demo-browser-live-acceptance: expected commit must be a full 40-hex SHA", file=sys.stderr)
        return 2
    try:
        report = run(args)
    except (AcceptanceError, OSError, subprocess.SubprocessError) as exc:
        report = {
            "result": "FAIL",
            "evidence_level": "live-swpc-render-qemu-browser-runtime",
            "accepted_source_commit": args.expected_commit,
            "error": str(exc),
            "safety": "No force-commission fallback is permitted; a failed cleanup leaves the target fail-closed.",
        }
        _write_report(args.report, report)
        return 2
    _write_report(args.report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
