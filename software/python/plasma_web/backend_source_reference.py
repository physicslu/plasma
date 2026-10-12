"""Read-only source-reference presentation, never backend execution admission.

A pinned source release is not an installed runtime. Absence of a release file
in a slim PPU kit returns no source version; corrupted present metadata fails
closed and never manufactures a version, runtime SHA or programming claim.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .device_catalog import DeviceCatalogIntegrityError, DeviceCatalogRecord

ROOT = Path(__file__).resolve().parents[3]
UPSTREAM_RELEASE = "release/openocd.json"
_ST_REPO = "https://github.com/STMicroelectronics/OpenOCD.git"


def load_pinned_upstream(root: Path = ROOT) -> dict[str, Any] | None:
    file = root / UPSTREAM_RELEASE
    try:
        payload = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None  # Slim PPU bundle: cannot claim source version.
    except (OSError, UnicodeError, ValueError) as exc:
        raise DeviceCatalogIntegrityError("pinned OpenOCD release authority is unreadable") from exc
    if not isinstance(payload, dict):
        raise DeviceCatalogIntegrityError("pinned OpenOCD release must be an object")
    commit = payload.get("source_commit")
    version = payload.get("version")
    if (payload.get("schema_version") != 1
            or payload.get("engine") != "openocd"
            or payload.get("source_repository") != "https://github.com/openocd-org/openocd.git"
            or not isinstance(commit, str) or re.fullmatch("[a-f0-9]{40}", commit) is None
            or not isinstance(version, str) or re.fullmatch(r"\d+\.\d+\.\d+", version) is None
            or payload.get("runtime_id") != f"{version}-{commit[:12]}"
            or payload.get("hardware_runtime_ready") is not False):
        raise DeviceCatalogIntegrityError("pinned OpenOCD source authority is inconsistent")
    return {
        "provider_id": "openocd-upstream",
        "provider_name": "Upstream OpenOCD",
        "source_repository": payload["source_repository"],
        "source_version": version,
        "source_commit": commit,
        "pinned_release_runtime_id": payload["runtime_id"],
        "installed_runtime_id": None,
        "installed_binary_sha256": None,
        "evidence_scope": "catalog_mapping_only",
        "hardware_runtime_ready": False,
        "physical_programming_qualified": False,
    }


@lru_cache(maxsize=1)
def default_pinned_upstream() -> dict[str, Any] | None:
    return load_pinned_upstream()


def backend_source_reference(
    row: DeviceCatalogRecord,
    candidate: dict[str, Any] | None,
    upstream: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """The source reference is *not* a runtime selection or executable provider."""
    if not row.production_admitted or row.identifier_kind != "manufacturer_part_number":
        return None
    if row.mapping_status == "mapped":
        if row.openocd_distribution != "upstream-openocd" or not row.target_config:
            raise DeviceCatalogIntegrityError("mapped catalog row has unsupported source provider")
        # Slim installs omit release/openocd.json; backend source is still
        # identifiable but the exact source version is NOT attested.
        return {
            "provider_id": "openocd-upstream",
            "provider_name": "Upstream OpenOCD",
            "mapping_status": "mapped",
            "target_config": row.target_config,
            "flash_driver": None,
            "source_repository": upstream["source_repository"] if upstream else None,
            "source_version": upstream["source_version"] if upstream else None,
            "source_commit": upstream["source_commit"] if upstream else None,
            "pinned_release_runtime_id": upstream["pinned_release_runtime_id"] if upstream else None,
            "installed_runtime_id": None,
            "installed_binary_sha256": None,
            "evidence_scope": "catalog_mapping_only",
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }
    if row.mapping_status != "no_mapping" or candidate is None:
        return None
    if (candidate.get("status") != "research_only"
            or candidate.get("production_mapping_status") != "no_mapping"
            or candidate.get("family") != row.family
            or candidate.get("source_repository") != _ST_REPO
            or candidate.get("executable") is not False
            or candidate.get("production_binding_authorized") is not False
            or candidate.get("hardware_runtime_ready") is not False):
        raise DeviceCatalogIntegrityError("research candidate source reference is not safely bounded")
    commit = candidate.get("source_commit")
    if not isinstance(commit, str) or re.fullmatch("[a-f0-9]{40}", commit) is None:
        raise DeviceCatalogIntegrityError("candidate source commit is invalid")
    return {
        "provider_id": candidate["provider_id"],
        "provider_name": "ST OpenOCD",
        "mapping_status": "candidate",
        "target_config": candidate["target_config_source_path"],
        "flash_driver": candidate["flash_driver"],
        "source_repository": candidate["source_repository"],
        "source_version": None,  # A source commit is not an installed executable version.
        "source_commit": commit,
        "pinned_release_runtime_id": None,
        "installed_runtime_id": None,
        "installed_binary_sha256": None,
        "evidence_scope": "source_pinned_research_only",
        "hardware_runtime_ready": False,
        "physical_programming_qualified": False,
    }
