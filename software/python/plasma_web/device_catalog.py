from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable


DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100
DEVICE_CATALOG_MANIFEST_ENV = "PLASMA_DEVICE_CATALOG_MANIFEST"
DEVICE_CATALOG_PATH_ENV = "PLASMA_DEVICE_CATALOG_PATH"  # legacy; never used by the production loader
PRODUCTION_MANIFEST_RELATIVE_PATH = Path("data/device-catalog/production/icpn-v1-manifest.json")
MANIFEST_SCHEMA_VERSION = 1
PRODUCTION_SELECTION_POLICY = "admitted_exact_manufacturer_part_number_only"

ADMITTED_CANONICAL_FIELDS = (
    "manufacturer",
    "icpn",
    "family",
    "series",
    "base_device",
    "package",
    "pin_count",
    "flash_size",
    "temperature_grade",
    "option_suffix",
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
    "source_type",
    "source_reference",
    "source_authority",
    "verification_status",
)

_IDENTIFIER_KIND_PRIORITY = {
    "manufacturer_part_number": 0,
    "cmsis_device_name": 1,
    "ordering_pattern": 2,
    "family_alias": 3,
}


class DeviceCatalogIntegrityError(RuntimeError):
    """The production Device Catalog cannot be trusted or loaded."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git object identity, not a security primitive


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    package: str | None = None
    pin_count: str | None = None
    flash_size: str | None = None
    temperature_grade: str | None = None
    option_suffix: str | None = None
    base_device: str | None = None
    mapping_method: str | None = None
    source_type: str | None = None
    source_reference: str | None = None
    source_authority: str | None = None
    verification_status: str | None = None
    catalog_version: str | None = None
    catalog_revision_sha256: str | None = None
    production_admitted: bool = False

    @property
    def icpn(self) -> str | None:
        """Return an ICPN only when exact manufacturer part-number granularity is admitted."""
        return self.identifier if self.identifier_kind == "manufacturer_part_number" else None

    def to_payload(self) -> dict[str, object]:
        physical_engineering_status = "no_evidence" if self.production_admitted else self.validation_status
        return {
            "vendor": self.vendor,
            "family": self.family,
            "subfamily": self.subfamily,
            "plasma_series": self.plasma_series,
            "identifier": self.identifier,
            "identifier_kind": self.identifier_kind,
            "icpn": self.icpn,
            "package": self.package,
            "pin_count": self.pin_count,
            "flash_size": self.flash_size,
            "temperature_grade": self.temperature_grade,
            "option_suffix": self.option_suffix,
            "base_device": self.base_device,
            "cpu_architectures": list(self.cpu_architectures),
            "backend": {
                "type": "openocd",
                "distribution": self.openocd_distribution,
                "target_config": self.target_config,
                "mapping_status": self.mapping_status,
                "mapping_method": self.mapping_method,
            },
            "catalog_verification": {
                "status": self.verification_status,
                "source_type": self.source_type,
                "source_authority": self.source_authority,
                "source_reference": self.source_reference,
            },
            "physical_validation": {
                # Exact commercial identity + OpenOCD mapping do not prove
                # physical PPU/socket support. Keep these domains separate.
                "engineering_status": physical_engineering_status,
                "ppu_status": "no_evidence",
                "socket_status": "no_evidence",
            },
            "catalog": {
                "scope": "production_admitted" if self.production_admitted else "explicit_legacy",
                "version": self.catalog_version,
                "revision_sha256": self.catalog_revision_sha256,
            },
            "catalog_origin": self.catalog_origin,
        }


class DeviceCatalog:
    """Read-only runtime catalog. Production instances contain admitted exact ICPNs only."""

    def __init__(
        self,
        records: Iterable[DeviceCatalogRecord],
        *,
        catalog_id: str = "explicit-device-catalog",
        catalog_version: str = "explicit",
        status: str = "explicit",
        revision_sha256: str | None = None,
        source_count: int = 1,
    ) -> None:
        self._records = tuple(records)
        self.catalog_id = catalog_id
        self.catalog_version = catalog_version
        self.status = status
        self.revision_sha256 = revision_sha256
        self.source_count = source_count

    @property
    def size(self) -> int:
        return len(self._records)

    @property
    def records(self) -> tuple[DeviceCatalogRecord, ...]:
        return self._records

    @property
    def metadata(self) -> dict[str, object]:
        vendors: dict[str, Counter[str]] = {}
        for record in self._records:
            vendors.setdefault(record.vendor, Counter())[record.family] += 1
        taxonomy = [
            {
                "vendor": vendor,
                "count": sum(families.values()),
                "families": [
                    {"family": family, "count": count}
                    for family, count in sorted(families.items())
                ],
            }
            for vendor, families in sorted(vendors.items())
        ]
        return {
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "catalog_status": self.status,
            "catalog_revision_sha256": self.revision_sha256,
            "catalog_size": self.size,
            "source_count": self.source_count,
            "taxonomy": taxonomy,
        }

    @classmethod
    def from_csv(cls, path: Path) -> "DeviceCatalog":
        """Load one explicit CSV for tests/tools; default production loading uses from_manifest()."""
        data = path.read_bytes()
        header = next(csv.reader(io.StringIO(data.decode("utf-8"))), [])
        if tuple(header) == ADMITTED_CANONICAL_FIELDS:
            records = _parse_admitted_source(
                data,
                origin=str(path),
                catalog_version="explicit-admitted",
                catalog_revision_sha256=_sha256(data),
            )
            return cls(
                records,
                catalog_id="explicit-admitted",
                catalog_version="explicit-admitted",
                status="explicit",
                revision_sha256=_sha256(data),
            )
        return cls(_parse_legacy_source(data, origin=str(path)))

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> "DeviceCatalog":
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DeviceCatalogIntegrityError(f"cannot read production Device Catalog manifest: {manifest_path}") from exc
        if not isinstance(manifest, dict):
            raise DeviceCatalogIntegrityError("production Device Catalog manifest must be an object")
        if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise DeviceCatalogIntegrityError("unsupported production Device Catalog manifest schema_version")
        catalog_id = manifest.get("catalog_id")
        catalog_version = manifest.get("catalog_version")
        status = manifest.get("status")
        if not isinstance(catalog_id, str) or not catalog_id:
            raise DeviceCatalogIntegrityError("production Device Catalog manifest requires catalog_id")
        if not isinstance(catalog_version, str) or not catalog_version:
            raise DeviceCatalogIntegrityError("production Device Catalog manifest requires catalog_version")
        if status != "production":
            raise DeviceCatalogIntegrityError("production Device Catalog manifest status must be production")
        if manifest.get("selection_policy") != PRODUCTION_SELECTION_POLICY:
            raise DeviceCatalogIntegrityError("production Device Catalog selection_policy is not exact-ICPN-only")
        raw_sources = manifest.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise DeviceCatalogIntegrityError("production Device Catalog manifest requires sources")

        all_records: list[DeviceCatalogRecord] = []
        source_digests: list[tuple[str, str]] = []
        seen_keys: set[tuple[str, str]] = set()
        for index, raw_source in enumerate(raw_sources, start=1):
            if not isinstance(raw_source, dict):
                raise DeviceCatalogIntegrityError(f"catalog source {index} must be an object")
            manufacturer = raw_source.get("manufacturer")
            family = raw_source.get("family")
            relative_path = raw_source.get("path")
            expected_rows = raw_source.get("row_count")
            expected_blob = raw_source.get("git_blob_sha")
            if not all(isinstance(value, str) and value for value in (manufacturer, family, relative_path, expected_blob)):
                raise DeviceCatalogIntegrityError(f"catalog source {index} has invalid identity fields")
            if isinstance(expected_rows, bool) or not isinstance(expected_rows, int) or expected_rows < 1:
                raise DeviceCatalogIntegrityError(f"catalog source {index} has invalid row_count")

            source_path = (manifest_path.parent / relative_path).resolve()
            try:
                data = source_path.read_bytes()
            except OSError as exc:
                raise DeviceCatalogIntegrityError(f"cannot read admitted catalog source: {source_path}") from exc
            actual_blob = _git_blob_sha(data)
            if actual_blob != expected_blob:
                raise DeviceCatalogIntegrityError(
                    f"admitted catalog source Git blob mismatch: {relative_path} expected={expected_blob} actual={actual_blob}"
                )
            source_sha256 = _sha256(data)
            source_digests.append((relative_path, source_sha256))
            records = _parse_admitted_source(
                data,
                origin=relative_path,
                expected_manufacturer=manufacturer,
                expected_family=family,
                catalog_version=catalog_version,
            )
            if len(records) != expected_rows:
                raise DeviceCatalogIntegrityError(
                    f"admitted catalog source row_count mismatch: {relative_path} expected={expected_rows} actual={len(records)}"
                )
            for record in records:
                key = (record.vendor.casefold(), record.identifier.casefold())
                if key in seen_keys:
                    raise DeviceCatalogIntegrityError(f"duplicate admitted ICPN across production sources: {record.identifier}")
                seen_keys.add(key)
            all_records.extend(records)

        revision_input = json.dumps(source_digests, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        revision_sha256 = _sha256(revision_input)
        all_records = [
            DeviceCatalogRecord(
                **{
                    field: getattr(record, field)
                    for field in DeviceCatalogRecord.__dataclass_fields__
                    if field not in {"catalog_revision_sha256"}
                },
                catalog_revision_sha256=revision_sha256,
            )
            for record in all_records
        ]
        all_records.sort(key=lambda record: (record.vendor.casefold(), record.family.casefold(), record.identifier.casefold()))
        return cls(
            all_records,
            catalog_id=catalog_id,
            catalog_version=catalog_version,
            status=status,
            revision_sha256=revision_sha256,
            source_count=len(raw_sources),
        )

    def resolve(
        self,
        vendor: str,
        identifier: str,
        *,
        target_config: str | None = None,
    ) -> DeviceCatalogRecord | None:
        """Resolve one server-owned catalog identity without trusting browser display metadata."""
        if not isinstance(vendor, str) or not isinstance(identifier, str):
            return None
        normalized_vendor = vendor.strip().casefold()
        normalized_identifier = identifier.strip().casefold()
        normalized_target = target_config.strip().casefold() if isinstance(target_config, str) else None
        if not normalized_vendor or not normalized_identifier:
            return None
        matches = [
            record
            for record in self._records
            if record.vendor.casefold() == normalized_vendor
            and record.identifier.casefold() == normalized_identifier
            and (normalized_target is None or record.target_config.casefold() == normalized_target)
        ]
        return matches[0] if len(matches) == 1 else None

    def search(self, query: str, *, limit: int = DEFAULT_SEARCH_LIMIT) -> list[DeviceCatalogRecord]:
        normalized = query.strip().casefold()
        if not normalized:
            return []
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > MAX_SEARCH_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_SEARCH_LIMIT}")
        tokens = normalized.split()
        ranked: list[tuple[int, int, int, str, str, DeviceCatalogRecord]] = []
        for record in self._records:
            identifier = record.identifier.casefold()
            taxonomy = " ".join(
                value.casefold()
                for value in (
                    record.vendor,
                    record.family,
                    record.subfamily or "",
                    record.plasma_series,
                    record.base_device or "",
                    record.package or "",
                )
            )
            searchable = f"{identifier} {taxonomy}"
            if not all(token in searchable for token in tokens):
                continue
            if identifier == normalized:
                match_rank = 0
            elif identifier.startswith(normalized):
                match_rank = 1
            elif normalized in identifier:
                match_rank = 2
            elif normalized in taxonomy:
                match_rank = 3
            else:
                match_rank = 4
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


def _parse_admitted_source(
    data: bytes,
    *,
    origin: str,
    expected_manufacturer: str | None = None,
    expected_family: str | None = None,
    catalog_version: str | None = None,
    catalog_revision_sha256: str | None = None,
) -> list[DeviceCatalogRecord]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DeviceCatalogIntegrityError(f"admitted catalog source is not UTF-8: {origin}") from exc
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != ADMITTED_CANONICAL_FIELDS:
        raise DeviceCatalogIntegrityError(f"admitted catalog source schema mismatch: {origin}")
    records: list[DeviceCatalogRecord] = []
    for row_number, row in enumerate(reader, start=2):
        manufacturer = (row.get("manufacturer") or "").strip()
        icpn = (row.get("icpn") or "").strip()
        family = (row.get("family") or "").strip()
        series = (row.get("series") or "").strip()
        base_device = (row.get("base_device") or "").strip()
        target_config = (row.get("openocd_target_config") or "").strip()
        mapping_method = (row.get("mapping_status") or "").strip()
        source_reference = (row.get("source_reference") or "").strip()
        source_authority = (row.get("source_authority") or "").strip()
        source_type = (row.get("source_type") or "").strip()
        verification_status = (row.get("verification_status") or "").strip()
        if not all((manufacturer, icpn, family, series, base_device, target_config, mapping_method)):
            raise DeviceCatalogIntegrityError(f"{origin}:{row_number}: admitted ICPN row has empty required identity/mapping field")
        if expected_manufacturer is not None and manufacturer != expected_manufacturer:
            raise DeviceCatalogIntegrityError(f"{origin}:{row_number}: manufacturer does not match manifest")
        if expected_family is not None and family != expected_family:
            raise DeviceCatalogIntegrityError(f"{origin}:{row_number}: family does not match manifest")
        if not source_reference or not source_authority or not source_type or not verification_status.startswith("verified_"):
            raise DeviceCatalogIntegrityError(f"{origin}:{row_number}: admitted ICPN lacks authoritative verification provenance")
        records.append(
            DeviceCatalogRecord(
                vendor=manufacturer,
                family=family,
                subfamily=series,
                plasma_series=family,
                identifier=icpn,
                identifier_kind="manufacturer_part_number",
                cpu_architectures=(),
                target_config=target_config,
                openocd_distribution="upstream-openocd",
                mapping_status="mapped",
                validation_status="no_evidence",
                catalog_origin=origin,
                package=(row.get("package") or "").strip() or None,
                pin_count=(row.get("pin_count") or "").strip() or None,
                flash_size=(row.get("flash_size") or "").strip() or None,
                temperature_grade=(row.get("temperature_grade") or "").strip() or None,
                option_suffix=(row.get("option_suffix") or "").strip() or None,
                base_device=base_device,
                mapping_method=mapping_method,
                source_type=source_type,
                source_reference=source_reference,
                source_authority=source_authority,
                verification_status=verification_status,
                catalog_version=catalog_version,
                catalog_revision_sha256=catalog_revision_sha256,
                production_admitted=True,
            )
        )
    return records


def _parse_legacy_source(data: bytes, *, origin: str) -> list[DeviceCatalogRecord]:
    """Compatibility parser for explicit tests/tools only. Production never calls this path."""
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
        records: list[DeviceCatalogRecord] = []
        for row in reader:
            raw_architectures = row.get("cpu_architectures", "[]")
            parsed_architectures = json.loads(raw_architectures)
            if not isinstance(parsed_architectures, list) or not all(isinstance(item, str) for item in parsed_architectures):
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
                    catalog_origin=row.get("catalog_origin", "").strip() or origin,
                )
            )
        return records
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid explicit legacy Device Catalog: {origin}") from exc


def default_catalog_manifest_path() -> Path:
    configured = os.environ.get(DEVICE_CATALOG_MANIFEST_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return _repository_root() / PRODUCTION_MANIFEST_RELATIVE_PATH


def default_catalog_path() -> Path:
    """Deprecated explicit CSV helper retained for tooling/tests; not used by get_default_device_catalog()."""
    configured = os.environ.get(DEVICE_CATALOG_PATH_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return _repository_root() / "data" / "device-catalog" / "research" / "openocd-parts-canonical.csv"


@lru_cache(maxsize=1)
def get_default_device_catalog() -> DeviceCatalog:
    return DeviceCatalog.from_manifest(default_catalog_manifest_path())


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate and inspect the Plasma production ICPN catalog")
    parser.add_argument("--manifest", type=Path, default=default_catalog_manifest_path())
    parser.add_argument("--json", action="store_true", help="Print metadata as JSON")
    args = parser.parse_args(argv)
    try:
        catalog = DeviceCatalog.from_manifest(args.manifest)
    except DeviceCatalogIntegrityError as exc:
        print(f"Device Catalog validation failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(catalog.metadata, indent=2, sort_keys=True))
    else:
        print(
            f"Device Catalog PASS: {catalog.catalog_id} v{catalog.catalog_version} "
            f"rows={catalog.size} revision={catalog.revision_sha256}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
