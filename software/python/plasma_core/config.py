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
    max_supported_sites: int = 8
    max_concurrent_jobs: int = 2
    max_queue_depth_per_site: int = 16
    output_root: Path = Path("output")
    log_root: Path = Path("logs")
    max_metadata_bytes: int = 65_536
    max_map_bytes: int = 1_048_576
    max_binary_bytes: int = 67_108_864


@dataclass(slots=True)
class SiteConfig:
    """One independently controlled, one-based Programming Site inside a PPU."""

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
class PPUConfig:
    """Identity of one physical Plasma Programming Unit (PPU)."""

    id: str = "local-ppu"
    facility_id: str = "default-facility"
    model: str = "generic"
    display_name: str = "Plasma Programming Unit"


@dataclass(slots=True)
class PlasmaConfig:
    server: ServerConfig
    sites: list[SiteConfig] = field(default_factory=list)
    ppu: PPUConfig = field(default_factory=PPUConfig)

    @property
    def site_count(self) -> int:
        return len(self.sites)

    @property
    def enabled_site_count(self) -> int:
        return sum(site.enabled for site in self.sites)

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
        if any(
            isinstance(site_id, bool)
            or not isinstance(site_id, int)
            or site_id < 1
            or site_id > maximum
            for site_id in ids
        ):
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"site IDs must be integer values in range 1..{maximum}",
            )
        if len(ids) != len(set(ids)):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "site IDs must be unique")
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
    declared_root_fields = {"ppu", "server", "sites"}
    unknown_root_fields = set(raw) - declared_root_fields
    if unknown_root_fields:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "configuration contains unknown root fields",
            context={"unknown_fields": sorted(str(field) for field in unknown_root_fields)},
        )
    try:
        server = _server_from_dict(raw.get("server", {}), config_path.parent.parent)
        ppu = _ppu_from_dict(raw.get("ppu", {}))
        sites = [_site_from_dict(item) for item in raw.get("sites", [])]
    except (TypeError, ValueError) as exc:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            "configuration contains invalid fields",
            original_exception=exc,
        ) from exc
    config = PlasmaConfig(server=server, sites=sites, ppu=ppu)
    config.validate()
    return config
