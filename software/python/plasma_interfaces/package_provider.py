"""OPF Package Provider seam: a Programming Job uses the existing C-2 executor.

A successful child process is NOT proof that a DUT was programmed. Until
Provider-specific programming evidence is qualified, this interface always
refuses a successful Flash result. It has no root or hardware access.
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from .base import BaseInterface, ProgressCallback


@dataclass(frozen=True, repr=False)
class TrustedProviderAction:
    """Runtime-only authority: never populated from Job metadata or a Bundle."""

    asset_request: Any
    authorization: Mapping[str, Any]
    owner_credential: Any
    route: Any


class PackageProviderInterface(BaseInterface):
    """Reuse the trusted Package Action executor under an existing Site Job."""

    def __init__(self) -> None:
        self._run: Callable[..., dict[str, Any]] | None = None
        self._job: JobRequest | None = None
        self._trusted: TrustedProviderAction | None = None
        self._cancel = threading.Event()
        self._running: asyncio.Task[dict[str, Any]] | None = None
        self.last_receipt: dict[str, Any] | None = None

    @property
    def runtime_wired(self) -> bool:
        return self._run is not None

    def wire_runtime(self, run: Callable[..., dict[str, Any]]) -> None:
        if self._run is not None:
            raise RuntimeError("PACKAGE_PROVIDER_ALREADY_WIRED")
        self._run = run

    def bind_runtime_job(self, job_id: str, active_asset_set: dict[str, Any] | None,
                         deadline_monotonic: float, trusted: TrustedProviderAction | None) -> None:
        if (self._run is None or not isinstance(trusted, TrustedProviderAction)
                or trusted.asset_request.job_id != job_id
                or active_asset_set is None
                or active_asset_set.get("asset_set_sha256") != trusted.route.asset_set_sha256):
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PROVIDER_JOB_NOT_AUTHORIZED")
        self._trusted = trusted

    def prepare_request(self, request: JobRequest) -> None:
        if (self._trusted is None or request.job_id != self._trusted.asset_request.job_id
                or request.metadata.get("provider") != self._trusted.route.provider_package
                or request.metadata.get("profile") != self._trusted.route.profile_package
                or request.target != self._trusted.route.target
                or request.site_id != self._trusted.route.site_id
                or request.operation.value != self._trusted.route.operation):
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PROVIDER_JOB_BINDING_MISMATCH")
        self._job = request

    async def flash_cycle(self, image: bytes,
                          progress: ProgressCallback | None = None) -> dict[str, object]:
        if self._run is None or self._job is None or self._trusted is None:
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, "PROVIDER_RUNTIME_NOT_WIRED")
        if image != self._job.image or self._running is not None:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "PROVIDER_IMAGE_OR_STATE_MISMATCH")
        self._cancel = threading.Event()
        self._running = asyncio.create_task(asyncio.to_thread(
            self._run, self._trusted, self._cancel))
        try:
            receipt = await asyncio.shield(self._running)
            self.last_receipt = dict(receipt)
        except asyncio.CancelledError:
            self._cancel.set()
            try:
                await asyncio.wait_for(asyncio.shield(self._running), timeout=20)
            except (TimeoutError, Exception) as exc:
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise PlasmaError(ErrorCode.INTERFACE_FAILURE,
                                  "PACKAGE_PROCESS_TERMINATION_UNPROVEN") from exc
            raise
        finally:
            if self._running.done():
                self._running = None
        # Process exit 0, even with stdout containing "PASS", is not a
        # readback/SAFE_OFF receipt from a qualified transport.
        raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                          "PROVIDER_PROGRAMMING_EVIDENCE_NOT_QUALIFIED")

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PROVIDER_OPERATION_NOT_WIRED")

    async def program(self, image: bytes, address: int = 0,
                      progress: ProgressCallback | None = None) -> None:
        raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PROVIDER_OPERATION_NOT_WIRED")

    async def verify(self, image: bytes, address: int = 0,
                     progress: ProgressCallback | None = None) -> None:
        raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PROVIDER_OPERATION_NOT_WIRED")

    async def read(self, address: int, length: int,
                   progress: ProgressCallback | None = None) -> bytes:
        raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED, "PROVIDER_OPERATION_NOT_WIRED")

    async def safe_shutdown(self) -> None:
        task = self._running
        self._cancel.set()
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=20)
            except (TimeoutError, Exception) as exc:
                raise PlasmaError(ErrorCode.INTERFACE_FAILURE,
                                  "PACKAGE_PROCESS_TERMINATION_UNPROVEN") from exc
        self._running = None
        self._trusted = None
        self._job = None
