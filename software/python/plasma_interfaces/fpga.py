from __future__ import annotations

from plasma_core.errors import ErrorCode, PlasmaError

from .base import BaseInterface, ProgressCallback


class FPGAInterface(BaseInterface):
    """Reserved PS/PL boundary for one Programming Site's future FPGA bus layer."""

    def __init__(
        self,
        site_id: int | None = None,
        register_base: int | None = None,
        *,
        channel_id: int | None = None,
    ) -> None:
        if site_id is not None and channel_id is not None and site_id != channel_id:
            raise TypeError("site_id and legacy channel_id disagree")
        resolved_site_id = site_id if site_id is not None else channel_id
        if resolved_site_id is None:
            raise TypeError("site_id is required")
        self.site_id = resolved_site_id
        self.register_base = register_base

    @property
    def channel_id(self) -> int:
        """Legacy alias for pre-Site Python integrations."""
        return self.site_id

    def _not_ready(self) -> PlasmaError:
        return PlasmaError(
            ErrorCode.INTERFACE_NOT_CONFIGURED,
            "FPGA register map is not implemented in the pure-software prototype",
            context={
                "site_id": self.site_id,
                # Temporary compatibility for diagnostics consumed by older tools.
                "channel_id": self.site_id,
                "register_base": self.register_base,
            },
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
