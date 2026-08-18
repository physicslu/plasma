from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ErrorCode, PlasmaError


IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


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

    @property
    def max_supported_sites(self) -> int:
        """Canonical domain name; max_supported_channels is the v3.1 compatibility field."""
        return self.max_supported_channels

    @property
    def max_queue_depth_per_site(self) -> int:
        """Canonical domain name; max_queue_depth_per_channel is the v3.1 compatibility field."""
        return self.max_queue_depth_per_channel


@dataclass(slots=True)
class SiteConfig:
    """One independently controlled programming site inside a PPU."""

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
        self.sites = list(sites if sites is not None else (channels or []))
        self.ppu = ppu if ppu is not None else (programmer or PPUConfig())

    @property
    def site_count(self) -> int:
        return len(self.sites)

    @property
    def enabled_site_count(self) -> int:
        return sum(site.enabled for site in self.sites)

    @property
    def channels(self) -> list[SiteConfig]:
        """Legacy alias for sites."""
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
        if any(site_id < 0 or site_id >= maximum for site_id in ids):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"site IDs must be in range 0..{maximum - 1}",
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
        if canonical in values:
            values[legacy] = values.pop(canonical)
    for key in ("output_root", "log_root"):
        path = Path(values.get(key, key.removesuffix("_root")))
        values[key] = path if path.is_absolute() else (base_dir / path).resolve()
    return ServerConfig(**values)


def _site_from_dict(raw: dict[str, Any]) -> SiteConfig:
    values = dict(raw)
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
        site_items = raw.get("sites", raw.get("channels", []))
        sites = [_site_from_dict(item) for item in site_items]
    except (TypeError, ValueError) as exc:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "configuration contains invalid fields",
            original_exception=exc,
        ) from exc
    config = PlasmaConfig(server=server, sites=sites, ppu=ppu)
    config.validate()
    return config
