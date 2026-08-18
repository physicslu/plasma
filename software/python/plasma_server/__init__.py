"""Async Plasma server and local Programming Site scheduler."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .server import PlasmaServer
    from .site_manager import ChannelManager, SiteManager
    from .site_worker import ChannelWorker, SiteWorker

__all__ = [
    "ChannelManager",
    "ChannelWorker",
    "PlasmaServer",
    "SiteManager",
    "SiteWorker",
]


def __getattr__(name: str) -> Any:
    if name in {"ChannelManager", "SiteManager"}:
        from .site_manager import ChannelManager, SiteManager

        return SiteManager if name == "SiteManager" else ChannelManager
    if name in {"ChannelWorker", "SiteWorker"}:
        from .site_worker import ChannelWorker, SiteWorker

        return SiteWorker if name == "SiteWorker" else ChannelWorker
    if name == "PlasmaServer":
        from .server import PlasmaServer

        return PlasmaServer
    raise AttributeError(name)
