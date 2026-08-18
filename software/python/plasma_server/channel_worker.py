"""Compatibility module for the pre-Site worker import path.

New code must import :class:`SiteWorker` from ``plasma_server.site_worker``.
Plasma protocol v3.1 still uses ``channel_id`` on the wire; that does not make
Channel the canonical Python domain term.
"""

from .site_worker import ChannelWorker, SiteWorker

__all__ = ["ChannelWorker", "SiteWorker"]
