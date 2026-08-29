from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class PPUHTTPError(RuntimeError):
    """Raised when a configured PPU cannot satisfy the fleet-facing REST contract."""


class PPUTransportError(PPUHTTPError):
    """Raised when Manager cannot establish or complete HTTP transport to a PPU."""


class PPUHttpClient:
    def __init__(self, endpoint: str, timeout_s: float) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_s = timeout_s

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        accepted_statuses: frozenset[int],
        body: dict[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> tuple[int, dict[str, Any]]:
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json", "User-Agent": "plasma-manager/1"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.endpoint}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_s if timeout_s is None else timeout_s) as response:
                status = response.status
                response_data = response.read()
        except HTTPError as exc:
            status = exc.code
            response_data = exc.read()
            if status not in accepted_statuses:
                raise PPUHTTPError(f"{path} returned HTTP {status}") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise PPUTransportError(f"{path} request failed: {exc}") from exc

        if status not in accepted_statuses:
            raise PPUHTTPError(f"{path} returned HTTP {status}")
        try:
            payload = json.loads(response_data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PPUHTTPError(f"{path} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise PPUHTTPError(f"{path} JSON payload must be an object")
        return status, payload

    def _get(self, path: str, accepted_statuses: frozenset[int]) -> tuple[int, dict[str, Any]]:
        return self._request_json("GET", path, accepted_statuses=accepted_statuses)

    def liveness(self) -> tuple[int, dict[str, Any]]:
        return self._get("/api/health/live", frozenset({200}))

    def readiness(self) -> tuple[int, dict[str, Any]]:
        return self._get("/api/health/ready", frozenset({200, 503}))

    def node(self) -> tuple[int, dict[str, Any]]:
        return self._get("/api/node", frozenset({200}))

    def status(self) -> tuple[int, dict[str, Any]]:
        return self._get("/api/status", frozenset({200}))

    def ps_loopback(
        self,
        body: dict[str, Any],
        *,
        timeout_s: float,
    ) -> tuple[int, dict[str, Any]]:
        """Relay the one explicitly approved Phase-0 write to a PPU Gateway.

        This is deliberately not a generic proxy. The path and method are fixed so
        a browser or caller cannot make Manager fetch an arbitrary URL or route.
        """
        return self._request_json(
            "POST",
            "/api/engineering/diagnostics/loopback",
            accepted_statuses=frozenset({200, 400, 404, 409, 422, 500, 502, 503, 504}),
            body=body,
            timeout_s=timeout_s,
        )
