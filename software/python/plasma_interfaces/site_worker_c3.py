"""Runtime-side client of the local Stage C-3 Site Worker (control socket).

plasma-server (the trusted Runtime, identified by the Worker through its
systemd MainPID) runs one REST Site Job through C-3 as:

  stage Job-owned Normalized Image -> open_job_session -> bind_image(profile)
  -> run(flash_cycle) -> close_session -> remove staged image

The Worker owns Site admission, PS-local OpenOCD, SAFE_OFF verification and
sealing. This client sends no path, executable or Tcl: only the Job ID, the
Site, the exact-ICPN Flash profile resolved from IC Support and the image
SHA256/size. Wire protocol: ``plasma.ppu.site-worker.v1`` (one JSON line).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from plasma_core.errors import ErrorCode, PlasmaError

PROTOCOL = "plasma.ppu.site-worker.v1"
DEFAULT_IMAGE_ROOT = Path("/run/plasma-server/normalized-images")


class SiteWorkerRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class C3FlashProfile:
    icpn: str
    target_config: str
    flash_base: int
    flash_size: int
    erase_granularity: int

    def to_wire(self) -> dict[str, Any]:
        return {
            "icpn": self.icpn,
            "target_config": self.target_config,
            "flash_base": self.flash_base,
            "flash_size": self.flash_size,
            "erase_granularity": self.erase_granularity,
        }


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
    not_ready = code.startswith(("ENGINE_NOT_READY", "SITE_WORKER_UNREACHABLE"))
    return PlasmaError(
        ErrorCode.INTERFACE_NOT_CONFIGURED if not_ready else ErrorCode.INTERFACE_FAILURE,
        f"C-3 Site Worker {stage} refused: {code}",
        context={"site_worker_stage": stage, "site_worker_code": code,
                 "outcome_unknown": unknown, **context},
    )


async def run_flash_cycle(
    client: SiteWorkerControlClient,
    *,
    job_id: str,
    site_id: int,
    profile: C3FlashProfile,
    image: bytes,
    image_root: Path,
    max_runtime_s: int,
) -> dict[str, Any]:
    """One complete C-3 Flash cycle for one REST Job. Cancellation (task
    cancel / timeout) closes the session, which cancels the in-flight
    OpenOCD operation inside the Worker (the Worker seals on an unproven
    SAFE_OFF); the staged image is always removed."""
    digest = hashlib.sha256(image).hexdigest()
    context = {"job_id": job_id, "site_id": site_id, "icpn": profile.icpn}
    staged = stage_image(image_root, job_id, image)
    session_id: str | None = None
    try:
        try:
            opened = await asyncio.to_thread(
                client.call, "open_job_session", job_id=job_id, sites=[site_id],
                max_runtime_s=max_runtime_s)
            session_id = str(opened["session_id"])
            await asyncio.to_thread(
                client.call, "bind_image", session_id=session_id, profile=profile.to_wire(),
                image_sha256=digest, image_size=len(image))
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
                context={**context, "site_worker_result": result},
            )
        if result.get("readback_sha256") != digest or result.get("bytes_verified") != len(image):
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                "C-3 Flash cycle readback evidence does not match the Job image",
                context={**context, "expected_sha256": digest, "site_worker_result": result},
            )
        return {**result, "image_sha256": digest, "session_id": session_id}
    finally:
        if session_id is not None:
            # Shielded: a cancelled Job still closes its session (stops OpenOCD).
            await asyncio.shield(asyncio.to_thread(_close_quietly, client, session_id))
        try:
            staged.unlink()
        except FileNotFoundError:
            pass


def _close_quietly(client: SiteWorkerControlClient, session_id: str) -> Mapping[str, Any] | None:
    try:
        return client.call("close_session", session_id=session_id)
    except SiteWorkerRefused:
        return None
