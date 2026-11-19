"""Manager-only SQLite Selector read projection for an active published revision."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog_sqlite_repository import CatalogSqliteShadowRepository
from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError


def read_selector_view(
    database_path: str,
) -> tuple[DeviceCatalog, dict[tuple[str, str], dict[str, Any]], dict[str, int]]:
    if not isinstance(database_path, str) or not database_path.strip():
        raise DeviceCatalogIntegrityError("SQLite Selector database path is not configured")
    snapshot = CatalogSqliteShadowRepository(Path(database_path).expanduser()).read_active()
    qualifications = snapshot.qualifications
    if len(qualifications) != snapshot.catalog.size:
        raise DeviceCatalogIntegrityError("SQLite Selector requires a complete qualification snapshot")
    counts = {str(level): 0 for level in range(4)}
    level_names = ("DISCOVERED", "PROGRAMMING_CANDIDATE", "PROGRAMMABLE", "PLASMA_VERIFIED")
    for record in snapshot.catalog.records:
        key = (record.vendor.casefold(), record.identifier.casefold())
        projection = qualifications.get(key)
        if not isinstance(projection, dict):
            raise DeviceCatalogIntegrityError("SQLite Selector qualification identity missing")
        level = projection.get("catalog_level")
        if (type(level) is not int or level not in (0, 1, 2, 3)
                or projection.get("catalog_level_state") != level_names[level]):
            raise DeviceCatalogIntegrityError("SQLite Selector qualification invariant mismatch")
        if projection.get("data_only_publication"):
            CatalogSqliteShadowRepository._validate_publication(record, projection)
        elif (projection.get("execution_authorized") is not False
              or projection.get("job_selectable") is not (level >= 2)
              or (level >= 2 and projection.get("state") != "SUPPORTED")
              or (level == 3 and not (projection.get("ppu_ready") or projection.get("socket_ready")))):
            raise DeviceCatalogIntegrityError("SQLite Selector qualification invariant mismatch")
        counts[str(level)] += 1
    return snapshot.catalog, qualifications, counts
