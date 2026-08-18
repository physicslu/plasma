"""Compatibility adapter for the pre-Site ChannelManager API.

Canonical code must use :class:`SiteManager` from ``plasma_server.site_manager``.
This adapter deliberately exposes zero-based Channel-indexed ``interfaces`` and
``workers`` views and defaults STATUS to the v3.1 ``programmer/channels`` shape.
It keeps compatibility semantics at this module boundary instead of polluting
the one-based SiteManager domain model.
"""

from __future__ import annotations

from typing import Any

from plasma_core.models import legacy_channel_id_from_site

from .site_manager import SiteManager


class ChannelManager:
    """Legacy v3.1 facade over the canonical one-based :class:`SiteManager`."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._site_manager = SiteManager(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._site_manager, name)

    @property
    def interfaces(self) -> dict[int, Any]:
        return {
            legacy_channel_id_from_site(site_id): interface
            for site_id, interface in self._site_manager.interfaces.items()
        }

    @property
    def workers(self) -> dict[int, Any]:
        return {
            legacy_channel_id_from_site(site_id): worker
            for site_id, worker in self._site_manager.workers.items()
        }

    async def start(self) -> list[str]:
        return await self._site_manager.start()

    async def shutdown(self) -> None:
        await self._site_manager.shutdown()

    def enqueue(self, request: Any):
        return self._site_manager.enqueue(request)

    async def submit(self, request: Any):
        return await self._site_manager.submit(request)

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self._site_manager.cancel(job_id)

    def status(
        self,
        *,
        site_id: int | None = None,
        channel_id: int | None = None,
        job_id: str | None = None,
        protocol_version: str = "3.1",
    ) -> dict[str, Any]:
        return self._site_manager.status(
            site_id=site_id,
            channel_id=channel_id,
            job_id=job_id,
            protocol_version=protocol_version,
        )


__all__ = ["ChannelManager", "SiteManager"]
