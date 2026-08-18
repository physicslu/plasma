"""Async Plasma server and local Programming Site scheduler."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .channel_manager import ChannelManager, SiteManager
    from .server import PlasmaServer

__all__ = ["ChannelManager", "PlasmaServer", "SiteManager"]


def __getattr__(name: str) -> Any:
    if name in {"ChannelManager", "SiteManager"}:
        from .channel_manager import ChannelManager, SiteManager

        return SiteManager if name == "SiteManager" else ChannelManager
    if name == "PlasmaServer":
        from .server import PlasmaServer

        return PlasmaServer
    raise AttributeError(name)
