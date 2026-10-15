"""Read-only NXP Phase 1 IDENTIFIED IC Selector search projection.

Keep the Production manifest, admission and execution resolution unchanged.
Only exact, source-locked, previously reviewed official NXP material rows are
projected. No research candidates and no inference of Phase 2 SUPPORTED.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, DeviceCatalogRecord, _repository_root

RESEARCH = Path("data/device-catalog/research")
SOURCE_BLOBS = (
    ("nxp-8-lpc82x-official-phase1-observations-v1.csv", "449a3a6cb5e98ff1edef8ea2bb6a065ef8482528", 8),
    ("nxp-8-lpc81x-phase1-official-material-v1.csv", "2d94cdc9506b336dc580a178d3309dea6c1d8c63", 8),
    ("nxp-11-lpc11u-lpc83x-phase1-official-material-v1.csv", "0a90ceb12dde7e37fbee0e1ede0f230bea0891f5", 11),
    ("nxp-25-lpc-exact-material-12nc-phase1-v1.csv", "31d3fd024c01ff21db0534a5522fc0fbedf88890", 25),
    ("nxp-21-k40-k60-kl4x-official-materials-phase1-v1.csv", "d11788fb5b210bd3b3ed06807f922c3ac1e2f8a0", 21),
)
EXPECTED_NEW_IDENTIFIED = 73
PHASE1_CATALOG_ORIGIN = "nxp_phase1_identified_official_material"
OFFICIAL_SOURCE_TYPE = "official_nxp_exact_material_12nc"
_ALLOWED_URI = "https://www.nxp.com/"

def _check(ok: bool, message: str) -> None:
    if not ok:
        raise DeviceCatalogIntegrityError("NXP Phase1 selector: " + message)

def _read_locked_sources(root: Path) -> list[tuple[str, dict[str, str]]]:
    combined: list[tuple[str, dict[str, str]]] = []
    for filename, expected_git_sha, expected_rows in SOURCE_BLOBS:
        path = root / RESEARCH / filename
        raw = path.read_bytes()  # no network or heuristic fallback
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        _check(actual == expected_git_sha, "source Git blob changed: " + filename)
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
        _check(len(rows) == expected_rows and not any(None in r for r in rows),
               "source identity row count/schema changed: " + filename)
        combined.extend((filename, row) for row in rows)
    _check(len(combined) == EXPECTED_NEW_IDENTIFIED, "source identity total drift")
    return combined

def _extract(filename: str, row: dict[str, str]) -> tuple[str, str, str, str, str, str | None, str | None, str, str]:
    """Return verified material, 12NC, NXP family/base, package, optional
    pins/Flash and primary official URI. Values are not suffix-inferred."""
    icpn = row["icpn"]
    nc = row["manufacturer_12nc"]
    if filename.startswith("nxp-8-lpc82x-"):
        _check(all(row[k] == "false" for k in (
            "openocd_programming_qualified", "production_admitted",
            "physical_hil_verified", "original_material_html_binary_archived")),
            "LPC82x is not independently qualified for execution or original bytes")
        _check(row["manufacturer_material_status"] == "Active", "LPC82x manufacturer material status")
        family, base, pkg = "LPC82x", row["datasheet_base"], row["nxp_product_package_alias"]
        pins, flash, uri = None, row["flash_kb"], row["manufacturer_material_url"]
    elif filename.startswith("nxp-8-lpc81x-"):
        _check(all(row[k] == "false" for k in (
            "programming_qualified", "production_admitted",
            "physical_hil_verified", "original_manufacturer_html_bytes_archived")),
            "LPC81x is not independently qualified for execution or original bytes")
        _check(row["manufacturer_status"] == "Active", "LPC81x manufacturer material status")
        family, base, pkg = "LPC81x", row["manufacturer_base"], row["package"]
        pins, flash, uri = row["terminal_count"], row["flash_kb"], row["material_url"]
    elif filename.startswith("nxp-11-lpc11u-"):
        _check(all(row[k] == "false" for k in (
            "openocd_programming_qualified", "production_admitted",
            "physical_hil_verified", "original_manufacturer_html_bytes_archived")),
            "LPC11U/LPC83x is not independently qualified for execution or original bytes")
        _check(row["manufacturer_material_status"] == "Active", "LPC11U/83x material status")
        family = row["datasheet_id"]
        base, pkg = row["manufacturer_base"], row["manufacturer_package_alias"]
        pins, flash, uri = None, row["flash_kb"], row["official_exact_material_page"]
    elif filename.startswith("nxp-25-lpc-"):
        _check(all(row[k] == "false" for k in (
            "phase2_software_supported", "production_admitted",
            "physical_hil_passed", "raw_original_official_html_archived")),
            "LPC material cannot acquire programming/Production/HIL")
        _check(row["material_lifecycle_observed"] == "Active", "LPC material status")
        family, base, pkg = row["manufacturer_family"], row["manufacturer_model_lead"], row["package"]
        pins, flash, uri = row["pin_count"], None, row["official_package_quality_url"]
    elif filename.startswith("nxp-21-k40-"):
        _check(row["phase1_identified"] == "true"
               and row["phase1_information_complete"] == "false"
               and all(row[k] == "false" for k in (
                    "phase2_programming_supported", "production_admitted",
                    "phase3_hil_passed", "original_official_html_archived")),
               "Kinetis row is not a Phase1-only official identity")
        _check(row["manufacturer_material_status"] == "Active", "Kinetis material status")
        family, base, pkg = row["manufacturer_family"], row["base_device"], row["package"]
        pins, flash, uri = row["package_terminal_count"], row["flash_kb"], row["official_material_product_url"]
    else:
        raise DeviceCatalogIntegrityError("unapproved Phase1 material source")
    _check(bool(icpn) and icpn.strip() == icpn and " " not in icpn,
           "not a complete individual commercial material")
    _check(len(nc) == 12 and nc.isascii() and nc.isdecimal(),
           "invalid manufacturer material 12NC")
    _check(bool(base) and bool(family) and bool(pkg), "manufacturer Base/Family/Package missing")
    _check(uri.startswith(_ALLOWED_URI), "untrusted manufacturer source URI")
    if flash:
        _check(flash.isdecimal() and int(flash) > 0, "source Flash size not evidenced")
    return icpn, nc, family, base, pkg, pins, flash, uri, filename

def build_nxp_phase1_selector_catalog(production: DeviceCatalog, *, root: Path | None = None) -> DeviceCatalog:
    """Compose the Phase1 lookup index, not a new Production/Job Catalog."""
    source_root = root if root is not None else _repository_root()
    records = list(production.records)
    existing = {(r.vendor.upper(), r.identifier.upper()) for r in records}
    added: set[str] = set()
    material_ids: set[str] = set()
    for filename, row in _read_locked_sources(source_root):
        icpn, nc, family, base, pkg, pins, flash, uri, filename = _extract(filename, row)
        _check(icpn not in added and nc not in material_ids, "duplicate official exact ICPN/12NC")
        _check(("NXP", icpn.upper()) not in existing, "Phase1 exact material overlaps Production admission")
        added.add(icpn)
        material_ids.add(nc)
        records.append(DeviceCatalogRecord(
            vendor="NXP", family=family, subfamily=base, plasma_series=family,
            identifier=icpn, identifier_kind="manufacturer_part_number",
            cpu_architectures=(), target_config="", openocd_distribution="",
            mapping_status="no_mapping", validation_status="no_evidence",
            catalog_origin=PHASE1_CATALOG_ORIGIN, package=pkg, pin_count=pins or None,
            flash_size=f"{flash} kB" if flash else None,
            base_device=base, mapping_method=None, source_type=OFFICIAL_SOURCE_TYPE,
            source_reference=f"{filename}: material={icpn}, NXP 12NC={nc}",
            source_authority=uri, verification_status="verified_phase1_identified",
            catalog_version="NXP-Phase1-source-locked-v1",
            catalog_revision_sha256=None, production_admitted=False,
        ))
    _check(len(added) == EXPECTED_NEW_IDENTIFIED, "Phase1 official ICPN count changed")
    return DeviceCatalog(
        records,
        catalog_id=production.catalog_id + ":phase1-lookup",
        catalog_version=production.catalog_version + "+NXP-Phase1",
        status="phase1_search_only",
        revision_sha256=None,
        source_count=production.source_count + len(SOURCE_BLOBS),
    )
