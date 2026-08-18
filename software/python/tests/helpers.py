from __future__ import annotations

from pathlib import Path
from typing import Any

from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.models import site_id_from_legacy_channel


def make_config(
    root: Path,
    *,
    enabled_sites: int | None = None,
    max_supported_sites: int | None = None,
    max_concurrent_jobs: int | None = None,
    site_options: dict[int, dict[str, Any]] | None = None,
    queue_depth: int = 16,
    # Legacy test-helper aliases keep old tests explicit while they migrate.
    enabled_channels: int | None = None,
    max_supported_channels: int | None = None,
    channel_options: dict[int, dict[str, Any]] | None = None,
) -> PlasmaConfig:
    if enabled_sites is not None and enabled_channels is not None:
        raise TypeError("use either enabled_sites or legacy enabled_channels, not both")
    if max_supported_sites is not None and max_supported_channels is not None:
        raise TypeError("use either max_supported_sites or legacy max_supported_channels, not both")
    if site_options is not None and channel_options is not None:
        raise TypeError("use either site_options or legacy channel_options, not both")

    enabled = enabled_sites if enabled_sites is not None else (
        enabled_channels if enabled_channels is not None else 2
    )
    maximum = max_supported_sites if max_supported_sites is not None else (
        max_supported_channels if max_supported_channels is not None else 8
    )
    if site_options is not None:
        options_by_site = dict(site_options)
    else:
        options_by_site = {
            site_id_from_legacy_channel(channel_id): options
            for channel_id, options in (channel_options or {}).items()
        }

    sites: list[SiteConfig] = []
    for site_id in range(1, maximum + 1):
        options = options_by_site.get(site_id, {})
        sites.append(
            SiteConfig(
                id=site_id,
                enabled=site_id <= enabled,
                interface="mock",
                operation_timeout_s=float(options.get("operation_timeout_s", 1.0)),
                max_retries=int(options.get("max_retries", 0)),
                retry_backoff_s=float(options.get("retry_backoff_s", 0.001)),
                mock=dict(options.get("mock", {})),
            )
        )
    config = PlasmaConfig(
        server=ServerConfig(
            host="127.0.0.1",
            port=0,
            max_supported_sites=maximum,
            max_concurrent_jobs=max_concurrent_jobs or enabled,
            max_queue_depth_per_site=queue_depth,
            output_root=root / "output",
            log_root=root / "logs",
        ),
        sites=sites,
    )
    config.validate()
    return config
