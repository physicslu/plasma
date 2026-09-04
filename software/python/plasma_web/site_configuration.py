from __future__ import annotations

import os
import tempfile
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from plasma_core.config import PlasmaConfig, SiteConfig, load_config
from plasma_core.errors import ErrorCode, PlasmaError


SUPPORTED_SITE_INTERFACES = frozenset({"mock", "openocd", "fpga"})
SITE_DESIRED_FIELDS = frozenset({"enabled", "interface", "target"})
MAX_TARGET_LENGTH = 256


def _config_error(message: str, *, context: dict[str, Any] | None = None) -> PlasmaError:
    return PlasmaError(ErrorCode.CONFIG_INVALID, message, context=context or {})


def _site_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _config_error("site_id must be a positive integer starting at 1")
    return value


def _validated_values(raw: dict[str, Any]) -> tuple[bool, str, str]:
    if not isinstance(raw, dict):
        raise _config_error("Site desired configuration must be an object")
    if set(raw) != SITE_DESIRED_FIELDS:
        raise _config_error(
            "Site desired configuration has invalid fields",
            context={
                "unknown_fields": sorted(set(raw) - SITE_DESIRED_FIELDS),
                "missing_fields": sorted(SITE_DESIRED_FIELDS - set(raw)),
            },
        )

    enabled = raw["enabled"]
    interface = raw["interface"]
    target = raw["target"]
    if not isinstance(enabled, bool):
        raise _config_error("Site desired enabled must be a boolean")
    if not isinstance(interface, str) or interface not in SUPPORTED_SITE_INTERFACES:
        raise _config_error(
            "Site desired interface is unsupported",
            context={"interface": interface, "supported": sorted(SUPPORTED_SITE_INTERFACES)},
        )
    if (
        not isinstance(target, str)
        or not target
        or target != target.strip()
        or len(target) > MAX_TARGET_LENGTH
        or any(ord(character) < 0x20 for character in target)
    ):
        raise _config_error(
            f"Site desired target must be a non-empty trimmed string of at most {MAX_TARGET_LENGTH} characters"
        )
    return enabled, interface, target


def _site_dict(site: SiteConfig) -> dict[str, Any]:
    return {
        "site_id": site.id,
        "enabled": site.enabled,
        "interface": site.interface,
        "target": site.target,
    }


class SiteConfigurationController:
    """PPU-authoritative desired Site configuration persisted in canonical PPU YAML.

    Phase 1 deliberately does not mutate a running SiteManager. A successful write
    updates the canonical PPU configuration atomically; the Gateway reports desired
    and observed runtime state separately so the operator can see whether a Plasma
    Server restart is still required.
    """

    def __init__(self, config_path: str | Path) -> None:
        self._path = Path(config_path).expanduser().resolve()
        self._lock = threading.RLock()

    def current(self) -> dict[str, Any]:
        with self._lock:
            config = load_config(self._path)
            return {
                "source": "canonical_ppu_config",
                "sites": [_site_dict(site) for site in sorted(config.sites, key=lambda item: item.id)],
            }

    def update(self, site_id: int, raw: dict[str, Any]) -> dict[str, Any]:
        normalized_site_id = _site_id(site_id)
        enabled, interface, target = _validated_values(raw)

        with self._lock:
            document = self._load_document()
            config = load_config(self._path)
            existing = next((site for site in config.sites if site.id == normalized_site_id), None)
            if existing is None:
                raise PlasmaError(
                    ErrorCode.SITE_INVALID,
                    f"site does not exist: SITE{normalized_site_id}",
                )

            candidate_site = replace(
                existing,
                enabled=enabled,
                interface=interface,
                target=target,
            )
            candidate_sites = [
                candidate_site if site.id == normalized_site_id else site
                for site in config.sites
            ]
            PlasmaConfig(server=config.server, sites=candidate_sites, ppu=config.ppu).validate()

            raw_sites = document.get("sites")
            if not isinstance(raw_sites, list):
                raise _config_error("canonical PPU configuration sites must be an array")
            matching = [
                item
                for item in raw_sites
                if isinstance(item, dict) and item.get("id") == normalized_site_id
            ]
            if len(matching) != 1:
                raise _config_error(
                    "canonical PPU configuration Site identity is ambiguous",
                    context={"site_id": normalized_site_id, "matches": len(matching)},
                )
            matching[0].update(
                {
                    "enabled": enabled,
                    "interface": interface,
                    "target": target,
                }
            )
            self._write_atomic(document)
            # Re-load the persisted file instead of returning the candidate object so
            # the response proves the exact on-disk representation remains valid.
            return self.current()

    def _load_document(self) -> dict[str, Any]:
        try:
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise _config_error(f"cannot load canonical PPU configuration: {self._path.name}") from exc
        if not isinstance(raw, dict):
            raise _config_error("canonical PPU configuration root must be an object")
        return raw

    def _write_atomic(self, document: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.",
            suffix=".tmp",
            dir=self._path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(yaml.safe_dump(document, sort_keys=False))
                handle.flush()
                os.fsync(handle.fileno())
            # Validate exactly what is about to replace the canonical configuration.
            load_config(temporary)
            os.replace(temporary, self._path)
        finally:
            if temporary.exists():
                temporary.unlink()
