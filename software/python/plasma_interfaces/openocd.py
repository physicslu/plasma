from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest

from .base import BaseInterface, ProgressCallback
from .site_worker_c3 import (
    DEFAULT_IMAGE_ROOT,
    SiteWorkerControlClient,
)


class OpenOCDInterface(BaseInterface):
    """Per-Site OpenOCD interface for the Z2 C-3 Site Worker product path.

    The complete Flash cycle runs through the local Stage C-3 Site Worker,
    which owns Site admission and the PS-local OpenOCD. Only ``flash_cycle`` is
    offered; the target config and Flash geometry come from the selected
    verified Bundle Profile. There is no IC Catalog, exact-ICPN compiler or
    software-validation process path. Without a Site Worker socket the
    interface cannot execute anything.
    """

    def __init__(self, options: dict[str, Any]) -> None:
        socket_path = options.get("site_worker_socket")
        self._site_worker = (
            SiteWorkerControlClient(Path(str(socket_path))) if socket_path else None
        )
        self.normalized_image_root = Path(
            str(options.get("normalized_image_root", DEFAULT_IMAGE_ROOT))
        )
        self._request: JobRequest | None = None
        # Installed by the trusted Runtime composition, never by Job metadata.
        self.opf_flash_executor: Callable[..., Awaitable[dict[str, Any]]] | None = None
        self.opf_flash_preflight: Callable[..., dict[str, Any]] | None = None
        self._runtime_job: tuple[str, dict[str, Any] | None, float] | None = None

    def bind_runtime_job(self, job_id: str, active_asset_set: dict[str, Any] | None,
                         deadline_monotonic: float) -> None:
        self._runtime_job = (job_id, deepcopy(active_asset_set), deadline_monotonic)

    @property
    def site_worker_ready(self) -> bool:
        """Configured for the C-3 Site Worker product path."""
        return self._site_worker is not None

    def _require_ready(self) -> None:
        if not self.site_worker_ready:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD runtime requires the C-3 Site Worker",
            )

    def _flash_cycle_only(self, operation: Operation) -> None:
        self._require_ready()
        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            "the C-3 Site Worker path offers only the complete flash_cycle operation",
            context={"operation": operation.value},
        )

    def prepare_request(self, request: JobRequest) -> None:
        self._require_ready()
        if request.operation is not Operation.FLASH_CYCLE:
            self._flash_cycle_only(request.operation)
        if self.opf_flash_preflight is None or self._runtime_job is None:
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, "OPF_RUNTIME_NOT_WIRED")
        try:
            self.opf_flash_preflight(
                active_asset_set=self._runtime_job[1], target=request.target,
                site_id=request.site_id, image_size=request.image_size,
                provider=request.metadata.get("provider"), profile=request.metadata.get("profile"))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "OPF_FLASH_DENIED:" + str(exc)) from exc
        self._request = request

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        self._flash_cycle_only(Operation.ERASE)

    async def program(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._flash_cycle_only(Operation.PROGRAM)

    async def verify(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._flash_cycle_only(Operation.VERIFY)

    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        self._flash_cycle_only(Operation.READ)
        raise AssertionError("unreachable")

    async def flash_cycle(
        self,
        image: bytes,
        progress: ProgressCallback | None = None,
    ) -> dict[str, object]:
        self._require_ready()
        request = self._request
        if request is None or request.operation is not Operation.FLASH_CYCLE:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD operation has no matching prepared Job",
            )
        if image != request.image or not image:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "OpenOCD Job image mismatch")
        assert self._site_worker is not None
        if (self.opf_flash_executor is None or self._runtime_job is None
                or self._runtime_job[0] != request.job_id):
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED,
                              "OPF_RUNTIME_NOT_WIRED")
        evidence = await self.opf_flash_executor(
            self._site_worker, request=request,
            active_asset_set=self._runtime_job[1],
            job_deadline_monotonic=self._runtime_job[2],
            image_root=self.normalized_image_root,
        )
        if progress:
            await progress(len(image), len(image))
        return evidence

    async def safe_shutdown(self) -> None:
        self._request = None
        self._runtime_job = None
