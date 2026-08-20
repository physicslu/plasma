from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


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

    @abstractmethod
    async def verify(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        raise NotImplementedError

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