from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:5173/api/manager/ppu"


class AcceptanceError(RuntimeError):
    pass


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
        evidence_root: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.environment = environment
        self.evidence_root = evidence_root or Path("artifacts/runtime-acceptance")
        self._run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]

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
            **result,
        }
        path = directory / f"{scenario}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path
