"""A Mock PPU's own Active Set and Resource identity.

A Mock Site is not a shortcut past admission. It declares the geometry it
simulates the way a real Site's Bundle Profile does, and the PPU then admits
its Job Bindings through exactly the path a Z2 uses: the Resource Set is
re-derived here, the Manager's claim is only compared, and a disagreement
between what the Mock simulates and what the Job was planned against fails
closed instead of being papered over.

Nothing here is a hardware capability. A Mock Resource Set authorizes no
execution by itself: route admission remains the execution authority, and a
Mock route is never ``hardware_runtime_ready``.
"""
from __future__ import annotations

from typing import Any

from plasma_core.config import PlasmaConfig, SiteConfig
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_opf import bundle_v3

# Package identities of the simulated Provider and Profile. They are part of
# the Resource Set identity, so a Job planned against a real Provider can never
# be admitted by a Mock Site and the other way round.
MOCK_PROVIDER_ID = "mock-platform-provider"
MOCK_PROFILE_ID = "mock-programming-profile"
MOCK_ROUTE_ID = "mock-site-simulated"
MOCK_TARGET_CONFIG = "target/mock-simulated.cfg"
MOCK_IMAGE_PACKAGE_KIND = "mock-programming-asset"
MOCK_DRIVER_ABI = "mock-simulated:1"
MOCK_PLATFORM = {"platform": "mock", "board": "mock-site", "fpga_part": "none"}
# Mock Sites offer the basic operations a Profile may declare. ``programming``
# is never declared by a Profile: it is the Job kind that runs a list of these.
MOCK_OPERATIONS = ("erase", "program", "verify", "read")
RESOURCES_SCHEMA = "plasma.ppu.package-resources.v1"

# Defaults mirror MockInterface's own, so a Site that declares nothing still
# produces a Resource Set that agrees with the interface it describes.
DEFAULT_FLASH_SIZE = 256 * 1024
DEFAULT_FLASH_BASE = 0
DEFAULT_ERASE_GRANULARITY = 1


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, code)


def site_geometry(site: SiteConfig) -> dict[str, int]:
    """The Flash window a Mock Site simulates, as its options declare it."""
    options = site.mock if isinstance(site.mock, dict) else {}
    geometry = {
        "flash_base": options.get("flash_base", DEFAULT_FLASH_BASE),
        "flash_size": options.get("flash_size", DEFAULT_FLASH_SIZE),
        "erase_granularity": options.get("erase_granularity", DEFAULT_ERASE_GRANULARITY),
    }
    _need(all(type(value) is int for value in geometry.values()),
          "MOCK_SITE_GEOMETRY_INVALID")
    _need(geometry["flash_base"] >= 0 and geometry["flash_size"] > 0
          and geometry["erase_granularity"] > 0
          and geometry["flash_size"] % geometry["erase_granularity"] == 0,
          "MOCK_SITE_GEOMETRY_INVALID")
    return geometry


def mock_route(
    *,
    icpn: str,
    sites: list[int],
    flash_base: int = DEFAULT_FLASH_BASE,
    flash_size: int = DEFAULT_FLASH_SIZE,
    erase_granularity: int = DEFAULT_ERASE_GRANULARITY,
    max_image_bytes: int | None = None,
    operations: tuple[str, ...] = MOCK_OPERATIONS,
    route_id: str = MOCK_ROUTE_ID,
    provider_id: str = MOCK_PROVIDER_ID,
    profile_id: str = MOCK_PROFILE_ID,
) -> bundle_v3.ProgrammingRoute:
    """One simulated Programming Route, validated by the real route parser."""
    return bundle_v3.parse_route({
        "schema": bundle_v3.ROUTE_SCHEMA,
        "route_id": route_id,
        "target": dict(MOCK_PLATFORM),
        "image_package": {"kind": MOCK_IMAGE_PACKAGE_KIND},
        "provider": {
            "id": provider_id,
            "version": "1.0.0",
            "options": {"schema": bundle_v3.OPTIONS_SCHEMA,
                        "options": {"type": "object", "properties": {}}},
        },
        "profile": {
            "id": profile_id,
            "version": "1.0.0",
            "capabilities": {
                "schema": bundle_v3.CAPABILITIES_SCHEMA,
                "target": icpn,
                "provider_package": provider_id,
                "operations": list(operations),
                "sites": sorted(set(sites)),
                "transport": "fpga",
                "driver_abi": MOCK_DRIVER_ABI,
                "fpga_package": None,
                "max_image_bytes": flash_size if max_image_bytes is None else max_image_bytes,
            },
            "flash_profile": {
                "schema": bundle_v3.FLASH_PROFILE_SCHEMA,
                "icpn": icpn,
                "target_config": MOCK_TARGET_CONFIG,
                "flash_base": flash_base,
                "flash_size": flash_size,
                "erase_granularity": erase_granularity,
            },
        },
    })


def mock_resource_identity(route: bundle_v3.ProgrammingRoute, *,
                           generation: int = 1) -> dict[str, Any]:
    """The PPU-derived Resource identity a Mock Site reports as VERIFIED.

    The Active Set digest is derived from the Resource Set itself, so two Mock
    PPUs with different simulated geometry never share an identity and a
    changed simulation is a changed Active Set.
    """
    _need(type(generation) is int and generation >= 1, "MOCK_GENERATION_INVALID")
    resource = bundle_v3.resource_set_descriptor(route)
    digest = bundle_v3.resource_set_sha256(resource)
    asset_set_sha256 = bundle_v3.sha256_hex(bundle_v3.canonical_json({
        "mock_active_set": digest, "generation": generation,
    }))
    return {
        "schema": RESOURCES_SCHEMA,
        "state": "VERIFIED",
        "asset_set_sha256": asset_set_sha256,
        "generation": generation,
        "resource_set": resource,
        "resource_set_sha256": digest,
    }


def mock_active_asset_set(identity: dict[str, Any]) -> dict[str, Any]:
    """The pinned Active Set that matches one Mock Resource identity."""
    return {
        "state": "ACTIVE",
        "asset_set_sha256": identity["asset_set_sha256"],
        "generation": identity["generation"],
        "ready": True,
    }


def mock_resources_for_config(config: PlasmaConfig, *,
                              generation: int = 1) -> dict[str, Any]:
    """Build one Mock PPU's identity from the Sites it actually has enabled.

    Every enabled Mock Site must name the same exact ICPN and simulate the same
    geometry: one PPU runs one Resource Set, exactly as a real PPU does.
    """
    sites = [site for site in config.sites if site.enabled and site.interface == "mock"]
    _need(bool(sites), "MOCK_RESOURCES_NO_ENABLED_MOCK_SITE")
    targets = {site.target for site in sites}
    _need(len(targets) == 1 and None not in targets and all(targets),
          "MOCK_RESOURCES_SITE_TARGET_NOT_UNIFORM")
    geometries = {tuple(sorted(site_geometry(site).items())) for site in sites}
    _need(len(geometries) == 1, "MOCK_RESOURCES_SITE_GEOMETRY_NOT_UNIFORM")
    route = mock_route(
        icpn=str(targets.pop()),
        sites=[site.id for site in sites],
        **site_geometry(sites[0]),
    )
    return mock_resource_identity(route, generation=generation)


def install_mock_resources(manager: Any, *, generation: int = 1) -> dict[str, Any]:
    """Wire a Mock PPU's Active Set and Resource resolver onto its SiteManager.

    Both halves come from one identity, so the Active Set the PPU pins and the
    Resource Set it re-derives can never disagree by construction. Existing
    wiring is never replaced: a PPU that already has a trusted resolver keeps
    it, so this can never downgrade a real PPU to a simulated identity.
    """
    identity = mock_resources_for_config(manager.config, generation=generation)
    active = mock_active_asset_set(identity)
    _need(getattr(manager, "_active_resource_resolver", None) is None
          and getattr(manager, "_active_asset_set_reader", None) is None,
          "MOCK_RESOURCES_ALREADY_WIRED")
    manager._active_resource_resolver = lambda: dict(identity)
    manager._active_asset_set_reader = lambda: dict(active)
    return identity
