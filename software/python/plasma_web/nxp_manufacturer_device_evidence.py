"""NXP manufacturer-only Device Evidence projection for the 212 admitted exact ICPNs.

This module is intentionally NOT a programming profile. Values remain
source-bound to the exact /part/ HTML evidence, with independent SHA locks.
Never derive I/O Supply/VDDA or infer shared Base Device from a SKU suffix.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .device_catalog import DeviceCatalogRecord

EVIDENCE_RELATIVE_PATH = Path("data/device-catalog/research/nxp-212-manufacturer-device-evidence-v5.csv")
EVIDENCE_GIT_BLOB_SHA = "541a62a9e6bf5a8c79436bd0e09ab1845394b964"
EXPECTED_EXACT_ROWS = 212
EXPECTED_FAMILIES = {"MCX": 196, "K32L2": 16}
FIELDS = (
    "icpn", "base_device", "base_device_evidence_state", "package",
    "pin_count", "flash", "ram", "operating_vdd", "io_supply",
    "vdda", "operating_temperature", "source_url", "source_html_sha256",
    "ram_evidence_state", "vdd_evidence_state", "io_supply_evidence_state",
    "vdda_evidence_state", "production_layer1_only",
    "programming_profile_qualified",
)
_RANGE_V = re.compile(r"^(\d+(?:\.\d+)?) to (\d+(?:\.\d+)?) V$")
_RANGE_C = re.compile(r"^(-?\d+) to (-?\d+) C$")
_RAM = re.compile(r"^(\d+(?:\.\d+)?) kB$")
_SHA = re.compile(r"^[a-f0-9]{64}$")


class NXPManufacturerDeviceEvidenceError(ValueError):
    """An exact NXP manufacturer/source binding is not trustworthy."""


def _require(ok: bool, why: str) -> None:
    if not ok:
        raise NXPManufacturerDeviceEvidenceError(why)


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class NXPManufacturerDeviceEvidence:
    """Exact-SKU read-only evidence. No additional Catalog or runtime identity."""

    def __init__(self, rows: dict[str, dict[str, str]]) -> None:
        self._rows = rows

    @property
    def size(self) -> int:
        return len(self._rows)

    @classmethod
    def from_file(cls, path: Path) -> "NXPManufacturerDeviceEvidence":
        try:
            original = path.read_bytes()
        except OSError as exc:
            raise NXPManufacturerDeviceEvidenceError(
                f"cannot load official NXP manufacturer evidence: {path}"
            ) from exc
        _require(_git_blob(original) == EVIDENCE_GIT_BLOB_SHA,
                 "NXP exact manufacturer evidence Git blob changed")
        try:
            reader = csv.DictReader(io.StringIO(original.decode("utf-8"), newline=""))
            _require(tuple(reader.fieldnames or ()) == FIELDS, "NXP evidence schema drift")
            source_rows = list(reader)
        except (UnicodeError, csv.Error) as exc:
            raise NXPManufacturerDeviceEvidenceError("malformed NXP source CSV") from exc
        _require(len(source_rows) == EXPECTED_EXACT_ROWS, "NXP 212-row evidence cardinality drift")
        rows: dict[str, dict[str, str]] = {}
        vdd_count = 0
        for entry in source_rows:
            sku = entry["icpn"]
            _require(sku and sku == sku.strip() and sku.casefold() not in rows,
                     f"duplicate/invalid exact manufacturer SKU: {sku}")
            _require(entry["base_device"] == sku and
                     entry["base_device_evidence_state"] == "exact_sku_singleton_not_manufacturer_base_verified",
                     f"{sku}: unsupported inferred Base Device grouping")
            _require(entry["package"] and entry["pin_count"].isdigit() and
                     int(entry["pin_count"]) > 0 and
                     entry["flash"] and _RAM.fullmatch(entry["flash"]) is not None and
                     _RAM.fullmatch(entry["ram"]) is not None,
                     f"{sku}: malformed exact Package/Pin/Flash/RAM evidence")
            _require(_RANGE_C.fullmatch(entry["operating_temperature"]) is not None,
                     f"{sku}: malformed ambient temperature")
            _require(entry["source_url"] == f"https://www.nxp.com/part/{sku}" and
                     _SHA.fullmatch(entry["source_html_sha256"]) is not None,
                     f"{sku}: official exact /part/ authority or SHA mismatch")
            _require(entry["ram_evidence_state"] ==
                     "independently_replayed_exact_manufacturer_html",
                     f"{sku}: RAM evidence does not meet original-source replay")
            _require(entry["io_supply"] == entry["vdda"] == "" and
                     entry["io_supply_evidence_state"] ==
                     entry["vdda_evidence_state"] == "not_individually_sourced",
                     f"{sku}: unsupported I/O or analog supply inference")
            _require(entry["production_layer1_only"] == "true" and
                     entry["programming_profile_qualified"] == "false",
                     f"{sku}: programming authority must remain false")
            voltage = entry["operating_vdd"]
            if voltage:
                match = _RANGE_V.fullmatch(voltage)
                _require(match is not None and float(match.group(1)) < float(match.group(2)) and
                         entry["vdd_evidence_state"] ==
                         "independently_replayed_exact_manufacturer_html",
                         f"{sku}: unqualified source voltage")
                vdd_count += 1
            else:
                _require(entry["vdd_evidence_state"] !=
                         "independently_replayed_exact_manufacturer_html",
                         f"{sku}: VDD missing but declared verified")
            rows[sku.casefold()] = entry
        _require(vdd_count == 208, "NXP voltage source completeness drift")
        return cls(rows)

    def resolve_exact(self, record: "DeviceCatalogRecord") -> dict[str, Any] | None:
        if record.vendor != "NXP" or record.family not in EXPECTED_FAMILIES:
            return None
        row = self._rows.get(record.identifier.casefold())
        if row is None:
            return None
        sku = row["icpn"]
        _require(record.identifier == sku and record.icpn == sku and record.production_admitted,
                 f"{sku}: not a Production-admitted exact manufacturer identity")
        _require(record.mapping_status == "no_mapping" and not record.target_config,
                 f"{sku}: this evidence cannot authorize a backend route")
        for label, observed, expected in (
            ("base_device", record.base_device, row["base_device"]),
            ("package", record.package, row["package"]),
            ("pin_count", record.pin_count, row["pin_count"]),
            ("flash_size", record.flash_size, row["flash"]),
            ("temperature_grade", record.temperature_grade, row["operating_temperature"]),
            ("source_authority", record.source_authority, row["source_url"]),
        ):
            _require(observed == expected, f"{sku}: Production Catalog {label} / manufacturer source drift")
        temperature = _RANGE_C.fullmatch(row["operating_temperature"])
        assert temperature is not None
        voltage = _RANGE_V.fullmatch(row["operating_vdd"]) if row["operating_vdd"] else None
        unknown = ["io_supply", "vdda"]
        if voltage is None:
            unknown.append("operating_vdd")
        _require(float(temperature.group(1)) < float(temperature.group(2)),
                 f"{sku}: inverted operating temperature")
        return {
            "schema_version": "1.0.0",
            "status": "manufacturer_device_partial_evidence",
            "profile_id": "nxp-exact-manufacturer-device-v5",
            "icpn": sku,
            "manufacturer": "NXP",
            "family": record.family,
            "base_device": row["base_device"],
            "base_device_evidence_state": row["base_device_evidence_state"],
            "package": row["package"],
            "pin_count": row["pin_count"],
            "flash_size": row["flash"],
            "ram_size": row["ram"],
            "operating_vdd_v": ({
                "min": float(voltage.group(1)),
                "max": float(voltage.group(2)),
            } if voltage else None),
            "io_supply_v": None,
            "vdda_v": None,
            "operating_temperature_c": {
                "min": int(temperature.group(1)),
                "max": int(temperature.group(2)),
            },
            "unknown_fields": unknown,
            "manufacturer_device_full_profile_complete": False,
            "evidence": {
                "authority": "NXP official",
                "source_surface": "nxp_exact_part_html",
                "exact_url": row["source_url"],
                "source_html_sha256": row["source_html_sha256"],
                "ram_evidence_state": row["ram_evidence_state"],
                "vdd_evidence_state": row["vdd_evidence_state"],
            },
            "programming_profile_authority": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }


@lru_cache(maxsize=1)
def get_default_nxp_manufacturer_device_evidence() -> NXPManufacturerDeviceEvidence:
    return NXPManufacturerDeviceEvidence.from_file(_root() / EVIDENCE_RELATIVE_PATH)
