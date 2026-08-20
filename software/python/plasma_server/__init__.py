"""Async Plasma server and local Programming Site scheduler."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .server import PlasmaServer
    from .site_manager import SiteManager
    from .site_worker import SiteWorker

__all__ = ["PlasmaServer", "SiteManager", "SiteWorker"]


def __getattr__(name: str) -> Any:
    if name == "SiteManager":
        from .site_manager import SiteManager

        return SiteManager
    if name == "SiteWorker":
        from .site_worker import SiteWorker

        return SiteWorker
    if name == "PlasmaServer":
        from .server import PlasmaServer

        return PlasmaServer
    raise AttributeError(name)
