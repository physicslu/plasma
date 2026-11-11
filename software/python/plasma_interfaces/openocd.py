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

    Every Job runs through the local Stage C-3 Site Worker, which owns Site
    admission and the PS-local OpenOCD. ``programming`` runs the ordered
    erase / program / verify ``operations`` list of its SiteManager-admitted
    Job Binding as ONE Job in ONE C-3 session (Program never erases, Verify
    never writes); ``read`` is an independent Job on its bound range;
    ``flash_cycle`` is the legacy complete cycle. Separate erase / program /
    verify Jobs are not offered. The target config and Flash geometry come
    from the selected verified Bundle Profile. There is no IC Catalog,
    exact-ICPN compiler or software-validation process path. Without a Site
    Worker socket the interface cannot execute anything.
    """

    OPERATIONS = frozenset({Operation.FLASH_CYCLE, Operation.PROGRAMMING, Operation.READ})

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
        self._runtime_job: tuple[str, dict[str, Any] | None, float,
                                 dict[str, Any] | None] | None = None
        # Worker receipt of the prepared ``read`` Job (bytes excluded).
        self.operation_evidence: dict[str, Any] | None = None

    def bind_runtime_job(self, job_id: str, active_asset_set: dict[str, Any] | None,
                         deadline_monotonic: float,
                         job_binding: dict[str, Any] | None) -> None:
        """Pin the Runtime-admitted Job context, including the SiteManager-
        verified Job Binding whose ``range.address`` is the write address
        (None only for the separate inline / bundle-reference contract)."""
        self._runtime_job = (job_id, deepcopy(active_asset_set), deadline_monotonic,
                             deepcopy(job_binding))

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

    def _unsupported(self, operation: Operation) -> None:
        self._require_ready()
        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            "the C-3 Site Worker path offers programming (an operations list), "
            "read and the legacy flash_cycle, not a separate " + operation.value + " Job",
            context={"operation": operation.value},
        )

    def _binding(self, operation: Operation) -> dict[str, Any]:
        """The admitted Job Binding of a programming / read Job (never a default)."""
        binding = self._runtime_job[3] if self._runtime_job is not None else None
        job_range = binding.get("range") if isinstance(binding, dict) else None
        if (not isinstance(binding, dict) or binding.get("operation") != operation.value
                or not isinstance(job_range, dict)
                or type(job_range.get("address")) is not int
                or type(job_range.get("length")) is not int):
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                f"C-3 {operation.value} requires an admitted Job Binding",
                context={"operation": operation.value},
            )
        return binding

    def prepare_request(self, request: JobRequest) -> None:
        self._require_ready()
        if request.operation not in self.OPERATIONS:
            self._unsupported(request.operation)
        if self.opf_flash_preflight is None or self._runtime_job is None:
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED, "OPF_RUNTIME_NOT_WIRED")
        if request.operation is not Operation.FLASH_CYCLE:
            self._binding(request.operation)
        try:
            self.opf_flash_preflight(
                active_asset_set=self._runtime_job[1], target=request.target,
                site_id=request.site_id, image_size=request.image_size,
                job_binding=self._runtime_job[3],
                provider=request.metadata.get("provider"), profile=request.metadata.get("profile"),
                **({} if request.operation is Operation.FLASH_CYCLE
                   else {"operation": request.operation.value}))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "OPF_FLASH_DENIED:" + str(exc)) from exc
        self._request = request
        self.operation_evidence = None

    async def _execute(self, operation: Operation) -> dict[str, Any]:
        self._require_ready()
        request = self._request
        if request is None or request.operation is not operation:
            raise PlasmaError(
                ErrorCode.INTERFACE_NOT_CONFIGURED,
                "OpenOCD operation has no matching prepared Job",
            )
        assert self._site_worker is not None
        if (self.opf_flash_executor is None or self._runtime_job is None
                or self._runtime_job[0] != request.job_id):
            raise PlasmaError(ErrorCode.INTERFACE_NOT_CONFIGURED,
                              "OPF_RUNTIME_NOT_WIRED")
        self._binding(operation)
        return dict(await self.opf_flash_executor(
            self._site_worker, request=request,
            active_asset_set=self._runtime_job[1],
            job_deadline_monotonic=self._runtime_job[2],
            image_root=self.normalized_image_root,
            job_binding=self._runtime_job[3],
        ))

    async def run_operations(
        self,
        operations: tuple[str, ...],
        image: bytes,
        progress: ProgressCallback | None = None,
    ) -> dict[str, object]:
        """One ``programming`` Job: the Binding's ordered list in one C-3 session."""
        self._require_ready()
        request = self._request
        binding = self._binding(Operation.PROGRAMMING)
        if (request is None or list(operations) != binding.get("operations")
                or image != request.image
                or bool(image) != ("program" in operations or "verify" in operations)):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT,
                              "OpenOCD programming Job does not match its Job Binding")
        evidence = await self._execute(Operation.PROGRAMMING)
        if progress:
            total = len(image) or binding["range"]["length"]
            await progress(total, total)
        return evidence

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        self._unsupported(Operation.ERASE)

    async def program(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._unsupported(Operation.PROGRAM)

    async def verify(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        self._unsupported(Operation.VERIFY)

    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        self._require_ready()
        job_range = self._binding(Operation.READ)["range"]
        if address != job_range["address"] or length != job_range["length"]:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT,
                              "OpenOCD read range is not the Job Binding range")
        evidence = await self._execute(Operation.READ)
        data = evidence.pop("data", None)
        if type(data) is not bytes or len(data) != length:
            raise PlasmaError(ErrorCode.INTERFACE_FAILURE,
                              "C-3 read returned no verified data")
        # Read bytes go to the Job output file, never into the Job result.
        self.operation_evidence = evidence
        if progress:
            await progress(length, length)
        return data

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
            job_binding=self._runtime_job[3],
        )
        if progress:
            await progress(len(image), len(image))
        return evidence

    async def safe_shutdown(self) -> None:
        self._request = None
        self._runtime_job = None
        self.operation_evidence = None
