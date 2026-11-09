"""Canonical Bundle v3 construction from a Programming Route plus image.

This is the single host-side Bundle v3 writer for image programming
Bundles. It is shared by the Manager (Console-driven programming) and the
developer fixture builder (``scripts/bluepill_bundle_v3_image_build.py``).

A *Programming Route* is the declarative, data-only pair of Bundle Packages
that make a image image executable on one PPU platform:

* ``platform-provider`` Package: Provider options schema;
* ``programming-profile`` Package: Provider capabilities (target, Sites,
  operations, transport, Driver ABI, size limit) and the flash profile
  (target config, base, size, erase granularity).

The route is an input to Bundle construction, never an execution gate on the
PPU. The PPU still verifies the received Bundle bytes, owner authorization,
actual Target/FPGA/Driver ABI, Site ownership and SAFE_OFF at B2/B3/Job time.
Nothing in this module talks to a PPU, installs a Bundle, or touches hardware.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

BUNDLE_SCHEMA = "plasma.ppu.bundle.v3"
ROUTE_SCHEMA = "plasma.opf.programming-route.v1"
CAPABILITIES_SCHEMA = "plasma.ppu.provider-capabilities.v1"
OPTIONS_SCHEMA = "plasma.ppu.provider-options.v1"
FLASH_PROFILE_SCHEMA = "plasma.ppu.openocd-flash-profile.v1"
# Same identifier/version grammar as the PPU Bundle v3 verifier.
SAFE_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
SAFE_VERSION = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
SAFE_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\.bin\Z")
MAX_IMAGE_BYTES = 1024 * 1024
MAX_ROUTE_BYTES = 16 * 1024


class BundleBuildError(ValueError):
    """Fixed reason code; never echoes untrusted input values."""


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise BundleBuildError(code)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_zip(contents: Mapping[str, bytes]) -> bytes:
    """Deterministic ZIP: sorted, STORED, fixed 1980 timestamp, regular 0644."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "x") as archive:
        for name, raw in sorted(contents.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            entry.compress_type = zipfile.ZIP_STORED
            archive.writestr(entry, raw)
    return buffer.getvalue()


def _unique_pairs(pairs):
    result: dict[str, Any] = {}
    for key, value in pairs:
        _need(key not in result, "ROUTE_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


@dataclass(frozen=True)
class ProgrammingRoute:
    route_id: str
    target: dict[str, str]
    image_package_kind: str
    provider_id: str
    provider_version: str
    provider_options: dict[str, Any]
    profile_id: str
    profile_version: str
    capabilities: dict[str, Any]
    flash_profile: dict[str, Any]

    @property
    def icpn(self) -> str:
        return str(self.capabilities["target"])

    @property
    def sites(self) -> tuple[int, ...]:
        return tuple(self.capabilities["sites"])

    @property
    def max_image_bytes(self) -> int:
        return int(self.capabilities["max_image_bytes"])

    def summary(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "target": dict(self.target),
            "icpn": self.icpn,
            "sites": list(self.sites),
            "provider": self.provider_id,
            "profile": self.profile_id,
            "operations": list(self.capabilities["operations"]),
            "driver_abi": self.capabilities["driver_abi"],
            "transport": self.capabilities["transport"],
            "max_image_bytes": self.max_image_bytes,
            "target_config": self.flash_profile["target_config"],
            "flash_base": self.flash_profile["flash_base"],
            "flash_size": self.flash_profile["flash_size"],
        }


def parse_route(payload: object) -> ProgrammingRoute:
    """Validate one route with the same rules the Bundle builders enforce."""
    _need(type(payload) is dict and set(payload) <= {
        "schema", "route_id", "description", "target", "image_package", "provider", "profile"}
        and {"schema", "route_id", "target", "image_package", "provider", "profile"} <= set(payload),
        "ROUTE_FIELDS_INVALID")
    _need(payload["schema"] == ROUTE_SCHEMA, "ROUTE_SCHEMA_UNSUPPORTED")
    route_id = payload["route_id"]
    _need(type(route_id) is str and SAFE_NAME.fullmatch(route_id) is not None, "ROUTE_ID_INVALID")
    target = payload["target"]
    _need(type(target) is dict and set(target) == {"platform", "board", "fpga_part"}
          and all(type(v) is str and SAFE_VERSION.fullmatch(v) for v in target.values()),
          "ROUTE_TARGET_INVALID")
    image_package = payload["image_package"]
    # The PPU Bundle v3 wire kind of the programming image Package, declared by
    # the route (data) so product code carries no retired vocabulary.
    _need(type(image_package) is dict and set(image_package) == {"kind"}
          and type(image_package["kind"]) is str
          and SAFE_NAME.fullmatch(image_package["kind"]) is not None
          and image_package["kind"] not in {"platform-provider", "programming-profile", "fpga-image"},
          "ROUTE_IMAGE_PACKAGE_INVALID")
    provider, profile = payload["provider"], payload["profile"]
    _need(type(provider) is dict and set(provider) == {"id", "version", "options"},
          "ROUTE_PROVIDER_INVALID")
    _need(type(profile) is dict and set(profile) == {
        "id", "version", "capabilities", "flash_profile"}, "ROUTE_PROFILE_INVALID")
    for package in (provider, profile):
        _need(type(package["id"]) is str and SAFE_NAME.fullmatch(package["id"]) is not None
              and type(package["version"]) is str
              and SAFE_VERSION.fullmatch(package["version"]) is not None,
              "ROUTE_PACKAGE_ID_INVALID")
    _need(provider["id"] != profile["id"], "ROUTE_PACKAGE_ID_INVALID")
    options = provider["options"]
    _need(type(options) is dict and options.get("schema") == OPTIONS_SCHEMA
          and set(options) == {"schema", "options"} and type(options["options"]) is dict,
          "ROUTE_PROVIDER_OPTIONS_INVALID")
    caps = profile["capabilities"]
    _need(type(caps) is dict and set(caps) == {
        "schema", "target", "provider_package", "operations", "sites",
        "transport", "driver_abi", "fpga_package", "max_image_bytes"},
        "ROUTE_CAPABILITIES_INVALID")
    _need(caps["schema"] == CAPABILITIES_SCHEMA
          and caps["provider_package"] == provider["id"]
          and type(caps["target"]) is str and bool(caps["target"])
          and caps["transport"] == "fpga" and caps["fpga_package"] is None
          and type(caps["driver_abi"]) is str and bool(caps["driver_abi"])
          and type(caps["operations"]) is list and "flash_cycle" in caps["operations"]
          and type(caps["sites"]) is list and bool(caps["sites"])
          and all(type(s) is int and s > 0 for s in caps["sites"])
          and caps["sites"] == sorted(set(caps["sites"]))
          and type(caps["max_image_bytes"]) is int
          and 0 < caps["max_image_bytes"] <= MAX_IMAGE_BYTES,
          "ROUTE_CAPABILITIES_INVALID")
    flash = profile["flash_profile"]
    _need(type(flash) is dict and set(flash) == {
        "schema", "icpn", "target_config", "flash_base", "flash_size", "erase_granularity"},
        "ROUTE_FLASH_PROFILE_INVALID")
    _need(flash["schema"] == FLASH_PROFILE_SCHEMA and flash["icpn"] == caps["target"]
          and type(flash["target_config"]) is str and bool(flash["target_config"])
          and all(type(flash[k]) is int for k in ("flash_base", "flash_size", "erase_granularity"))
          and flash["flash_base"] >= 0 and flash["flash_size"] > 0
          and flash["erase_granularity"] > 0
          and flash["flash_size"] % flash["erase_granularity"] == 0
          and caps["max_image_bytes"] <= flash["flash_size"],
          "ROUTE_FLASH_PROFILE_INVALID")
    return ProgrammingRoute(
        route_id=route_id, target=dict(target), image_package_kind=image_package["kind"],
        provider_id=provider["id"], provider_version=provider["version"],
        provider_options=options,
        profile_id=profile["id"], profile_version=profile["version"],
        capabilities=caps, flash_profile=flash,
    )


def load_route(path: Path) -> ProgrammingRoute:
    _need(isinstance(path, Path) and not path.is_symlink() and path.is_file()
          and 0 < path.stat().st_size <= MAX_ROUTE_BYTES, "ROUTE_FILE_UNTRUSTED")
    try:
        payload = json.loads(path.read_bytes(), object_pairs_hook=_unique_pairs)
    except BundleBuildError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise BundleBuildError("ROUTE_JSON_INVALID") from exc
    return parse_route(payload)


def load_routes(root: Path) -> tuple[ProgrammingRoute, ...]:
    """Load every ``*.json`` route in one directory; any invalid file fails closed."""
    _need(isinstance(root, Path) and root.is_dir() and not root.is_symlink(),
          "ROUTE_ROOT_UNAVAILABLE")
    routes = tuple(load_route(path) for path in sorted(root.glob("*.json")))
    _need(len({r.route_id for r in routes}) == len(routes), "ROUTE_ID_DUPLICATE")
    return routes


def resolve_routes(routes: tuple[ProgrammingRoute, ...], *, icpn: str,
                   site: int) -> tuple[ProgrammingRoute, ...]:
    """Routes whose Profile declares this exact target and Site."""
    return tuple(r for r in routes if r.icpn == icpn and site in r.sites)


def user_image_identity(image_sha256: str, profile_id: str) -> tuple[str, str]:
    """Deterministic (asset_package_id, bundle_name) for a user image image."""
    _need(type(image_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", image_sha256)
          is not None, "IMAGE_SHA256_INVALID")
    asset = f"img-{image_sha256[:16]}"
    name = f"{profile_id}-img-{image_sha256[:12]}"[:64]
    return asset, name


def safe_image_filename(filename: object) -> str:
    """Keep a user's ``*.bin`` name when it is a plain safe name, else ``image.bin``."""
    if type(filename) is str and SAFE_FILENAME.fullmatch(filename):
        return filename
    return "image.bin"


@dataclass(frozen=True)
class ProgrammingBundle:
    archive: bytes
    archive_sha256: str
    bundle_name: str
    version: str
    target: dict[str, str]
    provider_id: str
    profile_id: str
    asset_package_id: str
    image_filename: str
    image_sha256: str
    image_size: int
    icpn: str

    def summary(self) -> dict[str, Any]:
        return {
            "bundle_schema": BUNDLE_SCHEMA,
            "archive_sha256": self.archive_sha256,
            "archive_size": len(self.archive),
            "bundle_name": self.bundle_name,
            "version": self.version,
            "target": dict(self.target),
            "provider": self.provider_id,
            "profile": self.profile_id,
            "asset_package_id": self.asset_package_id,
            "image_filename": self.image_filename,
            "image_sha256": self.image_sha256,
            "image_size": self.image_size,
            "icpn": self.icpn,
        }


def build_image_bundle(
    route: ProgrammingRoute,
    image: bytes,
    *,
    image_filename: str,
    asset_package_id: str,
    bundle_name: str,
    version: str = "1.0.0",
) -> ProgrammingBundle:
    """Build Provider -> Profile -> Image Bundle v3 bytes; no I/O, no deployment."""
    _need(isinstance(route, ProgrammingRoute), "ROUTE_REQUIRED")
    _need(type(image) is bytes and len(image) > 0, "IMAGE_EMPTY")
    _need(len(image) <= route.max_image_bytes, "IMAGE_EXCEEDS_PROFILE_MAX_IMAGE")
    _need(len(image) <= route.flash_profile["flash_size"], "IMAGE_EXCEEDS_FLASH_SIZE")
    _need(type(image_filename) is str and SAFE_FILENAME.fullmatch(image_filename)
          is not None, "IMAGE_FILENAME_INVALID")
    for value in (asset_package_id, bundle_name):
        _need(type(value) is str and SAFE_NAME.fullmatch(value) is not None,
              "PACKAGE_OR_BUNDLE_ID_INVALID")
    _need(asset_package_id not in {route.provider_id, route.profile_id},
          "PACKAGE_OR_BUNDLE_ID_INVALID")
    _need(type(version) is str and SAFE_VERSION.fullmatch(version) is not None,
          "BUNDLE_VERSION_INVALID")

    provider_dir = f"payload/packages/{route.provider_id}/data"
    profile_dir = f"payload/packages/{route.profile_id}/data"
    members = {
        f"{provider_dir}/plasma-provider-options.json": canonical_json(route.provider_options),
        f"{profile_dir}/plasma-provider.json": canonical_json(route.capabilities),
        f"{profile_dir}/plasma-flash-profile.json": canonical_json(route.flash_profile),
        f"payload/packages/{asset_package_id}/data/{image_filename}": image,
    }

    def package(pid: str, kind: str, package_version: str, requires: list[str]) -> dict:
        paths = sorted(p for p in members if p.startswith(f"payload/packages/{pid}/"))
        return {"id": pid, "kind": kind, "version": package_version, "requires": requires,
                "files": [{"path": p, "size": len(members[p]),
                           "sha256": sha256_hex(members[p]), "executable": False}
                          for p in paths]}

    manifest = {
        "schema": BUNDLE_SCHEMA,
        "name": bundle_name, "version": version,
        "purpose": "programming", "target": dict(route.target),
        # The existing B3 verified-set reader requires this exact action set.
        "actions": ["install", "verify"],
        "packages": [
            package(route.provider_id, "platform-provider", route.provider_version, []),
            package(route.profile_id, "programming-profile", route.profile_version,
                    [route.provider_id]),
            package(asset_package_id, route.image_package_kind, version, [route.profile_id]),
        ],
    }
    archive = canonical_zip({"manifest.json": canonical_json(manifest), **members})
    return ProgrammingBundle(
        archive=archive, archive_sha256=sha256_hex(archive),
        bundle_name=bundle_name, version=version, target=dict(route.target),
        provider_id=route.provider_id, profile_id=route.profile_id,
        asset_package_id=asset_package_id, image_filename=image_filename,
        image_sha256=sha256_hex(image), image_size=len(image),
        icpn=route.icpn,
    )


def build_user_image_bundle(route: ProgrammingRoute, image: bytes, *,
                               filename: object = None) -> ProgrammingBundle:
    """Console path: deterministic identities derived from the image digest."""
    _need(type(image) is bytes and 0 < len(image) <= MAX_IMAGE_BYTES,
          "IMAGE_SIZE_INVALID")
    asset, name = user_image_identity(sha256_hex(image), route.profile_id)
    return build_image_bundle(
        route, image, image_filename=safe_image_filename(filename),
        asset_package_id=asset, bundle_name=name)
