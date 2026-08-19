from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class PPUHTTPError(RuntimeError):
    """Raised when a configured PPU cannot satisfy the fleet-facing REST contract."""


class PPUHttpClient:
    def __init__(self, endpoint: str, timeout_s: float) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_s = timeout_s

    def _get(self, path: str, accepted_statuses: frozenset[int]) -> tuple[int, dict[str, Any]]:
        request = Request(
            f"{self.endpoint}{path}",
            headers={"Accept": "application/json", "User-Agent": "plasma-manager/1"},
            method="GET",
        )
        try:
            response = urlopen(request, timeout=self.timeout_s)
            status = response.status
            data = response.read()
        except HTTPError as exc:
            status = exc.code
            data = exc.read()
            if status not in accepted_statuses:
                raise PPUHTTPError(f"{path} returned HTTP {status}") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise PPUHTTPError(f"{path} request failed: {exc}") from exc

        if status not in accepted_statuses:
            raise PPUHTTPError(f"{path} returned HTTP {status}")
        try:
            payload = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PPUHTTPError(f"{path} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise PPUHTTPError(f"{path} JSON payload must be an object")
        return status, payload

    def liveness(self) -> tuple[int, dict[str, Any]]:
        return self._get("/api/health/live", frozenset({200}))

    def readiness(self) -> tuple[int, dict[str, Any]]:
        return self._get("/api/health/ready", frozenset({200, 503}))

    def node(self) -> tuple[int, dict[str, Any]]:
        return self._get("/api/node", frozenset({200}))

    def status(self) -> tuple[int, dict[str, Any]]:
        return self._get("/api/status", frozenset({200}))
