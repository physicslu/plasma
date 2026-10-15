"""Read-only, SHA-locked NXP Phase 1 IC Information projection for admitted ICPNs.

The 501-row v24 ledger is research evidence, NOT a source of selectable IDs.
Production Catalog controls which exact ICPNs may enter this projection.
No Phase 2 Programming / OpenOCD qualification or Phase 3 HIL is inferred.
"""
from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .device_catalog import DeviceCatalogRecord

LEDGER_RELATIVE_PATH = Path(
    "data/device-catalog/research/nxp-501-phase1-kl25-k32l2a-io-v24.csv"
)
LEDGER_GIT_BLOB = "6c595bc259b2c929d3f912639a7fa1f5a23d4b91"
SOURCE_SCHEMA_VERSION = 24
TOTAL_ROWS = 501
ADMITTED_ROWS = 224
RESEARCH_ONLY_ROWS = 277
ATTRIBUTES = ("ram", "working_vdd", "io_supply", "vdda")
STATES = ("VERIFIED", "PARTIAL", "UNKNOWN", "CONFLICT")
EXPECTED_ADMITTED_COUNTS = {
    "ram": {"VERIFIED": 199, "PARTIAL": 25, "UNKNOWN": 0, "CONFLICT": 0},
    "working_vdd": {"VERIFIED": 135, "PARTIAL": 27, "UNKNOWN": 62, "CONFLICT": 0},
    "io_supply": {"VERIFIED": 119, "PARTIAL": 16, "UNKNOWN": 89, "CONFLICT": 0},
    "vdda": {"VERIFIED": 135, "PARTIAL": 0, "UNKNOWN": 89, "CONFLICT": 0},
}
REQUIRED_FIELDS = (
    "icpn", "identity_state", "source_file", "source_file_git_blob",
    "manufacturer_uri", "base_device", "package", "pin_count", "flash",
    "temperature", "phase", "field_source_scope", "field_evidence_note",
    "document_uri", "document_revision", "document_page_evidence",
    "manufacturer_official_source_url_v21", "manufacturer_document_revision_v21",
    "manufacturer_document_page_v21", "mcxa1fs_source_url_v18",
    "mcxa3fs_source_url_v20", "operating_source_uri_v23",
    "operating_source_revision_v23", "operating_table_locator_v23",
    "io_reference_source_uri_v24", "io_reference_source_revision_v24",
    "io_reference_source_locator_v24",
    "k32l2b_source_primary_v22",
) + tuple(x for field in ATTRIBUTES for x in (field, field + "_state"))

class NXPPhase1InformationError(ValueError):
    """Phase 1 source or Production identity binding is not trustworthy."""


def _require(ok: bool, msg: str) -> None:
    if not ok:
        raise NXPPhase1InformationError(msg)


def _root() -> Path:
    # Phase 1 is repository-owned Research data, NOT part of the installed
    # Python wheel. The canonical Production manifest anchors the data tree.
    from .device_catalog import default_catalog_manifest_path

    return default_catalog_manifest_path().resolve().parents[3]


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _source_for(row: dict[str, str], field: str) -> tuple[str | None, str | None, str | None]:
    """Source is field-specific; do not suggest one datasheet proved everything."""
    if field == "io_supply" and row["io_reference_source_uri_v24"]:
        return (
            row["io_reference_source_uri_v24"],
            row["io_reference_source_revision_v24"],
            row["io_reference_source_locator_v24"],
        )
    if field in {"working_vdd", "io_supply", "vdda"} and row["operating_source_uri_v23"]:
        return (
            row["operating_source_uri_v23"],
            row["operating_source_revision_v23"],
            row["operating_table_locator_v23"],
        )
    if field == "ram":
        if row["manufacturer_official_source_url_v21"]:
            return (
                row["manufacturer_official_source_url_v21"],
                row["manufacturer_document_revision_v21"],
                row["manufacturer_document_page_v21"],
            )
        if row["mcxa3fs_source_url_v20"]:
            return row["mcxa3fs_source_url_v20"], None, None
        if row["mcxa1fs_source_url_v18"]:
            return row["mcxa1fs_source_url_v18"], None, None
        if row["k32l2b_source_primary_v22"]:
            return row["k32l2b_source_primary_v22"], None, None
    if row["document_uri"]:
        return row["document_uri"], row["document_revision"] or None, row["document_page_evidence"] or None
    # Original source authority may be the exact NXP /part/ page and not a datasheet.
    return row["manufacturer_uri"] or None, None, None


class NXPPhase1Information:
    """Immutable bounded research fields, joined ONLY to Production exact identities."""

    def __init__(self, rows: dict[str, dict[str, str]]) -> None:
        self._admitted = rows

    @property
    def size(self) -> int:
        return len(self._admitted)

    @classmethod
    def from_file(cls, path: Path) -> "NXPPhase1Information":
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise NXPPhase1InformationError(f"missing NXP Phase 1 v24 ledger: {path}") from exc
        _require(_git_blob(data) == LEDGER_GIT_BLOB, "NXP Phase 1 v24 Git blob changed")
        try:
            reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
            names = tuple(reader.fieldnames or ())
            _require(len(names) == len(set(names)) and all(n in names for n in REQUIRED_FIELDS),
                     "NXP Phase 1 v24 field schema changed")
            all_rows = list(reader)
        except (UnicodeError, csv.Error) as exc:
            raise NXPPhase1InformationError("malformed NXP Phase 1 evidence CSV") from exc
        _require(len(all_rows) == TOTAL_ROWS, "NXP Phase 1 v24 total count drift")
        seen: set[str] = set()
        admitted: dict[str, dict[str, str]] = {}
        counts = {x: Counter() for x in ATTRIBUTES}
        research_count = 0
        for row in all_rows:
            sku = row["icpn"]
            _require(bool(sku) and sku == sku.strip() and sku.casefold() not in seen,
                     f"duplicate/invalid Phase 1 exact ICPN {sku!r}")
            seen.add(sku.casefold())
            _require(row["phase"] == "1" and row["identity_state"] in {"ADMITTED", "RESEARCH_ONLY"},
                     f"{sku}: invalid phase/admission state")
            if row["identity_state"] == "RESEARCH_ONLY":
                research_count += 1
                continue
            _require(row["source_file"] and row["source_file_git_blob"]
                     and row["manufacturer_uri"] and row["package"] and row["pin_count"]
                     and row["flash"], f"{sku}: missing original exact manufacturer binding")
            for field in ATTRIBUTES:
                state = row[field + "_state"]
                _require(state in STATES, f"{sku}: invalid {field} evidence state")
                _require((state == "UNKNOWN") == (row[field] == ""),
                         f"{sku}: {field} value/state inconsistent")
                counts[field][state] += 1
            admitted[sku.casefold()] = row
        _require(research_count == RESEARCH_ONLY_ROWS and len(admitted) == ADMITTED_ROWS,
                 "NXP 501/224/277 Phase 1 cohort drift")
        _require(all(dict(counts[x]) == {k: v for k, v in EXPECTED_ADMITTED_COUNTS[x].items() if v}
                     for x in ATTRIBUTES), "NXP v24 Phase 1 evidence counts drift")
        return cls(admitted)

    def resolve_exact(self, record: "DeviceCatalogRecord") -> dict[str, Any] | None:
        if record.vendor != "NXP":
            return None
        row = self._admitted.get(record.identifier.casefold())
        if row is None:
            # Research-only SKUs must never acquire a Selector identity.
            return None
        sku = row["icpn"]
        _require(record.production_admitted and record.icpn == sku and record.identifier == sku,
                 f"{sku}: not a Production-admitted exact ICPN")
        for label, actual, expected in (
            ("base_device", record.base_device, row["base_device"]),
            ("package", record.package, row["package"]),
            ("pin_count", record.pin_count, row["pin_count"]),
            ("flash_size", record.flash_size, row["flash"]),
            ("temperature_grade", record.temperature_grade, row["temperature"]),
            ("source_authority", record.source_authority, row["manufacturer_uri"]),
        ):
            _require(actual == expected, f"{sku}: Production {label} / Phase 1 research drift")
        attrs: dict[str, dict[str, Any]] = {}
        for field in ATTRIBUTES:
            state = row[field + "_state"]
            source_url, revision, locator = _source_for(row, field)
            value = row[field] or None
            attrs[field] = {
                "value": value, "unit": (row.get(field + "_unit") or None),
                "state": state, "source_url": source_url if value else None,
                "source_revision": revision if value else None,
                "source_locator": locator if value else None,
            }
        return {
            "schema_version": SOURCE_SCHEMA_VERSION,
            "icpn": sku,
            "manufacturer": "NXP",
            "scope": "research_field_evidence_only",
            "fields": attrs,
            "original_manufacturer_pdf_binary_sha256_qualified": False,
            "catalog_admission_changed": False,
            "software_programming_qualified": False,
            "physical_programming_qualified": False,
        }


@lru_cache(maxsize=1)
def get_default_nxp_phase1_information() -> NXPPhase1Information:
    return NXPPhase1Information.from_file(_root() / LEDGER_RELATIVE_PATH)
