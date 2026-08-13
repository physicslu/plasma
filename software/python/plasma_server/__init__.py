"""Async Plasma server and multi-channel scheduler."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .channel_manager import ChannelManager
    from .server import PlasmaServer

__all__ = ["ChannelManager", "PlasmaServer"]


def __getattr__(name: str) -> Any:
    if name == "ChannelManager":
        from .channel_manager import ChannelManager

        return ChannelManager
    if name == "PlasmaServer":
        from .server import PlasmaServer

        return PlasmaServer
    raise AttributeError(name)
