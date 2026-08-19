from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml


class ManagerConfigError(ValueError):
    """Raised when Plasma Manager configuration is invalid."""


@dataclass(frozen=True, slots=True)
class PPURegistryEntry:
    endpoint: str
    alias: str | None = None


@dataclass(frozen=True, slots=True)
class ManagerConfig:
    host: str = "127.0.0.1"
    port: int = 18180
    request_timeout_s: float = 2.0
    poll_interval_s: float = 2.0
    ppus: tuple[PPURegistryEntry, ...] = ()


def normalize_endpoint(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManagerConfigError("PPU endpoint must be a non-empty HTTP(S) URL")
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname is None:
        raise ManagerConfigError("PPU endpoint must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ManagerConfigError("PPU endpoint must not embed credentials")
    if parsed.query or parsed.fragment:
        raise ManagerConfigError("PPU endpoint must not contain query parameters or fragments")
    if parsed.path not in {"", "/"}:
        raise ManagerConfigError("PPU endpoint must identify the Gateway root, not a nested path")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _registry_entry(raw: Any) -> PPURegistryEntry:
    if not isinstance(raw, dict):
        raise ManagerConfigError("each ppus entry must be a mapping")
    unexpected = set(raw) - {"endpoint", "alias"}
    if unexpected:
        raise ManagerConfigError(f"unsupported PPU registry fields: {', '.join(sorted(unexpected))}")
    endpoint = normalize_endpoint(raw.get("endpoint"))
    alias = raw.get("alias")
    if alias is not None:
        if not isinstance(alias, str) or not alias.strip() or len(alias.strip()) > 128:
            raise ManagerConfigError("PPU alias must be 1-128 characters")
        alias = alias.strip()
    return PPURegistryEntry(endpoint=endpoint, alias=alias)


def load_manager_config(path: str | Path) -> ManagerConfig:
    config_path = Path(path).resolve()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ManagerConfigError(f"cannot load Plasma Manager configuration: {config_path}") from exc
    if not isinstance(raw, dict):
        raise ManagerConfigError("Plasma Manager configuration root must be a mapping")

    unexpected_root = set(raw) - {"manager", "ppus"}
    if unexpected_root:
        raise ManagerConfigError(
            f"unsupported Plasma Manager configuration fields: {', '.join(sorted(unexpected_root))}"
        )

    manager_raw = raw.get("manager", {})
    if not isinstance(manager_raw, dict):
        raise ManagerConfigError("manager must be a mapping")
    unexpected_manager = set(manager_raw) - {
        "host",
        "port",
        "request_timeout_s",
        "poll_interval_s",
    }
    if unexpected_manager:
        raise ManagerConfigError(
            f"unsupported manager fields: {', '.join(sorted(unexpected_manager))}"
        )

    host = manager_raw.get("host", "127.0.0.1")
    port = manager_raw.get("port", 18180)
    request_timeout_s = manager_raw.get("request_timeout_s", 2.0)
    poll_interval_s = manager_raw.get("poll_interval_s", 2.0)
    if not isinstance(host, str) or not host.strip():
        raise ManagerConfigError("manager.host must be a non-empty string")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ManagerConfigError("manager.port must be an integer in range 1..65535")
    if isinstance(request_timeout_s, bool) or not isinstance(request_timeout_s, (int, float)):
        raise ManagerConfigError("manager.request_timeout_s must be numeric")
    request_timeout_s = float(request_timeout_s)
    if not 0 < request_timeout_s <= 60:
        raise ManagerConfigError("manager.request_timeout_s must be in range (0, 60]")
    if isinstance(poll_interval_s, bool) or not isinstance(poll_interval_s, (int, float)):
        raise ManagerConfigError("manager.poll_interval_s must be numeric")
    poll_interval_s = float(poll_interval_s)
    if not 0.1 <= poll_interval_s <= 300:
        raise ManagerConfigError("manager.poll_interval_s must be in range [0.1, 300]")

    ppus_raw = raw.get("ppus", [])
    if not isinstance(ppus_raw, list):
        raise ManagerConfigError("ppus must be a list")
    ppus = tuple(_registry_entry(item) for item in ppus_raw)
    endpoints = [entry.endpoint for entry in ppus]
    if len(endpoints) != len(set(endpoints)):
        raise ManagerConfigError("PPU endpoints must be unique")

    return ManagerConfig(
        host=host.strip(),
        port=port,
        request_timeout_s=request_timeout_s,
        poll_interval_s=poll_interval_s,
        ppus=ppus,
    )
