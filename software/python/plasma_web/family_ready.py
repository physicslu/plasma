"""Reviewed L3 PPU Family Ready derivations; never synthetic per-IC HIL passes.

The exact allowlist is intersected with canonical L2 SUPPORTED qualification in
ProgrammingQualificationRegistry. A shared programming guide or CFG alone never
qualifies an unreviewed order code, nor attests its physical package or Site.
"""
from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from .device_catalog import DeviceCatalogIntegrityError
from .runtime_evidence_root import default_runtime_evidence_root, source_files_available


MANIFEST_REL = "release/physical-compatibility/l3-family-ready-v1.json"
SCHEMA = "plasma.catalog.l3-family-ready.v1"


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise DeviceCatalogIntegrityError(f"L3 Family Ready: {reason}")


class FamilyReadyRegistry:
    """Explicit, version-locked exact ICPN inheritance from a real PPU HIL anchor."""

    def __init__(self, groups: list[dict[str, Any]], *, root: Path | None = None) -> None:
        self._entries: dict[tuple[str, str], dict[str, Any]] = {}
        self._anchors: dict[str, dict[str, Any]] = {}
        seen_groups: set[str] = set()
        for group in groups:
            _require(isinstance(group, dict), "group must be an object")
            group_id = group.get("group_id")
            manufacturer = group.get("manufacturer")
            series = group.get("series")
            anchor_id = group.get("anchor_configuration_id")
            guide = group.get("guide")
            provider = group.get("provider")
            profiles = group.get("profiles")
            _require(isinstance(group_id, str) and group_id and group_id not in seen_groups,
                     "missing or duplicate group ID")
            seen_groups.add(group_id)
            _require(all(isinstance(value, str) and value for value in (manufacturer, series, anchor_id)),
                     "manufacturer, series and physical HIL anchor required")
            _require(isinstance(guide, dict)
                     and all(isinstance(guide.get(field), str) and guide[field]
                             for field in ("document", "scope", "uri", "source_lock_sha256"))
                     and guide["uri"].startswith("https://")
                     and len(guide["source_lock_sha256"]) == 64
                     and all(c in "0123456789abcdef" for c in guide["source_lock_sha256"]),
                     "reviewed manufacturer guide URL and 64-character SHA256 lock required")
            _require(isinstance(provider, dict)
                     and all(isinstance(provider.get(field), str) and provider[field]
                             for field in ("provider_id", "version", "target_config", "flash_driver")),
                     "locked OpenOCD Provider, CFG and Driver required")
            _require(isinstance(profiles, list) and profiles, "at least one qualified Flash profile required")
            self._anchors[anchor_id] = {"group_id": group_id, "manufacturer": manufacturer,
                                        "series": series, "provider": deepcopy(provider)}
            for profile in profiles:
                _require(isinstance(profile, dict), "profile must be an object")
                profile_id = profile.get("programming_profile_id")
                erase_bytes = profile.get("erase_unit_bytes")
                guide_lock_key = profile.get("manufacturer_guide_source_lock_key")
                source_path = profile.get("manufacturer_source_lock_path")
                icpns = profile.get("exact_icpns")
                _require(isinstance(profile_id, str) and profile_id
                         and type(erase_bytes) is int and erase_bytes > 0
                         and isinstance(guide_lock_key, str) and guide_lock_key
                         and isinstance(source_path, str) and source_path.startswith("release/")
                         and not Path(source_path).is_absolute() and ".." not in Path(source_path).parts,
                         "profile identity, erase geometry and safe source lock path required")
                _require(isinstance(icpns, list) and icpns, "nonempty reviewed exact ICPN allowlist required")
                if root is not None:
                    try:
                        data = json.loads((root / source_path).read_text(encoding="utf-8"))
                        group_evidence = data["manufacturer_programming_group"]
                        source_lock = group_evidence["manufacturer_evidence"]["source_lock"][guide_lock_key]
                    except (OSError, ValueError, KeyError, TypeError) as exc:
                        raise DeviceCatalogIntegrityError("L3 Family Ready: missing/invalid manufacturer source lock") from exc
                    _require(source_lock == guide["source_lock_sha256"]
                             and group_evidence["manufacturer"] == manufacturer
                             and group_evidence["series"] == series
                             and group_evidence["manufacturer_evidence"]["programming_profile_id"] == profile_id
                             and group_evidence["shared_flash_geometry"]["erase_unit_bytes"] == erase_bytes
                             and data["provider"]["target_config"] == provider["target_config"]
                             and data["provider"]["flash_driver"] == provider["flash_driver"],
                             "manufacturer Programming Guide, Flash geometry or OpenOCD source lock drift")
                for icpn in icpns:
                    _require(isinstance(icpn, str) and icpn.startswith(series),
                             "allowlist ICPN must match reviewed series")
                    key = (manufacturer.casefold(), icpn.casefold())
                    _require(key not in self._entries, f"duplicate reviewed exact ICPN: {key}")
                    self._entries[key] = {
                        "evidence_origin": "FAMILY_DERIVED",
                        "group_id": group_id,
                        "anchor_configuration_id": anchor_id,
                        "manufacturer_guide": deepcopy(guide),
                        "provider": deepcopy(provider),
                        "programming_profile_id": profile_id,
                        "erase_unit_bytes": erase_bytes,
                        "limitations": [
                            "Family Ready is inferred from a separate exact ICPN's real PPU/Site HIL PASS, not a physical test of this exact ICPN.",
                            "Package/board wiring, current PPU/Site, runtime and supply require independent live safety admission.",
                            "No Socket or Adapter fixture qualification is inherited.",
                        ],
                    }

    def for_exact(self, manufacturer: str, icpn: str) -> dict[str, Any] | None:
        entry = self._entries.get((manufacturer.casefold(), icpn.casefold()))
        return deepcopy(entry) if entry is not None else None

    @property
    def exact_keys(self) -> set[tuple[str, str]]:
        return set(self._entries)

    @property
    def anchors(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._anchors)


@lru_cache(maxsize=1)
def get_default_family_ready_registry() -> FamilyReadyRegistry:
    root = default_runtime_evidence_root()
    if not source_files_available(root, (MANIFEST_REL,)):
        return FamilyReadyRegistry([])
    assert root is not None
    try:
        payload = json.loads((root / MANIFEST_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DeviceCatalogIntegrityError("L3 Family Ready manifest unavailable/invalid") from exc
    _require(isinstance(payload, dict) and payload.get("schema") == SCHEMA
             and isinstance(payload.get("family_groups"), list), "invalid manifest schema")
    return FamilyReadyRegistry(payload["family_groups"], root=root)
