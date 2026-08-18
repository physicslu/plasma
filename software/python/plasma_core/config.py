from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from .errors import ErrorCode, PlasmaError


IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(slots=True, init=False)
class ServerConfig:
    host: str
    port: int
    max_supported_sites: int
    max_concurrent_jobs: int
    max_queue_depth_per_site: int
    output_root: Path
    log_root: Path
    max_metadata_bytes: int
    max_map_bytes: int
    max_binary_bytes: int

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9900,
        max_supported_sites: int | None = None,
        max_concurrent_jobs: int = 2,
        max_queue_depth_per_site: int | None = None,
        output_root: Path = Path("output"),
        log_root: Path = Path("logs"),
        max_metadata_bytes: int = 65_536,
        max_map_bytes: int = 1_048_576,
        max_binary_bytes: int = 67_108_864,
        *,
        max_supported_channels: int | None = None,
        max_queue_depth_per_channel: int | None = None,
    ) -> None:
        if max_supported_sites is not None and max_supported_channels is not None:
            raise TypeError("use either max_supported_sites or legacy max_supported_channels, not both")
        if max_queue_depth_per_site is not None and max_queue_depth_per_channel is not None:
            raise TypeError(
                "use either max_queue_depth_per_site or legacy max_queue_depth_per_channel, not both"
            )
        self.host = host
        self.port = port
        self.max_supported_sites = (
            max_supported_sites
            if max_supported_sites is not None
            else (max_supported_channels if max_supported_channels is not None else 8)
        )
        self.max_concurrent_jobs = max_concurrent_jobs
        self.max_queue_depth_per_site = (
            max_queue_depth_per_site
            if max_queue_depth_per_site is not None
            else (max_queue_depth_per_channel if max_queue_depth_per_channel is not None else 16)
        )
        self.output_root = output_root
        self.log_root = log_root
        self.max_metadata_bytes = max_metadata_bytes
        self.max_map_bytes = max_map_bytes
        self.max_binary_bytes = max_binary_bytes

    @property
    def max_supported_channels(self) -> int:
        """Legacy compatibility alias. Prefer max_supported_sites."""
        return self.max_supported_sites

    @property
    def max_queue_depth_per_channel(self) -> int:
        """Legacy compatibility alias. Prefer max_queue_depth_per_site."""
        return self.max_queue_depth_per_site


@dataclass(slots=True)
class SiteConfig:
    """One independently controlled, one-based programming Site inside a PPU."""

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


# Compatibility alias for code that still imports the pre-domain-rename type.
ChannelConfig = SiteConfig


@dataclass(slots=True, init=False)
class PPUConfig:
    """Identity of one physical Plasma Programming Unit (PPU)."""

    id: str
    facility_id: str
    model: str
    display_name: str

    def __init__(
        self,
        id: str = "local-ppu",
        facility_id: str | None = None,
        model: str = "generic",
        display_name: str = "Plasma Programming Unit",
        *,
        site_id: str | None = None,
    ) -> None:
        # site_id used to mean the deployment location. Keep it only as an
        # input compatibility alias while Facility becomes the canonical term.
        if facility_id is not None and site_id is not None and facility_id != site_id:
            raise TypeError("facility_id and legacy site_id disagree")
        self.id = id
        if facility_id is not None:
            self.facility_id = facility_id
        elif site_id is not None:
            self.facility_id = site_id
        else:
            self.facility_id = "default-facility"
        self.model = model
        self.display_name = display_name

    @property
    def site_id(self) -> str:
        """Legacy deployment-location alias. Prefer facility_id."""
        return self.facility_id


# Compatibility alias for code that still imports the pre-domain-rename type.
ProgrammerConfig = PPUConfig


@dataclass(slots=True, init=False)
class PlasmaConfig:
    server: ServerConfig
    sites: list[SiteConfig]
    ppu: PPUConfig

    def __init__(
        self,
        server: ServerConfig,
        sites: list[SiteConfig] | None = None,
        ppu: PPUConfig | None = None,
        *,
        channels: list[SiteConfig] | None = None,
        programmer: PPUConfig | None = None,
    ) -> None:
        if sites is not None and channels is not None:
            raise TypeError("use either sites or legacy channels, not both")
        if ppu is not None and programmer is not None:
            raise TypeError("use either ppu or legacy programmer, not both")
        self.server = server
        if sites is not None:
            self.sites = list(sites)
        else:
            # Legacy ChannelConfig objects used 0-based IDs. Convert them once
            # at the compatibility boundary so the domain model stays 1-based.
            self.sites = [replace(channel, id=channel.id + 1) for channel in (channels or [])]
        self.ppu = ppu if ppu is not None else (programmer or PPUConfig())

    @property
    def site_count(self) -> int:
        return len(self.sites)

    @property
    def enabled_site_count(self) -> int:
        return sum(site.enabled for site in self.sites)

    @property
    def channels(self) -> list[SiteConfig]:
        """Legacy alias for sites. IDs are canonical one-based Site IDs."""
        return self.sites

    @property
    def programmer(self) -> PPUConfig:
        """Legacy alias for ppu."""
        return self.ppu

    @property
    def channel_count(self) -> int:
        """Legacy alias for site_count."""
        return self.site_count

    @property
    def enabled_channel_count(self) -> int:
        """Legacy alias for enabled_site_count."""
        return self.enabled_site_count

    def validate(self) -> None:
        for field_name, value in (
            ("ppu.id", self.ppu.id),
            ("ppu.facility_id", self.ppu.facility_id),
        ):
            if not isinstance(value, str) or IDENTITY_PATTERN.fullmatch(value) is None:
                raise PlasmaError(
                    ErrorCode.CONFIG_INVALID,
                    f"{field_name} must be 1-128 ASCII letters, digits, '.', '_' or '-', starting with a letter or digit",
                )
        for field_name, value in (
            ("ppu.model", self.ppu.model),
            ("ppu.display_name", self.ppu.display_name),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise PlasmaError(
                    ErrorCode.CONFIG_INVALID,
                    f"{field_name} must be 1-256 characters",
                )

        maximum = self.server.max_supported_sites
        if not 1 <= maximum <= 8:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "max_supported_sites must be between 1 and 8",
            )
        if not 1 <= self.server.max_concurrent_jobs <= maximum:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "max_concurrent_jobs must be between 1 and max_supported_sites",
            )
        if self.server.max_queue_depth_per_site < 1:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "max_queue_depth_per_site must be positive")
        ids = [site.id for site in self.sites]
        if len(ids) != len(set(ids)):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "site IDs must be unique")
        if any(site_id < 1 or site_id > maximum for site_id in ids):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"site IDs must be in range 1..{maximum}",
            )
        supported_interfaces = {"mock", "openocd", "fpga"}
        for site in self.sites:
            if site.interface not in supported_interfaces:
                raise PlasmaError(
                    ErrorCode.CONFIG_INVALID,
                    f"unsupported interface '{site.interface}' on SITE{site.id}",
                )
            if site.operation_timeout_s <= 0 or site.max_retries < 0:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, f"invalid retry/timeout settings on SITE{site.id}")


def _server_from_dict(raw: dict[str, Any], base_dir: Path) -> ServerConfig:
    values = dict(raw)
    aliases = (
        ("max_supported_sites", "max_supported_channels"),
        ("max_queue_depth_per_site", "max_queue_depth_per_channel"),
    )
    for canonical, legacy in aliases:
        if canonical in values and legacy in values:
            raise TypeError(f"use either {canonical} or legacy {legacy}, not both")
        if legacy in values:
            values[canonical] = values.pop(legacy)
    for key in ("output_root", "log_root"):
        path = Path(values.get(key, key.removesuffix("_root")))
        values[key] = path if path.is_absolute() else (base_dir / path).resolve()
    return ServerConfig(**values)


def _site_from_dict(raw: dict[str, Any], *, legacy_channel: bool = False) -> SiteConfig:
    values = dict(raw)
    if legacy_channel and "id" in values:
        values["id"] = int(values["id"]) + 1
    register_base = values.get("register_base")
    if isinstance(register_base, str):
        values["register_base"] = int(register_base, 0)
    return SiteConfig(**values)


def _ppu_from_dict(raw: dict[str, Any]) -> PPUConfig:
    return PPUConfig(**dict(raw))


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
        if "ppu" in raw and "programmer" in raw:
            raise TypeError("use either ppu or legacy programmer, not both")
        if "sites" in raw and "channels" in raw:
            raise TypeError("use either sites or legacy channels, not both")
        server = _server_from_dict(raw.get("server", {}), config_path.parent.parent)
        ppu = _ppu_from_dict(raw.get("ppu", raw.get("programmer", {})))
        if "sites" in raw:
            sites = [_site_from_dict(item) for item in raw.get("sites", [])]
        else:
            sites = [
                _site_from_dict(item, legacy_channel=True)
                for item in raw.get("channels", [])
            ]
    except (TypeError, ValueError) as exc:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "configuration contains invalid fields",
            original_exception=exc,
        ) from exc
    config = PlasmaConfig(server=server, sites=sites, ppu=ppu)
    config.validate()
    return config
