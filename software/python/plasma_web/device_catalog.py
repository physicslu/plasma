from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable


DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100

_IDENTIFIER_KIND_PRIORITY = {
    "manufacturer_part_number": 0,
    "cmsis_device_name": 1,
    "ordering_pattern": 2,
    "family_alias": 3,
}


@dataclass(frozen=True, slots=True)
class DeviceCatalogRecord:
    vendor: str
    family: str
    subfamily: str | None
    plasma_series: str
    identifier: str
    identifier_kind: str
    cpu_architectures: tuple[str, ...]
    target_config: str
    openocd_distribution: str
    mapping_status: str
    validation_status: str
    catalog_origin: str

    @property
    def icpn(self) -> str | None:
        """Return an ICPN only when the source proves exact manufacturer part-number granularity."""
        return self.identifier if self.identifier_kind == "manufacturer_part_number" else None

    def to_payload(self) -> dict[str, object]:
        return {
            "vendor": self.vendor,
            "family": self.family,
            "subfamily": self.subfamily,
            "plasma_series": self.plasma_series,
            "identifier": self.identifier,
            "identifier_kind": self.identifier_kind,
            "icpn": self.icpn,
            "package": None,
            "cpu_architectures": list(self.cpu_architectures),
            "backend": {
                "type": "openocd",
                "distribution": self.openocd_distribution,
                "target_config": self.target_config,
                "mapping_status": self.mapping_status,
            },
            "physical_validation": {
                # The current canonical research catalog contains no PPU/Socket
                # configuration evidence. Do not infer physical support from an
                # OpenOCD mapping candidate.
                "engineering_status": self.validation_status,
                "ppu_status": "no_evidence",
                "socket_status": "no_evidence",
            },
            "catalog_origin": self.catalog_origin,
        }


class DeviceCatalog:
    """Read-only, part-number-first runtime view of the canonical device catalog."""

    def __init__(self, records: Iterable[DeviceCatalogRecord]) -> None:
        self._records = tuple(records)
        self._identity_index: dict[tuple[str, str], DeviceCatalogRecord] = {}
        for record in self._records:
            key = (record.vendor.casefold(), record.identifier.casefold())
            existing = self._identity_index.get(key)
            if existing is not None and existing != record:
                raise ValueError(
                    "device catalog identity must be unique by vendor + identifier: "
                    f"{record.vendor} / {record.identifier}"
                )
            self._identity_index[key] = record

    @property
    def size(self) -> int:
        return len(self._records)

    @classmethod
    def from_csv(cls, path: Path) -> "DeviceCatalog":
        records: list[DeviceCatalogRecord] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                raw_architectures = row.get("cpu_architectures", "[]")
                parsed_architectures = json.loads(raw_architectures)
                if not isinstance(parsed_architectures, list) or not all(
                    isinstance(item, str) for item in parsed_architectures
                ):
                    raise ValueError("cpu_architectures must be a JSON string array")
                identifier = row.get("part_number", "").strip()
                vendor = row.get("vendor", "").strip()
                family = row.get("family", "").strip()
                if not identifier or not vendor or not family:
                    raise ValueError("device catalog rows require vendor, family, and part_number")
                records.append(
                    DeviceCatalogRecord(
                        vendor=vendor,
                        family=family,
                        subfamily=row.get("subfamily", "").strip() or None,
                        plasma_series=row.get("plasma_series", "").strip(),
                        identifier=identifier,
                        identifier_kind=row.get("identifier_kind", "").strip(),
                        cpu_architectures=tuple(parsed_architectures),
                        target_config=row.get("target_config", "").strip(),
                        openocd_distribution=row.get("openocd_distribution", "").strip(),
                        mapping_status=row.get("mapping_status", "").strip(),
                        validation_status=row.get("validation_status", "").strip(),
                        catalog_origin=row.get("catalog_origin", "").strip(),
                    )
                )
        return cls(records)

    def resolve(self, vendor: str, identifier: str) -> DeviceCatalogRecord | None:
        """Resolve one canonical catalog identity without trusting browser-supplied metadata."""
        if not isinstance(vendor, str) or not isinstance(identifier, str):
            return None
        normalized_vendor = vendor.strip().casefold()
        normalized_identifier = identifier.strip().casefold()
        if not normalized_vendor or not normalized_identifier:
            return None
        return self._identity_index.get((normalized_vendor, normalized_identifier))

    def search(self, query: str, *, limit: int = DEFAULT_SEARCH_LIMIT) -> list[DeviceCatalogRecord]:
        normalized = query.strip().casefold()
        if not normalized:
            return []
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > MAX_SEARCH_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_SEARCH_LIMIT}")

        ranked: list[tuple[int, int, int, str, str, DeviceCatalogRecord]] = []
        for record in self._records:
            identifier = record.identifier.casefold()
            if identifier == normalized:
                match_rank = 0
            elif identifier.startswith(normalized):
                match_rank = 1
            elif normalized in identifier:
                match_rank = 2
            else:
                continue
            ranked.append(
                (
                    match_rank,
                    _IDENTIFIER_KIND_PRIORITY.get(record.identifier_kind, 99),
                    len(record.identifier),
                    record.identifier.casefold(),
                    record.vendor.casefold(),
                    record,
                )
            )

        ranked.sort(key=lambda item: item[:-1])
        return [item[-1] for item in ranked[:limit]]


def default_catalog_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "device-catalog" / "research" / "openocd-parts-canonical.csv"


@lru_cache(maxsize=1)
def get_default_device_catalog() -> DeviceCatalog:
    return DeviceCatalog.from_csv(default_catalog_path())
