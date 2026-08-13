from __future__ import annotations

from plasma_core.errors import ErrorCode, PlasmaError

from .base import BaseInterface, ProgressCallback


class FPGAInterface(BaseInterface):
    """Reserved PS/PL boundary for the future FPGA bus layer."""

    def __init__(self, channel_id: int, register_base: int | None) -> None:
        self.channel_id = channel_id
        self.register_base = register_base

    def _not_ready(self) -> PlasmaError:
        return PlasmaError(
            ErrorCode.INTERFACE_NOT_CONFIGURED,
            "FPGA register map is not implemented in the pure-software prototype",
            context={"channel_id": self.channel_id, "register_base": self.register_base},
        )

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        raise self._not_ready()

    async def program(
        self,
        firmware: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        raise self._not_ready()

    async def verify(
        self,
        firmware: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        raise self._not_ready()

    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        raise self._not_ready()

    async def safe_shutdown(self) -> None:
        return None
