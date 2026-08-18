"""Compatibility module for the pre-Site manager import path.

New code must import :class:`SiteManager` from ``plasma_server.site_manager``.
The legacy module remains importable while downstream code migrates.
"""

from .site_manager import ChannelManager, SiteManager

__all__ = ["ChannelManager", "SiteManager"]
