"""Runtime-side client of the local Stage C-3 Site Worker (control socket).

plasma-server (the trusted Runtime, identified by the Worker through its
systemd MainPID) runs one REST Site Job through C-3 as:

  stage Job-owned Normalized Image -> open_job_session(profile)
  -> bind_image(image identity) -> run(flash_cycle) -> close_session -> remove staged image

The Worker owns Site admission, PS-local OpenOCD, SAFE_OFF verification and
sealing. The verified Bundle Flash profile is pinned once at Session open;
bind_image sends SHA256, size and the verified Job Binding ``load_address``,
never a second Geometry declaration; the Worker re-derives the erase window from
the session Profile. Wire protocol: ``plasma.ppu.site-worker.v3`` (one JSON line).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
from pathlib import Path
from typing import Any, Callable, Mapping

from plasma_core.errors import ErrorCode, PlasmaError

PROTOCOL = "plasma.ppu.site-worker.v3"
DEFAULT_IMAGE_ROOT = Path("/run/plasma-server/normalized-images")


class SiteWorkerRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SiteWorkerControlClient:
    def __init__(self, socket_path: Path, timeout_s: float = 30.0) -> None:
        self.socket_path = Path(socket_path)
        self.timeout_s = timeout_s

    def call(self, op: str, *, timeout_s: float | None = None, **fields: Any) -> dict[str, Any]:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout_s if timeout_s is None else timeout_s)
                sock.connect(str(self.socket_path))
                sock.sendall((json.dumps({"protocol": PROTOCOL, "op": op, **fields}) + "\n").encode())
                data = b""
                while not data.endswith(b"\n"):
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
            reply = json.loads(data.decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise SiteWorkerRefused("SITE_WORKER_UNREACHABLE:" + type(exc).__name__) from exc
        if not isinstance(reply, dict):
            raise SiteWorkerRefused("SITE_WORKER_REPLY_INVALID")
        if not reply.get("ok"):
            raise SiteWorkerRefused(str(reply.get("error")))
        result = reply.get("result")
        if not isinstance(result, dict):
            raise SiteWorkerRefused("SITE_WORKER_REPLY_INVALID")
        return result

    def open_job_session(self, *, job_id: str, sites: list[int], max_runtime_s: int,
                         provider_route: Mapping[str, Any], deadline_monotonic: float,
                         profile: Mapping[str, Any] | None = None,
                         expected_engine_selection_sha256: str | None = None,
                         ) -> dict[str, Any]:
        fields = {"provider_route": dict(provider_route),
                  "deadline_monotonic": deadline_monotonic}
        if profile is not None:
            fields["profile"] = dict(profile)
        if expected_engine_selection_sha256 is not None:
            fields["expected_engine_selection_sha256"] = expected_engine_selection_sha256
        return self.call("open_job_session", job_id=job_id, sites=sites,
                         max_runtime_s=max_runtime_s, **fields)


def stage_image(image_root: Path, job_id: str, image: bytes) -> Path:
    """Write the Job-owned Normalized Image exactly once (never reuse a file)."""
    image_root = Path(image_root)
    path = image_root / f"{job_id}.bin"
    if path.parent != image_root or "/" in job_id or job_id in {".", ".."}:
        raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "job_id cannot name a staged image")
    image_root.mkdir(mode=0o750, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
    try:
        view = memoryview(image)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return path


def _refusal(stage: str, exc: SiteWorkerRefused, **context: Any) -> PlasmaError:
    code = exc.code
    unknown = code.startswith("OUTCOME_UNKNOWN")
    safe_failure = code.startswith("OPERATION_FAILED_SAFE:")
    not_ready = code.startswith(("ENGINE_NOT_READY", "WORKER_ENGINE_",
                                 "SITE_WORKER_UNREACHABLE"))
    return PlasmaError(
        ErrorCode.INTERFACE_NOT_CONFIGURED if not_ready else ErrorCode.INTERFACE_FAILURE,
        f"C-3 Site Worker {stage} refused: {code}",
        recoverable=safe_failure,
        context={"site_worker_stage": stage, "site_worker_code": code,
                 "outcome_unknown": unknown, **context},
    )


async def run_flash_cycle(
    client: SiteWorkerControlClient,
    *,
    job_id: str,
    site_id: int,
    icpn: str,
    image: bytes,
    image_root: Path,
    max_runtime_s: int,
    session_factory: Callable[[], Mapping[str, Any]],
    load_address: int,
    erase_length: int,
) -> dict[str, Any]:
    """One complete C-3 Flash cycle for one REST Job. Cancellation (task
    cancel / timeout) closes the session, which cancels the in-flight
    OpenOCD operation inside the Worker. An unproven SAFE_OFF remains sealed;
    the staged image is always removed."""
    digest = hashlib.sha256(image).hexdigest()
    context = {"job_id": job_id, "site_id": site_id, "icpn": icpn,
               "load_address": load_address}
    # The one range this Job may touch; the Worker re-derives it independently
    # and the Adapter must report exactly this executed range.
    expected_range = {"load_address": load_address, "erase_address": load_address,
                      "erase_length": erase_length, "write_address": load_address,
                      "verify_address": load_address, "readback_address": load_address}
    staged = stage_image(image_root, job_id, image)
    session_id: str | None = None
    try:
        try:
            # The verified OPF Session opener owns the single Profile binding.
            opened = await asyncio.to_thread(session_factory)
            session_id = str(opened["session_id"])
            bound = await asyncio.to_thread(
                client.call, "bind_image", session_id=session_id,
                image_sha256=digest, image_size=len(image), load_address=load_address)
            if ({k: bound.get(k) for k in ("load_address", "erase_address", "erase_length")}
                    != {k: expected_range[k]
                        for k in ("load_address", "erase_address", "erase_length")}):
                raise PlasmaError(
                    ErrorCode.INTERFACE_FAILURE,
                    "C-3 Site Worker bound a different Flash range than the Job Binding",
                    context={**context, "site_worker_stage": "bind_image",
                             "site_worker_bind": dict(bound)},
                )
            result = await asyncio.to_thread(
                client.call, "run", timeout_s=max_runtime_s + 30.0, session_id=session_id,
                site=site_id, operation="flash_cycle")
        except SiteWorkerRefused as exc:
            stage = "open" if session_id is None else "run"
            raise _refusal(stage, exc, **context) from None
        if result.get("result") != "PASS":
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                f"C-3 Flash cycle failed: {result.get('code', 'FAIL')}",
                recoverable=result.get("safe_off") is True,
                context={**context, "site_worker_result": result},
            )
        if result.get("readback_sha256") != digest or result.get("bytes_verified") != len(image):
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                "C-3 Flash cycle readback evidence does not match the Job image",
                context={**context, "expected_sha256": digest, "site_worker_result": result},
            )
        if {k: result.get(k) for k in expected_range} != expected_range:
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                "C-3 Flash cycle range evidence does not match the Job Binding",
                context={**context, "expected_range": expected_range,
                         "site_worker_result": result, "outcome_unknown": True},
            )
        return {**result, "image_sha256": digest, "session_id": session_id}
    finally:
        try:
            if session_id is not None:
                # A retry is safe only after close has waited for the native
                # operation and its cleanup to finish. Failed close is
                # authoritative even if the Flash result had SAFE_OFF.
                closed = await asyncio.shield(asyncio.to_thread(
                    _close_quietly, client, session_id))
                if closed is None or not closed.get("closed") or closed.get("sealed_sites"):
                    raise PlasmaError(
                        ErrorCode.INTERFACE_FAILURE,
                        "C-3 Site Worker close did not confirm hardware release",
                        context={**context, "site_worker_stage": "close",
                                 "outcome_unknown": True},
                    )
        finally:
            try:
                staged.unlink()
            except FileNotFoundError:
                pass


def _close_quietly(client: SiteWorkerControlClient, session_id: str) -> Mapping[str, Any] | None:
    try:
        return client.call("close_session", session_id=session_id)
    except SiteWorkerRefused:
        return None
