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


# --------------------------------------------------------------------------
# OFE-1A identity contract (docs/architecture/opf-resource-image-identity-v1.md)
#
# Programming Resource Set: every Bundle v3 Package except the Job Image,
# plus Target platform, Driver ABI and hardware constraints, each Package
# pinned by exact per-file content SHA256. Job Image Asset: image
# content SHA256/size/format/load address and target applicability. Job
# Binding: exact (Resource, Image, PPU, Site, ICPN, Profile) tuple.
#
# These identities are NOT an execution authority yet. Until OFE-1B adds
# PPU-side verification, the Bundle archive SHA256 remains the only Active
# Asset Set, B1/B2/B3 and Job identity, and nothing here may skip B1/B2/B3.
# --------------------------------------------------------------------------
RESOURCE_SET_SCHEMA = "plasma.opf.programming-resource-set.v1"
IMAGE_ASSET_SCHEMA = "plasma.opf.job-image-asset.v1"
JOB_BINDING_SCHEMA = "plasma.opf.job-image-binding.v1"
# Same vocabulary as plasma_core.assets.ProgrammingAssetFormat; only raw binary
# has a validated Image normalizer and a single contiguous segment today.
IMAGE_FORMATS = frozenset({"binary"})
RESOURCE_KINDS = frozenset({"platform-provider", "programming-profile", "fpga-image"})
MAX_RESOURCE_PACKAGES = 31  # Bundle v3 verifier allows 32 Packages incl. Image.
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_PPU_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
PROVIDER_OPTIONS_FILE = "plasma-provider-options.json"
CAPABILITIES_FILE = "plasma-provider.json"
FLASH_PROFILE_FILE = "plasma-flash-profile.json"


def _resource_members(route: ProgrammingRoute) -> dict[str, bytes]:
    """Canonical Provider + Profile member bytes, shared by writer and identity."""
    provider_dir = f"payload/packages/{route.provider_id}/data"
    profile_dir = f"payload/packages/{route.profile_id}/data"
    return {
        f"{provider_dir}/{PROVIDER_OPTIONS_FILE}": canonical_json(route.provider_options),
        f"{profile_dir}/{CAPABILITIES_FILE}": canonical_json(route.capabilities),
        f"{profile_dir}/{FLASH_PROFILE_FILE}": canonical_json(route.flash_profile),
    }


def _package_entry(members: Mapping[str, bytes], pid: str, kind: str, version: str,
                   requires: list[str]) -> dict[str, Any]:
    paths = sorted(p for p in members if p.startswith(f"payload/packages/{pid}/"))
    return {"id": pid, "kind": kind, "version": version, "requires": requires,
            "files": [{"path": p, "size": len(members[p]),
                       "sha256": sha256_hex(members[p]), "executable": False}
                      for p in paths]}


def _resource_packages(route: ProgrammingRoute,
                       members: Mapping[str, bytes]) -> list[dict[str, Any]]:
    return [
        _package_entry(members, route.provider_id, "platform-provider",
                       route.provider_version, []),
        _package_entry(members, route.profile_id, "programming-profile",
                       route.profile_version, [route.provider_id]),
    ]


def resource_set_descriptor(route: ProgrammingRoute) -> dict[str, Any]:
    """Canonical Resource descriptor; Image bytes and filename never enter it."""
    _need(isinstance(route, ProgrammingRoute), "ROUTE_REQUIRED")
    caps, flash = route.capabilities, route.flash_profile
    return parse_resource_set({
        "schema": RESOURCE_SET_SCHEMA,
        "target": dict(route.target),
        "abi": {"driver_abi": caps["driver_abi"], "transport": caps["transport"]},
        "constraints": {
            "icpn": caps["target"], "sites": list(caps["sites"]),
            "operations": list(caps["operations"]),
            "max_image_bytes": caps["max_image_bytes"],
            "target_config": flash["target_config"], "flash_base": flash["flash_base"],
            "flash_size": flash["flash_size"],
            "erase_granularity": flash["erase_granularity"],
        },
        "fpga_package": caps["fpga_package"],
        "image_package_kind": route.image_package_kind,
        "packages": _resource_packages(route, _resource_members(route)),
    })


def _is_int(value: object) -> bool:
    return type(value) is int


def parse_resource_set(payload: object) -> dict[str, Any]:
    """Strict structural validation; returns a normalized deep copy.

    A descriptor proves nothing about stored bytes by itself: a descriptor that
    did not come from :func:`resource_set_descriptor` or
    :func:`identity_from_manifest` must be compared with one derived from
    verified bytes (:func:`verify_resource_set`) before any use.
    """
    _need(type(payload) is dict and set(payload) == {
        "schema", "target", "abi", "constraints", "fpga_package",
        "image_package_kind", "packages"}, "RESOURCE_SET_FIELDS_INVALID")
    _need(payload["schema"] == RESOURCE_SET_SCHEMA, "RESOURCE_SET_SCHEMA_UNSUPPORTED")
    target = payload["target"]
    _need(type(target) is dict and set(target) == {"platform", "board", "fpga_part"}
          and all(type(v) is str and SAFE_VERSION.fullmatch(v) for v in target.values()),
          "RESOURCE_TARGET_INVALID")
    abi = payload["abi"]
    _need(type(abi) is dict and set(abi) == {"driver_abi", "transport"}
          and type(abi["driver_abi"]) is str and 0 < len(abi["driver_abi"]) <= 64
          and abi["transport"] == "fpga", "RESOURCE_ABI_INVALID")
    c = payload["constraints"]
    _need(type(c) is dict and set(c) == {
        "icpn", "sites", "operations", "max_image_bytes", "target_config",
        "flash_base", "flash_size", "erase_granularity"}
        and type(c["icpn"]) is str and 0 < len(c["icpn"]) <= 96
        and type(c["sites"]) is list and bool(c["sites"])
        and all(_is_int(s) and s > 0 for s in c["sites"])
        and c["sites"] == sorted(set(c["sites"]))
        and type(c["operations"]) is list and "flash_cycle" in c["operations"]
        and all(type(o) is str and SAFE_NAME.fullmatch(o) for o in c["operations"])
        and len(set(c["operations"])) == len(c["operations"])
        and type(c["target_config"]) is str and bool(c["target_config"])
        and all(_is_int(c[k]) for k in (
            "max_image_bytes", "flash_base", "flash_size", "erase_granularity"))
        and 0 < c["max_image_bytes"] <= MAX_IMAGE_BYTES
        and c["flash_base"] >= 0 and c["flash_size"] > 0 and c["erase_granularity"] > 0
        and c["flash_size"] % c["erase_granularity"] == 0
        and c["max_image_bytes"] <= c["flash_size"], "RESOURCE_CONSTRAINTS_INVALID")
    fw_kind = payload["image_package_kind"]
    _need(type(fw_kind) is str and SAFE_NAME.fullmatch(fw_kind) is not None
          and fw_kind not in RESOURCE_KINDS, "RESOURCE_IMAGE_KIND_INVALID")
    packages = payload["packages"]
    _need(type(packages) is list and 2 <= len(packages) <= MAX_RESOURCE_PACKAGES,
          "RESOURCE_PACKAGES_INVALID")
    seen: dict[str, str] = {}
    paths: set[str] = set()
    for package in packages:
        _need(type(package) is dict and set(package) == {
            "id", "kind", "version", "requires", "files"}, "RESOURCE_PACKAGE_INVALID")
        pid, kind = package["id"], package["kind"]
        _need(type(pid) is str and SAFE_NAME.fullmatch(pid) is not None
              and type(kind) is str and kind in RESOURCE_KINDS
              and type(package["version"]) is str
              and SAFE_VERSION.fullmatch(package["version"]) is not None,
              "RESOURCE_PACKAGE_INVALID")
        _need(pid not in seen, "RESOURCE_PACKAGE_CONFLICT")
        requires = package["requires"]
        _need(type(requires) is list and all(type(r) is str for r in requires)
              and len(set(requires)) == len(requires), "RESOURCE_PACKAGE_INVALID")
        # Dependencies must already be present: no missing Package, no cycle.
        _need(all(r in seen for r in requires), "RESOURCE_DEPENDENCY_MISSING")
        files = package["files"]
        _need(type(files) is list and bool(files), "RESOURCE_PACKAGE_FILES_INVALID")
        for entry in files:
            _need(type(entry) is dict and set(entry) == {"path", "size", "sha256", "executable"}
                  and type(entry["path"]) is str
                  and entry["path"].startswith(f"payload/packages/{pid}/")
                  and ".." not in entry["path"].split("/")
                  and _is_int(entry["size"]) and entry["size"] >= 0
                  and type(entry["sha256"]) is str and HEX64.fullmatch(entry["sha256"])
                  and type(entry["executable"]) is bool, "RESOURCE_FILE_DESCRIPTOR_INVALID")
            _need(entry["path"] not in paths, "RESOURCE_PACKAGE_CONFLICT")
            paths.add(entry["path"])
        seen[pid] = kind
    kinds = list(seen.values())
    _need(kinds.count("platform-provider") == 1 and kinds.count("programming-profile") == 1
          and kinds.count("fpga-image") <= 1, "RESOURCE_PACKAGE_SET_INVALID")
    provider = next(p for p in packages if p["kind"] == "platform-provider")
    profile = next(p for p in packages if p["kind"] == "programming-profile")
    _need(provider["id"] in profile["requires"], "RESOURCE_DEPENDENCY_MISSING")
    fpga = payload["fpga_package"]
    _need(fpga is None and "fpga-image" not in kinds
          or type(fpga) is str and seen.get(fpga) == "fpga-image",
          "RESOURCE_FPGA_PACKAGE_INVALID")
    return json.loads(canonical_json(payload))


def resource_set_sha256(descriptor: object) -> str:
    return sha256_hex(canonical_json(parse_resource_set(descriptor)))


def parse_image_asset(payload: object) -> dict[str, Any]:
    _need(type(payload) is dict and set(payload) == {
        "schema", "format", "sha256", "size", "load_address", "icpn"}
        and payload["schema"] == IMAGE_ASSET_SCHEMA, "IMAGE_ASSET_FIELDS_INVALID")
    _need(payload["format"] in IMAGE_FORMATS, "IMAGE_ASSET_FORMAT_UNSUPPORTED")
    _need(type(payload["sha256"]) is str and HEX64.fullmatch(payload["sha256"]) is not None
          and _is_int(payload["size"]) and 0 < payload["size"] <= MAX_IMAGE_BYTES
          and _is_int(payload["load_address"]) and payload["load_address"] >= 0
          and type(payload["icpn"]) is str and 0 < len(payload["icpn"]) <= 96,
          "IMAGE_ASSET_FIELDS_INVALID")
    return dict(payload)


def _check_applicable(asset: Mapping[str, Any], resource: Mapping[str, Any]) -> None:
    c = resource["constraints"]
    _need(asset["icpn"] == c["icpn"], "IMAGE_ASSET_TARGET_MISMATCH")
    _need(asset["size"] <= c["max_image_bytes"], "IMAGE_ASSET_EXCEEDS_PROFILE_MAX_IMAGE")
    offset = asset["load_address"] - c["flash_base"]
    _need(offset >= 0 and offset % c["erase_granularity"] == 0
          and offset + asset["size"] <= c["flash_size"], "IMAGE_ASSET_ADDRESS_INVALID")


def image_asset_descriptor(resource: object, image: bytes, *,
                           load_address: int | None = None,
                           image_format: str = "binary") -> dict[str, Any]:
    """Image identity from actual bytes; the filename never enters it."""
    parsed = parse_resource_set(resource)
    _need(type(image) is bytes and len(image) > 0, "IMAGE_ASSET_EMPTY")
    descriptor = {
        "schema": IMAGE_ASSET_SCHEMA, "format": image_format,
        "sha256": sha256_hex(image), "size": len(image),
        "load_address": (parsed["constraints"]["flash_base"]
                         if load_address is None else load_address),
        "icpn": parsed["constraints"]["icpn"],
    }
    return verify_image_asset(descriptor, image, parsed)


def verify_image_asset(descriptor: object, image: bytes,
                       resource: object) -> dict[str, Any]:
    """Fail closed unless declared SHA/size/format/address match bytes and Profile."""
    asset = parse_image_asset(descriptor)
    _need(type(image) is bytes and len(image) == asset["size"], "IMAGE_ASSET_SIZE_MISMATCH")
    _need(sha256_hex(image) == asset["sha256"], "IMAGE_ASSET_SHA256_MISMATCH")
    _check_applicable(asset, parse_resource_set(resource))
    return asset


def image_asset_sha256(descriptor: object) -> str:
    return sha256_hex(canonical_json(parse_image_asset(descriptor)))


def job_image_binding(resource: object, asset: object, *,
                      ppu_id: str, site_id: int) -> dict[str, Any]:
    """Exact Resource + Image + PPU + Site + Target/Profile binding (no I/O)."""
    parsed = parse_resource_set(resource)
    fw = parse_image_asset(asset)
    _check_applicable(fw, parsed)
    _need(type(ppu_id) is str and SAFE_PPU_ID.fullmatch(ppu_id) is not None,
          "JOB_BINDING_PPU_INVALID")
    _need(_is_int(site_id) and site_id in parsed["constraints"]["sites"],
          "JOB_BINDING_SITE_NOT_IN_PROFILE")
    profile = next(p for p in parsed["packages"] if p["kind"] == "programming-profile")
    return {
        "schema": JOB_BINDING_SCHEMA,
        "resource_set_sha256": resource_set_sha256(parsed),
        "image_asset_sha256": image_asset_sha256(fw),
        "ppu_id": ppu_id, "site_id": site_id,
        "icpn": parsed["constraints"]["icpn"], "profile": profile["id"],
    }


def verify_job_binding(binding: object, resource: object, asset: object, *,
                       ppu_id: str, site_id: int) -> str:
    """Return the binding SHA256 only for the exact expected tuple."""
    expected = job_image_binding(resource, asset, ppu_id=ppu_id, site_id=site_id)
    _need(type(binding) is dict and canonical_json(binding) == canonical_json(expected),
          "JOB_BINDING_MISMATCH")
    return sha256_hex(canonical_json(expected))


def identity_from_manifest(manifest: object, read_file) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive (Resource, Image) descriptors from one programming Bundle v3.

    ``read_file(path)`` returns stored member bytes (ZIP member or B3 staged
    file). Every byte read is checked against the manifest SHA256/size; the
    Resource Packages must be byte-identical to the canonical writer output, so
    a hand-edited or non-canonical Resource Package fails closed. This proves
    identity only; it does NOT replace B3 whole-archive verification.
    """
    _need(type(manifest) is dict and manifest.get("schema") == BUNDLE_SCHEMA
          and manifest.get("purpose") == "programming"
          and manifest.get("actions") == ["install", "verify"]
          and type(manifest.get("packages")) is list, "BUNDLE_MANIFEST_UNSUPPORTED")
    packages = manifest["packages"]
    _need(all(type(p) is dict and type(p.get("kind")) is str for p in packages),
          "BUNDLE_MANIFEST_UNSUPPORTED")
    image_pkgs = [p for p in packages if p["kind"] not in RESOURCE_KINDS]
    providers = [p for p in packages if p["kind"] == "platform-provider"]
    profiles = [p for p in packages if p["kind"] == "programming-profile"]
    # Route-built programming Bundles carry no FPGA Package today (fpga_package
    # must be null); anything else is outside this contract version.
    _need(len(packages) == 3 and len(image_pkgs) == 1 and len(providers) == 1
          and len(profiles) == 1, "BUNDLE_PACKAGE_SET_UNSUPPORTED")
    provider, profile, fw_pkg = providers[0], profiles[0], image_pkgs[0]

    def read(entry: object) -> bytes:
        _need(type(entry) is dict and type(entry.get("path")) is str
              and _is_int(entry.get("size")) and type(entry.get("sha256")) is str,
              "BUNDLE_FILE_DESCRIPTOR_INVALID")
        raw = read_file(entry["path"])
        _need(type(raw) is bytes and len(raw) == entry["size"]
              and sha256_hex(raw) == entry["sha256"], "BUNDLE_FILE_MISMATCH")
        return raw

    def member(package: Mapping[str, Any], name: str) -> object:
        path = f"payload/packages/{package.get('id')}/data/{name}"
        entries = [e for e in package.get("files") or [] if type(e) is dict
                   and e.get("path") == path]
        _need(len(entries) == 1, "BUNDLE_RESOURCE_FILE_MISSING")
        try:
            return json.loads(read(entries[0]), object_pairs_hook=_unique_pairs)
        except BundleBuildError:
            raise
        except (ValueError, UnicodeError) as exc:
            raise BundleBuildError("BUNDLE_RESOURCE_JSON_INVALID") from exc

    # Reuse the Route validator: the stored Packages must form a valid Route.
    route = parse_route({
        "schema": ROUTE_SCHEMA, "route_id": profile.get("id"),
        "target": manifest.get("target"), "image_package": {"kind": fw_pkg["kind"]},
        "provider": {"id": provider.get("id"), "version": provider.get("version"),
                     "options": member(provider, PROVIDER_OPTIONS_FILE)},
        "profile": {"id": profile.get("id"), "version": profile.get("version"),
                    "capabilities": member(profile, CAPABILITIES_FILE),
                    "flash_profile": member(profile, FLASH_PROFILE_FILE)},
    })
    resource = resource_set_descriptor(route)
    _need(canonical_json(resource["packages"]) == canonical_json([provider, profile]),
          "BUNDLE_RESOURCE_NOT_CANONICAL")
    files = fw_pkg.get("files")
    _need(fw_pkg.get("requires") == [profile["id"]] and type(files) is list
          and len(files) == 1 and type(files[0]) is dict
          and files[0].get("executable") is False
          and type(files[0].get("path")) is str
          and files[0]["path"].startswith(f"payload/packages/{fw_pkg.get('id')}/data/")
          and files[0]["path"].endswith(".bin"), "BUNDLE_IMAGE_PACKAGE_INVALID")
    return resource, image_asset_descriptor(resource, read(files[0]))


def identity_from_archive(archive: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """:func:`identity_from_manifest` over canonical Bundle v3 ZIP bytes."""
    _need(type(archive) is bytes and bool(archive), "BUNDLE_ARCHIVE_INVALID")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            names = set(bundle.namelist())
            manifest = json.loads(bundle.read("manifest.json"), object_pairs_hook=_unique_pairs)

            def read_file(path: str) -> bytes:
                _need(path in names, "BUNDLE_FILE_MISSING")
                return bundle.read(path)

            return identity_from_manifest(manifest, read_file)
    except BundleBuildError:
        raise
    except (zipfile.BadZipFile, KeyError, ValueError, UnicodeError) as exc:
        raise BundleBuildError("BUNDLE_ARCHIVE_INVALID") from exc


def verify_resource_set(expected: object, manifest: object, read_file) -> str:
    """Fail closed unless stored Bundle bytes reproduce the expected Resource Set."""
    want = parse_resource_set(expected)
    actual, _image = identity_from_manifest(manifest, read_file)
    _need(canonical_json(actual) == canonical_json(want), "RESOURCE_SET_MISMATCH")
    return resource_set_sha256(actual)


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
    # OFE-1A identity contract (informational). ``archive_sha256`` stays the
    # ONLY Active Asset Set / B1-B3 / Job authority; see module docstring.
    resource_set_sha256: str
    image_asset_sha256: str

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
            "resource_set_sha256": self.resource_set_sha256,
            "image_asset_sha256": self.image_asset_sha256,
            "identity_authority": "archive_sha256",
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

    members = {
        **_resource_members(route),
        f"payload/packages/{asset_package_id}/data/{image_filename}": image,
    }
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "name": bundle_name, "version": version,
        "purpose": "programming", "target": dict(route.target),
        # The existing B3 verified-set reader requires this exact action set.
        "actions": ["install", "verify"],
        "packages": [
            *_resource_packages(route, members),
            _package_entry(members, asset_package_id, route.image_package_kind, version,
                           [route.profile_id]),
        ],
    }
    archive = canonical_zip({"manifest.json": canonical_json(manifest), **members})
    resource = resource_set_descriptor(route)
    asset = image_asset_descriptor(resource, image)
    return ProgrammingBundle(
        archive=archive, archive_sha256=sha256_hex(archive),
        bundle_name=bundle_name, version=version, target=dict(route.target),
        provider_id=route.provider_id, profile_id=route.profile_id,
        asset_package_id=asset_package_id, image_filename=image_filename,
        image_sha256=sha256_hex(image), image_size=len(image),
        icpn=route.icpn,
        resource_set_sha256=resource_set_sha256(resource),
        image_asset_sha256=image_asset_sha256(asset),
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
