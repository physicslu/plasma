"""Read-only Manager REST transport. No credentials or hardware writes."""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

_MAX_BYTES = 8 * 1024 * 1024


class FleetError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _manager_get(url: str, route: str, *, timeout: float = 5.0) -> dict:
    """Bounded Manager GET, refusing redirects and embedded credentials."""
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or not 0 < timeout <= 60
        ):
            raise ValueError("invalid Manager base URL or timeout")
        parsed.port  # Reject invalid port syntax.
    except ValueError as exc:
        raise FleetError("Manager URL must be an HTTP(S) origin without credentials") from exc
    origin = url.rstrip("/")
    request = Request(origin + route, method="GET", headers={"Accept": "application/json"})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            data = response.read(_MAX_BYTES + 1)
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise FleetError(f"Manager GET failed: {type(exc).__name__}") from exc
    if len(data) > _MAX_BYTES:
        raise FleetError("Manager Fleet response exceeds size limit")
    try:
        body = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise FleetError("Manager Fleet response is not valid JSON") from exc
    if not isinstance(body, dict) or body.get("ok") is not True:
        raise FleetError("Manager response violates the expected contract")
    return body


def manager_fleet(url: str, *, timeout: float = 5.0) -> dict:
    body = _manager_get(url, "/api/fleet", timeout=timeout)
    if not isinstance(body.get("ppus"), list):
        raise FleetError("Manager Fleet response violates the expected contract")
    return body


def manager_batch(url: str, batch_id: str, *, timeout: float = 5.0) -> dict:
    """Observe an existing Manager Batch; never issue Start or POST."""
    if not isinstance(batch_id, str) or re.fullmatch(r"[0-9a-f]{32}", batch_id) is None:
        raise FleetError("Batch ID must be exactly 32 lowercase hexadecimal characters")
    body = _manager_get(url, "/api/programming/batches/" + batch_id, timeout=timeout)
    batch = body.get("batch")
    if not isinstance(batch, dict) or batch.get("batch_id") != batch_id:
        raise FleetError("Manager Batch identity or response contract mismatch")
    return batch
