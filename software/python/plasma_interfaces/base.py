from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from plasma_core.errors import ErrorCode, PlasmaError

if TYPE_CHECKING:
    from plasma_core.models import ExecutionImageRef


ProgressCallback = Callable[[int, int], Awaitable[None]]


class BaseInterface(ABC):
    """Hardware boundary. One instance belongs to exactly one Programming Site."""

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
