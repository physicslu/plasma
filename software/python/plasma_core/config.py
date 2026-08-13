from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ErrorCode, PlasmaError


@dataclass(slots=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 9900
    max_supported_channels: int = 8
    max_concurrent_jobs: int = 2
    max_queue_depth_per_channel: int = 16
    output_root: Path = Path("output")
    log_root: Path = Path("logs")
    max_metadata_bytes: int = 65_536
    max_map_bytes: int = 1_048_576
    max_binary_bytes: int = 67_108_864


@dataclass(slots=True)
class ChannelConfig:
    id: int
    enabled: bool = False
    interface: str = "mock"
    target: str = "STM32F103C8T6"
    operation_timeout_s: float = 30.0
    max_retries: int = 0
    retry_backoff_s: float = 0.05
    register_base: int | None = None
    mock: dict[str, Any] = field(default_factory=dict)
    openocd: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlasmaConfig:
    server: ServerConfig
    channels: list[ChannelConfig]

    def validate(self) -> None:
        maximum = self.server.max_supported_channels
        if not 1 <= maximum <= 8:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "max_supported_channels must be between 1 and 8",
            )
        if not 1 <= self.server.max_concurrent_jobs <= maximum:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "max_concurrent_jobs must be between 1 and max_supported_channels",
            )
        if self.server.max_queue_depth_per_channel < 1:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "max_queue_depth_per_channel must be positive")
        ids = [channel.id for channel in self.channels]
        if len(ids) != len(set(ids)):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "channel IDs must be unique")
        if any(channel_id < 0 or channel_id >= maximum for channel_id in ids):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"channel IDs must be in range 0..{maximum - 1}",
            )
        supported_interfaces = {"mock", "openocd", "fpga"}
        for channel in self.channels:
            if channel.interface not in supported_interfaces:
                raise PlasmaError(
                    ErrorCode.CONFIG_INVALID,
                    f"unsupported interface '{channel.interface}' on CH{channel.id}",
                )
            if channel.operation_timeout_s <= 0 or channel.max_retries < 0:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"invalid retry/timeout settings on CH{channel.id}")


def _server_from_dict(raw: dict[str, Any], base_dir: Path) -> ServerConfig:
    values = dict(raw)
    for key in ("output_root", "log_root"):
        path = Path(values.get(key, key.removesuffix("_root")))
        values[key] = path if path.is_absolute() else (base_dir / path).resolve()
    return ServerConfig(**values)


def _channel_from_dict(raw: dict[str, Any]) -> ChannelConfig:
    values = dict(raw)
    register_base = values.get("register_base")
    if isinstance(register_base, str):
        values["register_base"] = int(register_base, 0)
    return ChannelConfig(**values)


def load_config(path: str | Path) -> PlasmaConfig:
    config_path = Path(path).resolve()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            f"cannot load configuration: {config_path}",
            original_exception=exc,
        ) from exc
    if not isinstance(raw, dict):
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "configuration root must be a mapping")
    try:
        server = _server_from_dict(raw.get("server", {}), config_path.parent.parent)
        channels = [_channel_from_dict(item) for item in raw.get("channels", [])]
    except (TypeError, ValueError) as exc:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "configuration contains invalid fields",
            original_exception=exc,
        ) from exc
    config = PlasmaConfig(server=server, channels=channels)
    config.validate()
    return config
