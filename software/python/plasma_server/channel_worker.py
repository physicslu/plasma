"""Compatibility module for the pre-Site worker import path.

New code must import :class:`SiteWorker` from ``plasma_server.site_worker``.
Plasma protocol v3.1 still uses ``channel_id`` on the wire; that does not make
Channel the canonical Python domain term.
"""

# Re-export JobEventLogger because older tests/plugins patched it through this
# module. The object is shared with site_worker, so the compatibility patch
# still affects the canonical implementation.
from .site_worker import ChannelWorker, JobEventLogger, SiteWorker

__all__ = ["ChannelWorker", "JobEventLogger", "SiteWorker"]
