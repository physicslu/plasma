from __future__ import annotations

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import validate_site_id

from .base import BaseInterface, ProgressCallback


class FPGAInterface(BaseInterface):
    """Reserved PS/PL boundary for one Programming Site's future FPGA bus layer."""

    def __init__(self, site_id: int, register_base: int | None = None) -> None:
        self.site_id = validate_site_id(site_id)
        self.register_base = register_base

    def _not_ready(self) -> PlasmaError:
        return PlasmaError(
            ErrorCode.INTERFACE_NOT_CONFIGURED,
            "FPGA register map is not implemented in the pure-software prototype",
            context={
                "site_id": self.site_id,
                "register_base": self.register_base,
            },
        )

    async def erase(self, progress: ProgressCallback | None = None) -> None:
        raise self._not_ready()

    async def program(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        raise self._not_ready()

    async def verify(
        self,
        image: bytes,
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