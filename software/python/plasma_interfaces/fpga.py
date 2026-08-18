from __future__ import annotations

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import legacy_channel_id_from_site, site_id_from_legacy_channel, validate_site_id

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
        canonical = validate_site_id(site_id) if site_id is not None else None
        legacy = site_id_from_legacy_channel(channel_id) if channel_id is not None else None
        if canonical is not None and legacy is not None and canonical != legacy:
            raise TypeError("site_id and legacy channel_id refer to different Sites")
        resolved_site_id = canonical if canonical is not None else legacy
        if resolved_site_id is None:
            raise TypeError("site_id is required")
        self.site_id = resolved_site_id
        self.register_base = register_base

    @property
    def channel_id(self) -> int:
        """Legacy zero-based v3.1 identity derived from the one-based Site ID."""
        return legacy_channel_id_from_site(self.site_id)

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
