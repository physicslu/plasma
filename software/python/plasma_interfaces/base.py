from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from plasma_core.errors import ErrorCode, PlasmaError

from .runtime_context import RuntimeJobContext

if TYPE_CHECKING:
    from plasma_core.models import ExecutionImageRef, JobRequest


ProgressCallback = Callable[[int, int], Awaitable[None]]


class BaseInterface(ABC):
    """Hardware boundary. One instance belongs to exactly one Programming Site."""

    # True only for an interface that executes an admitted Job Binding and
    # verifies it against what it was asked to do. Declaring it grants no
    # execution authority: route admission remains the execution authority.
    CONSUMES_JOB_BINDING = False

    def prepare_request(self, request: "JobRequest") -> None:
        """Prepare one handler attempt for a Job.

        Handlers invoke this hook every time an attempt enters the hardware
        boundary. Real interfaces normally need no preparation. MockInterface
        uses it to bind the immutable Mock runtime snapshot and advance the
        deterministic attempt number without coupling SiteWorker to Mock.
        """

    @staticmethod
    def _require_runtime_context(context: object) -> RuntimeJobContext:
        """Accept only a context the PPU Runtime itself built.

        Anything shaped like one -- a dict echoed from Job metadata, a stub
        carrying the right attribute names -- is refused, so an interface can
        never be talked into treating a Manager claim as already admitted.
        """
        if type(context) is not RuntimeJobContext:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                "RUNTIME_CONTEXT_NOT_TRUSTED",
            )
        return context

    def bind_runtime_job(self, context: RuntimeJobContext) -> None:
        """Bind one Job attempt's trusted Runtime context.

        SiteWorker calls this on every interface, for every attempt, before the
        attempt runs. The default accepts a context that carries no
        authorization source and refuses one it cannot consume: an interface
        must never be handed an admitted Job Binding or a trusted Provider
        Action that it would then silently ignore.
        """
        context = self._require_runtime_context(context)
        if context.has_authorization:
            raise PlasmaError(
                ErrorCode.OPERATION_UNSUPPORTED,
                "interface cannot consume a trusted Runtime Job context",
                context={"job_id": context.job_id, "site_id": context.site_id},
            )

    @abstractmethod
    async def erase(self, progress: ProgressCallback | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def program(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        raise NotImplementedError

    async def program_image_ref(
        self,
        image_ref: "ExecutionImageRef",
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        """Program an immutable execution image reference when the interface supports it."""
        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            "interface does not support execution image references",
            context={"scheme": image_ref.scheme},
        )

    async def run_operations(
        self,
        operations: tuple[str, ...],
        image: bytes,
        progress: ProgressCallback | None = None,
    ) -> dict[str, object]:
        """One ``programming`` Job: the ordered erase / program / verify list.

        The default composes this interface's own operations in the given
        order, running only the listed ones. An interface with one hardware
        session per Job (C-3 OpenOCD) overrides it and returns its evidence.
        """
        for operation in operations:
            if operation == "erase":
                await self.erase(progress)
            elif operation == "program":
                await self.program(image, 0, progress)
            elif operation == "verify":
                await self.verify(image, 0, progress)
            else:
                raise PlasmaError(
                    ErrorCode.OPERATION_UNSUPPORTED,
                    f"'{operation}' is not a programming operation",
                )
        return {}

    async def flash_cycle(
        self,
        image: bytes,
        progress: ProgressCallback | None = None,
    ) -> dict[str, object]:
        """Complete Flash cycle (Erase -> Program -> Verify -> full Readback).

        Returns evidence (e.g. readback SHA256). Interfaces that cannot prove
        every step must not emulate it from separate operations.
        """
        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            "interface does not support the complete Flash cycle",
        )

    @abstractmethod
    async def verify(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        raise NotImplementedError

    async def verify_image_ref(
        self,
        image_ref: "ExecutionImageRef",
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        """Verify against an immutable execution image reference when supported."""
        raise PlasmaError(
            ErrorCode.OPERATION_UNSUPPORTED,
            "interface does not support execution image references",
            context={"scheme": image_ref.scheme},
        )

    @abstractmethod
    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def safe_shutdown(self) -> None:
        """Leave only this Site in a defined safe state."""
        raise NotImplementedError
