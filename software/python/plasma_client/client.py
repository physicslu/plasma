from __future__ import annotations

import asyncio
import contextlib
import hashlib
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from plasma_core.diagnostics import (
    DIAGNOSTIC_PROTOCOL_VERSION,
    DIAGNOSTIC_REQUEST_MESSAGE_TYPE,
    ECHO_TRANSFORM,
    LOOPBACK_DIAGNOSTIC_TYPE,
    PS_LOOPBACK_ENDPOINT,
    crc32_hex,
)
from plasma_core.enums import JobState, Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_core.protocol import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    Frame,
    ProtocolLimits,
    encode_frame,
    read_frame,
)


class PlasmaClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9900,
        *,
        protocol_version: str = PROTOCOL_VERSION,
        connect_timeout_s: float = 5.0,
        response_timeout_s: float = 60.0,
        limits: ProtocolLimits = ProtocolLimits(),
    ) -> None:
        if protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
            raise ValueError(f"unsupported Plasma protocol version: {protocol_version}")
        self.host = host
        self.port = port
        self.protocol_version = protocol_version
        self.connect_timeout_s = connect_timeout_s
        self.response_timeout_s = response_timeout_s
        self.limits = limits

    async def _exchange(
        self,
        frame: Frame,
        *,
        response_timeout_s: float | None = None,
    ) -> Frame:
        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.connect_timeout_s,
            )
            writer.write(encode_frame(frame, self.limits))
            await writer.drain()
            response = await asyncio.wait_for(
                read_frame(reader, self.limits),
                timeout=response_timeout_s or self.response_timeout_s,
            )
        except TimeoutError as exc:
            raise PlasmaError(
                ErrorCode.CONNECTION_TIMEOUT,
                f"timeout communicating with {self.host}:{self.port}",
                recoverable=True,
                original_exception=exc,
            ) from exc
        except (OSError, ConnectionError) as exc:
            raise PlasmaError(
                ErrorCode.CONNECTION_FAILED,
                f"cannot connect to {self.host}:{self.port}",
                recoverable=True,
                original_exception=exc,
            ) from exc
        finally:
            if writer:
                writer.close()
                with contextlib.suppress(ConnectionError):
                    await writer.wait_closed()

        metadata = response.metadata
        if not metadata.get("ok"):
            raw = metadata.get("error") or {}
            try:
                code = ErrorCode(raw.get("error_code"))
            except ValueError:
                code = ErrorCode.INTERNAL_ERROR
            raise PlasmaError(
                code,
                str(raw.get("message", "remote Plasma error")),
                recoverable=bool(raw.get("recoverable", False)),
                original_exception=raw.get("original_exception"),
                context=raw.get("context") or {},
            )
        return response

    async def send(self, frame: Frame, *, response_timeout_s: float | None = None) -> dict[str, Any]:
        return (await self._exchange(frame, response_timeout_s=response_timeout_s)).metadata

    async def diagnostic_loopback(
        self,
        payload: bytes,
        *,
        test_id: str,
        sequence: int,
        endpoint: str = PS_LOOPBACK_ENDPOINT,
        pattern: str | None = None,
        seed: str | None = None,
        response_timeout_s: float | None = None,
    ) -> tuple[dict[str, Any], bytes]:
        """Execute a real Protocol v3.3 diagnostic exchange with the Plasma Server.

        This method does not submit a programming Job and does not use a Site
        Interface. The PS loopback response must therefore come from the real
        Plasma Server process reached over the configured TCP connection.
        """
        metadata: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "message_type": DIAGNOSTIC_REQUEST_MESSAGE_TYPE,
            "diagnostic_type": LOOPBACK_DIAGNOSTIC_TYPE,
            "diagnostic_version": DIAGNOSTIC_PROTOCOL_VERSION,
            "endpoint": endpoint,
            "test_id": test_id,
            "sequence": sequence,
            "transform": ECHO_TRANSFORM,
            "payload_length": len(payload),
            "tx_crc32": crc32_hex(payload),
        }
        if pattern is not None:
            metadata["pattern"] = pattern
        if seed is not None:
            metadata["seed"] = seed
        response = await self._exchange(
            Frame(metadata=metadata, binary=payload),
            response_timeout_s=response_timeout_s,
        )
        return response.metadata, response.binary

    async def submit(self, request: JobRequest) -> dict[str, Any]:
        timeout = max(self.response_timeout_s, request.timeout_s * (request.max_retries + 1) + 10)
        return await self.send(
            Frame(
                metadata=request.protocol_metadata(self.protocol_version),
                map_data=request.map_data,
                binary=request.image,
            ),
            response_timeout_s=timeout,
        )

    async def start(self, request: JobRequest) -> dict[str, Any]:
        """Queue a Job and return its ID immediately, without waiting for completion."""
        metadata = request.protocol_metadata(self.protocol_version)
        metadata["wait_for_completion"] = False
        return await self.send(
            Frame(
                metadata=metadata,
                map_data=request.map_data,
                binary=request.image,
            )
        )

    async def wait_for_job(
        self,
        job_id: str,
        *,
        poll_interval_s: float = 0.1,
        timeout_s: float | None = None,
        on_update: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Poll Job state until terminal and return the normal result response shape."""
        started = time.monotonic()
        while True:
            response = await self.status(job_id=job_id)
            job = response["job"]
            if on_update:
                on_update(job)
            state = JobState(job["state"])
            if state.terminal:
                result = job.get("result")
                if result is None:
                    raise PlasmaError(
                        ErrorCode.INTERNAL_ERROR,
                        f"terminal job has no result: {job_id}",
                    )
                return {"ok": True, "result": result}
            if timeout_s is not None and time.monotonic() - started >= timeout_s:
                raise PlasmaError(
                    ErrorCode.CONNECTION_TIMEOUT,
                    f"timed out waiting for job: {job_id}",
                    recoverable=True,
                )
            await asyncio.sleep(max(0.01, poll_interval_s))

    async def program(
        self,
        site_id: int,
        image: bytes,
        *,
        image_name: str | None = None,
        map_data: dict[str, Any] | None = None,
        timeout_s: float = 30.0,
        max_retries: int = 0,
        client_id: str = "plasma-cli",
    ) -> dict[str, Any]:
        return await self.submit(
            JobRequest(
                site_id=site_id,
                operation=Operation.PROGRAM,
                image=image,
                map_data=map_data or {},
                timeout_s=timeout_s,
                max_retries=max_retries,
                client_id=client_id,
                metadata={"image_name": image_name} if image_name else {},
            )
        )

    async def erase(self, site_id: int, **options: Any) -> dict[str, Any]:
        return await self.submit(JobRequest(site_id=site_id, operation=Operation.ERASE, **options))

    async def verify(self, site_id: int, image: bytes, **options: Any) -> dict[str, Any]:
        return await self.submit(
            JobRequest(site_id=site_id, operation=Operation.VERIFY, image=image, **options)
        )

    async def read(
        self,
        site_id: int,
        map_data: dict[str, Any],
        **options: Any,
    ) -> dict[str, Any]:
        return await self.submit(
            JobRequest(site_id=site_id, operation=Operation.READ, map_data=map_data, **options)
        )

    async def status(
        self,
        *,
        site_id: int | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "message_type": "request",
            "operation": Operation.STATUS.value,
        }
        if site_id is not None:
            metadata["site_id"] = site_id
        if job_id is not None:
            metadata["target_job_id"] = job_id
        return await self.send(Frame(metadata=metadata))

    async def cancel(self, job_id: str) -> dict[str, Any]:
        return await self.send(
            Frame(
                metadata={
                    "protocol_version": self.protocol_version,
                    "message_type": "request",
                    "operation": Operation.CANCEL.value,
                    "target_job_id": job_id,
                }
            )
        )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
