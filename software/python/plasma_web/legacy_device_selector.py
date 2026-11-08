"""Legacy PPU-hosted Device Selector (``GET /api/devices/search``) projection.

Transitional, Catalog-only adapter. The Device Selector is owned by Manager
(OPF S0-S5, PR-C1): the PPU Gateway never imports this module at startup and
never needs it to accept, run or report Programming Jobs / Batches / Health.
When this module, its Catalog/Qualification dependencies or the Catalog data
are absent, the Gateway answers ``503 DEVICE_SELECTOR_UNAVAILABLE`` instead of
an empty (fake) result. No new Catalog Service is implemented here; Console
consumers migrate to Manager in PR-C2.
"""

from __future__ import annotations

import re
from typing import Any

from plasma_core.ic_support import ICSupportIntegrityError, get_default_ic_support_resolver
from plasma_core.manufacturer_device_basic import get_default_manufacturer_device_basic_resolver

from .backend_candidate_registry import get_default_backend_candidate_registry
from .backend_source_reference import backend_source_reference, default_pinned_upstream
from .device_catalog import (
    DEFAULT_SEARCH_LIMIT,
    MAX_SEARCH_LIMIT,
    DeviceCatalogIntegrityError,
    get_default_device_catalog,
)
from .gateway_base import WEB_REST_CONTRACT_VERSION
from .microchip_upstream_openocd_evidence import microchip_upstream_openocd_evidence
from .nxp_manufacturer_device_evidence import get_default_nxp_manufacturer_device_evidence
from .openocd_provider_registry import get_default_openocd_provider_registry
from .programming_qualification import get_default_programming_qualification_registry

# Data-availability failures that make the Selector unavailable (never empty).
SELECTOR_DATA_ERRORS: tuple[type[BaseException], ...] = (
    DeviceCatalogIntegrityError,
    ICSupportIntegrityError,
    OSError,
)

__all__ = [
    "DEFAULT_SEARCH_LIMIT",
    "MAX_SEARCH_LIMIT",
    "SELECTOR_DATA_ERRORS",
    "parse_public_catalog_levels",
    "search",
    "warm",
]


_MICROCHIP_IDENTITY_ORDER = re.compile(
    r"\A(ATSAML(10|11)(D|E)(14|15|16)A)-([AMUY])([UFZ])(T?)(KPH)?\Z"
)
_MICROCHIP_IDENTITY_PACKAGES = {"A":"TQFP","M":"VQFN","U":"WLCSP","Y":"SSOP"}
_MICROCHIP_IDENTITY_FLASH_KB = {"14":16,"15":32,"16":64}
_MICROCHIP_IDENTITY_PDF_SHA = (
    "ee9c04451141173b787374388ddf9b607a5a569415ae85d9b5715237fd1cbb9e"
)


def _microchip_ic_information(
    record: Any, qualification: dict[str, Any],
) -> dict[str, Any] | None:
    """Read-only manufacturer information; canonical Qualification owns Level."""
    if record.vendor != "Microchip":
        return None
    if record.family == "PIC32MX":
        ref = record.source_reference or ""
        if (not record.production_admitted
            or record.mapping_status != "no_mapping" or record.target_config
            or not record.base_device or not record.identifier.startswith("PIC32MX")
            or record.source_authority != "Microchip Technology official"
            or record.verification_status !=
                "verified_microchip_mcp_exact_ordering_and_pinned_openocd_devid"
            or f"partNumber={record.icpn}" not in ref
            or f"basePartNumber={record.base_device}" not in ref
            or "original_response_sha256=" not in ref
            or "expected_devid=" not in ref
            or qualification["catalog_level"] != 1
            or qualification["state"] != "CANDIDATE"
            or qualification["job_selectable"]
            or qualification["execution_authorized"]):
            raise ValueError("Microchip PIC32MX exact identity/route evidence boundary changed")
        return {
            "status": "manufacturer_exact_material_identity_route_candidate",
            "manufacturer": "Microchip", "icpn": record.icpn,
            "identity_state": "IDENTIFIED", "information_complete": False,
            "catalog_level": qualification["catalog_level"],
            "catalog_level_state": qualification["catalog_level_state"],
            "programming_state": qualification["state"],
            "compatibility_state": "NOT_TESTED",
            "ram_size": None, "core_model": None,
            "working_vdd_v": None, "io_supply_v": None, "vdda_v": None,
            "field_states": {
                "manufacturer": "VERIFIED", "icpn": "VERIFIED",
                "base_device": "VERIFIED", "package": "UNKNOWN",
                "pin_count": "UNKNOWN", "flash": "UNKNOWN",
                "ram": "UNKNOWN", "temperature": "UNKNOWN",
                "core_model": "UNKNOWN", "working_vdd": "UNKNOWN",
                "io_supply": "UNKNOWN", "vdda": "UNKNOWN",
                "core_architecture": "UNKNOWN",
            },
            "source": {
                "authority": "Microchip Technology official",
                "exact_mcp_material_source": ref,
                "provider_route_evidence": "OpenOCD v0.12.0 pinned driver DEVID",
                "official_pdf_grammar_not_exact_material_list": False,
            },
            "software_supported": False,
            "programming_provider": None,
            "supported_operations": [],
            "verified_configurations": [],
            "programming_profile_authority": False,
            "hardware_runtime_ready": False,
        }
    match = _MICROCHIP_IDENTITY_ORDER.fullmatch(record.icpn or "")
    if match is None or record.family != "SAML1X" or not record.production_admitted:
        raise ValueError("unknown Microchip exact SKU in admitted Product Catalog")
    base, series, group, density, package_code, grade, _carrier, kph = match.groups()
    package = _MICROCHIP_IDENTITY_PACKAGES[package_code]
    pin_count = 24 if group == "D" else 32
    high = 85 if grade == "U" else 125
    ram = 16 if density == "16" else (8 if series == "11" or density == "15" else 4)
    restrictions = (
        (group == "D" and package not in ("VQFN", "SSOP"))
        or (group == "E" and package not in ("VQFN", "TQFP", "WLCSP"))
        or (grade == "Z" and package not in ("VQFN", "TQFP"))
        or (bool(kph) and (series != "11" or package not in ("VQFN", "TQFP")))
    )
    if (restrictions or record.base_device != base
        or record.subfamily != "SAML" + series
        or record.package != package or record.pin_count != str(pin_count)
        or record.flash_size != f"{_MICROCHIP_IDENTITY_FLASH_KB[density]} KB"
        or record.temperature_grade != f"-40..{high} C"
        or record.mapping_status != "no_mapping" or record.target_config
        or record.verification_status != "verified_microchip_mcp_exact_ordering_and_pdf_applicability"
        or "original_response_sha256=" not in (record.source_reference or "")
        or _MICROCHIP_IDENTITY_PDF_SHA not in (record.source_reference or "")
        or f"partNumber={record.icpn}" not in (record.source_reference or "")
        or f"basePartNumber={base}" not in (record.source_reference or "")):
        raise ValueError("Microchip original evidence applicability drift")
    return {
        "status":"manufacturer_exact_material_partial_information",
        "manufacturer":"Microchip","icpn":record.icpn,
        "identity_state":"IDENTIFIED",
        "information_complete":False,
        "catalog_level": qualification["catalog_level"],
        "catalog_level_state": qualification["catalog_level_state"],
        "programming_state": qualification["state"],
        "compatibility_state":"NOT_TESTED",
        "ram_size":f"{ram} KB",
        "core_model":"Arm Cortex-M23",
        "working_vdd_v":None,"io_supply_v":None,"vdda_v":None,
        "field_states":{
            "manufacturer":"VERIFIED","icpn":"VERIFIED","base_device":"VERIFIED",
            "package":"VERIFIED","pin_count":"VERIFIED","flash":"VERIFIED",
            "ram":"VERIFIED","temperature":"VERIFIED","core_model":"VERIFIED",
            "working_vdd":"PARTIAL","io_supply":"UNKNOWN","vdda":"UNKNOWN",
            "core_architecture":"UNKNOWN",
        },
        "source":{
            "authority":"Microchip Technology official",
            "exact_mcp_material_source":record.source_reference,
            "pdf_revision":"DS60001513G",
            "pdf_original_sha256":_MICROCHIP_IDENTITY_PDF_SHA,
            "pdf_printed_pages":[14,16],
            "official_pdf_grammar_not_exact_material_list":True,
        },
        "software_supported":False,
        "programming_provider":None,
        "supported_operations":[],
        "verified_configurations":[],
        "programming_profile_authority":False,
        "hardware_runtime_ready":False,
    }


def _parse_public_catalog_levels(raw: str | None) -> tuple[int, ...]:
    """Parse the customer-facing IC Selector level filter.

    Level 0 is intentionally not exposed by this public Product API.
    """
    if raw is None or not raw.strip():
        return (1, 2, 3)
    values: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            level = int(token)
        except ValueError as exc:
            raise ValueError("levels must be a comma-separated subset of 1,2,3") from exc
        if level not in {1, 2, 3}:
            raise ValueError("public IC Selector levels must be a subset of 1,2,3; Level 0 is internal-only")
        if level not in values:
            values.append(level)
    if not values:
        raise ValueError("levels must include at least one of 1,2,3")
    return tuple(sorted(values))


def _device_search_payload(
    query: str,
    limit: int,
    offset: int = 0,
    *,
    levels: tuple[int, ...] = (1, 2, 3),
) -> dict[str, Any]:
    catalog = get_default_device_catalog()
    programming_qualification = get_default_programming_qualification_registry()
    qualification_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def qualification_for(record: Any) -> dict[str, Any]:
        exact_icpn = record.icpn or record.identifier
        key = (record.vendor, exact_icpn)
        qualification = qualification_cache.get(key)
        if qualification is None:
            qualification = programming_qualification.describe(record.vendor, exact_icpn)
            qualification_cache[key] = qualification
        return qualification

    def visible(record: Any) -> bool:
        level = qualification_for(record).get("catalog_level")
        return isinstance(level, int) and level in levels and level >= 1

    matches, total_count = catalog.search_with_total(
        query,
        limit=limit,
        offset=offset,
        predicate=visible,
    )

    # Candidate evidence is an independent, read-only display projection.
    # It never modifies authoritative backend routing or Job admission.
    candidates = get_default_backend_candidate_registry()
    upstream = default_pinned_upstream()
    versioned_providers = get_default_openocd_provider_registry()
    ic_support = get_default_ic_support_resolver()
    device_basic = get_default_manufacturer_device_basic_resolver()
    results = []
    for record in matches:
        item = record.to_payload()
        qualification = qualification_for(record)
        item["catalog_level"] = qualification["catalog_level"]
        item["catalog_level_state"] = qualification["catalog_level_state"]
        item["job_selectable"] = bool(qualification.get("job_selectable", False))

        candidate = candidates.lookup(record)
        item["backend_candidate"] = candidate
        item["backend_source_reference"] = backend_source_reference(record, candidate, upstream)
        item["backend_providers"] = (
            versioned_providers.describe(record.vendor, record.identifier)
            if versioned_providers is not None else []
        )
        exact_icpn = record.icpn or record.identifier
        basic = device_basic.resolve_exact(
            exact_icpn,
            manufacturer=record.vendor,
            family=record.family,
            series=record.subfamily,
            base_device=record.base_device,
            package=record.package,
            pin_count=record.pin_count,
            flash_size=record.flash_size,
            temperature_grade=record.temperature_grade,
        )
        item["manufacturer_device_basic_profile"] = (
            basic.to_payload() if basic is not None else None
        )
        item["nxp_manufacturer_device_profile"] = (
            get_default_nxp_manufacturer_device_evidence().resolve_exact(record)
            if record.vendor == "NXP" and record.family in {"MCX", "K32L2"}
            else None
        )
        item["microchip_ic_information"] = _microchip_ic_information(record, qualification)
        item["upstream_openocd_evidence"] = microchip_upstream_openocd_evidence(record)
        support = ic_support.resolve_exact(exact_icpn)
        item["selected_profile"] = (
            support.to_selected_profile_payload()
            if support is not None
            else None
        )
        item["programming_qualification"] = qualification
        results.append(item)

    level_counts = programming_qualification.summary["catalog_level_counts"]
    catalog_size = sum(int(level_counts[str(level)]) for level in levels)
    return {
        "ok": True,
        "rest_contract_version": WEB_REST_CONTRACT_VERSION,
        "scope": "customer_ic_selector",
        "query": query,
        "levels": list(levels),
        "catalog_size": catalog_size,
        "count": len(results),
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "results": results,
    }


parse_public_catalog_levels = _parse_public_catalog_levels


def search(query: str, limit: int, offset: int = 0, *, levels: tuple[int, ...] = (1, 2, 3)) -> dict[str, Any]:
    return _device_search_payload(query, limit, offset, levels=levels)


def warm() -> dict[str, int]:
    """Build the immutable Qualification registry once; return Level counts."""
    counts = get_default_programming_qualification_registry().summary["catalog_level_counts"]
    return {str(level): int(counts[str(level)]) for level in range(4)}
