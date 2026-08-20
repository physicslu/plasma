from __future__ import annotations

from pathlib import Path
from typing import Any

from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig


def make_config(
    root: Path,
    *,
    enabled_sites: int = 2,
    max_supported_sites: int = 8,
    max_concurrent_jobs: int | None = None,
    site_options: dict[int, dict[str, Any]] | None = None,
    queue_depth: int = 16,
) -> PlasmaConfig:
    options_by_site = dict(site_options or {})
    sites: list[SiteConfig] = []
    for site_id in range(1, max_supported_sites + 1):
        options = options_by_site.get(site_id, {})
        sites.append(
            SiteConfig(
                id=site_id,
                enabled=site_id <= enabled_sites,
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
            max_supported_sites=max_supported_sites,
            max_concurrent_jobs=max_concurrent_jobs or enabled_sites,
            max_queue_depth_per_site=queue_depth,
            output_root=root / "output",
            log_root=root / "logs",
        ),
        sites=sites,
    )
    config.validate()
    return config
