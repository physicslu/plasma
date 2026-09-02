from __future__ import annotations

import ipaddress
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from plasma_core.errors import ErrorCode, PlasmaError


PPU_NETWORK_INTERFACE = "eth0"
PPU_NETWORK_MODE_DHCP = "dhcp"
PPU_NETWORK_MODE_STATIC = "static"
PPU_NETWORK_MODES = frozenset({PPU_NETWORK_MODE_DHCP, PPU_NETWORK_MODE_STATIC})
MAX_DNS_SERVERS = 3


def _config_error(message: str, *, context: dict[str, Any] | None = None) -> PlasmaError:
    return PlasmaError(ErrorCode.CONFIG_INVALID, message, context=context or {})


def _ipv4(value: Any, label: str) -> ipaddress.IPv4Address:
    if not isinstance(value, str) or not value:
        raise _config_error(f"{label} must be a non-empty IPv4 address string")
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise _config_error(f"{label} must be a valid IPv4 address") from exc
    if address.is_unspecified or address.is_multicast:
        raise _config_error(f"{label} must be a usable unicast IPv4 address")
    return address


def _host_address(value: Any, prefix_length: int, label: str) -> ipaddress.IPv4Address:
    address = _ipv4(value, label)
    network = ipaddress.IPv4Network(f"{address}/{prefix_length}", strict=False)
    if prefix_length <= 30 and address in {network.network_address, network.broadcast_address}:
        raise _config_error(f"{label} must be a usable host address for /{prefix_length}")
    return address


@dataclass(frozen=True, slots=True)
class PPUNetworkSettings:
    """Desired PPU eth0 configuration.

    Phase 1 persists and validates this object only. It deliberately does not
    claim that the Linux network stack has applied the desired configuration.
    """

    revision: int = 1
    interface: str = PPU_NETWORK_INTERFACE
    mode: str = PPU_NETWORK_MODE_DHCP
    address: str | None = None
    prefix_length: int | None = None
    gateway: str | None = None
    dns_servers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise _config_error("PPU network settings revision must be a positive integer")
        if self.interface != PPU_NETWORK_INTERFACE:
            raise _config_error(
                f"PPU network interface is fixed to {PPU_NETWORK_INTERFACE} in Phase 1",
                context={"interface": self.interface},
            )
        if self.mode not in PPU_NETWORK_MODES:
            raise _config_error(
                "PPU network mode must be dhcp or static",
                context={"mode": self.mode},
            )

        if not isinstance(self.dns_servers, (list, tuple)):
            raise _config_error("PPU network dns_servers must be an array")
        if len(self.dns_servers) > MAX_DNS_SERVERS:
            raise _config_error(f"PPU network dns_servers supports at most {MAX_DNS_SERVERS} addresses")
        normalized_dns: list[str] = []
        for index, raw_dns in enumerate(self.dns_servers):
            dns = _ipv4(raw_dns, f"PPU network dns_servers[{index}]")
            normalized_dns.append(str(dns))
        if len(set(normalized_dns)) != len(normalized_dns):
            raise _config_error("PPU network dns_servers must not contain duplicates")
        object.__setattr__(self, "dns_servers", tuple(normalized_dns))

        if self.mode == PPU_NETWORK_MODE_DHCP:
            if self.address is not None or self.prefix_length is not None or self.gateway is not None or normalized_dns:
                raise _config_error(
                    "DHCP mode must not include static address, prefix_length, gateway, or dns_servers"
                )
            return

        if isinstance(self.prefix_length, bool) or not isinstance(self.prefix_length, int):
            raise _config_error("Static PPU network prefix_length must be an integer")
        if not 1 <= self.prefix_length <= 32:
            raise _config_error("Static PPU network prefix_length must be 1..32")
        address = _host_address(self.address, self.prefix_length, "Static PPU network address")
        network = ipaddress.IPv4Network(f"{address}/{self.prefix_length}", strict=False)

        if self.gateway is not None:
            gateway = _host_address(self.gateway, self.prefix_length, "Static PPU network gateway")
            if gateway not in network:
                raise _config_error(
                    "Static PPU network gateway must be on the configured subnet",
                    context={"network": str(network), "gateway": str(gateway)},
                )
            if gateway == address:
                raise _config_error("Static PPU network gateway must not equal the PPU address")

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "interface": self.interface,
            "mode": self.mode,
            "address": self.address,
            "prefix_length": self.prefix_length,
            "gateway": self.gateway,
            "dns_servers": list(self.dns_servers),
        }


class PPUNetworkSettingsController:
    """Thread-safe desired-network state with fail-closed atomic persistence."""

    def __init__(self, persistence_path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self._persistence_path = Path(persistence_path).expanduser().resolve() if persistence_path else None
        self._settings = PPUNetworkSettings()
        if self._persistence_path is not None and self._persistence_path.is_file():
            self._settings = self._load(self._persistence_path)

    def snapshot(self) -> PPUNetworkSettings:
        with self._lock:
            return self._settings

    def current(self) -> dict[str, Any]:
        return self.snapshot().to_dict()

    def update(self, raw: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise _config_error("PPU network settings must be an object")
        expected = {"mode", "address", "prefix_length", "gateway", "dns_servers"}
        if set(raw) != expected:
            raise _config_error(
                "PPU network settings have invalid fields",
                context={
                    "unknown_fields": sorted(set(raw) - expected),
                    "missing_fields": sorted(expected - set(raw)),
                },
            )
        with self._lock:
            candidate = PPUNetworkSettings(
                revision=self._settings.revision + 1,
                mode=raw["mode"],
                address=raw["address"],
                prefix_length=raw["prefix_length"],
                gateway=raw["gateway"],
                dns_servers=raw["dns_servers"],
            )
            if self._persistence_path is not None:
                self._write_atomic(self._persistence_path, candidate)
            self._settings = candidate
            return candidate.to_dict()

    @staticmethod
    def _load(path: Path) -> PPUNetworkSettings:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise _config_error(f"cannot load PPU network settings: {path}") from exc
        expected = {
            "revision",
            "interface",
            "mode",
            "address",
            "prefix_length",
            "gateway",
            "dns_servers",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise _config_error("PPU network settings persistence fields are invalid")
        return PPUNetworkSettings(**raw)

    @staticmethod
    def _write_atomic(destination: Path, settings: PPUNetworkSettings) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(yaml.safe_dump(settings.to_dict(), sort_keys=False))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
