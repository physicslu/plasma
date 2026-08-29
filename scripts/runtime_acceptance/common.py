from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

DEFAULT_BASE_URL = "http://127.0.0.1:5173/api/manager/ppu"
TERMINAL_JOB_STATES = {"success", "failed", "error", "cancelled", "timeout", "aborted"}
TERMINAL_BATCH_STATES = {"success", "error", "partial", "cancelled"}


class AcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    facility_id: str
    ppu_id: str
    site_count: int
    provider: str


@dataclass(frozen=True)
class Image:
    name: str
    data: bytes
    sha256: str

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")


def build_image(name: str, *, size: int = 64 * 1024, multiplier: int = 37, offset: int = 13) -> Image:
    data = bytes(((index * multiplier + offset) & 0xFF) for index in range(size))
    return Image(name=name, data=data, sha256=hashlib.sha256(data).hexdigest())


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


class Client:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        environment: str = "managed-software",
        allow_real_hardware: bool = False,
        evidence_root: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.environment = environment
        self.allow_real_hardware = allow_real_hardware
        self.evidence_root = evidence_root or Path("artifacts/runtime-acceptance")
        self._run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        self._mock_restore_events: list[dict[str, Any]] = []

    def idem(self, label: str) -> str:
        return f"runtime-acceptance-{label}-{uuid.uuid4().hex}"

    def request(
        self,
        method: str,
        path_or_url: str,
        *,
        json_body: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 130.0,
    ) -> tuple[int, dict[str, Any]]:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}{path_or_url}"
        request_headers = {"Accept": "application/json", **(headers or {})}
        body = data
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                payload = json.loads(raw) if raw else {}
                return response.status, payload
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise AcceptanceError(f"HTTP {exc.code}: {method} {url}\n{raw}") from exc
        except urllib.error.URLError as exc:
            raise AcceptanceError(f"request failed: {method} {url}: {exc}") from exc

    def target_url(self, target: Target) -> str:
        facility = urllib.parse.quote(target.facility_id, safe="")
        ppu = urllib.parse.quote(target.ppu_id, safe="")
        return f"{self.base_url}/api/engineering/targets/{facility}/{ppu}"

    def discover_target(self, *, site_count: int | None = None, minimum_sites: int = 1) -> Target:
        status, catalog = self.request("GET", "/api/engineering/targets")
        if status != 200 or catalog.get("ok") is not True:
            raise AcceptanceError("Engineering target catalog is unavailable")
        catalog_provider = str(catalog.get("provider") or "")
        for facility in catalog.get("facilities", []):
            for ppu in facility.get("ppus", []):
                count = int(ppu["site_count"])
                if site_count is not None and count != site_count:
                    continue
                if count < minimum_sites:
                    continue
                provider = str(ppu.get("provider") or catalog_provider or "unknown")
                target = Target(str(facility["facility_id"]), str(ppu["ppu_id"]), count, provider)
                self.require_safe_target(target)
                return target
        requested = f"exactly {site_count}" if site_count is not None else f"at least {minimum_sites}"
        raise AcceptanceError(f"no Engineering PPU has {requested} Sites")

    def require_safe_target(self, target: Target) -> None:
        if target.provider == "mock":
            return
        if not self.allow_real_hardware:
            raise AcceptanceError(
                f"refusing write-capable acceptance against provider={target.provider!r}; "
                "use --allow-real-hardware only under an explicitly approved hardware plan"
            )

    def begin_session(self) -> str:
        status, payload = self.request(
            "POST",
            "/api/engineering/session",
            json_body={},
            headers={"Idempotency-Key": self.idem("session")},
        )
        if status not in {200, 201} or payload.get("ok") is not True:
            raise AcceptanceError("Engineering session creation failed")
        return str(payload["session"]["session_id"])

    def cache_image(self, target: Target, session_id: str, image: Image) -> dict[str, Any]:
        target_url = self.target_url(target)
        descriptor = {
            "session_id": session_id,
            "asset_name": image.name,
            "asset_type": "image",
            "asset_format": "binary",
            "asset_size": image.size,
            "asset_sha256": image.sha256,
        }
        status, checked = self.request(
            "POST",
            f"{target_url}/api/programming-assets/check",
            json_body=descriptor,
            headers={"Idempotency-Key": self.idem("asset-check")},
        )
        if status not in {200, 201}:
            raise AcceptanceError("Programming Asset cache check failed")
        initial = checked["programming_asset"]
        uploaded = False
        if not initial["cache_hit"]:
            query = urllib.parse.urlencode(
                {
                    "session_id": session_id,
                    "name": image.name,
                    "type": "image",
                    "format": "binary",
                    "sha256": image.sha256,
                }
            )
            status, response = self.request(
                "POST",
                f"{target_url}/api/programming-assets?{query}",
                data=image.data,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Idempotency-Key": self.idem("asset-upload"),
                },
            )
            if status not in {200, 201}:
                raise AcceptanceError("Programming Image upload failed")
            uploaded = True
            effective = response["programming_asset"]
        else:
            effective = initial
        if effective["asset_sha256"] != image.sha256:
            raise AcceptanceError("PPU cache SHA does not match client Image SHA")
        return {"initial_cache_hit": bool(initial["cache_hit"]), "uploaded": uploaded, "asset": effective}

    def job_status(self, target: Target, job_id: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"job": job_id})
        status, payload = self.request("GET", f"{self.target_url(target)}/api/status?{query}")
        if status != 200 or payload.get("ok") is not True:
            raise AcceptanceError(f"Job status failed: {job_id}")
        return payload["job"]

    def wait_job(self, target: Target, job_id: str, *, timeout: float = 60.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            job = self.job_status(target, job_id)
            if job["state"] in TERMINAL_JOB_STATES:
                return job
            if time.monotonic() >= deadline:
                raise AcceptanceError(f"Job did not become terminal: {job_id}")
            time.sleep(0.1)

    def batch_status(self, batch_id: str) -> dict[str, Any]:
        encoded = urllib.parse.quote(batch_id, safe="")
        status, payload = self.request("GET", f"/api/batches/{encoded}")
        if status != 200 or payload.get("ok") is not True:
            raise AcceptanceError(f"Batch status failed: {batch_id}")
        return payload["batch"]

    def current_mock(self) -> dict[str, Any]:
        status, payload = self.request("GET", "/api/mock/runtime")
        if status != 200 or payload.get("ok") is not True:
            raise AcceptanceError("Mock Runtime settings are unavailable")
        return payload["mock_runtime"]

    @staticmethod
    def writable_mock(snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "enabled": snapshot["enabled"],
            "default_image_size_bytes": snapshot["default_image_size_bytes"],
            "operations": copy.deepcopy(snapshot["operations"]),
            "seed": copy.deepcopy(snapshot["seed"]),
        }

    def set_mock(self, payload: dict[str, Any], label: str) -> dict[str, Any]:
        status, response = self.request(
            "POST",
            "/api/mock/runtime",
            json_body=payload,
            headers={"Idempotency-Key": self.idem(label)},
        )
        if status != 200 or response.get("ok") is not True:
            raise AcceptanceError("Mock Runtime update failed")
        return response["mock_runtime"]

    @contextlib.contextmanager
    def deterministic_program(self, *, base_time_ms: int) -> Iterator[dict[str, Any]]:
        original = self.current_mock()
        restore = self.writable_mock(original)
        desired = self.writable_mock(original)
        desired["enabled"] = True
        desired["operations"]["program"]["error_rate_per_mille"] = 0
        desired["operations"]["program"]["base_time_ms"] = base_time_ms
        desired["operations"]["program"]["jitter_ms"] = 0
        effective = self.set_mock(desired, "mock-setup")
        try:
            yield effective
        finally:
            restored = self.set_mock(restore, "mock-restore")
            expected = restore["operations"]["program"]["error_rate_per_mille"]
            actual = restored["operations"]["program"]["error_rate_per_mille"]
            event = {
                "expected_program_error_rate_per_mille": expected,
                "restored_program_error_rate_per_mille": actual,
                "restored_revision": restored.get("revision"),
                "ok": actual == expected,
            }
            self._mock_restore_events.append(event)
            if actual != expected:
                raise AcceptanceError(f"Mock Runtime restore verification failed: {event}")

    def write_evidence(self, scenario: str, result: dict[str, Any]) -> Path:
        directory = self.evidence_root / self._run_id
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "scenario": scenario,
            "result": result.get("result", "PASS"),
            "recorded_at": datetime.now(UTC).isoformat(),
            "commit": git_commit(),
            "environment": self.environment,
            "base_url": self.base_url,
            "allow_real_hardware": self.allow_real_hardware,
            "mock_restore_events": list(self._mock_restore_events),
            **result,
        }
        path = directory / f"{scenario}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


def assert_job_image(job: dict[str, Any], image: Image, *, site_id: int | None = None) -> None:
    if job["state"] != "success":
        raise AcceptanceError(f"Job is not successful: {json.dumps(job, indent=2)}")
    if site_id is not None and int(job["site_id"]) != site_id:
        raise AcceptanceError(f"Job Site mismatch: expected {site_id}, got {job['site_id']}")
    result = job.get("result") or {}
    if result.get("state") != "success":
        raise AcceptanceError("successful Job has non-success result")
    if result.get("image_sha256") != image.sha256 or int(result.get("image_size", -1)) != image.size:
        raise AcceptanceError("Job Image identity does not match accepted Programming Image")
