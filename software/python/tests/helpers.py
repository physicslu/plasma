from __future__ import annotations

from pathlib import Path
from typing import Any

from plasma_core.config import ChannelConfig, PlasmaConfig, ServerConfig


def make_config(
    root: Path,
    *,
    enabled_channels: int = 2,
    max_supported_channels: int = 8,
    max_concurrent_jobs: int | None = None,
    channel_options: dict[int, dict[str, Any]] | None = None,
    queue_depth: int = 16,
) -> PlasmaConfig:
    channel_options = channel_options or {}
    channels: list[ChannelConfig] = []
    for channel_id in range(max_supported_channels):
        options = channel_options.get(channel_id, {})
        channels.append(
            ChannelConfig(
                id=channel_id,
                enabled=channel_id < enabled_channels,
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
            max_supported_channels=max_supported_channels,
            max_concurrent_jobs=max_concurrent_jobs or enabled_channels,
            max_queue_depth_per_channel=queue_depth,
            output_root=root / "output",
            log_root=root / "logs",
        ),
        channels=channels,
    )
    config.validate()
    return config
